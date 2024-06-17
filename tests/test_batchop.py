from batchop import exceptions
from batchop.batchop import main_execute

from common import BaseTmpDir


class TestListCommand(BaseTmpDir):
    def test_list_script(self):
        self.run_script("list.txt")


class TestDeleteCommand(BaseTmpDir):
    def test_delete_script(self):
        self.run_script("delete.txt")


class TestMoveCommand(BaseTmpDir):
    def test_move_script(self):
        self.run_script("move.txt")

    def test_move_files_collision(self):
        with self.assertRaises(exceptions.PathCollision):
            main_execute(
                "move 'empty*.txt' to whatever",
                directory=self.tmpdirpath,
                require_confirm=False,
            )

    # TODO: test for moving directories as well as files


class TestRenameCommand(BaseTmpDir):
    def test_rename_script(self):
        self.run_script("rename.txt")
