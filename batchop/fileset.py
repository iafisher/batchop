import dataclasses
import decimal
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, List

from . import filters
from .common import BatchOpError, NumberLike, PathLike, unit_to_multiple
from .filters import Filter


@dataclass
class FileSetSize:
    file_count: int
    directory_count: int
    size_in_bytes: int


class FileSet:
    root: Path
    filters: List[Filter]

    def __init__(self, root: PathLike, filters: List[Filter] = []) -> None:
        self.root = Path(root)
        self.filters = filters

    @classmethod
    def with_default_filters(cls, root: PathLike) -> "FileSet":
        return FileSet(root).is_not_hidden()

    def resolve(self) -> Generator[Path, None, None]:
        # TODO: does this give a reasonable iteration order?
        stack = list(self.root.iterdir())
        while stack:
            item = stack.pop()
            # TODO: terminate filter application early if possible
            results = [filters.expand_result(f.test(item)) for f in self.filters]
            should_include = all(include_self for include_self, _ in results)
            should_recurse = all(include_children for _, include_children in results)

            if should_include:
                yield item

            if should_recurse and item.is_dir():
                for child in item.iterdir():
                    stack.append(child)

    def calculate_size(self) -> FileSetSize:
        r = FileSetSize(file_count=0, directory_count=0, size_in_bytes=0)
        for p in self.resolve():
            if p.is_dir():
                r.directory_count += 1
            else:
                # TODO: special files?
                r.file_count += 1
                r.size_in_bytes += p.stat().st_size

        return r

    def pop(self) -> None:
        self.filters.pop()

    def push(self, f: Filter) -> None:
        self.filters.append(f)

    def clear(self) -> None:
        self.filters.clear()

    def copy_with(self, f: Filter) -> "FileSet":
        return FileSet(self.root, self.filters + [f])

    def is_folder(self) -> "FileSet":
        return self.copy_with(filters.FilterIsFolder())

    def is_file(self) -> "FileSet":
        return self.copy_with(filters.FilterIsFile())

    def is_empty(self) -> "FileSet":
        return self.copy_with(filters.FilterIsEmpty())

    def is_not_empty(self) -> "FileSet":
        return self.copy_with(filters.FilterNegated(filters.FilterIsEmpty()))

    def is_named(self, pattern: str) -> "FileSet":
        return self.copy_with(filters.FilterIsNamed(pattern))

    def is_not_named(self, pattern: str) -> "FileSet":
        return self.copy_with(filters.FilterNegated(filters.FilterIsNamed(pattern)))

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

    # TODO: is_git_ignored() -- https://github.com/mherrmann/gitignore_parser

    def _normalize_path(self, path_like: PathLike) -> Path:
        path = Path(path_like)
        if path.is_absolute():
            if not path.is_relative_to(self.root):
                raise BatchOpError(
                    f"filter path ({path}) cannot be outside of file-set root ({self.root})"
                )
        else:
            path = self.root / path

        return path


def _n_times_unit(n: NumberLike, unit: str) -> int:
    multiple = unit_to_multiple(unit)
    if multiple is None:
        raise BatchOpError(f"{unit!r} is not a recognized unit")

    if isinstance(n, str):
        n = decimal.Decimal(n)

    return int(n * multiple)
