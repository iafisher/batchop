from pathlib import Path

from batchop import parsing
from batchop.fileset import FileSet

from common import TEST_SCRIPTS_PATH, BaseTmpDir


class TestListCommand(BaseTmpDir):
    def test_list_all(self):
        self.assert_paths_equal(
            self.bop.list(self.fs),
            [
                "constitution.txt",
                "empty_dir",
                "empty_file.txt",
                "misc",
                "misc/empty_file.txt",
                "pride-and-prejudice",
                "pride-and-prejudice/pride-and-prejudice-ch1.txt",
                "pride-and-prejudice/pride-and-prejudice-ch2.txt",
            ],
        )

    def assert_paths_equal(self, actual, expected):
        actual = [p.relative_to(self.tmpdirpath) for p in actual]
        expected = [Path(s) for s in expected]
        self.assertEqual(list(sorted(actual)), list(sorted(expected)))


class TestFileSetViaScript(BaseTmpDir):
    def test_via_script(self):
        for stmt, expected_paths in self._read_blocks():
            tokens = parsing.tokenize(stmt)
            filters_ = parsing.parse_np_and_preds(tokens, cwd=Path(self.tmpdirpath))
            print(filters_)
            fs = FileSet(self.tmpdirpath, filters_)
            actual_paths = [
                p.relative_to(self.tmpdirpath) for p in sorted(fs.resolve())
            ]
            self.assertEqual(actual_paths, expected_paths)

    def _read_blocks(self):
        with open(TEST_SCRIPTS_PATH / "filters.txt", "r") as f:
            current_statement = None
            current_block = []
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith(">"):
                    if current_statement is not None:
                        yield current_statement, current_block

                    current_statement = line[1:]
                    current_block.clear()
                else:
                    if current_statement is None:
                        raise Exception(f"expected line {i} to begin with '>'")

                    current_block.append(Path(line))

            if current_statement is not None:
                yield current_statement, current_block
