import os
import re
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any, List, Optional

from batchop import exceptions, filters, globreplace, parsing, patterns
from batchop.batchop import BatchOp, main_execute
from batchop.common import bytes_to_unit
from batchop.fileset import FileSet
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


class TestUtilities(unittest.TestCase):
    def test_bytes_to_unit(self):
        self.assertEqual(bytes_to_unit(235, color=False), None)
        self.assertEqual(bytes_to_unit(1270, color=False), "1.3 KB")
        self.assertEqual(bytes_to_unit(40278, color=False), "40.3 KB")
        self.assertEqual(bytes_to_unit(50_040_278, color=False), "50.0 MB")
        self.assertEqual(bytes_to_unit(238_150_040_278, color=False), "238.2 GB")


class TestGlobReplace(unittest.TestCase):
    def test_glob_to_regex(self):
        self.assertEqual(globreplace.glob_to_regex("*.md"), r"^(.+?)\.md$")
        self.assertEqual(
            globreplace.glob_to_regex("*.* *.md"), r"^(.+?)\.(.+?)\ (.+?)\.md$"
        )
        self.assertEqual(globreplace.glob_to_regex("*.*"), r"^(.+?)\.(.+?)$")

    def test_glob_to_regex_repl(self):
        self.assertEqual(globreplace.glob_to_regex_repl("#1 #2.#3"), r"\1 \2.\3")

    def test_glob_replacement(self):
        p = globreplace.glob_to_regex("B*.* *.md")
        repl = globreplace.glob_to_regex_repl("book #1 #3.md")
        r = re.sub(p, repl, "B2024.05 Underworld.md")
        self.assertEqual(r, "book 2024 Underworld.md")


class BaseTmpDir(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmpdirpath = os.path.join(self.tmpdir.name, "test_tree")

        shutil.copytree(TEST_TREE_PATH, self.tmpdirpath)
        # create an empty directory; this has to be done dynamically because git won't track an empty directory so it
        # can't exist in the test_tree/ directory
        os.mkdir(os.path.join(self.tmpdirpath, "empty_dir"))

        self.bop = BatchOp()
        self.fs = FileSet(self.tmpdirpath)

    def tearDown(self):
        self.tmpdir.cleanup()

    def assert_file_exists(self, path):
        self.assertTrue(os.path.exists(os.path.join(self.tmpdirpath, path)))

    def assert_file_not_exists(self, path):
        self.assertFalse(os.path.exists(os.path.join(self.tmpdirpath, path)))


class TestFileSetViaScript(BaseTmpDir):
    def test_via_script(self):
        for stmt, expected_paths in self._read_blocks():
            tokens = parsing.tokenize(stmt)
            filters_ = parsing.parse_np_and_preds(tokens, cwd=Path(self.tmpdirpath))
            print(filters_)
            fs = FileSet(self.tmpdirpath, filters_)
            actual_paths = [
                p.relative_to(self.tmpdirpath) for p in sorted(fs.resolve())
            ]
            self.assertEqual(actual_paths, expected_paths)

    def _read_blocks(self):
        with open(TEST_SCRIPTS_PATH / "filters.txt", "r") as f:
            current_statement = None
            current_block = []
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith(">"):
                    if current_statement is not None:
                        yield current_statement, current_block

                    current_statement = line[1:]
                    current_block.clear()
                else:
                    if current_statement is None:
                        raise Exception(f"expected line {i} to begin with '>'")

                    current_block.append(Path(line))

            if current_statement is not None:
                yield current_statement, current_block


class TestListCommand(BaseTmpDir):
    def test_list_all(self):
        self.assert_paths_equal(
            self.bop.list(self.fs),
            [
                "constitution.txt",
                "empty_dir",
                "empty_file.txt",
                "misc",
                "misc/empty_file.txt",
                "pride-and-prejudice",
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )

    def assert_paths_equal(self, actual, expected):
        actual = [p.relative_to(self.tmpdirpath) for p in actual]
        expected = [Path(s) for s in expected]
        self.assertEqual(list(sorted(actual)), list(sorted(expected)))


class TestRenameCommand(BaseTmpDir):
    def test_rename_pride_and_prejudice(self):
        context = uuid.uuid4().hex

        main_execute(
            "rename 'pride-and-prejudice-ch*.txt' to 'ch#1.txt",
            directory=self.tmpdirpath,
            require_confirm=False,
            context=context,
        )

        self.assert_file_exists("pride-and-prejudice/ch1.txt")
        self.assert_file_exists("pride-and-prejudice/ch2.txt")

        self.assert_file_not_exists("pride-and-prejudice/pride-and-prejudice-ch1.txt")
        self.assert_file_not_exists("pride-and-prejudice/pride-and-prejudice-ch2.txt")

        main_execute(
            "undo",
            directory=self.tmpdirpath,
            require_confirm=False,
            context=context,
        )

        self.assert_file_not_exists("pride-and-prejudice/ch1.txt")
        self.assert_file_not_exists("pride-and-prejudice/ch2.txt")

        self.assert_file_exists("pride-and-prejudice/pride-and-prejudice-ch1.txt")
        self.assert_file_exists("pride-and-prejudice/pride-and-prejudice-ch2.txt")


class TestMoveCommand(BaseTmpDir):
    def test_move_files(self):
        context = uuid.uuid4().hex

        main_execute(
            "move '*-ch*.txt' to chapters",
            directory=self.tmpdirpath,
            require_confirm=False,
            context=context,
        )

        self.assert_file_not_exists("pride-and-prejudice/pride-and-prejudice-ch1.txt")
        self.assert_file_not_exists("pride-and-prejudice/pride-and-prejudice-ch2.txt")
        self.assert_file_exists("chapters/pride-and-prejudice-ch1.txt")
        self.assert_file_exists("chapters/pride-and-prejudice-ch2.txt")
        # didn't move other stuff
        self.assert_file_exists("empty_dir")
        self.assert_file_exists("constitution.txt")

        main_execute(
            "undo", directory=self.tmpdirpath, require_confirm=False, context=context
        )

        self.assert_file_exists("pride-and-prejudice/pride-and-prejudice-ch1.txt")
        self.assert_file_exists("pride-and-prejudice/pride-and-prejudice-ch2.txt")
        self.assert_file_not_exists("chapters/pride-and-prejudice-ch1.txt")
        self.assert_file_not_exists("chapters/pride-and-prejudice-ch2.txt")
        self.assert_file_not_exists("chapters/")

    def test_move_files_collision(self):
        with self.assertRaises(exceptions.PathCollision):
            main_execute(
                "move 'empty*.txt' to whatever",
                directory=self.tmpdirpath,
                require_confirm=False,
            )

    # TODO: test for moving directories as well as files


class TestDeleteCommand(BaseTmpDir):
    def test_delete_empty_files(self):
        main_execute(
            "delete empty files",
            directory=self.tmpdirpath,
            require_confirm=False,
        )

        self.assert_file_not_exists("empty_file.txt")
        # didn't delete other stuff
        self.assert_file_exists("empty_dir")
        self.assert_file_exists("constitution.txt")

    def test_delete_folder_by_name(self):
        main_execute(
            "delete pride-and-prejudice",
            directory=self.tmpdirpath,
            require_confirm=False,
        )

        self.assert_file_not_exists("pride-and-prejudice")
        self.assert_file_not_exists("pride-and-prejudice/pride-and-prejudice-ch1.txt")
        self.assert_file_not_exists("pride-and-prejudice/pride-and-prejudice-ch2.txt")

    def test_delete_glob_pattern_and_undo(self):
        context = uuid.uuid4().hex

        main_execute(
            "delete '*.txt'",
            directory=self.tmpdirpath,
            require_confirm=False,
            context=context,
        )

        self.assert_file_not_exists("constitution.txt")
        self.assert_file_not_exists("empty_file.txt")
        self.assert_file_not_exists("pride-and-prejudice/pride-and-prejudice-ch1.txt")
        self.assert_file_not_exists("pride-and-prejudice/pride-and-prejudice-ch2.txt")
        self.assert_file_exists("empty_dir")
        self.assert_file_exists("pride-and-prejudice")

        main_execute(
            "undo",
            directory=self.tmpdirpath,
            require_confirm=False,
            context=context,
        )

        self.assert_file_exists("constitution.txt")
        self.assert_file_exists("empty_file.txt")
        self.assert_file_exists("pride-and-prejudice/pride-and-prejudice-ch1.txt")
        self.assert_file_exists("pride-and-prejudice/pride-and-prejudice-ch2.txt")
        self.assert_file_exists("empty_dir")
        self.assert_file_exists("pride-and-prejudice")


TEST_ROOT_PATH = Path(__file__).absolute().parent
TEST_TREE_PATH = TEST_ROOT_PATH / "test_tree"
TEST_SCRIPTS_PATH = TEST_ROOT_PATH / "scripts"
