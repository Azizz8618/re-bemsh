#!/usr/bin/env python3
"""Тесты tools/asm_zone_links.py (только stdlib, unittest)."""

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asm_zone_links as az  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DIS = ROOT / 'dis'


class TestParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datas = az.scan(str(DIS))
        cls.by_zone = {d.zone: d for d in cls.datas}
        cls.by = az.group_by_value(cls.datas)

    def test_four_zones_are_scanned(self):
        self.assertEqual(sorted(self.by_zone),
                         ['0055', '0056', '0057', '0060'])
        for data in self.datas:
            self.assertTrue(data.refs)
            self.assertTrue(data.cells)

    def test_label_only_start_line_is_parsed(self):
        # disbesm6 prints word 0 as a separate 'START мнем операнд' line.
        ref = [r for r in self.by_zone['0055'].refs
               if r.line == 9 and r.mnem == 'выпр']
        self.assertEqual(len(ref), 1)
        self.assertEqual(az.oct_key(ref[0].value), '70707')
        self.assertEqual(ref[0].addr, 0)

    def test_numeric_call_16_is_octal_020(self):
        # 0060 word 5: пв 16(М1) = CALL 020(М1) (AGENTS section 2).
        refs = [r for r in self.by_zone['0060'].refs
                if r.addr == 5 and r.kind == 'NUM']
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].mnem, 'пв')
        self.assertEqual(az.oct_key(refs[0].value), '20')
        self.assertEqual(refs[0].line, 24)


class TestKeyAddresses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datas = az.scan(str(DIS))
        cls.by_zone = {d.zone: d for d in cls.datas}
        cls.by = az.group_by_value(cls.datas)

    def test_gate_70707_in_three_zones(self):
        refs = self.by['70707']
        self.assertEqual(sorted({r.zone for r in refs}),
                         ['0055', '0056', '0060'])
        # Eight copies at 0060.0770-0777, one at 0055.0 and 0056.0.
        z60 = sorted(r.addr for r in refs if r.zone == '0060')
        self.assertEqual(z60, list(range(0o770, 0o1000)))
        self.assertFalse(self.by_zone['0057'].refs and
                         any(az.oct_key(r.value) == '70707'
                             for r in self.by_zone['0057'].refs))

    def test_3604_call_target_in_all_four_zones(self):
        refs = self.by['3604']
        counts = {z: sum(1 for r in refs if r.zone == z)
                  for z in ('0055', '0056', '0057', '0060')}
        self.assertEqual(counts, {'0055': 1, '0056': 4,
                                  '0057': 8, '0060': 3})
        self.assertEqual(len(refs), 16)
        self.assertTrue(all(r.transfer for r in refs))

    def test_3762_vector_dispatch_in_0057(self):
        refs = self.by['3762']
        n57 = sum(1 for r in refs if r.zone == '0057')
        self.assertEqual(n57, 35)
        self.assertEqual(len(refs), 43)
        first = min(r.line for r in refs if r.zone == '0057')
        last = max(r.line for r in refs if r.zone == '0057')
        self.assertEqual((first, last), (42, 1910))

    def test_4012_exit_only_in_0057(self):
        refs = self.by['4012']
        self.assertEqual([(r.zone, r.addr, r.line) for r in refs],
                         [('0057', 2, 16), ('0057', 4, 21)])

    def test_shared_code_0055_0056_only(self):
        for value in ('220', '221', '301'):
            pairs = az.cell_pairs(self.datas, value)
            same = {(a, b): s for a, b, s in pairs}
            self.assertTrue(same[('0055', '0056')], value)
            for a, b, s in pairs:
                if '0057' in (a, b) or '0060' in (a, b):
                    self.assertFalse(s, (value, a, b))

    def test_other_offset_is_different_even_in_0055_0056(self):
        # 0020 is not part of the 169 shared words.
        pairs = az.cell_pairs(self.datas, '20')
        same = {(a, b): s for a, b, s in pairs}
        self.assertFalse(same[('0055', '0056')])

    def test_cross_zone_rows(self):
        rows = az.cross_zone(self.datas)
        idx = {r['value']: r for r in rows}
        for value in ('3604', '3762', '70707', '220', '221', '301'):
            self.assertIn(value, idx)
        self.assertNotIn('4012', idx)  # referenced in one zone only
        self.assertEqual(idx['3604']['cells'], 'вне зоны')
        self.assertEqual(idx['220']['cells'], 'НЕТ')


class TestCLI(unittest.TestCase):
    def test_json_output(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = az.main(['--json'])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        found = {row['value']: row for row in payload}
        self.assertEqual(sorted(z for z in found['3604']['zones']),
                         ['0055', '0056', '0057', '0060'])
        self.assertTrue(found['220']['pairs'][0]['identical'])

    def test_detail_output_has_evidence_lines(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            az.main(['--value', '4012'])
        text = buf.getvalue()
        self.assertIn('0057 2:OCT L16', text)
        self.assertIn('0057 4:OCT L21', text)
        for line in text.splitlines():
            self.assertLessEqual(len(line), 60)

    def test_all_lines_are_short(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            az.main(['--limit', '20'])
        for line in buf.getvalue().splitlines():
            self.assertLessEqual(len(line), 60)


if __name__ == '__main__':
    unittest.main()
