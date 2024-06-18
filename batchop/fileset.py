import decimal
import enum
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, List, Optional

from . import exceptions, filters
from .common import NumberLike, PathLike, PatternLike, unit_to_multiple
from .filters import Filter


@dataclass
class FileSetSize:
    file_count: int
    directory_count: int
    size_in_bytes: int

    def is_empty(self) -> bool:
        return self.file_count == 0 and self.directory_count == 0


class RecurseBehavior(enum.Enum):
    NORMAL = 1
    # once we hit a directory that is included, don't recurse into its children
    # useful for moving and deleting directories because `mv` and `rm` just need to take a directory root
    EXCLUDE_DIR_CHILDREN = 2
    # once we hit a directory that is included, include all its children regardless of filters
    # useful for previewing deletion because any children of directory will be deleted
    INCLUDE_DIR_CHILDREN = 3


class FileSet:
    root: Path
    filters: List[Filter]
    special_files: bool

    def __init__(
        self,
        root: PathLike,
        filters_: Optional[List[Filter]] = None,
        *,
        special_files: bool = False
    ) -> None:
        self.root = Path(root).absolute()
        self.filters = filters_ or []
        self.special_files = special_files

    def resolve(
        self, *, recurse: RecurseBehavior = RecurseBehavior.NORMAL
    ) -> Generator[Path, None, None]:
        all_filters = []
        if not self.special_files:
            all_filters.append(filters.FilterIsSpecial().negate())
        all_filters.extend(self.filters)

        for f in all_filters:
            f.make_absolute(self.root)

        # TODO: does this give a reasonable iteration order?
        stack = list(self.root.iterdir())
        while stack:
            item = stack.pop()
            # TODO: terminate filter application early if possible
            results = [filters.expand_result(f.test(item)) for f in all_filters]
            should_include = all(include_self for include_self, _ in results)
            should_recurse = all(include_children for _, include_children in results)

            if should_include:
                yield item

            if recurse == RecurseBehavior.EXCLUDE_DIR_CHILDREN:
                if should_include:
                    should_recurse = False
            elif recurse == RecurseBehavior.INCLUDE_DIR_CHILDREN:
                if should_include and item.is_dir():
                    yield from self._resolve_unconditional(item)
                    continue

            if should_recurse and item.is_dir():
                for child in item.iterdir():
                    stack.append(child)

    def _resolve_unconditional(self, p: Path) -> Generator[Path, None, None]:
        stack = list(p.iterdir())
        while stack:
            item = stack.pop()
            yield item
            if item.is_dir():
                stack.extend(list(item.iterdir()))

    def calculate_size(
        self, *, recurse: RecurseBehavior = RecurseBehavior.NORMAL
    ) -> FileSetSize:
        r = FileSetSize(file_count=0, directory_count=0, size_in_bytes=0)
        for p in self.resolve(recurse=recurse):
            if p.is_dir():
                r.directory_count += 1
            else:
                # TODO: special files?
                r.file_count += 1
                # TODO: handle stat() exception
                r.size_in_bytes += p.stat().st_size

        return r

    def optimize(self):
        _promote_is_in_path_filter_to_root(self)

    def pop(self) -> None:
        self.filters.pop()

    def push(self, f: Filter) -> None:
        self.filters.append(f)

    def extend(self, fs: List[Filter]) -> None:
        self.filters.extend(fs)

    def clear(self) -> None:
        self.filters.clear()

    def copy_with(self, f: Filter) -> "FileSet":
        return FileSet(self.root, self.filters + [f])

    def is_dir(self) -> "FileSet":
        return self.copy_with(filters.FilterIsDirectory())

    def is_file(self) -> "FileSet":
        return self.copy_with(filters.FilterIsFile())

    def is_empty(self) -> "FileSet":
        return self.copy_with(filters.FilterIsEmpty())

    def is_not_empty(self) -> "FileSet":
        return self.copy_with(filters.FilterIsEmpty().negate())

    def is_like(self, pattern: str) -> "FileSet":
        return self.copy_with(filters.glob_pattern_to_filter(pattern))

    def is_not_like(self, pattern: str) -> "FileSet":
        return self.copy_with(filters.glob_pattern_to_filter(pattern).negate())

    def matches(self, pattern: PatternLike) -> "FileSet":
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        return self.copy_with(filters.FilterMatches(pattern))

    def does_not_match(self, pattern: PatternLike) -> "FileSet":
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        return self.copy_with(filters.FilterMatches(pattern).negate())

    def is_in(self, path_like: PathLike) -> "FileSet":
        path = self._normalize_path(path_like)
        return self.copy_with(filters.FilterIsInPath(path))

    def is_in_glob(self, pattern: str) -> "FileSet":
        raise NotImplementedError

    def is_in_regex(self, pattern: str) -> "FileSet":
        raise NotImplementedError

    def is_not_in(self, path_like: PathLike) -> "FileSet":
        path = self._normalize_path(path_like)
        return self.copy_with(filters.FilterIsNotInPath(path))

    def is_not_in_glob(self, pattern: str) -> "FileSet":
        raise NotImplementedError

    def is_not_in_regex(self, pattern: str) -> "FileSet":
        raise NotImplementedError

    def is_hidden(self) -> "FileSet":
        return self.copy_with(filters.FilterIsHidden())

    def is_not_hidden(self) -> "FileSet":
        return self.copy_with(filters.FilterIsNotHidden())

    def size_gt(self, n: NumberLike, unit: str) -> "FileSet":
        return self.copy_with(filters.FilterSizeGreater(_n_times_unit(n, unit)))

    def size_ge(self, n: NumberLike, unit: str) -> "FileSet":
        return self.copy_with(filters.FilterSizeGreaterEqual(_n_times_unit(n, unit)))

    def size_lt(self, n: NumberLike, unit: str) -> "FileSet":
        return self.copy_with(filters.FilterSizeLess(_n_times_unit(n, unit)))

    def size_le(self, n: NumberLike, unit: str) -> "FileSet":
        return self.copy_with(filters.FilterSizeLessEqual(_n_times_unit(n, unit)))

    def with_ext(self, ext: str) -> "FileSet":
        return self.copy_with(filters.FilterHasExtension(ext))

    def _normalize_path(self, path_like: PathLike) -> Path:
        path = Path(path_like)
        if path.is_absolute():
            if not path.is_relative_to(self.root):
                raise exceptions.PathOutsideOfRoot(path=path, root=self.root)
        else:
            path = self.root / path

        return path


def _n_times_unit(n: NumberLike, unit: str) -> int:
    multiple = unit_to_multiple(unit)
    if multiple is None:
        raise exceptions.UnknownSizeUnit(unit)

    if isinstance(n, str):
        n = decimal.Decimal(n)

    return int(n * multiple)


# Optimizations
# -------------


def _promote_is_in_path_filter_to_root(fs: FileSet) -> None:
    i = None
    for j, f in enumerate(fs.filters):
        if isinstance(f, filters.FilterIsInPath):
            f.make_absolute(fs.root)
            fs.root = f.path
            i = j
            break

    if i is not None:
        fs.filters.pop(i)
