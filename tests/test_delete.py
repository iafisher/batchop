import uuid

from batchop.batchop import main_execute

from common import BaseTmpDir


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
