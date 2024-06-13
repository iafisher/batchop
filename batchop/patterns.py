import abc
import decimal
import re
from dataclasses import dataclass
from typing import Any, List, Optional

from . import filters
from .common import unit_to_multiple


@dataclass
class WordMatch:
    captured: Optional[Any]
    consumed: bool = True
    negated: bool = False


class BasePattern(abc.ABC):
    @abc.abstractmethod
    def test(self, token: str) -> Optional[WordMatch]:
        pass


@dataclass
class Opt(BasePattern):
    pattern: BasePattern

    def test(self, token: str) -> Optional[WordMatch]:
        m = self.pattern.test(token)
        if m is not None:
            return m
        else:
            return WordMatch(captured=None, consumed=False)


@dataclass
class Lit(BasePattern):
    literal: str
    case_sensitive: bool = False
    captures: bool = False

    def test(self, token: str) -> Optional[WordMatch]:
        if self.case_sensitive:
            matches = token == self.literal
        else:
            matches = token.lower() == self.literal.lower()

        if matches:
            captured = token if self.captures else None
            return WordMatch(captured=captured)
        else:
            return None


@dataclass
class AnyLit(BasePattern):
    literals: List[str]
    case_sensitive: bool = False
    captures: bool = False

    def test(self, token: str) -> Optional[WordMatch]:
        matches = False
        for literal in self.literals:
            if self.case_sensitive:
                matches = token == literal
            else:
                matches = token.lower() == literal.lower()

            if matches:
                break

        if matches:
            captured = token if self.captures else None
            return WordMatch(captured=captured)
        else:
            return None


@dataclass
class Not(BasePattern):
    def test(self, token: str) -> Optional[WordMatch]:
        if token.lower() == "not":
            return WordMatch(captured=None, negated=True)
        else:
            return WordMatch(captured=None, consumed=False)


@dataclass
class Decimal(BasePattern):
    def test(self, token: str) -> Optional[WordMatch]:
        try:
            captured = decimal.Decimal(token)
        except decimal.InvalidOperation:
            return None
        else:
            return WordMatch(captured=captured)


@dataclass
class Int(BasePattern):
    def test(self, token: str) -> Optional[WordMatch]:
        try:
            captured = int(token, base=0)
        except ValueError:
            return None
        else:
            return WordMatch(captured=captured)


@dataclass
class String(BasePattern):
    def test(self, token: str) -> Optional[WordMatch]:
        if token != "":
            return WordMatch(captured=token)
        else:
            return None


_size_unit_pattern = re.compile(
    r"^([0-9]+(?:\.[0-9]+)?)(b|byte|bytes|kb|kilobyte|kilobytes|mb|megabyte|megabytes|gb|gigabyte|gigabytes)$"
)


@dataclass
class SizeUnit(BasePattern):
    def test(self, token: str) -> Optional[WordMatch]:
        # TODO: allow space in between size and unit
        token_lower = token.lower()
        m = _size_unit_pattern.match(token)
        if m is None:
            return None

        n = m.group(1)
        unit = m.group(2)
        multiple = unit_to_multiple(unit)
        if multiple is None:
            return None

        captured = int(decimal.Decimal(n) * multiple)
        return WordMatch(captured=captured)


PATTERNS = [
    # 'that is a file'
    (
        [
            Opt(Lit("that")),
            AnyLit(["is", "are"]),
            Not(),
            Opt(Lit("a")),
            Lit("file"),
        ],
        filters.FilterIsFile,
    ),
    # 'that is a folder'
    (
        [
            Opt(Lit("that")),
            AnyLit(["is", "are"]),
            Not(),
            Opt(Lit("a")),
            Lit("folder"),
        ],
        filters.FilterIsFolder,
    ),
    # 'that is named X'
    (
        [Opt(AnyLit(["is", "are"])), Not(), Lit("named"), String()],
        filters.FilterIsNamed,
    ),
    # 'that is empty'
    (
        [Opt(Lit("that")), AnyLit(["is", "are"]), Not(), Lit("empty")],
        filters.FilterIsEmpty,
    ),
    # '> X bytes'
    ([AnyLit([">", "gt"]), SizeUnit()], filters.FilterSizeGreater),
    # '>= X bytes'
    (
        [AnyLit([">=", "gte", "ge"]), SizeUnit()],
        filters.FilterSizeGreaterEqual,
    ),
    # '< X bytes'
    ([AnyLit(["<", "lt"]), SizeUnit()], filters.FilterSizeLess),
    # '<= X bytes'
    (
        [AnyLit(["<=", "lte", "le"]), SizeUnit()],
        filters.FilterSizeLessEqual,
    ),
    # 'that is in X'
    (
        [
            Opt(Lit("that")),
            Opt(AnyLit(["is", "are"])),
            Not(),
            Lit("in"),
            String(),
        ],
        # TODO: support glob and regex
        filters.FilterIsInPath,
    ),
    # 'that is hidden'
    (
        [Opt(Lit("that")), Opt(AnyLit(["is", "are"])), Not(), Lit("hidden")],
        filters.FilterIsHidden,
    ),
    # 'that has extension X'
    (
        [
            Opt(Lit("that")),
            AnyLit(["has", "have"]),
            AnyLit(["ext", "extension"]),
            String(),
        ],
        filters.FilterHasExtension,
    ),
    # 'with extension X'
    (
        [
            Lit("with"),
            AnyLit(["ext", "extension"]),
            String(),
        ],
        filters.FilterHasExtension,
    ),
]
