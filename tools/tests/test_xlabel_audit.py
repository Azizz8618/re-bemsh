#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for tools/xlabel_audit.py.

Run:  python3 -m unittest tools.tests.test_xlabel_audit -v
"""

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import xlabel_audit as XA  # noqa: E402


FIXTURE_B = """СТАРТ 1
X2000 ЭКВ '2000' , внешняя связь
X7417B ЭКВ '7417' , MEM_P03_Z0156
X1213 ЭКВ '1213' , вне зоны 0..1777
X77420 ЭКВ '77420' , CALL-OUT
P201 ЭКВ '201' , локальная цель
* X7417B: это комментарий, а не использование
        ПВ X2000(М16) , вызов
        ПБ X7417B(М7) , возврат
        ПБ X1213(М3) , локальная цель
        И  X77420(М10) , гипотеза
        ПБ P201(М3) , локальная цель
"""

FIXTURE_C = """СТАРТ 1
X2000 ЭКВ '2000' , ещё одно определение
        ПВ X2000(М16) , вызов
        ПБ X2000(М16) , вызов
"""


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        (self.dir / "MBE-Z0147.be").write_text(FIXTURE_B, encoding="utf-8")
        (self.dir / "MBE2-Z0566.be").write_text(FIXTURE_C, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_definitions_only_x_equ(self):
        defs = XA.parse_definitions(self.dir)
        names = [item.name for item in defs]
        self.assertEqual(names,
                         ["X2000", "X7417B", "X1213", "X77420",
                          "X2000"])
        first = defs[0]
        self.assertEqual((first.family, first.zone, first.line),
                         ("MBE", "0147", 2))
        self.assertEqual((first.value, first.oct_value), ("2000", 0o2000))
        self.assertEqual(defs[-1].family, "MBE2")
        self.assertNotIn("P201", names)

    def test_usages_are_file_local_and_skip_comments(self):
        defs = XA.parse_definitions(self.dir)
        counts, places = XA.parse_usages(self.dir, defs)
        self.assertEqual(counts[("MBE-Z0147.be", "X2000")], 1)
        self.assertEqual(counts[("MBE2-Z0566.be", "X2000")], 2)
        self.assertEqual(counts[("MBE-Z0147.be", "X7417B")], 1)
        self.assertEqual(sum(counts.values()), 6)
        self.assertEqual(places[("MBE-Z0147.be", "X1213")],
                         [("MBE-Z0147.be", 10)])
        self.assertNotIn(("MBE-Z0147.be", "P201"), counts)

    def test_classification_of_named_externals(self):
        cases = {
            0o2000: ("*PAGE*", "3"),
            0o4000: ("MON*ITOR", ""),
            0o70000: ("SYSCALL", ""),
            0o7417: ("УППСЛУ", ""),
            0o77316: ("ДЛЯСВЯ", ""),
        }
        for value, (name, ca) in cases.items():
            cls = XA.classify(value)
            self.assertEqual(cls.cls, XA.TRUE_EXTERNAL)
            self.assertEqual(cls.name, name)
            self.assertEqual(cls.ca, ca)
            self.assertTrue(cls.evidence)

    def test_boundaries_internal_and_unknown(self):
        for value in (0, 0o63, 0o1213, 0o1777):
            cls = XA.classify(value)
            self.assertEqual(cls.cls, XA.INTERNAL_OFFSET, oct(value))
        for value in (0o2001, 0o77420, 0o77777):
            cls = XA.classify(value)
            self.assertEqual(cls.cls, XA.UNKNOWN_ABSOLUTE, oct(value))
        self.assertEqual(XA.classify(0o2000).cls, XA.TRUE_EXTERNAL)

    def test_comment_format_and_length(self):
        defs = XA.parse_definitions(self.dir)
        by_name = {item.name: item for item in defs if item.zone == "0147"}
        named = XA.recommend_comment(by_name["X2000"],
                                     XA.classify(0o2000))
        internal = XA.recommend_comment(by_name["X1213"],
                                        XA.classify(0o1213))
        unknown = XA.recommend_comment(by_name["X77420"],
                                       XA.classify(0o77420))
        self.assertEqual(named, ", ВНЕШ: *PAGE* [СА 3], адрес 2000")
        self.assertIn("локальная цель, не внешняя связь", internal)
        self.assertIn("внешняя связь, имя не восстановлено", unknown)
        for comment in (named, internal, unknown):
            self.assertLessEqual(len(comment), XA.COMMENT_LIMIT)
            self.assertTrue(comment.startswith(", "))

    def test_name_patterns(self):
        self.assertEqual(XA.name_pattern("X120C"),
                         "Xddd[ABCE] (offset-candidate)")
        self.assertEqual(XA.name_pattern("X7417B"),
                         "XddddB (callout page/symbol)")
        self.assertEqual(XA.name_pattern("X77420"),
                         "Xddddd (callout full)")
        self.assertEqual(XA.name_pattern("X063A"),
                         "Xddd[ABCE] (offset-candidate)")

    def test_report_totals_on_fixture(self):
        report = XA.build_report(self.dir, top=3)
        self.assertEqual(report["totals"]["files_scanned"], 2)
        self.assertEqual(report["totals"]["files_with_xdefs"], 2)
        self.assertEqual(report["totals"]["definitions"], 5)
        self.assertEqual(report["totals"]["code_usages"], 6)
        self.assertEqual(report["defs_by_class"][XA.TRUE_EXTERNAL], 3)
        self.assertEqual(report["defs_by_class"][XA.INTERNAL_OFFSET], 1)
        self.assertEqual(report["defs_by_class"][XA.UNKNOWN_ABSOLUTE], 1)
        self.assertEqual(report["by_family"]["MBE2"], 1)
        self.assertEqual(len(report["top_false"]), 2)
        self.assertEqual(report["top_false"][0]["label"], "X1213")

    def test_render_markdown_contains_explicit_statement(self):
        report = XA.build_report(self.dir, top=3)
        text = XA.render_markdown(report, top=3)
        self.assertIn("ЭКВ is not a cross-reference", text)
        self.assertIn("Полная таблица переаннотации", text)
        self.assertIn("X1213", text)


class RealRepoTests(unittest.TestCase):
    def test_real_repo_scan_is_stable(self):
        report = XA.build_report(XA.DEFAULT_BE_DIR, top=10)
        totals = report["totals"]
        self.assertEqual(totals["files_scanned"], 69)
        self.assertGreaterEqual(totals["definitions"], 400)
        self.assertEqual(
            sum(report["defs_by_class"].values()), totals["definitions"]
        )
        self.assertEqual(
            sum(report["address_by_class"].values()),
            totals["distinct_addresses"],
        )
        self.assertEqual(
            sum(report["uses_by_class"].values()), totals["code_usages"]
        )
        self.assertLessEqual(len(report["top_false"]), 10)
        self.assertEqual(len(report["reannotation"]), totals["definitions"])


if __name__ == "__main__":
    unittest.main()
