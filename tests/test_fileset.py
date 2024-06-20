from batchop.fileset import FilterSet

from common import BaseTmpDir


class TestFilterSet(BaseTmpDir):
    def test_filter_set(self):
        fileset = FilterSet().is_file().resolve(self.tmpdirpath, recursive=False)
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
        fileset = FilterSet().is_file().resolve(self.tmpdirpath, recursive=True)
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

        fileset = FilterSet().is_dir().resolve(self.tmpdirpath, recursive=False)
        self.assert_file_set_equals(
            fileset, ["empty_dir", "misc", "pride-and-prejudice"]
        )

        fileset = FilterSet().is_dir().resolve(self.tmpdirpath, recursive=True)
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
            FilterSet().is_file().is_empty().resolve(self.tmpdirpath, recursive=True)
        )
        self.assert_file_set_equals(fileset, ["empty_file.txt", "misc/empty_file.txt"])
