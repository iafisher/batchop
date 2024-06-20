import decimal
import enum
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from . import exceptions, filters
from .common import (
    AbsolutePath,
    NumberLike,
    PathLike,
    PatternLike,
    abspath,
    unit_to_multiple,
)


class IterateBehavior(enum.Enum):
    DEFAULT = 1
    ALWAYS_INCLUDE_CHILDREN = 2
    ALWAYS_EXCLUDE_CHILDREN = 3


@dataclass
class FileSetItem:
    path: AbsolutePath
    is_dir: bool
    is_root: bool
    size_bytes: int


@dataclass
class FileSet:
    items: List[FileSetItem]

    def file_count(self) -> int:
        return sum(1 for item in self.items if not item.is_dir)

    def dir_count(self) -> int:
        return sum(1 for item in self.items if item.is_dir)

    def size_bytes(self) -> int:
        return sum(item.size_bytes for item in self.items)

    def __iter__(self) -> Iterator[AbsolutePath]:
        return iter(item.path for item in self.items)

    def exclude_children(self) -> Iterator[AbsolutePath]:
        return (item.path for item in self.items if item.is_root)

    def __len__(self) -> int:
        return len(self.items)

    def is_empty(self) -> bool:
        return len(self.items) == 0


class FilterSet:
    _filters: List[filters.Filter]
    special_files: bool

    # TODO: should this take a `root` parameter here or in `resolve`?
    def __init__(
        self,
        _filters: Optional[List[filters.Filter]] = None,
        *,
        special_files: bool = False
    ) -> None:
        self._filters = _filters or []
        self.special_files = special_files

    def pop(self) -> None:
        self._filters.pop()

    def push(self, f: filters.Filter) -> None:
        self._filters.append(f)

    def extend(self, fs: List[filters.Filter]) -> None:
        self._filters.extend(fs)

    def clear(self) -> None:
        self._filters.clear()

    def get_filters(self) -> List[filters.Filter]:
        return self._filters

    def resolve(self, root_like: PathLike, *, recursive: bool) -> FileSet:
        root = abspath(root_like)
        _filters = [f.make_absolute(root) for f in self._filters]
        if not self.special_files:
            _filters.insert(0, filters.FilterIsSpecial().negate())

        r = []
        # TODO: does this give a reasonable iteration order?
        # (path, is_root, skip_filters)
        stack = [(p, True, False) for p in root.iterdir()]
        while stack:
            item, is_root, skip_filters = stack.pop()
            is_dir = item.is_dir()
            if skip_filters:
                should_include, should_recurse = True, True
            else:
                should_include, should_recurse = self._test(_filters, item)

            if should_include:
                # TODO: handle stat() exception
                size_bytes = item.stat().st_size if not is_dir else 0
                r.append(
                    FileSetItem(
                        item, is_dir=is_dir, is_root=is_root, size_bytes=size_bytes
                    )
                )

            if should_recurse and is_dir:
                is_root = not should_include
                for child in item.iterdir():
                    stack.append(
                        (
                            child,
                            is_root,
                            # skip_filters=
                            not is_root and recursive,
                        )
                    )

        return FileSet(r)

    @staticmethod
    def _test(_filters: List[filters.Filter], item: Path) -> Tuple[bool, bool]:
        # TODO: terminate filter application early if possible
        results = [filters.expand_result(f.test(item)) for f in _filters]
        should_include = all(include_self for include_self, _ in results)
        should_recurse = all(include_children for _, include_children in results)
        return should_include, should_recurse

    def is_file(self) -> "FilterSet":
        return self.copy_with(filters.FilterIsFile())

    def is_dir(self) -> "FilterSet":
        return self.copy_with(filters.FilterIsDirectory())

    def is_empty(self) -> "FilterSet":
        return self.copy_with(filters.FilterIsEmpty())

    def is_not_empty(self) -> "FilterSet":
        return self.copy_with(filters.FilterIsEmpty().negate())

    def is_like(self, pattern: str) -> "FilterSet":
        return self.copy_with(filters.glob_pattern_to_filter(pattern))

    def is_not_like(self, pattern: str) -> "FilterSet":
        return self.copy_with(filters.glob_pattern_to_filter(pattern).negate())

    def matches(self, pattern: PatternLike) -> "FilterSet":
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        return self.copy_with(filters.FilterMatches(pattern))

    def does_not_match(self, pattern: PatternLike) -> "FilterSet":
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        return self.copy_with(filters.FilterMatches(pattern).negate())

    def is_in(self, path_like: PathLike) -> "FilterSet":
        return self.copy_with(filters.FilterIsInPath(Path(path_like)))

    def is_in_glob(self, pattern: str) -> "FilterSet":
        raise NotImplementedError

    def is_in_regex(self, pattern: str) -> "FilterSet":
        raise NotImplementedError

    def is_not_in(self, path_like: PathLike) -> "FilterSet":
        return self.copy_with(filters.FilterIsNotInPath(Path(path_like)))

    def is_not_in_glob(self, pattern: str) -> "FilterSet":
        raise NotImplementedError

    def is_not_in_regex(self, pattern: str) -> "FilterSet":
        raise NotImplementedError

    def is_hidden(self) -> "FilterSet":
        return self.copy_with(filters.FilterIsHidden())

    def is_not_hidden(self) -> "FilterSet":
        return self.copy_with(filters.FilterIsNotHidden())

    def size_gt(self, n: NumberLike, unit: str) -> "FilterSet":
        return self.copy_with(filters.FilterSizeGreater(_n_times_unit(n, unit)))

    def size_ge(self, n: NumberLike, unit: str) -> "FilterSet":
        return self.copy_with(filters.FilterSizeGreaterEqual(_n_times_unit(n, unit)))

    def size_lt(self, n: NumberLike, unit: str) -> "FilterSet":
        return self.copy_with(filters.FilterSizeLess(_n_times_unit(n, unit)))

    def size_le(self, n: NumberLike, unit: str) -> "FilterSet":
        return self.copy_with(filters.FilterSizeLessEqual(_n_times_unit(n, unit)))

    def with_ext(self, ext: str) -> "FilterSet":
        return self.copy_with(filters.FilterHasExtension(ext))

    def copy_with(self, f: filters.Filter) -> "FilterSet":
        return FilterSet(self._filters + [f])


def _n_times_unit(n: NumberLike, unit: str) -> int:
    multiple = unit_to_multiple(unit)
    if multiple is None:
        raise exceptions.UnknownSizeUnit(unit)

    if isinstance(n, str):
        n = decimal.Decimal(n)

    return int(n * multiple)
