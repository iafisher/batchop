import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, List

from . import filters
from .filters import Filter


@dataclass
class FileSet:
    filters: List[Filter] = dataclasses.field(default_factory=list)

    @classmethod
    def with_default_filters(cls) -> "FileSet":
        return FileSet().is_not_hidden()

    def resolve(self, root: Path) -> Generator[Path, None, None]:
        # TODO: does this give a reasonable iteration order?
        stack = [root]
        while stack:
            item = stack.pop()
            # TODO: terminate filter application early if possible
            results = [f.test(item) for f in self.filters]
            should_include = all(r.should_include for r in results)
            should_recurse = all(r.should_recurse for r in results)

            if should_include:
                yield item

            if should_recurse and item.is_dir():
                for child in item.iterdir():
                    stack.append(child)

    def pop(self) -> None:
        self.filters.pop()

    def push(self, f: Filter) -> None:
        self.filters.append(f)

    def clear(self) -> None:
        self.filters.clear()

    def is_folder(self) -> "FileSet":
        self.filters.append(filters.FilterIsFolder())
        return self

    def is_file(self) -> "FileSet":
        self.filters.append(filters.FilterIsFile())
        return self

    def is_empty(self) -> "FileSet":
        self.filters.append(filters.FilterIsEmpty())
        return self

    def is_named(self, pattern: str) -> "FileSet":
        self.filters.append(filters.FilterIsNamed(pattern))
        return self

    def is_not_named(self, pattern: str) -> "FileSet":
        self.filters.append(filters.FilterNegated(filters.FilterIsNamed(pattern)))
        return self

    def is_in(self, pattern: str) -> "FileSet":
        self.filters.append(filters.FilterIsIn(pattern))
        return self

    def is_not_in(self, pattern: str) -> "FileSet":
        self.filters.append(filters.FilterIsNotIn(pattern))
        return self

    def is_hidden(self) -> "FileSet":
        self.filters.append(filters.FilterIsHidden())
        return self

    def is_not_hidden(self) -> "FileSet":
        self.filters.append(filters.FilterIsNotHidden())
        return self

    # TODO: is_git_ignored() -- https://github.com/mherrmann/gitignore_parser