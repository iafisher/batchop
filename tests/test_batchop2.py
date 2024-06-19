from batchop.batchop2 import BatchOp2, FilterSet, parse_query

from common import BaseTmpDir


class TestBatchOp2(BaseTmpDir):
    def test_delete(self):
        bop = BatchOp2(self.tmpdirpath)
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
