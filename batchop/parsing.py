from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, NoReturn, Optional, Tuple, Union

from . import exceptions, filters
from .filters import Filter
from .patterns import PATTERNS, BasePattern


@dataclass
class UnaryCommand:
    command: str
    filters: List[Filter]


@dataclass
class SpecialCommand:
    command: str


@dataclass
class RenameCommand:
    old: str
    new: str


@dataclass
class MoveCommand:
    filters: List[Filter]
    destination: str


ParsedCommand = Union[UnaryCommand, SpecialCommand, MoveCommand, RenameCommand]


def parse_command(words: Union[str, List[str]], *, cwd: Path) -> ParsedCommand:
    if isinstance(words, str):
        tokens = tokenize(words)
    else:
        tokens = words

    if len(tokens) == 0:
        raise exceptions.SyntaxEmptyInput

    command = tokens.pop(0).lower()

    if command in ("count", "list"):
        filters = parse_np_and_preds(tokens, cwd=cwd, empty_ok=True)
        return UnaryCommand(command=command, filters=filters)
    elif command == "delete":
        filters = parse_np_and_preds(tokens, cwd=cwd, empty_ok=False)
        return UnaryCommand(command=command, filters=filters)
    elif command == "undo":
        # TODO: handle trailing input
        # TODO: should probably not reuse UnaryCommand for this
        return SpecialCommand(command=command)
    elif command == "rename":
        return parse_rename_command(tokens)
    elif command == "move":
        return parse_move_command(tokens, cwd=cwd)
    else:
        raise exceptions.SyntaxUnknownCommand(command)


def parse_rename_command(tokens: List[str]) -> RenameCommand:
    if len(tokens) != 3 and tokens[1].lower() != "to":
        # TODO: more helpful error message
        raise exceptions.Syntax("could not parse `rename` command")

    return RenameCommand(tokens[0], tokens[2])


def parse_move_command(tokens: List[str], *, cwd: Path) -> MoveCommand:
    filters = parse_np_and_preds(tokens, cwd=cwd, trailing_ok=True)
    if not tokens:
        raise exceptions.SyntaxEndOfInput

    if tokens[0] != "to":
        raise exceptions.SyntaxExpectedToken(expected="to", actual=tokens[0])

    if len(tokens) > 2:
        raise exceptions.SyntaxExtraInput(tokens[3])

    return MoveCommand(filters=filters, destination=tokens[1])


def parse_np_and_preds(
    tokens: List[str], *, cwd: Path, empty_ok: bool = False, trailing_ok: bool = False
) -> List[Filter]:
    if empty_ok and not tokens:
        return []

    filters = parse_np(tokens, cwd=cwd)
    filters.extend(parse_preds(tokens, cwd=cwd, trailing_ok=trailing_ok))
    return filters


def parse_preds(
    tokens: List[str], *, cwd: Path, trailing_ok: bool = False
) -> List[Filter]:
    filters = []
    i = 0
    while i < len(tokens):
        matched_one = False
        for description in PATTERNS:
            m = try_phrase_match(description.patterns, tokens[i:])
            if m is not None:
                i += m.tokens_consumed
                if description.filter_constructor is not None:
                    if description.pass_cwd:
                        f = description.filter_constructor(*m.captures, cwd=cwd)
                    else:
                        f = description.filter_constructor(*m.captures)

                    if m.negated:
                        f = f.negate()

                    filters.append(f)

                matched_one = True
                break

        if not matched_one:
            if trailing_ok:
                break

            raise exceptions.SyntaxNoMatchingPattern(tokens[i])

    return filters


def parse_np(tokens: List[str], *, cwd: Path) -> List[Filter]:
    if len(tokens) == 0:
        raise exceptions.SyntaxEmptyInput

    r = []
    i = 0
    while i < len(tokens):
        tkn = tokens[i]
        f = adj_to_filter(tkn)
        if f is None:
            break
        r.append(f)
        i += 1

    if i == len(tokens):
        # failed to parse
        return []

    tkn = tokens[i]
    if tkn == "anything" or tkn == "everything":
        pass
    elif tkn == "files":
        r.append(filters.FilterIsFile())
    elif tkn in ("folders", "directories", "dirs"):
        r.append(filters.FilterIsDirectory())
    else:
        # TODO: should probably check this token isn't some special word
        r.append(filters.pattern_to_filter(tkn, cwd=cwd))

    # remove the tokens we consumed
    i += 1
    del tokens[:i]

    return r


def adj_to_filter(token: str) -> Optional[Filter]:
    if token == "all" or token == "any":
        return filters.FilterTrue()
    elif token == "empty":
        return filters.FilterIsEmpty()
    elif token == "hidden":
        return filters.FilterIsHidden()
    else:
        return None


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
                    raise exceptions.Impossible(
                        "multiple negations in the same pattern is not allowed"
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
