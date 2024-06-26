import os
import shlex
import shutil
import tempfile
import unittest
import uuid
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from batchop.batchop import BatchOp
from batchop.main import _main


class BaseTmpDir(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmpdirpath = os.path.join(self.tmpdir.name, "test_tree")

        shutil.copytree(TEST_TREE_PATH, self.tmpdirpath)
        # create an empty directory; this has to be done dynamically because git won't track an empty directory so it
        # can't exist in the test_tree/ directory
        os.mkdir(os.path.join(self.tmpdirpath, "empty_dir"))

        self._original_tree = self._list_files()
        self.context = uuid.uuid4().hex
        self.bop = BatchOp(self.tmpdirpath, context=self.context)

    def tearDown(self):
        self.tmpdir.cleanup()

    def assert_file_exists(self, path):
        self.assertTrue(os.path.exists(os.path.join(self.tmpdirpath, path)))

    def assert_file_not_exists(self, path):
        self.assertFalse(os.path.exists(os.path.join(self.tmpdirpath, path)))

    def assert_file_set_equals(self, actual, expected):
        self.assertEqual(
            list(sorted(p.relative_to(self.tmpdirpath) for p in actual)),
            list(sorted(Path(s) for s in expected)),
        )

    def assert_unchanged(self):
        self.assertEqual(self._original_tree, self._list_files())

    def _make_relative_and_sort(self, paths):
        r = [str(p.relative_to(self.tmpdirpath)) for p in paths]
        r.sort()
        return r

    def _list_files(self):
        return list(sorted(Path(self.tmpdirpath).rglob("*")))

    def run_script(self, name):
        context = uuid.uuid4().hex
        for cmd, output_lines in self.read_script(name):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                words = shlex.split(cmd)
                _main(
                    [
                        "-d",
                        self.tmpdirpath,
                        "--no-confirm",
                        "--context",
                        context,
                        "--sort",
                    ]
                    + words
                )

            self.assertEqual(
                mock_stdout.getvalue().rstrip("\n"),
                "\n".join(output_lines),
                msg=f"output not equal for command {cmd!r}",
            )

    @staticmethod
    def read_script(name):
        p = TEST_SCRIPTS_PATH / name
        with open(p, "r") as f:
            cmd = None
            block = []
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith(">"):
                    if cmd is not None:
                        yield cmd, block

                    cmd = line[1:]
                    block.clear()
                else:
                    if cmd is None:
                        raise Exception(f"expected line {i} of {p} to begin with '>'")

                    block.append(line)

            if cmd is not None:
                yield cmd, block


TEST_ROOT_PATH = Path(__file__).absolute().parent
TEST_TREE_PATH = TEST_ROOT_PATH / "test_tree"
TEST_SCRIPTS_PATH = TEST_ROOT_PATH / "scripts"
