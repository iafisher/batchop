from batchop.batchop2 import BatchOp2, FilterSet, parse_query

from common import BaseTmpDir


class TestBatchOp2(BaseTmpDir):
    def test_delete(self):
        bop = BatchOp2(self.tmpdirpath)
        filterset = FilterSet().is_file().is_empty()

        self.assertTrue(bop.count(filterset) > 0)
        bop.delete(filterset, require_confirm=False)
        self.assertEqual(bop.count(filterset), 0)
