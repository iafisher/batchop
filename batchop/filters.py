import abc
import decimal
import fnmatch
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FilterResult:
    should_include: bool
    should_recurse: bool = True


class Filter(abc.ABC):
    @abc.abstractmethod
    def test(self, p: Path) -> FilterResult:
        pass

    def negate(self) -> "Filter":
        # most filters can be negated generically but some have a specialized negation that is more
        # efficient
        return FilterNegated(self)


@dataclass
class FilterNegated(Filter):
    inner: Filter

    def test(self, p: Path) -> FilterResult:
        r = self.inner.test(p)
        # TODO: is it always right to pass should_recurse through unchanged?
        return FilterResult(
            should_include=not r.should_include, should_recurse=r.should_recurse
        )

    def __str__(self) -> str:
        return f"not ({self.inner})"


@dataclass
class FilterIsFolder(Filter):
    def test(self, p: Path) -> FilterResult:
        return FilterResult(p.is_dir())

    def __str__(self) -> str:
        return "is folder"


@dataclass
class FilterIsFile(Filter):
    def test(self, p: Path) -> FilterResult:
        return FilterResult(p.is_file())

    def __str__(self) -> str:
        return "is file"


@dataclass
class FilterIsEmpty(Filter):
    def test(self, p: Path) -> FilterResult:
        if p.is_dir():
            r = any(p.iterdir())
        else:
            r = p.stat().st_size == 0

        return FilterResult(r)

    def __str__(self) -> str:
        return "is empty"


@dataclass
class FilterIsNamed(Filter):
    pattern: str

    def test(self, p: Path) -> FilterResult:
        # TODO: case-insensitive file systems?
        r = fnmatch.fnmatch(p.name, self.pattern)
        return FilterResult(r)

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

    def test(self, p: Path) -> FilterResult:
        # TODO: messy
        # TODO: shouldn't include the directory itself
        r = (p.is_dir() and fnmatch.fnmatch(p.name, self.pattern)) or any(
            fnmatch.fnmatch(s, self.pattern) for s in p.parts[:-1]
        )
        return FilterResult(r)

    def negate(self) -> Filter:
        return FilterIsNotIn(self.pattern)

    def __str__(self) -> str:
        return f"is in {self.pattern!r}"


@dataclass
class FilterIsNotIn(Filter):
    pattern: str

    def test(self, p: Path) -> FilterResult:
        if p.is_dir() and fnmatch.fnmatch(p.name, self.pattern):
            return FilterResult(False, should_recurse=False)
        else:
            # assumption: if a parent directory was excluded we never got here in the first place
            # b/c we passed should_recurse=False above
            return FilterResult(True)

    def __str__(self) -> str:
        return f"is not in {self.pattern!r}"


@dataclass
class FilterIsHidden(Filter):
    def test(self, p: Path) -> FilterResult:
        # TODO: cross-platform?
        # TODO: only consider parts from search root?
        r = any(s.startswith(".") for s in p.parts)
        return FilterResult(r)

    def negate(self) -> Filter:
        return FilterIsNotHidden()

    def __str__(self) -> str:
        return "is hidden"


@dataclass
class FilterIsNotHidden(Filter):
    def test(self, p: Path) -> FilterResult:
        # TODO: cross-platform?
        if p.name.startswith("."):
            return FilterResult(False, should_recurse=False)
        else:
            return FilterResult(True)

    def __str__(self) -> str:
        return "is not hidden"


@dataclass
class FilterSizeGreater(Filter):
    base: decimal.Decimal
    multiple: int

    def test(self, p: Path) -> FilterResult:
        r = p.stat().st_size > (self.base * self.multiple)
        return FilterResult(r)

    def __str__(self) -> str:
        # TODO: human-readable units
        return f"> {self.base * self.multiple} bytes"


@dataclass
class FilterSizeGreaterEqual(Filter):
    base: decimal.Decimal
    multiple: int

    def test(self, p: Path) -> FilterResult:
        r = p.stat().st_size >= (self.base * self.multiple)
        return FilterResult(r)

    def __str__(self) -> str:
        return f">= {self.base * self.multiple} bytes"


@dataclass
class FilterSizeLess(Filter):
    base: decimal.Decimal
    multiple: int

    def test(self, p: Path) -> FilterResult:
        r = p.stat().st_size < (self.base * self.multiple)
        return FilterResult(r)

    def __str__(self) -> str:
        return f"< {self.base * self.multiple} bytes"


@dataclass
class FilterSizeLessEqual(Filter):
    base: decimal.Decimal
    multiple: int

    def test(self, p: Path) -> FilterResult:
        r = p.stat().st_size <= (self.base * self.multiple)
        return FilterResult(r)

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

    def test(self, p: Path) -> FilterResult:
        r = p.suffix == self.ext
        return FilterResult(r)

    def __str__(self) -> str:
        return f"has extension {self.ext!r}"
