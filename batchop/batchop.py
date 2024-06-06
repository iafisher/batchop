"""
Supported operations:

- delete <fileset>
- rename <pattern1> <pattern2>
- move <fileset> <destination>
- list <fileset>
- replace <pattern1> <pattern2> <fileset>
- run <cmd> <fileset>

Python interface:

    bop = BatchOp()
    bop.delete(FileSet().is_empty().is_folder().is_named("Archive"))

Command-line interface:

    $ batchop 'delete all folders named "Archive" that are not empty'
    $ batchop 'rename %_trip.jpg to %.jpg'

Interactive interface:

    $ batchop
    671 files, 17 folders
    > is a file
    671 files
    > ends with .md
    534 files
    > move to markdown-files

TODO: `--make-sandbox`
TODO: `rename` command (needs design)
TODO: gitignore support
  (if current directory has .git, apply .gitignore)
  probably also ignore hidden files by default
  tricky when you have multiple gitignores in the same repository
TODO: `move` command
TODO: `replace` command
TODO: `run` command
TODO: `trash` command
TODO: profiling + optimization
  idea: walk the tree, filter functions can prevent sub-traversal as well as
        excluding individual paths
TODO: adjectives

Profiling:

    before changing filter to tree-walking:

        5.97s user 6.29s system 88% cpu 13.838 total
        6.13s user 7.23s system 82% cpu 16.116 total

    after changing filter:

        3.31s user 7.44s system 81% cpu 13.131 total
        3.41s user 8.11s system 79% cpu 14.537 total

TODO: 'is not in __pycache__' gives different results before and after optimization
TODO: support absolute/relative paths for patterns

"""

import abc
import argparse
import dataclasses
import decimal
import fnmatch
import subprocess
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Callable,
    Generator,
    Iterator,
    List,
    NoReturn,
    Optional,
    Tuple,
    Union,
)


PathLike = Union[str, Path]


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--directory")
    parser.add_argument("words", nargs="*")
    args = parser.parse_args()

    if len(args.words) > 0:
        cmdstr = " ".join(args.words)
        main_execute(cmdstr, directory=args.directory)
    else:
        main_interactive(args.directory)


def main_execute(cmdstr: str, *, directory: Optional[str]) -> None:
    parsed_cmd = parse_command(cmdstr)

    bop = BatchOp(root=directory)
    fileset = FileSet(parsed_cmd.filters)
    if parsed_cmd.command == "delete":
        bop.delete(fileset)
    elif parsed_cmd.command == "list":
        for p in bop.list(fileset):
            print(p)
    elif parsed_cmd.command == "count":
        n = bop.count(fileset)
        print(n)
    else:
        err_unknown_command(parsed_cmd.command)


@dataclass
class ParsedCommand:
    command: str
    filters: List[Filter]


def parse_command(cmdstr: str) -> ParsedCommand:
    tokens = tokenize(cmdstr)
    if len(tokens) == 0:
        err_empty_input()

    command = tokens.pop(0).lower()

    if command in ("count", "delete", "list"):
        filters = parse_np_and_preds(tokens)
        return ParsedCommand(command=command, filters=filters)
    else:
        err_unknown_command(command)


def parse_np_and_preds(tokens: List[str]) -> List[Filter]:
    filters = parse_np(tokens)
    filters.extend(parse_preds(tokens))
    return filters


def parse_preds(tokens: List[str]) -> List[Filter]:
    filters = []
    i = 0
    while i < len(tokens):
        matched_one = False
        for pattern, filter_constructor in PATTERNS:
            m = try_phrase_match(pattern, tokens[i:])
            if m is not None:
                i += m.tokens_consumed
                if filter_constructor is not None:
                    f = filter_constructor(*m.captures)
                    if m.negated:
                        f = f.negate()

                    filters.append(f)

                matched_one = True
                break

        if not matched_one:
            # TODO: more helpful message
            raise BatchOpSyntaxError(f"could not parse starting at {tokens[i]!r}")

    return filters


def parse_np(tokens: List[str]) -> List[Filter]:
    if len(tokens) == 0:
        err_empty_input()

    tkn = tokens.pop(0)

    # TODO: parse adjectival modifiers (e.g., 'non-empty')
    if tkn == "anything" or tkn == "everything":
        return []
    elif tkn == "files":
        return [FilterIsFile()]
    elif tkn == "folders":
        return [FilterIsFolder()]
    else:
        tokens.insert(0, tkn)
        return []


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
class POpt(BasePattern):
    pattern: BasePattern

    def test(self, token: str) -> Optional[WordMatch]:
        m = self.pattern.test(token)
        if m is not None:
            return m
        else:
            return WordMatch(captured=None, consumed=False)


@dataclass
class PLit(BasePattern):
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
class PAnyLit(BasePattern):
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
class PNot(BasePattern):
    def test(self, token: str) -> Optional[WordMatch]:
        if token.lower() == "not":
            return WordMatch(captured=None, negated=True)
        else:
            return WordMatch(captured=None, consumed=False)


@dataclass
class PDecimal(BasePattern):
    def test(self, token: str) -> Optional[WordMatch]:
        try:
            captured = decimal.Decimal(token)
        except decimal.InvalidOperation:
            return None
        else:
            return WordMatch(captured=captured)


@dataclass
class PInt(BasePattern):
    def test(self, token: str) -> Optional[WordMatch]:
        try:
            captured = int(token, base=0)
        except ValueError:
            return None
        else:
            return WordMatch(captured=captured)


@dataclass
class PString(BasePattern):
    def test(self, token: str) -> Optional[WordMatch]:
        if token != "":
            return WordMatch(captured=token)
        else:
            return None


@dataclass
class PSizeUnit(BasePattern):
    def test(self, token: str) -> Optional[WordMatch]:
        token_lower = token.lower()
        if token_lower in ("b", "byte", "bytes"):
            captured = 1
        elif token_lower in ("kb", "kilobyte", "kilobytes"):
            captured = 1_000
        elif token_lower in ("mb", "megabyte", "megabytes"):
            captured = 1_000_000
        elif token_lower in ("gb", "gigabyte", "gigabytes"):
            captured = 1_000_000_000
        else:
            return None

        return WordMatch(captured=captured)


@dataclass
class PhraseMatch:
    captures: List[Any]
    negated: bool
    tokens_consumed: int


def try_phrase_match(
    patterns: List[BasePattern], tokens: List[str]
) -> Optional[PhraseMatch]:
    captures = []
    negated = False
    i = 0

    for pattern in patterns:
        if i >= len(tokens):
            # in case patterns ends with optional patterns
            token = ""
        else:
            token = tokens[i]

        m = pattern.test(token)
        if m is not None:
            if m.consumed:
                i += 1

            if m.captured is not None:
                captures.append(m.captured)

            if m.negated:
                if negated:
                    raise BatchOpImpossibleError(
                        "multiple negations in the same pattern"
                    )

                negated = True
        else:
            return None

    return PhraseMatch(captures=captures, negated=negated, tokens_consumed=i)


def tokenize(cmdstr: str) -> List[str]:
    r = []
    i = 0

    while i < len(cmdstr):
        c = cmdstr[i]
        if c.isspace():
            i = consume_whitespace(cmdstr, i)
            continue
        elif c == "'" or c == '"':
            word, i = consume_quote(cmdstr, i + 1, c)
        else:
            word, i = consume_word(cmdstr, i)

        r.append(word)

    return r


def consume_word(s: str, i: int) -> Tuple[str, int]:
    start = i
    while i < len(s):
        c = s[i]
        if c.isspace() or c == "'" or c == '"':
            break
        i += 1

    return s[start:i], i


def consume_whitespace(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1

    return i


def consume_quote(s: str, i: int, delimiter: str) -> Tuple[str, int]:
    start = i
    while i < len(s):
        # TODO: backslash escapes
        c = s[i]
        if c == delimiter:
            break
        i += 1

    return s[start:i], i + 1


def main_interactive(d: Optional[str]) -> None:
    import readline

    root = path_or_default(d)

    fs = FileSet.with_default_filters()
    if len(fs.filters) > 0:
        print("Filters applied by default: ")
        for f in fs.filters:
            print(f"  {f}")
        print()

    # whether to re-calculate the file set on next iteration of loop
    recalculate = True
    current_file = []
    while True:
        # TODO: separate counts for files and directories
        # TODO: default to ignoring .git + .gitignore?
        if recalculate:
            current_files = list(fs.resolve(root))
            print(f"{plural(len(current_files), 'file')}")

        recalculate = False
        try:
            s = input("> ").strip()
        except BatchOpSyntaxError as e:
            print(f"error: {e}")
            continue
        except EOFError:
            print()
            break

        if not s:
            continue

        if s.lower() == "list":
            for p in current_files:
                print(p)
            continue
        elif s[0] == "!":
            cmd = s[1:]
            if cmd == "pop":
                fs.pop()
                recalculate = True
            elif cmd == "clear":
                fs.clear()
                recalculate = True
            elif cmd == "filter" or cmd == "filters":
                for f in fs.filters:
                    print(f)
            elif cmd == "h" or cmd == "help":
                print("Directives:")
                print("  !clear              clear all filters")
                print("  !filter/!filters    print list of current filters")
                print("  !pop                remove the last-applied filter")
            else:
                print(
                    f"error: unknown directive: {cmd!r} (enter !help to see available directives)"
                )

            continue

        tokens = tokenize(s)
        filters = parse_preds(tokens)
        fs.filters.extend(filters)
        recalculate = True


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
        self.filters.append(FilterIsFolder())
        return self

    def is_file(self) -> "FileSet":
        self.filters.append(FilterIsFile())
        return self

    def is_empty(self) -> "FileSet":
        self.filters.append(FilterIsEmpty())
        return self

    def is_named(self, pattern: str) -> "FileSet":
        self.filters.append(FilterIsNamed(pattern))
        return self

    def is_not_named(self, pattern: str) -> "FileSet":
        self.filters.append(FilterNegated(FilterIsNamed(pattern)))
        return self

    def is_in(self, pattern: str) -> "FileSet":
        self.filters.append(FilterIsIn(pattern))
        return self

    def is_not_in(self, pattern: str) -> "FileSet":
        self.filters.append(FilterIsNotIn(pattern))
        return self

    def is_hidden(self) -> "FileSet":
        self.filters.append(FilterIsHidden())
        return self

    def is_not_hidden(self) -> "FileSet":
        self.filters.append(FilterIsNotHidden())
        return self

    # TODO: is_git_ignored() -- https://github.com/mherrmann/gitignore_parser


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


class BatchOp:
    def __init__(self, root: Optional[PathLike]) -> None:
        self.root = path_or_default(root)

    def list(self, fileset: FileSet) -> Generator[Path, None, None]:
        yield from list(fileset.resolve(self.root))

    def count(self, fileset: FileSet) -> int:
        return sum(1 for _ in fileset.resolve(self.root))

    def delete(self, fileset: FileSet) -> None:
        # TODO: don't remove files that are in a directory that will be removed
        # TODO: don't use -rf except for directories
        # TODO: pass paths to `rm` in batches
        for p in fileset.resolve(self.root):
            sh(["rm", "-rf", str(p)])


def sh(args: List[str]) -> None:
    subprocess.run(args, capture_output=True, check=True)


def path_or_default(p: Optional[PathLike]) -> Path:
    if p is None:
        r = Path(".")
    elif isinstance(p, Path):
        r = p
    else:
        r = Path(p)

    return r


def plural(n: int, s: str) -> str:
    return f"{n} {s}" if n == 1 else f"{n} {s}s"


class BatchOpError(Exception):
    pass


class BatchOpSyntaxError(BatchOpError):
    pass


class BatchOpImpossibleError(BatchOpError):
    pass


def err_unknown_word(word: str) -> NoReturn:
    raise BatchOpSyntaxError(f"unknown word: {word!r}")


def err_unknown_command(cmd: str) -> NoReturn:
    raise BatchOpSyntaxError(f"unknown command: {cmd!r}")


def err_empty_input() -> NoReturn:
    raise BatchOpSyntaxError("empty input")


PATTERNS = [
    # 'that is a file'
    (
        [
            POpt(PLit("that")),
            PAnyLit(["is", "are"]),
            PNot(),
            POpt(PLit("a")),
            PLit("file"),
        ],
        FilterIsFile,
    ),
    # 'that is a folder'
    (
        [
            POpt(PLit("that")),
            PAnyLit(["is", "are"]),
            PNot(),
            POpt(PLit("a")),
            PLit("folder"),
        ],
        FilterIsFolder,
    ),
    # 'that is named X'
    ([POpt(PAnyLit(["is", "are"])), PNot(), PLit("named"), PString()], FilterIsNamed),
    # 'that is empty'
    (
        [POpt(PLit("that")), PAnyLit(["is", "are"]), PNot(), PLit("empty")],
        FilterIsEmpty,
    ),
    # '> X bytes'
    ([PAnyLit([">", "gt"]), PDecimal(), PSizeUnit()], FilterSizeGreater),
    # '>= X bytes'
    ([PAnyLit([">=", "gte", "ge"]), PDecimal(), PSizeUnit()], FilterSizeGreaterEqual),
    # '< X bytes'
    ([PAnyLit(["<", "lt"]), PDecimal(), PSizeUnit()], FilterSizeLess),
    # '<= X bytes'
    ([PAnyLit(["<=", "lte", "le"]), PDecimal(), PSizeUnit()], FilterSizeLessEqual),
    # 'that is in X'
    (
        [
            POpt(PLit("that")),
            POpt(PAnyLit(["is", "are"])),
            PNot(),
            PLit("in"),
            PString(),
        ],
        FilterIsIn,
    ),
    # 'that is hidden'
    (
        [POpt(PLit("that")), POpt(PAnyLit(["is", "are"])), PNot(), PLit("hidden")],
        FilterIsHidden,
    ),
    # 'that has extension X'
    (
        [
            POpt(PLit("that")),
            PAnyLit(["has", "have"]),
            PAnyLit(["ext", "extension"]),
            PString(),
        ],
        FilterHasExtension,
    ),
]
