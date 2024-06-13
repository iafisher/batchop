import decimal
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, List, Optional

from batchop import patterns
from batchop.batchop import BatchOp
from batchop.fileset import FileSet
from batchop.filters import FilterIsFile, FilterIsFolder
from batchop.parsing import PhraseMatch, parse_command, tokenize, try_phrase_match


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


class TestListCommand(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        create_file_tree(self.tmpdir.name)
        self.bop = BatchOp()
        self.fs = FileSet(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_list_all(self):
        self.assert_paths_equal(
            self.bop.list(self.fs),
            [
                "constitution.txt",
                "empty_dir",
                "empty_file.txt",
                "pride-and-prejudice",
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )

    def test_list_files(self):
        fs = self.fs.is_file()
        self.assert_paths_equal(
            self.bop.list(fs),
            [
                "constitution.txt",
                "empty_file.txt",
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )

    def test_list_folders(self):
        fs = self.fs.is_folder()
        self.assert_paths_equal(self.bop.list(fs), ["empty_dir", "pride-and-prejudice"])

    def test_list_non_empty_folders(self):
        fs = self.fs.is_folder().is_not_empty()
        self.assert_paths_equal(self.bop.list(fs), ["pride-and-prejudice"])

    def test_list_in_folder(self):
        fs = self.fs.is_in("pride-and-prejudice")
        self.assert_paths_equal(
            self.bop.list(fs),
            [
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )

        # trailing slash shouldn't matter
        fs = self.fs.is_in("pride-and-prejudice/")
        self.assert_paths_equal(
            self.bop.list(fs),
            [
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )

    def test_list_by_size(self):
        fs = self.fs.size_gt(20, "kb")
        self.assert_paths_equal(self.bop.list(fs), ["constitution.txt"])

        fs = self.fs.size_lt(1, "kb")
        self.assert_paths_equal(self.bop.list(fs), ["empty_file.txt"])

    def test_list_by_extension(self):
        fs = self.fs.with_ext("txt")
        self.assert_paths_equal(
            self.bop.list(fs),
            [
                "constitution.txt",
                "empty_file.txt",
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )

    def assert_paths_equal(self, actual, expected):
        expected = [Path(os.path.join(self.tmpdir.name, p)) for p in expected]
        self.assertEqual(list(sorted(actual)), list(sorted(expected)))


def create_file_tree(root):
    create_file_tree_from_template(root, FILE_TREE)


def create_file_tree_from_template(root, t):
    for name, subtree_maybe in t.items():
        path = os.path.join(root, name)
        if subtree_maybe is not None:
            os.mkdir(path)
            create_file_tree_from_template(path, subtree_maybe)
        else:
            contents = (RESOURCES / name).read_text()
            with open(path, "w") as f:
                f.write(contents)


RESOURCES = Path(__file__).absolute().parent / "resources"
FILE_TREE = {
    "constitution.txt": None,
    "empty_dir": {},
    "empty_file.txt": None,
    "pride-and-prejudice": {
        "pride-and-prejudice-ch1.txt": None,
        "pride-and-prejudice-ch2.txt": None,
    },
}
