from batchop.batchop2 import BatchOp2, FilterSet3

from common import BaseTmpDir


class TestFilterSet(BaseTmpDir):
    def test_filter_set(self):
        fileset = FilterSet3().is_file().resolve(self.tmpdirpath, recursive=False)
        self.assert_file_set_equals(
            fileset,
            [
                "constitution.txt",
                "empty_file.txt",
                "misc/empty_file.txt",
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )

        # recursive=True shouldn't change anything since we are only looking at files
        fileset = FilterSet3().is_file().resolve(self.tmpdirpath, recursive=True)
        self.assert_file_set_equals(
            fileset,
            [
                "constitution.txt",
                "empty_file.txt",
                "misc/empty_file.txt",
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )

        fileset = FilterSet3().is_dir().resolve(self.tmpdirpath, recursive=False)
        self.assert_file_set_equals(
            fileset, ["empty_dir", "misc", "pride-and-prejudice"]
        )

        fileset = FilterSet3().is_dir().resolve(self.tmpdirpath, recursive=True)
        self.assert_file_set_equals(
            fileset,
            [
                "empty_dir",
                "misc",
                "misc/empty_file.txt",
                "pride-and-prejudice",
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )

        fileset = (
            FilterSet3().is_file().is_empty().resolve(self.tmpdirpath, recursive=True)
        )
        self.assert_file_set_equals(fileset, ["empty_file.txt", "misc/empty_file.txt"])


class TestBatchOp2(BaseTmpDir):
    def test_delete(self):
        bop = BatchOp2(self.tmpdirpath)
        filterset = FilterSet3().is_file().is_empty()
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
