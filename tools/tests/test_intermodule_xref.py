#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for tools/intermodule_xref.py.

Run:  python3 -m unittest tools.tests.test_intermodule_xref -v
  or:  python3 tools/tests/test_intermodule_xref.py
"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import global_xref as G  # noqa: E402
import intermodule_xref as IX  # noqa: E402


def make_ref(zone="0055", addr=10, mnem="сч", operand="D00030",
             kind="LBL", value=0o30, raw="D00030", key="D00030",
             src="ASM-Z0055-L1.asm"):
    """Construct a global_xref.Ref for classification tests."""
    return G.Ref(src, zone, addr, "%o" % addr, mnem, operand, 1,
                 key, kind, raw, value, False, "")


class ClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names = IX.load_global_names(str(ROOT))

    def classify(self, ref, zone_local=True):
        return IX.classify(ref, self.names, zone_local)

    def test_zone_local_bare_address_is_intra(self):
        # A/D labels and small operands are word offsets of the -a0 listing.
        for ref in (make_ref(value=0o30),
                    make_ref(kind="IMM", value=20, raw="20", key="IMM:20",
                             operand="20(М1)", mnem="пв")):
            row = self.classify(ref)
            self.assertEqual(row["category"], "INTRA")
            self.assertEqual(row["target"], "Z0055")
            self.assertEqual(row["target_zone"], "0055")
            self.assertEqual(row["relation"], "INTRA")
            self.assertIn("ZONE_0055_WORD_", row["label"])

    def test_known_zone_memory_label_02000_is_zone_0154(self):
        cases = (("0055", "ASM→B"), ("0147", "INTER-B"),
                 ("0576", "INTER-B/B2"))
        for zone, want_relation in cases:
            ref = make_ref(zone=zone, mnem="зп", operand="'2000'",
                           kind="OCT", value=0o2000, raw="'2000'",
                           key="OCT:2000")
            row = self.classify(ref)
            self.assertEqual(row["category"], "INTER")
            self.assertEqual(row["target"], "Z0154")
            self.assertEqual(row["target_zone"], "0154")
            self.assertEqual(row["relation"], want_relation)
            self.assertIn("ZONE_0154_AT_02000", row["label"])

    def test_external_memory_labels_from_global_tab(self):
        cases = ((0o70707, "MEM_70707_GATE"),
                 (0o04000, "MEM_04000_MONITOR"),
                 (0o70000, "MEM_70000_SYSCALL"))
        for value, want in cases:
            ref = make_ref(mnem="зп", operand="'%o'" % value, kind="OCT",
                           value=value, raw="'%o'" % value,
                           key="OCT:%o" % value)
            row = self.classify(ref)
            self.assertEqual(row["category"], "MEMORY")
            self.assertEqual(row["target_kind"], "MEMORY")
            self.assertEqual(row["relation"], "MEMORY/EXTERNAL")
            self.assertEqual(row["label"], want)

    def test_fill_and_pseudo_references_are_excluded(self):
        refs = [
            make_ref(kind="FUZZ", value=None, raw="D00003+34",
                     key="FUZZ:D00003+34"),
            make_ref(kind="OCT", value=0o25252, raw="'25252'",
                     key="OCT:25252", mnem="вчп"),
            make_ref(kind="OCT", value=0o72525, raw="'72525'",
                     key="OCT:72525", mnem="слиа"),
            make_ref(kind="IMM", value=-1, raw="-1", key="IMM:-1"),
            make_ref(kind="IMM", value=64, raw="64", key="IMM:64",
                     mnem="сда"),
        ]
        for ref in refs:
            row = self.classify(ref)
            self.assertEqual(row["category"], "EXCLUDED", ref.key)
            self.assertEqual(row["relation"], "EXCLUDED")

    def test_register_indirect_is_separate(self):
        ref = make_ref(kind="MOD", value=3, raw="(М3)", key="MOD:M3",
                       mnem="пб", operand="(М3)")
        row = self.classify(ref)
        self.assertEqual(row["category"], "REGISTER")
        self.assertEqual(row["target_kind"], "REGISTER")

    def test_nonlocal_listing_small_address_is_ambiguous(self):
        ref = make_ref(zone="0137", kind="LBL", value=0o30,
                       src="MBE-Z0137-named.asm")
        row = self.classify(ref, zone_local=False)
        self.assertEqual(row["category"], "AMBIGUOUS")
        self.assertNotEqual(row["target"], "Z0137")

    def test_relation_labels_cover_all_families(self):
        self.assertEqual(IX.relation("0147", "0547", "ZONE"), "INTER-B/B2")
        self.assertEqual(IX.relation("0547", "0147", "ZONE"), "INTER-B/B2")
        self.assertEqual(IX.relation("0147", "0055", "ZONE"), "B→ASM")
        self.assertEqual(IX.relation("0055", "0147", "ZONE"), "ASM→B")
        self.assertEqual(IX.relation("0055", "0056", "ZONE"), "INTER-ASM")
        self.assertEqual(IX.relation("0147", "0154", "ZONE"), "INTER-B")
        self.assertEqual(IX.relation("0147", "0147", "ZONE"), "INTRA")


class MatrixTests(unittest.TestCase):
    def test_matrix_aggregation_and_samples(self):
        rows = []
        for addr in (10, 20, 30):
            ref = make_ref(addr=addr, kind="LBL", value=0o30)
            rows.append(IX.classify(ref, {}, True))
        other = make_ref(zone="0056", src="ASM-Z0056-L1.asm",
                         kind="OCT", value=0o2000, raw="'2000'",
                         key="OCT:2000", mnem="зп", operand="'2000'")
        rows.append(IX.classify(other, {}, True))
        matrix = IX.build_matrix(rows, sample_limit=2)
        by_key = {(c["source"], c["target"]): c for c in matrix}
        intra = by_key[("0055", "Z0055")]
        self.assertEqual(intra["count"], 3)
        self.assertEqual(intra["relation"], "INTRA")
        self.assertEqual(len(intra["samples"]), 2)
        inter = by_key[("0056", "Z0154")]
        self.assertEqual(inter["count"], 1)
        self.assertEqual(inter["relation"], "ASM→B")
        self.assertEqual(matrix[0]["count"], 3)

    def test_global_tab_labels_are_loaded(self):
        names = IX.load_global_names(str(ROOT))
        self.assertEqual(names.get(0o70707), "CODE_ITM_GATE")
        self.assertEqual(names.get(0o70000), "SYSCALL_GATE")
        self.assertEqual(IX.memory_label(0o4000, names), "MEM_04000_MONITOR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
