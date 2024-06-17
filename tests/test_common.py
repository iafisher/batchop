import unittest

from batchop.common import bytes_to_unit


class TestUtilities(unittest.TestCase):
    def test_bytes_to_unit(self):
        self.assertEqual(bytes_to_unit(235, color=False), None)
        self.assertEqual(bytes_to_unit(1270, color=False), "1.3 KB")
        self.assertEqual(bytes_to_unit(40278, color=False), "40.3 KB")
        self.assertEqual(bytes_to_unit(50_040_278, color=False), "50.0 MB")
        self.assertEqual(bytes_to_unit(238_150_040_278, color=False), "238.2 GB")
