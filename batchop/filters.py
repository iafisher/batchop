import abc
import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Union

from . import exceptions


# if tuple, interpreted as (include_self, include_children)
Result = Union[bool, Tuple[bool, bool]]


def expand_result(r: Result) -> Tuple[bool, bool]:
    if isinstance(r, tuple):
        return r
    else:
        return r, True


class Filter(abc.ABC):
    # all subclasses must override this method
    @abc.abstractmethod
    def test(self, p: Path) -> Result:
        pass

    # only subclasses that internally store a path need to override this method
    # typical implementation:
    #   return FilterXYZ(_make_absolute(self.path, root))
    def make_absolute(self, root: Path) -> "Filter":
        return self

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
class FilterTrue(Filter):
    def test(self, p: Path) -> Result:
        return True

    def __str__(self) -> str:
        return "always true"


@dataclass
class FilterIsDirectory(Filter):
    def test(self, p: Path) -> Result:
        return p.is_dir()

    def __str__(self) -> str:
        return "is directory"


@dataclass
class FilterIsFile(Filter):
    def test(self, p: Path) -> Result:
        return p.is_file()

    def __str__(self) -> str:
        return "is file"


@dataclass
class FilterIsSpecial(Filter):
    def test(self, p: Path) -> Result:
        return not p.is_file() and not p.is_dir()

    def __str__(self) -> str:
        return "is special file"


@dataclass
class FilterIsEmpty(Filter):
    def test(self, p: Path) -> Result:
        if p.is_dir():
            return not any(p.iterdir())
        else:
            # TODO: handle stat() exception
            return p.stat().st_size == 0

    def __str__(self) -> str:
        return "is empty"


@dataclass
class FilterIsExactly(Filter):
    paths: List[Path]

    def test(self, p: Path) -> Result:
        return p in self.paths

    def make_absolute(self, root: Path) -> "Filter":
        return FilterIsExactly([_make_absolute(p, root) for p in self.paths])

    def __str__(self) -> str:
        return f"is exactly: {' '.join(map(repr, self.paths))}"


@dataclass
class FilterIsLikePath(Filter):
    pattern: str

    def test(self, p: Path) -> Result:
        # TODO: case-insensitive file systems?
        return fnmatch.fnmatch(p, self.pattern)  # type: ignore

    def __str__(self) -> str:
        return f"is like {self.pattern!r} (whole-path)"


@dataclass
class FilterIsLikeName(Filter):
    pattern: str

    def test(self, p: Path) -> Result:
        # TODO: case-insensitive file systems?
        return fnmatch.fnmatch(p.name, self.pattern)  # type: ignore

    def __str__(self) -> str:
        return f"is like {self.pattern!r} (name only)"


@dataclass
class FilterMatches(Filter):
    pattern: re.Pattern

    def test(self, p: Path) -> Result:
        return self.pattern.match(p.name) is not None

    def __str__(self) -> str:
        return f"matches regex {self.pattern!r}"


@dataclass
class FilterIsInPath(Filter):
    path: Path

    def test(self, p: Path) -> Result:
        return test_is_in_exact(self.path, p)

    def make_absolute(self, root: Path) -> "Filter":
        return FilterIsInPath(_make_absolute(self.path, root))

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
            # b/c we returned include_children=False above
            return True

    def make_absolute(self, root: Path) -> "Filter":
        return FilterIsNotInPath(_make_absolute(self.path, root))

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


@dataclass
class FilterExclude(Filter):
    path: Path

    def test(self, p: Path) -> Result:
        if self.path == p:
            return (False, False)
        else:
            # assumption: if a parent directory was excluded we never got here in the first place
            # b/c we returned include_children=False above
            return True

    def make_absolute(self, root: Path) -> "Filter":
        return FilterExclude(_make_absolute(self.path, root))

    def __str__(self) -> str:
        return f"exclude {self.path!r}"


def glob_pattern_to_filter(s: str):
    if "/" in s:
        return FilterIsLikePath(s)
    else:
        return FilterIsLikeName(s)


def pattern_to_filter(s: str) -> Filter:
    # delete '*.md'        -- glob pattern
    # delete /.*\\.md/     -- regex
    # delete __pycache__   -- path
    if s.startswith("/") and s.endswith("/"):
        return FilterMatches(re.compile(s[1:-1]))
    elif "*" in s or "?" in s or "[" in s:
        return glob_pattern_to_filter(s)
    else:
        return FilterIsExactly([Path(s)])


def _make_absolute(p: Path, root: Path) -> Path:
    if p.is_absolute():
        if p.is_relative_to(root) or p == root:
            return p
        else:
            raise exceptions.PathOutsideOfRoot(path=p, root=root)
    else:
        return root / p
