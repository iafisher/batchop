import uuid

from batchop import exceptions
from batchop.batchop import main_execute

from common import BaseTmpDir


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
