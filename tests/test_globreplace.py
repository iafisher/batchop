import re
import unittest

from batchop import globreplace


class TestGlobReplace(unittest.TestCase):
    def test_glob_to_regex(self):
        self.assertEqual(globreplace.glob_to_regex("*.md"), r"^(.+?)\.md$")
        self.assertEqual(
            globreplace.glob_to_regex("*.* *.md"), r"^(.+?)\.(.+?)\ (.+?)\.md$"
        )
        self.assertEqual(globreplace.glob_to_regex("*.*"), r"^(.+?)\.(.+?)$")

    def test_glob_to_regex_repl(self):
        self.assertEqual(globreplace.glob_to_regex_repl("#1 #2.#3"), r"\1 \2.\3")

    def test_glob_replacement(self):
        p = globreplace.glob_to_regex("B*.* *.md")
        repl = globreplace.glob_to_regex_repl("book #1 #3.md")
        r = re.sub(p, repl, "B2024.05 Underworld.md")
        self.assertEqual(r, "book 2024 Underworld.md")
