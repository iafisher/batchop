from batchop import exceptions
from batchop.batchop import BatchOp
from batchop.fileset import FilterSet
from batchop.main import main_mv

from common import BaseTmpDir


class TestListCommand(BaseTmpDir):
    def test_list_script(self):
        self.run_script("list.txt")


class TestDeleteCommand(BaseTmpDir):
    def test_delete_script(self):
        self.run_script("delete.txt")

    def test_delete_api(self):
        bop = BatchOp(self.tmpdirpath)
        filterset = FilterSet().is_file().is_empty()
        original_count = bop.count(filterset)
        self.assertTrue(original_count > 0)

        delete_result = bop.delete(filterset, require_confirm=False)

        self.assertEqual(
            self._make_relative_and_sort(delete_result.paths_deleted),
            ["empty_file.txt", "misc/empty_file.txt"],
        )
        self.assertEqual(bop.count(filterset), 0)

        undo_result = bop.undo(require_confirm=False)

        self.assertEqual(undo_result.num_ops, 2)
        self.assertEqual(bop.count(filterset), original_count)
        self.assert_unchanged()


class TestMoveCommand(BaseTmpDir):
    def test_move_script(self):
        self.run_script("move.txt")

    def test_move_files_collision(self):
        with self.assertRaises(exceptions.PathCollision):
            main_mv(
                self.bop,
                [],
                "whatever",
                query="empty*.txt",
                require_confirm=False,
                dry_run=False,
            )

        self.assert_unchanged()

    def test_move_api(self):
        bop = BatchOp(self.tmpdirpath)
        filterset = FilterSet().is_like("*-ch*.txt")
        self.assertEqual(bop.count(filterset.is_in("chapters")), 0)

        move_result = bop.move(filterset, "chapters", require_confirm=False)

        self.assertEqual(
            self._make_relative_and_sort(move_result.paths_moved),
            [
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )
        self.assertEqual(bop.count(filterset.is_in("chapters")), 2)

        bop.undo(require_confirm=False)

        self.assertEqual(bop.count(filterset.is_in("chapters")), 0)
        self.assert_unchanged()

    # TODO: test for moving directories as well as files


class TestRenameCommand(BaseTmpDir):
    def test_rename_script(self):
        self.run_script("rename.txt")

    def test_rename_api(self):
        # rename 'pride-and-prejudice-ch*.txt' to 'ch#1.txt
        bop = BatchOp(self.tmpdirpath)

        rename_result = bop.rename(
            FilterSet(),
            "pride-and-prejudice-ch*.txt",
            "ch#1.txt",
            require_confirm=False,
        )

        self.assert_file_set_equals(
            bop.list(FilterSet().is_in("pride-and-prejudice")),
            ["pride-and-prejudice/ch1.txt", "pride-and-prejudice/ch2.txt"],
        )
        self.assertEqual(len(rename_result.paths_renamed), 2)

        bop.undo(require_confirm=False)

        self.assert_unchanged()
