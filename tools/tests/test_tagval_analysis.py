#!/usr/bin/env python3
"""Unit tests for tools/tagval_analysis.py.

Values per MACRO-TABLE-FORMAT-VERIFIED.md sec.10.3 (dump words from
the Phase B debugger stops).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tagval_analysis as m  # noqa: E402

# (TAG, VAL) пары из sec.10.3 дампов Phase B (02127 -, 02130 - ...).
CASES = [
    ("00152705", "00003461"),
    ("32420000", "00103461"),
    ("00152630", "56402562"),
    ("42400002", "37102570"),
    ("32577776", "30100001"),
    ("00112720", "02602133"),
    ("00052711", "02602137"),
    ("00002762", "00100000"),
]


class TestSplitTagval(unittest.TestCase):
    def test_words_from_phase_b_dumps(self):
        for tag, val in CASES:
            self.assertEqual(m.split_tagval(tag + val), (tag, val))

    def test_int_input(self):
        tag, val = CASES[0]
        self.assertEqual(m.split_tagval(int(tag + val, 8)), (tag, val))

    def test_rejects_wrong_length(self):
        with self.assertRaises(ValueError):
            m.split_tagval("00152705")
        with self.assertRaises(ValueError):
            m.split_tagval("00152705000034610")


class TestAnalyze(unittest.TestCase):
    def test_analyze_all_words(self):
        for tag, val in CASES:
            w = tag + val
            self.assertEqual(m.analyze([w]), [(w, tag, val)])


if __name__ == '__main__':
    unittest.main()
