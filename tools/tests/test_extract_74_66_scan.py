#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты tools/extract_74_66_scan.py (только stdlib, unittest).

Запуск: python3 -m unittest tools.tests.test_extract_74_66_scan -v
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import extract_74_66_scan as ES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


class ParseReportTests(unittest.TestCase):
    def test_b_kond_decode_1_has_twenty_rows(self):
        rows = ES.parse_report(
            str(ROOT / "docs/SEMANTIC/B-KOND-DECODE-1.md"))
        self.assertEqual(len(rows), 20)
        by_target = {}
        for row in rows:
            for tag in row["targets"]:
                by_target[tag] = by_target.get(tag, 0) + 1
        self.assertEqual(by_target, {"Э66": 14, "Э72": 3, "Э74": 3})

    def test_missing_report_returns_empty(self):
        self.assertEqual(ES.parse_report("/no/such/report.md"), [])

    def test_only_rows_with_skip_reason_are_collected(self):
        rows = ES.parse_report(
            str(ROOT / "docs/SEMANTIC/B-KOND-DECODE-1.md"))
        for row in rows:
            self.assertIn("пропуск", row["reason"])
            self.assertTrue(row["targets"])


class GoldTests(unittest.TestCase):
    def test_read_gold_word_matches_report(self):
        word, path = ES.read_gold_word(str(ROOT), "0137", 57)
        self.assertEqual(format(word, "016o"), "2066614310004013")
        self.assertTrue(path.endswith("gold/MBE-Z0137-L1.bin"))

    def test_read_gold_word_returns_none_for_bad_zone(self):
        with tempfile.TemporaryDirectory() as tmp:
            word, path = ES.read_gold_word(tmp, "9999", 1)
            self.assertIsNone(word)
            self.assertIsNone(path)


class DecodeFormatTests(unittest.TestCase):
    def test_decode_target_halves(self):
        checks = (
            (0o020666143, "Э66", "immex", 4, 0o6143),
            (0o050721731, "Э72", "addrex", 10, 0o1731),
            (0o00740000, "Э74", "stop", 0, 0),
        )
        for half, name, kind, reg, arg in checks:
            with self.subTest(name=name):
                d = ES.decode(half)
                self.assertEqual(d["name"], name)
                self.assertEqual(d["kind"], kind)
                self.assertEqual(d["reg"], reg)
                self.assertEqual(d["arg"], arg)

    def test_format_half_exp_address(self):
        # Э72 '1731'(М12) и EXP-адрес '72100' в левой УВВ.
        self.assertEqual(ES.format_half(0o050721731), "Э72 '1731'(М12)")
        self.assertEqual(ES.format_half(0o051332100), "УВВ '72100'(М12)")

    def test_format_half_moda_and_reg2(self):
        self.assertEqual(ES.format_half(0o02200000), "МОДА")
        self.assertEqual(ES.format_half(0o066400003), "УИА 3(М15)")


class ByteSafetyTests(unittest.TestCase):
    def test_immex_left_is_byte_safe(self):
        safe, why = ES.byte_safety(0o020666143)  # Э66 immex слева
        self.assertTrue(safe)
        self.assertIn("immex", why)

    def test_addrex_left_is_not_byte_safe(self):
        safe, why = ES.byte_safety(0o054734663)  # Э73 addrex слева
        self.assertFalse(safe)
        self.assertIn("авто-мода", why)

    def test_stop_left_is_not_byte_safe(self):
        safe, _ = ES.byte_safety(0o060744653)  # Э74 слева
        self.assertFalse(safe)

    def test_str1_left_is_byte_safe(self):
        safe, _ = ES.byte_safety(0o020000650)  # ВЧ слева
        self.assertTrue(safe)


class ScanTests(unittest.TestCase):
    def test_full_scan_counts(self):
        rows = ES.scan(str(ROOT))
        self.assertEqual(len(rows), 20)
        safe = sum(1 for row in rows if row["byte_safe"])
        self.assertEqual(safe, 19)
        self.assertEqual(len(rows) - safe, 1)

    def test_full_scan_gold_words_match(self):
        for row in ES.scan(str(ROOT)):
            self.assertTrue(row["gold_match"], row)

    def test_known_fail_case_is_0145_230(self):
        bad = [row for row in ES.scan(str(ROOT)) if not row["byte_safe"]]
        self.assertEqual(len(bad), 1)
        self.assertEqual((bad[0]["zone"], bad[0]["address"]), ("0145", 230))
        self.assertIn("Э73", bad[0]["halves"])

    def test_known_proposed_representation(self):
        rows = ES.scan(str(ROOT))
        row = next(r for r in rows
                   if (r["zone"], r["address"]) == ("0144", 812))
        self.assertEqual(row["halves"], "МОДА / Э74 '0000'")

    def test_cli_json_and_table(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = ES.main(["--repo", str(ROOT), "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue().split("ИТОГО:")[0])
        self.assertEqual(len(data), 20)
        out2 = io.StringIO()
        with redirect_stdout(out2):
            rc = ES.main(["--repo", str(ROOT)])
        self.assertEqual(rc, 0)
        self.assertIn("сырое слово", out2.getvalue())


if __name__ == "__main__":
    unittest.main()
