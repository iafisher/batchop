import os
import shutil
import tempfile
import unittest
from pathlib import Path

from batchop.batchop import BatchOp
from batchop.fileset import FileSet


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


TEST_ROOT_PATH = Path(__file__).absolute().parent
TEST_TREE_PATH = TEST_ROOT_PATH / "test_tree"
TEST_SCRIPTS_PATH = TEST_ROOT_PATH / "scripts"
