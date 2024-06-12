import abc
import decimal
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Union


# if tuple, interpreted as (include_self, include_children)
Result = Union[bool, Tuple[bool, bool]]


def expand_result(r: Result) -> Tuple[bool, bool]:
    if isinstance(r, tuple):
        return r
    else:
        return r, True


class Filter(abc.ABC):
    @abc.abstractmethod
    def test(self, p: Path) -> Result:
        pass

    def negate(self) -> "Filter":
        # most filters can be negated generically but some have a specialized negation that is more
        # efficient
        return FilterNegated(self)


@dataclass
class FilterNegated(Filter):
    inner: Filter

    def test(self, p: Path) -> Result:
        r = self.inner.test(p)
        print("FilterNegated", self.inner, p, r)
        if isinstance(r, tuple):
            # TODO: is it always right to pass include_children through unchanged?
            include_self, include_children = r
            return not include_self, include_children
        else:
            return not r

    def __str__(self) -> str:
        return f"not ({self.inner})"


@dataclass
class FilterIsFolder(Filter):
    def test(self, p: Path) -> Result:
        return p.is_dir()

    def __str__(self) -> str:
        return "is folder"


@dataclass
class FilterIsFile(Filter):
    def test(self, p: Path) -> Result:
        return p.is_file()

    def __str__(self) -> str:
        return "is file"


@dataclass
class FilterIsEmpty(Filter):
    def test(self, p: Path) -> Result:
        if p.is_dir():
            return not any(p.iterdir())
        else:
            return p.stat().st_size == 0

    def __str__(self) -> str:
        return "is empty"


@dataclass
class FilterIsNamed(Filter):
    pattern: str

    def test(self, p: Path) -> Result:
        # TODO: case-insensitive file systems?
        return fnmatch.fnmatch(p.name, self.pattern)

    def __str__(self) -> str:
        return f"is named {self.pattern!r}"


@dataclass
class FilterIsInPath(Filter):
    path: Path

    def test(self, p: Path) -> Result:
        return test_is_in_exact(self.path, p)

    def negate(self) -> Filter:
        return FilterIsNotInPath(self.path)

    def __str__(self) -> str:
        return f"is in {self.path!r}"


@dataclass
class FilterIsNotInPath(Filter):
    path: Path

    def test(self, p: Path) -> Result:
        if test_is_in_exact(self.path, p):
            return (True, False)
        else:
            # assumption: if a parent directory was excluded we never got here in the first place
            # b/c we passed include_children=False above
            return True

    def __str__(self) -> str:
        return f"is not in {self.path!r}"


def test_is_in_exact(to_include, to_test):
    return to_test.is_relative_to(to_include) and to_test != to_include


@dataclass
class FilterIsHidden(Filter):
    def test(self, p: Path) -> Result:
        # TODO: cross-platform?
        # TODO: only consider parts from search root?
        return any(s.startswith(".") for s in p.parts)

    def negate(self) -> Filter:
        return FilterIsNotHidden()

    def __str__(self) -> str:
        return "is hidden"


@dataclass
class FilterIsNotHidden(Filter):
    def test(self, p: Path) -> Result:
        # TODO: cross-platform?
        if p.name.startswith("."):
            return (False, False)
        else:
            return True

    def __str__(self) -> str:
        return "is not hidden"


@dataclass
class FilterSizeGreater(Filter):
    byte_count: int

    def test(self, p: Path) -> Result:
        return p.is_file() and p.stat().st_size > self.byte_count

    def __str__(self) -> str:
        # TODO: human-readable units
        return f"> {self.byte_count:,} bytes"


@dataclass
class FilterSizeGreaterEqual(Filter):
    byte_count: int

    def test(self, p: Path) -> Result:
        return p.is_file() and p.stat().st_size >= self.byte_count

    def __str__(self) -> str:
        return f">= {self.byte_count:,} bytes"


@dataclass
class FilterSizeLess(Filter):
    byte_count: int

    def test(self, p: Path) -> Result:
        return p.is_file() and p.stat().st_size < self.byte_count

    def __str__(self) -> str:
        return f"< {self.byte_count:,} bytes"


@dataclass
class FilterSizeLessEqual(Filter):
    byte_count: int

    def test(self, p: Path) -> Result:
        return p.is_file() and p.stat().st_size <= self.byte_count

    def __str__(self) -> str:
        return f"<= {self.byte_count:,} bytes"


@dataclass
class FilterHasExtension(Filter):
    ext: str

    def __init__(self, ext: str) -> None:
        if ext.startswith("."):
            self.ext = ext
        else:
            self.ext = "." + ext

    def test(self, p: Path) -> Result:
        return p.suffix == self.ext

    def __str__(self) -> str:
        return f"has extension {self.ext!r}"
