from dataclasses import dataclass
from typing import Any, List, NoReturn, Optional, Tuple

from . import filters
from .common import BatchOpImpossibleError, BatchOpSyntaxError
from .filters import Filter
from .patterns import PATTERNS, BasePattern


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
        return [filters.FilterIsFile()]
    elif tkn == "folders":
        return [filters.FilterIsFolder()]
    else:
        tokens.insert(0, tkn)
        return []


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


def err_unknown_word(word: str) -> NoReturn:
    raise BatchOpSyntaxError(f"unknown word: {word!r}")


def err_unknown_command(cmd: str) -> NoReturn:
    raise BatchOpSyntaxError(f"unknown command: {cmd!r}")


def err_empty_input() -> NoReturn:
    raise BatchOpSyntaxError("empty input")
