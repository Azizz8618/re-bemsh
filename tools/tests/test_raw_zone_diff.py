#!/usr/bin/env python3
"""Unit tests for tools/raw_zone_diff.py.

Fixtures are synthetic; no gold or silver zone file is touched.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import raw_zone_diff as m  # noqa: E402

W0 = b'\x01\x02\x03\x04\x05\x06'
W1 = b'\x11\x12\x13\x14\x15\x16'
W2 = b'\x21\x22\x23\x24\x25\x26'


class TestDiffWords(unittest.TestCase):
    def test_equal_zones_no_diffs(self):
        self.assertEqual(m.diff_words([W0, W1, W2], [W0, W1, W2]), [])

    def test_diff_words_reported(self):
        self.assertEqual(m.diff_words([W0, W1, W2], [W0, W2, W2]),
                         [(1, W1, W2)])

    def test_missing_silver_word_reported(self):
        self.assertEqual(m.diff_words([W0, W1], [W0]),
                         [(1, W1, None)])

    def test_empty_zones(self):
        self.assertEqual(m.diff_words([], []), [])


class TestMain(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(prefix='raw-zone-diff-')
        self.addCleanup(self.d.cleanup)

    def write_zone(self, name, words):
        path = os.path.join(self.d.name, name)
        with open(path, 'wb') as f:
            f.write(b''.join(words))
        return path

    def test_main_exit_codes(self):
        g = self.write_zone('gold.bin', [W0, W1])
        s = self.write_zone('silver.bin', [W0, W1])
        self.assertEqual(m.main([g, s]), 0)
        s2 = self.write_zone('silver2.bin', [W0, W2])
        self.assertEqual(m.main([g, s2]), 1)

    def test_main_usage_error(self):
        self.assertEqual(m.main([]), 2)


if __name__ == '__main__':
    unittest.main()
