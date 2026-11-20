#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for tools/comment_audit.py.

Run:  python3 -m unittest tools.tests.test_comment_audit -v
  or:  python3 tools/tests/test_comment_audit.py
"""

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import comment_audit as CA  # noqa: E402


class ParseAndEmptyOperandTests(unittest.TestCase):
    def test_parse_line_splits_operand_and_comment(self):
        got = CA.parse_line("        ЗП             , записать по адресу из УИА")
        self.assertEqual(got["mnem"], "ЗП")
        self.assertEqual(got["operand"], "")
        self.assertEqual(got["comment"], "записать по адресу из УИА")

    def test_parse_line_ignores_eqv_and_headers(self):
        self.assertIsNone(CA.parse_line("OUT477 ЭКВ '477'"))
        self.assertIsNone(CA.parse_line("* шапка с , запятой"))
        self.assertIsNone(CA.parse_line("        ЗП   CEL775"))  # без комментария

    def test_empty_operand_detection(self):
        """Пустой операнд + комментарий-утверждение = Zero-halfword галлюцинация."""
        rec = CA.parse_line("        ЗП             , записать по адресу из УИА")
        self.assertFalse(CA.is_zero_word_comment(rec["comment"]))
        self.assertEqual(CA.claim_kinds(rec["comment"]), ["адрес", "уиа"])
        self.assertFalse(CA.classify_safe(rec["operand"], rec["comment"]))

    def test_zero_word_comment_is_exempt(self):
        """Корректная аннотация нулевого слова НЕ помечается как EMPTY-OPERAND."""
        for cm in ("нулевое слово (забел)", "пустое слово", "забел"):
            self.assertTrue(CA.is_zero_word_comment(cm))
            self.assertTrue(CA.classify_safe("", cm))
        rep = self._scan_one("ASM-Z9999.be",
                             "        ЗП             , нулевое слово (забел)\n")
        empty = [f for f in rep["findings"]
                 if "EMPTY-OPERAND-SEMANTIC" in f["categories"]]
        self.assertEqual(empty, [])

    def test_suggestion_for_empty_operand(self):
        rep = self._scan_one("ASM-Z9999.be",
                             "        ЗП             , записать по адресу из УИА\n")
        hits = [f for f in rep["findings"]
                if "EMPTY-OPERAND-SEMANTIC" in f["categories"]]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["detail"]["suggestion"],
                         ", нулевое слово (забел)")
        self.assertEqual(rep["top_empty_operand"][0]["comment"],
                         "записать по адресу из УИА")

    @staticmethod
    def _scan_one(name, body):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "bemsh").mkdir()
            (root / "bemsh" / name).write_text(body, encoding="utf-8")
            return CA.audit_corpus(root)


class ContradictionAndSafeTests(unittest.TestCase):
    def test_contradiction_label_not_in_operand(self):
        # Комментарий называет метку CEL776, которой нет в операнде CEL775.
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "bemsh").mkdir()
            (root / "bemsh" / "MBE-Z9998.be").write_text(
                "        СЧ   CEL775      , записать в CEL776\n",
                encoding="utf-8")
            rep = CA.audit_corpus(root)
        hits = [f for f in rep["findings"]
                if "CONTRADICTION" in f["categories"]]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["detail"]["missing_labels"], ["CEL776"])

    def test_contradiction_register_not_in_operand(self):
        op_regs, _ = CA.extract_references("BR232(М3)")
        cm_regs, _ = CA.extract_references("вызвать BR232, возврат в М15")
        self.assertIn("М15", cm_regs - op_regs)
        self.assertNotIn("М15", op_regs)
        self.assertFalse(CA.classify_safe("BR232(М3)",
                                          "вызвать BR232, возврат в М15"))

    def test_safe_comment_examples(self):
        """Классификатор безопасных комментариев (требование 2)."""
        self.assertTrue(CA.classify_safe("CEL775", "записать в CEL775"))
        self.assertTrue(CA.classify_safe("OUT477(М15)",
                                         "вызвать OUT477 через М15"))
        self.assertTrue(CA.classify_safe("AM763(М5)", "поиск по AM763"))

    def test_safe_comment_has_no_findings(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "bemsh").mkdir()
            (root / "bemsh" / "MBE-Z9997.be").write_text(
                "        ПВ  OUT477(М15) , вызвать OUT477 через М15\n"
                "        ЗП   CEL775      , записать в CEL775\n",
                encoding="utf-8")
            rep = CA.audit_corpus(root)
        self.assertEqual(rep["findings"], [])
        self.assertEqual(rep["safe_comments"], 2)


class RepetitionTautologyLengthTests(unittest.TestCase):
    @staticmethod
    def _scan(body, name="MBE-Z9996.be", threshold=20):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "bemsh").mkdir()
            (root / "bemsh" / name).write_text(body, encoding="utf-8")
            return CA.audit_corpus(root, repeat_threshold=threshold)

    def test_repetition_over_threshold(self):
        line = "        КОНД В'0300010502200000'    , повтор\n"
        rep = self._scan(line * 21, threshold=20)
        rep_flags = [f for f in rep["findings"]
                     if "REPETITION" in f["categories"]]
        self.assertEqual(len(rep_flags), 21)
        self.assertEqual(rep_flags[0]["detail"]["count_file"], 21)
        self.assertEqual(rep_flags[0]["detail"]["count_corpus"], 21)
        # При пороге 21 тот же текст уже не считается штампом.
        rep2 = self._scan(line * 21, threshold=21)
        self.assertEqual(
            [f for f in rep2["findings"] if "REPETITION" in f["categories"]], [])

    def test_tautology_phrases(self):
        rep = self._scan("        РЖА '3'        , константа\n")
        hits = [f for f in rep["findings"] if "TAUTOLOGY" in f["categories"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("константа", hits[0]["detail"]["phrases"])

    def test_length_comment_and_line(self):
        long_comment = "а" * (CA.MAX_COMMENT + 1)
        body = "        ЗП   CEL775      , " + long_comment + "\n"
        rep = self._scan(body)
        hits = [f for f in rep["findings"] if "LENGTH" in f["categories"]]
        self.assertEqual(len(hits), 1)
        self.assertTrue(any("comment" in x for x in hits[0]["detail"]["over"]))


class KnownZoneAndCliTests(unittest.TestCase):
    def test_zone_0055_known_line(self):
        """Бывший баг ASM-Z0055.be:596 исправлен: пустой операнд ЗП
        теперь честно помечен как нулевое слово; категории ошибки нет.
        Детектор при этом по-прежнему ловит синтетический плохой пример.
        """
        rep = CA.audit_corpus(ROOT, zone="0055")
        bad = [f for f in rep["findings"]
               if f["file"] == "ASM-Z0055.be" and f["line"] == 596
               and "EMPTY-OPERAND-SEMANTIC" in f["categories"]]
        self.assertEqual(bad, [])

        synthetic = (
            "Z0055   СТАРТ 1\n"
            "        М\n"
            "        ЗП             , записать по адресу из УИА\n"
            "        ФИНИШ\n"
        )
        with tempfile.TemporaryDirectory() as td:
            root2 = pathlib.Path(td)
            (root2 / "bemsh").mkdir()
            (root2 / "bemsh" / "ASM-Z0055.be").write_text(
                synthetic, encoding="utf-8")
            rep2 = CA.audit_corpus(root2)
        hits = [f for f in rep2["findings"]
                if "EMPTY-OPERAND-SEMANTIC" in f["categories"]]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["detail"]["suggestion"],
                         ", нулевое слово (забел)")

    def test_zone_filter_and_corpus_json(self):
        rep = CA.audit_corpus(ROOT, zone="0055")
        self.assertEqual(rep["scanned_files"], 1)
        self.assertTrue(all(f["zone"] == "0055" for f in rep["findings"]))
        all_rep = CA.audit_corpus(ROOT)
        self.assertEqual(all_rep["scanned_files"], 69)

    def test_text_and_json_output(self):
        out = CA.format_text_report(CA.audit_corpus(ROOT, zone="0055"), top=3)
        self.assertIn("COMMENT AUDIT", out)
        self.assertIn("CAVEATS", out)
        # JSON-сериализуемость полного отчёта; в исправленном корпусе
        # старой ошибочной фразы быть не должно.
        blob = json.dumps(CA.audit_corpus(ROOT, zone="0055"),
                          ensure_ascii=False)
        self.assertNotIn("записать по адресу из УИА", blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
