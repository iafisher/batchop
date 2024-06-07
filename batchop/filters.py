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
            return any(p.iterdir())
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
class FilterIsIn(Filter):
    # pattern can be:
    #   fixed string (matches name exactly)
    #   glob pattern
    #   TODO: absolute/relative file path (e.g., includes slash)
    #     tricky to handle relative file paths because we need to know root directory
    #   TODO: regex
    pattern: str

    def test(self, p: Path) -> Result:
        # TODO: messy
        # TODO: shouldn't include the directory itself
        return (p.is_dir() and fnmatch.fnmatch(p.name, self.pattern)) or any(
            fnmatch.fnmatch(s, self.pattern) for s in p.parts[:-1]
        )

    def negate(self) -> Filter:
        return FilterIsNotIn(self.pattern)

    def __str__(self) -> str:
        return f"is in {self.pattern!r}"


@dataclass
class FilterIsNotIn(Filter):
    pattern: str

    def test(self, p: Path) -> Result:
        if p.is_dir() and fnmatch.fnmatch(p.name, self.pattern):
            return (True, False)
        else:
            # assumption: if a parent directory was excluded we never got here in the first place
            # b/c we passed include_children=False above
            return True

    def __str__(self) -> str:
        return f"is not in {self.pattern!r}"


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
    base: decimal.Decimal
    multiple: int

    def test(self, p: Path) -> Result:
        return p.stat().st_size > (self.base * self.multiple)

    def __str__(self) -> str:
        # TODO: human-readable units
        return f"> {self.base * self.multiple} bytes"


@dataclass
class FilterSizeGreaterEqual(Filter):
    base: decimal.Decimal
    multiple: int

    def test(self, p: Path) -> Result:
        return p.stat().st_size >= (self.base * self.multiple)

    def __str__(self) -> str:
        return f">= {self.base * self.multiple} bytes"


@dataclass
class FilterSizeLess(Filter):
    base: decimal.Decimal
    multiple: int

    def test(self, p: Path) -> Result:
        return p.stat().st_size < (self.base * self.multiple)

    def __str__(self) -> str:
        return f"< {self.base * self.multiple} bytes"


@dataclass
class FilterSizeLessEqual(Filter):
    base: decimal.Decimal
    multiple: int

    def test(self, p: Path) -> Result:
        return p.stat().st_size <= (self.base * self.multiple)

    def __str__(self) -> str:
        return f"<= {self.base * self.multiple} bytes"


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
