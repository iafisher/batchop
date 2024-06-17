import uuid

from batchop.batchop import main_execute

from common import BaseTmpDir


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
