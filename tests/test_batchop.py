import decimal
import unittest
from typing import Any, List, Optional

from batchop.batchop import (
    FilterIsFile,
    FilterIsFolder,
    PAnyLit,
    PDecimal,
    PLit,
    PNot,
    POpt,
    PSizeUnit,
    PString,
    PhraseMatch,
    parse_command,
    tokenize,
    try_phrase_match,
)


class TestCommandParsing(unittest.TestCase):
    def test_delete_command(self):
        cmd = parse_command("delete everything")
        self.assertEqual(cmd.command, "delete")
        self.assertEqual(cmd.filters, [])

        cmd = parse_command("delete anything that is a file")
        self.assertEqual(cmd.command, "delete")
        self.assertEqual(cmd.filters, [FilterIsFile()])

        cmd = parse_command("delete folders")
        self.assertEqual(cmd.command, "delete")
        self.assertEqual(cmd.filters, [FilterIsFolder()])


class TestPatternMatching(unittest.TestCase):
    def test_match_literal(self):
        pattern = [PLit("is")]
        m = try_phrase_match(pattern, ["is"])
        self.assert_match(m)

        m = try_phrase_match(pattern, ["are"])
        self.assert_no_match(m)

    def test_match_optional(self):
        pattern = [POpt(PLit("an"))]
        m = try_phrase_match(pattern, ["folder"])
        self.assert_match(m)

        m = try_phrase_match(pattern, ["an"])
        self.assert_match(m)

        m = try_phrase_match(pattern, [])
        self.assert_match(m)

    def test_match_string(self):
        pattern = [PLit("named"), PString()]
        m = try_phrase_match(pattern, ["named", "test.txt"])
        self.assert_match(m, captures=["test.txt"])

        m = try_phrase_match(pattern, ["named"])
        self.assert_no_match(m)

    def test_match_any_lit(self):
        pattern = [PAnyLit(["gt", ">"])]
        m = try_phrase_match(pattern, ["gt"])
        self.assert_match(m)

        m = try_phrase_match(pattern, [">"])
        self.assert_match(m)

        m = try_phrase_match(pattern, ["<"])
        self.assert_no_match(m)

    def test_match_complex(self):
        pattern = [POpt(PLit("is")), PNot(), PDecimal(), PSizeUnit()]
        m = try_phrase_match(pattern, ["is", "10.7", "gigabytes"])
        self.assert_match(m, [decimal.Decimal("10.7"), 1_000_000_000])

        m = try_phrase_match(pattern, ["10.7", "gigabytes"])
        self.assert_match(m, [decimal.Decimal("10.7"), 1_000_000_000])

        m = try_phrase_match(pattern, ["is", "not", "2.1", "mb"])
        self.assert_match(m, [decimal.Decimal("2.1"), 1_000_000], negated=True)

        m = try_phrase_match(pattern, ["not", "2.1", "mb"])
        self.assert_match(m, [decimal.Decimal("2.1"), 1_000_000], negated=True)

    def assert_match(
        self, m: PhraseMatch, captures: List[Any] = [], negated: bool = False
    ) -> None:
        self.assertIsNotNone(m)
        self.assertEqual(m.captures, captures)
        self.assertEqual(m.negated, negated)

    def assert_no_match(self, m: Optional[PhraseMatch]) -> None:
        self.assertIsNone(m)


class TestTokenize(unittest.TestCase):
    def test_simple_words(self):
        self.assertEqual(tokenize("list all files"), ["list", "all", "files"])

    def test_quoted_strings(self):
        self.assertEqual(tokenize("named '*.md'"), ["named", "*.md"])
        self.assertEqual(tokenize('named "To Do *.md"'), ["named", "To Do *.md"])

    def test_weird_whitespace(self):
        self.assertEqual(tokenize("    a  b\tc   "), ["a", "b", "c"])
