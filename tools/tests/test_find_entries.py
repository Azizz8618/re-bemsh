#!/usr/bin/env python3
"""Тесты tools/find_entries.py (только stdlib, unittest)."""

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import find_entries as fe  # noqa: E402


class TestBeScanning(unittest.TestCase):
    def test_all_69_modules_have_one_zone_start(self):
        results = fe.scan_all_be()
        self.assertEqual(len(results), 69)
        for r in results:
            self.assertEqual(len(r["starts"]), 1, r["file"])
            # База СТАРТ теперь адрес загрузки (резиденты) или 10000.
            self.assertIn(r["starts"][0]["value"],
                          (0, 1, 0o2000, 0o4000, 0o6000,
                           0o24000, 0o26000, 0o70000,
                           0o74000, 0o76000, 0o10000), r["file"])

    def test_comment_entry_mentions_are_ignored(self):
        content = (
            "* ВХОД упомянут в комментарии, не директива\n"
            "* МАКРО ВХОДН: macros.be:10\n"
            "TESTZ СТАРТ 1\n"
            "FOO ВХОД A\n"
            "BAR ВХОДН B\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".be", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(content)
            path = Path(fh.name)
        try:
            r = fe.scan_be_file(path)
        finally:
            path.unlink()
        self.assertEqual(len(r["starts"]), 1)
        self.assertEqual([e["word"] for e in r["entries"]],
                         ["ВХОД", "ВХОДН"])
        self.assertEqual([e["line"] for e in r["entries"]], [4, 5])

    def test_call_targets_symbolic_and_numeric(self):
        # CA221 -> 0221к8; числовой операнд 17 -> 021к8 (AGENTS.md §2).
        content = (
            "TESTZ СТАРТ 1\n"
            "CA221 ЭКВ '221'\n"
            "         ПВ   CA221(М3)  , вызвать\n"
            "         ПВ   CA221(М4)  , вызвать\n"
            "         ПВ   17(М3)     , вызвать 021к8\n"
            "         ПВ   6003(М15)  , вне зоны -- не считать\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".be", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(content)
            path = Path(fh.name)
        try:
            r = fe.scan_be_file(path)
        finally:
            path.unlink()
        self.assertEqual(r["calls"][0o221], 2)
        self.assertEqual(r["calls"][0o21], 1)
        self.assertNotIn(0o6003, r["calls"])
        self.assertEqual(r["defacto"], (0o221, 2))

    def test_known_zone_top_call_targets(self):
        by_zone = {r["zone"]: r for r in fe.scan_all_be()}
        self.assertEqual(by_zone["0055"]["defacto"][0], 0o221)
        self.assertGreaterEqual(by_zone["0055"]["defacto"][1], 4)
        self.assertEqual(by_zone["0056"]["defacto"][0], 0o221)
        self.assertEqual(by_zone["0060"]["defacto"][0], 0o220)
        self.assertEqual(by_zone["0147"]["defacto"][0], 0o477)
        self.assertEqual(by_zone["0547"]["defacto"][0], 0o472)
        self.assertEqual(by_zone["0140"]["defacto"], None)


class TestListingScanning(unittest.TestCase):
    def test_summary_and_execute_symbols(self):
        L = fe.scan_listing()
        self.assertEqual(L["nam"], "00001")
        self.assertEqual(L["entry_logical"], "00001")
        self.assertEqual(L["ext_count"], 3)
        self.assertEqual(L["prog_entry_mem"], 0o1000)
        self.assertEqual(L["execute"]["PRINT8"]["addr"], 0o1205)
        self.assertEqual(L["execute"]["*CM400*"]["addr"], 0o1243)
        self.assertEqual(L["execute"]["*PAGE*"]["addr"], 0o2000)
        self.assertEqual(L["execute"]["MON*ITOR"]["addr"], 0o4000)
        self.assertEqual(L["start_decl"]["value"], 1)

    def test_standalone_entry_fields_and_star_entry(self):
        # ВХОДН= может встречаться без НАМ=; *ENTRY -- отдельная форма.
        content = (
            "MODULE  ВХОДН=00003  ВНЕШН=00002\n"
            "*ENTRY\n"
            "        START   04000\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(content)
            path = Path(fh.name)
        try:
            L = fe.scan_listing(path)
        finally:
            path.unlink()
        self.assertEqual(L["entry_logical"], "00003")
        self.assertEqual(L["ext_count"], 2)
        self.assertEqual(L["star_entry"][0]["raw"], "START")

    def test_three_external_references_from_met(self):
        L = fe.scan_listing()
        refs = L["met_external"]
        self.assertEqual(len(refs), 3)
        self.assertEqual({r["raw"]: r["logical"] for r in refs},
                         {"PRINT8": "00001", "CM400": "00002",
                          "PAGE": "00003"})


class TestSymtab(unittest.TestCase):
    def setUp(self):
        self.be = fe.scan_all_be()
        self.listing = fe.scan_listing()
        self.rows = fe.build_entry_rows(self.be, self.listing)

    def test_expected_role_counts(self):
        roles = [r["role"] for r in self.rows]
        self.assertEqual(roles.count("PROG_ENTRY"), 1)
        self.assertEqual(roles.count("EXT_SYMBOL"), 4)
        self.assertEqual(roles.count("ZONE_START"), 69)

    def test_symtab_line_format(self):
        text = fe.format_symtab(self.rows)
        lines = text.splitlines()
        self.assertEqual(len(lines), len(self.rows))
        for line in lines:
            self.assertRegex(line, r"^[0-7]+ [012] {0,62}\S{1,63}$")
            self.assertEqual(len(line.split()), 3)

    def test_program_entry_and_mapped_zone_start(self):
        by_name = {r["name"]: r for r in self.rows}
        self.assertEqual(by_name["MBE60_PROG_ENTRY"]["addr"], 0o1000)
        self.assertEqual(by_name["Z0154_ZONE_START"]["addr"], 0o2000)
        self.assertEqual(by_name["Z0154_ZONE_START"]["role"], "ZONE_START")
        self.assertTrue(by_name["Z0140_ZONE_START_LOCAL"]["name"].endswith(
            "_LOCAL"))

    def test_report_contains_both_tables(self):
        report = fe.render_report(self.be, self.listing, self.rows)
        self.assertIn("ВХОДН=00001", report)
        self.assertIn("PRINT8", report)
        self.assertIn("| 0147 |", report)
        self.assertIn("MBE60_PROG_ENTRY", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
