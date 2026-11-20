#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты tools/internal_call_scan.py (только stdlib, unittest).

Запуск: python3 -m unittest tools/tests/test_internal_call_scan.py -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import internal_call_scan as ics  # noqa: E402

ROOT = str(Path(__file__).resolve().parents[2])
TAB = '\t'


def write_tree(files):
    """Временный корень с минимальными листингами."""
    tmp = tempfile.TemporaryDirectory()
    for rel, content in files.items():
        path = os.path.join(tmp.name, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(content)
    return tmp, tmp.name


class TestNarrowedMnemonicSet(unittest.TestCase):
    def test_only_transfer_with_return_mnemonics(self):
        self.assertEqual(
            ics.TRANSFER_MNEMONICS,
            frozenset(('пв', 'пб', 'пио', 'пино', 'пио36')))
        for dropped in ('по', 'пе', 'цикл', 'выпр', 'пво', 'вжм', 'пио36x'):
            self.assertNotIn(dropped, ics.TRANSFER_MNEMONICS)

    def test_extract_numeric_splits_absolute_and_displacement(self):
        cases = (
            ("'605'(М2)", (0o605, 'absolute')),
            ("'1656'(М2)", (0o1656, 'absolute')),
            ('5(М7)', (5, 'displacement')),
            ('32(М14)', (0o32, 'displacement')),
            ("'2043'(М4)", (None, '')),  # >1777 -- вне зоны
            ('-1(М17)', (None, '')),
            ('D00571+12(М2)', (None, '')),
        )
        for operand, expected in cases:
            with self.subTest(operand=operand):
                self.assertEqual(ics.extract_numeric(operand), expected)


class TestLineParsing(unittest.TestCase):
    def test_address_zero_present_and_second_half_inherits(self):
        line0 = ('    0 02 24 40000 ' + TAB + 'START' + TAB + 'уиа' +
                 TAB + "'40000'(М2)")
        line1 = ('      02 30 00605 ' + TAB + TAB + 'пб' + TAB +
                 "'605'(М2)")
        self.assertEqual(ics.parse_line(line0)[:2], (True, 0))
        self.assertEqual(ics.parse_line(line0)[2:], ('START', 'уиа',
                                                     "'40000'(М2)"))
        self.assertEqual(ics.parse_line(line1)[:2], (False, None))
        self.assertEqual(ics.parse_line(line1)[3:], ('пб', "'605'(М2)"))

        tmp, base = write_tree({
            'dis-forced/Z0144.asm': line0 + '\n' + line1 + '\n',
            'dis/MBE-Z0144-L1.asm': line0 + '\n' + line1 + '\n',
        })
        try:
            refs, _disps, _meta = ics.scan_listings(base)
            # Одна ячейка в двух листингах -- дедупликация в одну запись.
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0]['addr'], 0)
            self.assertEqual(refs[0]['value'], '0605')
            self.assertEqual(refs[0]['raw_count'], 2)
        finally:
            tmp.cleanup()


class TestRealRepoCounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = ics.build(ROOT)

    def test_absolute_ref_counts_and_zones(self):
        s = self.result['stats']
        self.assertEqual(s['raw_absolute_refs'], 50)
        self.assertEqual(s['dedup_absolute_refs'], 50)
        self.assertEqual(s['displacement_refs'], 106)
        self.assertEqual(s['targets'], 41)
        self.assertEqual(s['multi_ref_targets'], 5)
        self.assertEqual(s['zones_with_targets'], 3)
        self.assertEqual(s['by_mnem_absolute'], {'пб': 50})
        self.assertEqual(s['by_zone_absolute'],
                         {'0144': 39, '0150': 10, '0162': 1})

    def test_no_small_numeric_call_operand_exists(self):
        # Ни одного ПВ/ПИО/ПИНО/ПИО36 с малым числовым операндом.
        for r in self.result['rows']:
            for src in r['sources']:
                self.assertTrue(src.startswith('пб@'), src)

    def test_multi_ref_targets_exact(self):
        multi = {('%s:%s' % (r['zone'], r['target'])): r['refs']
                 for r in self.result['rows'] if r['refs'] >= 2}
        self.assertEqual(multi, {
            '0144:1175': 2, '0144:1564': 2, '0144:1643': 5,
            '0144:1644': 2, '0150:0667': 3,
        })

    def test_catalog_and_p_labels(self):
        s = self.result['stats']
        self.assertEqual(s['catalog_entries'], 142)
        self.assertEqual(s['p_label_entries'], 44)
        by_key = {('%s:%s' % (r['zone'], r['target'])): r
                  for r in self.result['rows']}
        self.assertEqual(by_key['0144:0605']['p_labels'], ('P605',))
        self.assertEqual(by_key['0144:1173']['p_labels'], ('P1173',))
        self.assertEqual(by_key['0150:0614']['p_labels'], ('P614',))
        self.assertEqual(by_key['0162:0117']['proc_status'], ('ДАН',))

    def test_verdicts_and_label_coverage(self):
        s = self.result['stats']
        self.assertEqual(s['by_verdict'], {
            'PROCEDURE_ENTRY': 5, 'ALREADY_NAMED': 5,
            'FALSE_TARGET': 1, 'SINGLE_REF': 30,
        })
        self.assertEqual(s['procedures_confirmed'], 5)
        self.assertEqual(s['targets_with_p_label'], 5)
        self.assertEqual(s['targets_without_p_label'], 36)
        self.assertEqual(s['confirmed_without_p_label'], 5)

    def test_code_context_of_confirmed_entries(self):
        by_key = {('%s:%s' % (r['zone'], r['target'])): r
                  for r in self.result['rows']}
        for key in ('0144:1175', '0144:1564', '0144:1643',
                    '0144:1644', '0150:0667'):
            with self.subTest(key=key):
                self.assertTrue(by_key[key]['has_ret'])
                self.assertTrue(by_key[key]['base_is_data'])
        self.assertEqual(by_key['0144:1643']['target_mnem'], 'сч')
        self.assertEqual(by_key['0144:1564']['target_mnem'], 'пб')


class TestCli(unittest.TestCase):
    def test_json_and_out_cli(self):
        script = os.path.join(ROOT, 'tools', 'internal_call_scan.py')
        js = subprocess.run(
            [sys.executable, script, '--root', ROOT, '--json'],
            capture_output=True, text=True, check=True)
        data = json.loads(js.stdout)
        self.assertEqual(data['stats']['dedup_absolute_refs'], 50)
        self.assertEqual(data['stats']['procedures_confirmed'], 5)

        tmp = tempfile.TemporaryDirectory()
        try:
            out = os.path.join(tmp.name, 'report.md')
            subprocess.run(
                [sys.executable, script, '--root', ROOT, '--out', out],
                capture_output=True, text=True, check=True)
            text = Path(out).read_text(encoding='utf-8')
            self.assertIn(ics.TABLE_HEADER, text)
            self.assertIn('ТОП-30 ПО ЧИСЛУ ССЫЛОК', text)
            self.assertIn('Z0144 1643: 5 ссылок', text)
        finally:
            tmp.cleanup()


if __name__ == '__main__':
    unittest.main()
