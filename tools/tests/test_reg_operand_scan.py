#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты tools/reg_operand_scan.py (только stdlib, unittest).

Запуск: python3 -m unittest tools.tests.test_reg_operand_scan -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import reg_operand_scan as RS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


class ClassifyTests(unittest.TestCase):
    def test_valid_selectors(self):
        for value in (0o5, 0o20, 0o33, 0o36, 0o37, 0o100, 0o137, 0o200, 0o237):
            cls, note = RS.classify_operand(value)
            self.assertEqual(cls, "VALID", (value, note))
            self.assertIn("cmd_002", note)

    def test_holes_and_watchdog_are_suspicious(self):
        for value in (0o10, 0o40, 0o60, 0o140, 0o170, 0o210, 0o240, 0o377):
            cls, note = RS.classify_operand(value)
            self.assertEqual(cls, "SUSPICIOUS", (oct(value), note))

    def test_too_large_operand_is_suspicious(self):
        cls, note = RS.classify_operand(0o75423)
        self.assertEqual(cls, "SUSPICIOUS")
        self.assertIn("> 0377", note)
        self.assertIn("0o23", note)  # 0o75423 & 0377

    def test_no_operand_is_hypothetical(self):
        cls, note = RS.classify_operand(None)
        self.assertEqual(cls, "HYPOTHETICAL")
        self.assertIn("нет числового", note)


class ParseTests(unittest.TestCase):
    def test_parse_be_variants(self):
        tmp = tempfile.TemporaryDirectory()
        rel = os.path.join(tmp.name, "bemsh")
        os.makedirs(rel)
        path = os.path.join(rel, "MBE-Z9999.be")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("        РЕГ  '20'       , валидно\n")
            fh.write("        РЕГ  '75423'(М4), плохо\n")
            fh.write("        РЕГ            , голый\n")
            fh.write("        РЕГ  LABEL      , символьный\n")
            fh.write("        РЕГ  (М3) 7522   , регистр перед операндом\n")
            fh.write("        СЧРЖ            , не РЕГ\n")
        rows = RS.parse_be(path, tmp.name)
        self.assertEqual(len(rows), 5)
        self.assertEqual([r["value"] for r in rows],
                         [0o20, 0o75423, None, None, 0o7522])
        self.assertEqual(rows[1]["reg"], "4")
        self.assertEqual(rows[2]["classification"], "HYPOTHETICAL")
        self.assertEqual(rows[3]["symbolic"], "LABEL")
        self.assertEqual(rows[4]["reg"], "3")  # (М3) перед числом
        tmp.cleanup()

    def test_parse_asm_keeps_address_on_second_half(self):
        tmp = tempfile.TemporaryDirectory()
        rel = os.path.join(tmp.name, "dis-forced")
        os.makedirs(rel)
        path = os.path.join(rel, "Z9999.asm")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("  511 04 102 5423 \t\tрег\t'75423'(М4)\n")
            fh.write("      04 26 33521 \t\tпо\t'33521'(М4)\n")
            fh.write("  512 02 002 0105 \t\tрег\t'105'\n")
        rows = RS.parse_asm(path, tmp.name)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["addr"], "511")
        self.assertEqual(rows[0]["value"], 0o75423)
        self.assertEqual(rows[0]["reg"], "4")
        self.assertEqual(rows[1]["addr"], "512")
        tmp.cleanup()


class DecodeTests(unittest.TestCase):
    def test_decode_half_uses_correct_070000_extension(self):
        # Бит 18 (0x040000) включает 070000, а не 0700000 (siprod-баг).
        half = 0o21025423
        d = RS.decode_half(half)
        self.assertEqual(d["name"], "рег")
        self.assertEqual(d["reg"], 4)
        self.assertEqual(d["arg1"], 0o75423)

    def test_decode_word_from_real_gold(self):
        gold = RS.gold_path("0055")
        self.assertTrue(gold and os.path.isfile(gold))
        ev = RS.decode_word(gold, "511")
        self.assertEqual(ev["bytes_hex"], "44 2b 13 4b 37 51")
        self.assertEqual(ev["word_oct"], "2102542322633521")
        self.assertEqual(ev["left"]["name"], "рег")
        self.assertEqual(ev["left"]["arg1"], 0o75423)
        self.assertEqual(ev["right"]["name"], "по")

    def test_text_like_detection(self):
        ev = RS.decode_word(RS.gold_path("0055"), "515")
        self.assertTrue(ev["text_like"])
        self.assertEqual(ev["ascii"], "0/RF>R")


class ScanTests(unittest.TestCase):
    def test_full_scan_summary_and_fix_table(self):
        occ = RS.scan(str(ROOT))
        s = RS.summarize(occ)
        # Другие агенты могут править .be параллельно: проверяем только
        # что сканер нашёл все стабильные .asm-вхождения.
        self.assertGreater(s["by_source"]["be"], 100)
        self.assertEqual(s["by_source"]["asm"], 716)
        self.assertEqual(s["total"], s["by_source"]["be"] + s["by_source"]["asm"])
        # Corpus changed: КОНК/КОНД half words now include zero operands.
        self.assertGreaterEqual(s["min_value"], 0)
        self.assertLessEqual(s["max_value"], 0o777777)
        self.assertEqual(sum(s["by_class"].values()), s["total"])
        details = RS.suspicious_details(occ, str(ROOT))
        self.assertGreater(len(details), 100)
        fixes = RS.fix_table(details)
        self.assertTrue(fixes)
        for row in fixes:
            self.assertIn("gold/", row["byte_identity"])
            self.assertIn("==", row["byte_identity"])
        # Каждая правка сохраняет исходные 6 байт в КОНД В'...'
        self.assertTrue(all("КОНД" in r["proposed"] for r in fixes))

    def test_cli_json_and_text(self):
        import json
        import subprocess
        out = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "reg_operand_scan.py"),
             "--root", str(ROOT), "--json"],
            capture_output=True, text=True, check=True).stdout
        data = json.loads(out)
        self.assertIn("summary", data)
        self.assertIn("suspicious", data)
        self.assertGreater(data["summary"]["total"], 1000)


if __name__ == "__main__":
    unittest.main()
