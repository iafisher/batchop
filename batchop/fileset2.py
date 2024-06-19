import abc
import enum
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple, Union

from . import filters
from .common import AbsolutePath, PathLike, abspath
from .fileset import FileSetSize


class IterateBehavior(enum.Enum):
    DEFAULT = 1
    ALWAYS_INCLUDE_CHILDREN = 2
    ALWAYS_EXCLUDE_CHILDREN = 3


class FileSet(abc.ABC):
    @abc.abstractmethod
    def iterate(
        self, behavior: IterateBehavior = IterateBehavior.DEFAULT
    ) -> Generator[AbsolutePath, None, None]:
        pass

    def calculate_size(
        self, behavior: IterateBehavior = IterateBehavior.DEFAULT
    ) -> FileSetSize:
        r = FileSetSize()
        for p in self.iterate(behavior):
            if p.is_dir():
                r.directory_count += 1
            else:
                # TODO: special files?
                r.file_count += 1
                # TODO: handle stat() exception
                r.size_in_bytes += p.stat().st_size
        return r

    @abc.abstractmethod
    def make_concrete(self) -> "ConcreteFileSet":
        pass

    def count(self, behavior: IterateBehavior = IterateBehavior.DEFAULT) -> int:
        return sum(1 for _ in self.iterate(behavior))

    def is_empty(self) -> bool:
        return not any(self.iterate())


class FilterSet:
    _filters: List[filters.Filter]

    def __init__(self, _filters: Optional[List[filters.Filter]] = None) -> None:
        self._filters = _filters or []

    def resolve(self, root: PathLike) -> FileSet:
        return LazyFileSet(abspath(root), self)

    def test(self, item: Path) -> Tuple[bool, bool]:
        # TODO: terminate filter application early if possible
        results = [filters.expand_result(f.test(item)) for f in self._filters]
        should_include = all(include_self for include_self, _ in results)
        should_recurse = all(include_children for _, include_children in results)
        return should_include, should_recurse

    def is_file(self) -> "FilterSet":
        return self.copy_with(filters.FilterIsFile())

    def is_empty(self) -> "FilterSet":
        return self.copy_with(filters.FilterIsEmpty())

    def copy_with(self, f: filters.Filter) -> "FilterSet":
        return FilterSet(self._filters + [f])


class LazyFileSet(FileSet):
    root: AbsolutePath
    filterset: FilterSet

    def __init__(self, root: AbsolutePath, filterset: FilterSet) -> None:
        self.root = root
        self.filterset = filterset

    def iterate(
        self, behavior: IterateBehavior = IterateBehavior.DEFAULT
    ) -> Generator[AbsolutePath, None, None]:
        # TODO: does this give a reasonable iteration order?
        stack = list(self.root.iterdir())
        while stack:
            item = stack.pop()
            should_include, should_recurse = self.filterset.test(item)

            if should_include:
                yield item

            if behavior == IterateBehavior.ALWAYS_EXCLUDE_CHILDREN:
                if should_include:
                    should_recurse = False
            elif behavior == IterateBehavior.ALWAYS_INCLUDE_CHILDREN:
                if should_include and item.is_dir():
                    yield from self._resolve_unconditional(item)
                    continue

            if should_recurse and item.is_dir():
                for child in item.iterdir():
                    stack.append(child)

    def _resolve_unconditional(
        self, p: AbsolutePath
    ) -> Generator[AbsolutePath, None, None]:
        stack = list(p.iterdir())
        while stack:
            item = stack.pop()
            yield item
            if item.is_dir():
                stack.extend(list(item.iterdir()))

    def make_concrete(self) -> "ConcreteFileSet":
        return ConcreteFileSet(list(self.iterate()))


class ConcreteFileSet(FileSet):
    files: List[AbsolutePath]
    _size_cache: Dict[IterateBehavior, FileSetSize]

    def __init__(self, files: List[AbsolutePath]) -> None:
        self.files = files
        self._size_cache = {}

    def iterate(
        self, behavior: IterateBehavior = IterateBehavior.DEFAULT
    ) -> Generator[AbsolutePath, None, None]:
        if behavior == IterateBehavior.ALWAYS_INCLUDE_CHILDREN:
            raise NotImplementedError
        else:
            yield from self.files

    def calculate_size(
        self, behavior: IterateBehavior = IterateBehavior.DEFAULT
    ) -> FileSetSize:
        c = self._size_cache.get(behavior)
        if c is not None:
            return c

        r = super().calculate_size(behavior)
        self._size_cache[behavior] = r
        return r

    def make_concrete(self) -> "ConcreteFileSet":
        return self


FileOrFilterSet = Union[FileSet, FilterSet, str]
