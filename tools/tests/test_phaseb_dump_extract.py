#!/usr/bin/env python3
"""Unit tests for tools/phaseb_dump_extract.py.

Fixtures are synthetic dispak listing text.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import phaseb_dump_extract as m  # noqa: E402

SYNTH_LISTING = (
    " 02127: aox 0001\n"
    "0015 2705 0000 3461\n"
    "3242 0000 0010 3461\n"
    "some other line\n"
    "0011 2720 0260 2133\n"
)


class TestExtractDump(unittest.TestCase):
    def test_extract_after_aox_line(self):
        self.assertEqual(m.extract_dump(SYNTH_LISTING),
                         ["0015 2705 0000 3461", "3242 0000 0010 3461"])

    def test_no_aox_returns_empty(self):
        self.assertEqual(m.extract_dump("0015 2705 0000 3461\n"), [])

    def test_leading_dash_stripped(self):
        text = " 02127: aox\n- 0015 2705 0000 3461\n"
        self.assertEqual(m.extract_dump(text), ["0015 2705 0000 3461"])

    def test_limit_eight(self):
        text = " 02127: aox\n" + "".join(
            "%04o %04o %04o %04o\n" % (i, i, i, i) for i in range(1, 12))
        got = m.extract_dump(text)
        self.assertEqual(len(got), 8)


class TestMain(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(prefix='phaseb-dump-extract-')
        self.addCleanup(self.d.cleanup)

    def test_main_usage_error(self):
        self.assertEqual(m.main([]), 2)

    def test_main_prints_words(self):
        path = os.path.join(self.d.name, 'dbg5.txt')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(SYNTH_LISTING)
        self.assertEqual(m.main([path]), 0)


if __name__ == "__main__":
    unittest.main()
