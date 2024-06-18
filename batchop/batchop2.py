import abc
import enum
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, List, NewType, Optional, Self, Tuple, Union

from . import filters

AbsolutePath = NewType("AbsolutePath", Path)
PathLike = Union[Path, str]


def abspath(path_like: PathLike) -> AbsolutePath:
    if isinstance(path_like, Path):
        return AbsolutePath(path_like.absolute())
    else:
        return AbsolutePath(Path(path_like).absolute())


class IterateBehavior(enum.Enum):
    DEFAULT = 1
    ALWAYS_INCLUDE_CHILDREN = 2
    ALWAYS_EXCLUDE_CHILDREN = 3


@dataclass
class FileSetSize:
    file_count: int = 0
    directory_count: int = 0
    size_in_bytes: int = 0

    def is_empty(self) -> bool:
        return self.file_count == 0 and self.directory_count == 0


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


def parse_query(text: str) -> FilterSet:
    raise NotImplementedError


class BatchOp2:
    root: AbsolutePath

    def __init__(self, root: Optional[PathLike] = None) -> None:
        if root is None:
            self.root = abspath(Path.cwd())
        else:
            self.root = abspath(root)

    def delete(
        self, some_set: FileOrFilterSet, *, require_confirm: bool = True
    ) -> None:
        fileset = self._to_file_set(some_set)
        if require_confirm:
            fileset = fileset.make_concrete()
            if not confirm_delete(fileset):
                return

        for p in fileset.iterate(IterateBehavior.ALWAYS_EXCLUDE_CHILDREN):
            if p.is_dir():
                shutil.rmtree(p)
            else:
                os.remove(p)

    def count(self, some_set: FileOrFilterSet) -> int:
        fileset = self._to_file_set(some_set)
        return fileset.count()

    def _to_file_set(self, some_set: FileOrFilterSet) -> FileSet:
        if isinstance(some_set, FileSet):
            return some_set
        elif isinstance(some_set, FilterSet):
            return some_set.resolve(self.root)
        elif isinstance(some_set, str):
            return parse_query(some_set).resolve(self.root)
        else:
            raise Exception


def confirm_delete(fileset: FileSet) -> bool:
    size = fileset.calculate_size(IterateBehavior.ALWAYS_INCLUDE_CHILDREN)
    return confirm(
        f"Delete {size.file_count} files, {size.directory_count} directories, {size.size_in_bytes} bytes? "
    )


def confirm(prompt: str) -> bool:
    while True:
        r = input(prompt).strip().lower()
        if r == "yes" or r == "y":
            return True
        elif r == "no" or r == "n":
            return False
