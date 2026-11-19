#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for tools/literal_labels.py.

Run:  python3 -m unittest tools.tests.test_literal_labels -v
  or:  python3 tools/tests/test_literal_labels.py
"""

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import literal_labels as LL  # noqa: E402


class ClassificationTests(unittest.TestCase):
    def test_uia_operand_is_address(self):
        # УИА '4235'(М2) in ASM-Z0055.be:87 — must be relabelled.
        self.assertEqual(LL.classify("УИА", "4235", "0055"), "ADDRESS")
        self.assertEqual(LL.classify("ПВ", "604", "0137"), "ADDRESS")
        self.assertEqual(LL.classify("Э70", "773", "0055"), "ADDRESS")

    def test_extract_code_is_constant(self):
        # Э50 '105' is an extract code operand, never an address.
        self.assertEqual(LL.classify("Э50", "105", "0140"), "CONSTANT")
        for mnem in ("Э52", "Э54", "Э64", "Э73", "Э77"):
            self.assertEqual(LL.classify(mnem, "4", "0140"), "CONSTANT")

    def test_mask_and_data_word_are_constant(self):
        # СДА 64-6 — mask; a quoted '64' under СДА is an immediate field.
        self.assertEqual(LL.classify("СДА", "64", "0055"), "CONSTANT")
        self.assertEqual(LL.classify("РЖА", "3", "0137"), "CONSTANT")
        # В'................' data words are not extracted at all.
        code = LL._code_part("        КОНД В'7727070700000000'    ,слово 0")
        self.assertEqual(LL.QUOTED_OCTAL.findall(code), [])

    def test_fill_pattern_is_constant_not_address(self):
        self.assertEqual(LL.classify("ВЧП", "25252", "0146"), "CONSTANT")
        self.assertEqual(LL.classify("СЛИА", "72525", "0567"), "CONSTANT")
        # Same value outside a fill zone remains address-like.
        self.assertEqual(LL.classify("СЛИА", "25252", "0055"), "ADDRESS")

    def test_ambiguous_context(self):
        # СД '5' — shift count or cell?  Keep visible, mark hypothesis.
        self.assertEqual(LL.classify("СД", "5", "0055"), "AMBIGUOUS")
        self.assertEqual(LL.classify("НЕИЗВЕСТНО", "123", "0137"), "AMBIGUOUS")

    def test_eqv_definition_is_not_an_operand(self):
        code = LL._code_part("ERR564 ЭКВ '3564'")
        toks = code.split()
        self.assertEqual(toks[1], "ЭКВ")
        self.assertEqual(LL.classify("ERR564", "3564", "0055"), "AMBIGUOUS")
        # scan() explicitly overrides this to CONSTANT for is_eqv lines.


class LabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.occ = LL.scan(ROOT)
        cls.rows = LL.build_index(
            cls.occ, LL.load_global_roles(ROOT), LL.load_semantic_roles(ROOT),
            LL.load_existing_labels(ROOT), ROOT)

    def test_label_length_and_uppercase(self):
        for value, row in self.rows.items():
            label = row["label"]
            self.assertLessEqual(len(label), 6, (value, label))
            self.assertGreaterEqual(len(label), 2, (value, label))
            self.assertEqual(label, label.upper(), (value, label))
            self.assertRegex(label, r"^[A-Z0-9]+$", (value, label))

    def test_uniqueness(self):
        labels = [r["label"] for r in self.rows.values()]
        self.assertEqual(len(labels), len(set(labels)))

    def test_curated_globals(self):
        # Curated names are static knowledge; the live index changes after
        # the batch application (literals become labels and disappear).
        self.assertEqual(LL.CURATED_LABELS["70707"], "ITM707")
        self.assertEqual(LL.CURATED_LABELS["70000"], "SYSC70")
        if "70000" in self.rows:
            self.assertEqual(self.rows["70000"]["label"], "SYSC70")

    def test_constant_only_value_gets_no_label(self):
        # A value may be CONSTANT under Э50 and ADDRESS under СЧ — then it
        # legitimately gets a label.  Only values with NO address occurrence
        # must stay unlabelled.
        labelled_kinds = {}
        for o in self.occ:
            if o["is_eqv"]:
                continue
            labelled_kinds.setdefault(o["value"], set()).add(o["kind"])
        constant_only = {v for v, k in labelled_kinds.items()
                         if k == {"CONSTANT"}}
        overlap = constant_only & set(self.rows)
        self.assertEqual(overlap, set(), sorted(overlap)[:10])

    def test_table_file_matches_index(self):
        """After batch application the table must be internally consistent
        and every stored label must actually be declared in some .be source.
        (It is NOT required to equal a freshly scanned pre-application index.)
        """
        table = ROOT / "sym" / "ALL_LABELS.tab"
        if not table.exists():
            self.skipTest("table not generated yet")
        seen = {}
        for line in table.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            self.assertEqual(len(parts), 6, line)
            self.assertLessEqual(len(parts[0]), 6, line)
            seen[parts[1]] = parts[0]
        self.assertTrue(seen)
        be_text = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (ROOT / "bemsh").glob("*.be")
        )
        declared = set()
        for line in be_text.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and parts[1] == "ЭКВ":
                declared.add(parts[0])
        missing = {lab for lab in seen.values() if lab not in declared}
        self.assertEqual(missing, set(), sorted(missing)[:10])


class ApplyTests(unittest.TestCase):
    def test_apply_on_copy_is_byte_safe_textually(self):
        """Substitution + ЭКВ must not alter the assembled operand value."""
        sample = (
            "Z0055   СТАРТ 1\n"
            "        М\n"
            "* --- existing equivalents\n"
            "CEL777 ЭКВ '777'\n"
            "        УИА  '4235'(М2) ,слово 11, прав. часть\n"
            "        Э50  '105'      ,экстракод 50\n"
        )
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "bemsh").mkdir()
            (root / "sym").mkdir()
            target = root / "bemsh" / "ASM-Z0055.be"
            target.write_text(sample, encoding="utf-8")
            rows = {"4235": {"label": "AM4235"}}
            rep = LL.apply_zone(root, target, rows, [], do_backup=False)
            self.assertTrue(rep["written"])
            self.assertEqual(rep["replacements"], 1)
            out = target.read_text(encoding="utf-8")
            self.assertIn("УИА  AM4235(М2)", out)
            self.assertIn("AM4235 ЭКВ '4235'", out)
            # The extract code must remain untouched.
            self.assertIn("Э50  '105'", out)
            # ЭКВ inserted after М / existing equivalents, before first code.
            self.assertLess(out.index("CEL777 ЭКВ"), out.index("AM4235 ЭКВ"))
            self.assertLess(out.index("AM4235 ЭКВ"), out.index("УИА  AM4235"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
