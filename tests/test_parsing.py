import os
import re
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any, List, Optional

from batchop import filters, patterns
from batchop.parsing import (
    MoveCommand,
    PhraseMatch,
    RenameCommand,
    UnaryCommand,
    parse_command,
    tokenize,
    try_phrase_match,
)


class TestCommandParsing(unittest.TestCase):
    def test_delete_command(self):
        cwd = Path(".")

        cmd = parse_command("delete everything", cwd=cwd)
        self.assertEqual(cmd, UnaryCommand("delete", []))

        cmd = parse_command("delete anything that is a file", cwd=cwd)
        self.assertEqual(cmd, UnaryCommand("delete", [filters.FilterIsFile()]))

        cmd = parse_command("delete folders", cwd=cwd)
        self.assertEqual(cmd, UnaryCommand("delete", [filters.FilterIsDirectory()]))

    def test_list_command(self):
        cwd = Path(".")

        cmd = parse_command("list all empty files", cwd=cwd)
        self.assertEqual(
            cmd,
            UnaryCommand(
                "list",
                [filters.FilterTrue(), filters.FilterIsEmpty(), filters.FilterIsFile()],
            ),
        )

    def test_rename_command(self):
        cwd = Path(".")

        cmd = parse_command("rename '*.md' to '#1.md'", cwd=cwd)
        self.assertEqual(cmd, RenameCommand("*.md", "#1.md"))

    def test_move_command(self):
        cwd = Path(".")

        cmd = parse_command("move '*-ch*.txt' to books/austen", cwd=cwd)
        self.assertEqual(
            cmd,
            MoveCommand(
                [filters.FilterIsLikeName("*-ch*.txt")], destination="books/austen"
            ),
        )


class TestPatternMatching(unittest.TestCase):
    def test_match_literal(self):
        pattern = [patterns.Lit("is")]
        m = try_phrase_match(pattern, ["is"])
        self.assert_match(m)

        m = try_phrase_match(pattern, ["are"])
        self.assert_no_match(m)

    def test_match_optional(self):
        pattern = [patterns.Opt(patterns.Lit("an"))]
        m = try_phrase_match(pattern, ["folder"])
        self.assert_match(m)

        m = try_phrase_match(pattern, ["an"])
        self.assert_match(m)

        m = try_phrase_match(pattern, [])
        self.assert_match(m)

    def test_match_string(self):
        pattern = [patterns.Lit("named"), patterns.String()]
        m = try_phrase_match(pattern, ["named", "test.txt"])
        self.assert_match(m, captures=["test.txt"])

        m = try_phrase_match(pattern, ["named"])
        self.assert_no_match(m)

    def test_match_any_lit(self):
        pattern = [patterns.AnyLit(["gt", ">"])]
        m = try_phrase_match(pattern, ["gt"])
        self.assert_match(m)

        m = try_phrase_match(pattern, [">"])
        self.assert_match(m)

        m = try_phrase_match(pattern, ["<"])
        self.assert_no_match(m)

    def test_match_complex(self):
        pattern = [
            patterns.Opt(patterns.Lit("is")),
            patterns.Not(),
            patterns.SizeUnit(),
        ]
        m = try_phrase_match(pattern, ["is", "10.7gb"])
        self.assert_match(m, [10_700_000_000])

        # m = try_phrase_match(pattern, ["10.7", "gigabytes"])
        # self.assert_match(m, [10_700_000_000])

        m = try_phrase_match(pattern, ["is", "not", "2.1mb"])
        self.assert_match(m, [2_100_000], negated=True)

        m = try_phrase_match(pattern, ["not", "2.1mb"])
        self.assert_match(m, [2_100_000], negated=True)

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

    def test_size_and_unit(self):
        self.assertEqual(tokenize("10kb"), ["10kb"])
