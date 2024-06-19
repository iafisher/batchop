import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from . import filters
from .common import AbsolutePath, PathLike, abspath


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
class FileSet3:
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


class FilterSet3:
    _filters: List[filters.Filter]

    def __init__(self, _filters: Optional[List[filters.Filter]] = None) -> None:
        self._filters = _filters or []

    def test(self, item: Path) -> Tuple[bool, bool]:
        # TODO: terminate filter application early if possible
        results = [filters.expand_result(f.test(item)) for f in self._filters]
        should_include = all(include_self for include_self, _ in results)
        should_recurse = all(include_children for _, include_children in results)
        return should_include, should_recurse

    def resolve(self, root: PathLike, *, recursive: bool) -> FileSet3:
        r = []

        # TODO: does this give a reasonable iteration order?
        # (path, is_root, skip_filters)
        stack = [(p, True, False) for p in abspath(root).iterdir()]
        while stack:
            item, is_root, skip_filters = stack.pop()
            is_dir = item.is_dir()
            if skip_filters:
                should_include, should_recurse = True, True
            else:
                should_include, should_recurse = self.test(item)

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

        return FileSet3(r)

    def is_file(self) -> "FilterSet3":
        return self.copy_with(filters.FilterIsFile())

    def is_dir(self) -> "FilterSet3":
        return self.copy_with(filters.FilterIsDirectory())

    def is_empty(self) -> "FilterSet3":
        return self.copy_with(filters.FilterIsEmpty())

    def copy_with(self, f: filters.Filter) -> "FilterSet3":
        return FilterSet3(self._filters + [f])
