#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for tools/external_offset_scan.py.

Run:  python3 -m unittest tools.tests.test_external_offset_scan -v
  or:  python3 tools/tests/test_external_offset_scan.py
"""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

import external_offset_scan as EOS  # noqa: E402


class ParsingTests(unittest.TestCase):
    def test_parse_equ_and_zone(self):
        self.assertEqual(EOS.parse_equ("AM10 ЭКВ '10'"), ('AM10', '10'))
        self.assertIsNone(EOS.parse_equ("* AM10 ЭКВ '10'"))
        self.assertIsNone(EOS.parse_equ("        ЗП   AM10"))
        self.assertEqual(EOS.zone_from_path('MBE-Z0137.be'), '0137')
        self.assertEqual(EOS.zone_from_path('ASM-Z0055.be'), '0055')

    def test_parse_code_line_splits_operand_and_comment(self):
        got = EOS.parse_code_line(
            "        ЗП   BR150(М7)  , записать BR150 (переход) в М7")
        self.assertEqual(got['mnem'], 'ЗП')
        self.assertEqual(got['operand'], 'BR150(М7)')
        self.assertEqual(got['comment'], 'записать BR150 (переход) в М7')
        self.assertIsNone(EOS.parse_code_line("* ЗП BR150"))

    def test_label_boundaries(self):
        self.assertTrue(EOS.label_in_operand('BR150(М7)', 'BR150'))
        self.assertFalse(EOS.label_in_operand('B2112(М7)', 'B211'))
        self.assertFalse(EOS.label_in_operand('MB211', 'B211'))
        matchers = {'B211': EOS.label_pattern('B211'),
                    'B2112': EOS.label_pattern('B2112')}
        self.assertEqual(EOS.find_labels('И B2112(М1)', matchers), ['B2112'])


class ClassificationTests(unittest.TestCase):
    def test_local_entry_matches_zone_and_value(self):
        proc = {'0144': {'0122': {'ВЛОЖ'}}, '0161': {'0122': {'ОСН'}}}
        self.assertEqual(EOS.local_entry(proc, '0144', '122'), ('ВЛОЖ',))
        self.assertEqual(EOS.local_entry(proc, '0137', '122'), ())
        self.assertEqual(EOS.local_entry(proc, '0144', '10'), ())

    def test_classify_local_external_and_plain(self):
        proc = {'0144': {'0122': {'ВЛОЖ'}}}
        base = dict(zone='0144', value_oct='122')
        local = dict(base, target_like=True)
        EOS.classify_usage(local, proc)
        self.assertEqual(local['verdict'], 'LOCAL_ADDR')
        external = dict(base, zone='0137', target_like=True)
        EOS.classify_usage(external, proc)
        self.assertEqual(external['verdict'], 'EXTERNAL_OFFSET_CANDIDATE')
        data = dict(base, target_like=False)
        EOS.classify_usage(data, proc)
        self.assertEqual(data['verdict'], 'PLAIN_CONSTANT')

    def test_comment_role_makes_data_usage_target_like(self):
        self.assertTrue(EOS.is_target_like('ЗП', 'записать BR150 (переход) в М7'))
        self.assertFalse(EOS.is_target_like('ЗП', 'записать B211 (ячейка)'))
        self.assertTrue(EOS.is_target_like('ПО', ''))

    def test_summarize_verdict_priority(self):
        ext = dict(verdict='EXTERNAL_OFFSET_CANDIDATE')
        loc = dict(verdict='LOCAL_ADDR')
        self.assertEqual(EOS.summarize_verdict([loc, ext]),
                         'EXTERNAL_OFFSET_CANDIDATE')
        self.assertEqual(EOS.summarize_verdict([loc]), 'LOCAL_ADDR')
        self.assertEqual(EOS.summarize_verdict([]), 'UNKNOWN')


class PairTests(unittest.TestCase):
    def test_sequential_pair_with_small_constant(self):
        lines = [
            "* comment",
            "        И    B2113(М1)  , И с B2113",
            "        НТЖ  B2113(М1)  , поиск по B2113",
            "        ПО   44(М1)     , перейти по условию на 44",
        ]
        values = {'B2113': '113'}
        pairs = EOS.detect_pairs(lines, values, ['B2113'])
        seq = [p for p in pairs if p['kind'] == 'sequential']
        self.assertTrue(seq)
        self.assertEqual(seq[0]['other_line'], 4)
        self.assertIn('44', seq[0]['other_tokens'])
        self.assertEqual(seq[0]['other_mnem'], 'ПО')

    def test_register_pair_pv_with_loaded_small_constant(self):
        lines = [
            "        ЗП   BR150(М7)  , записать BR150 (переход) в М7",
            "        МОДА           , настроить адресацию",
            "        ПБ   BR5673(М7), перейти с возвратом BR5673 через М7",
        ]
        values = {'BR150': '150', 'BR5673': '75737'}
        pairs = EOS.detect_pairs(lines, values, ['BR150'])
        reg = [p for p in pairs if p['kind'] == 'register']
        self.assertTrue(reg)
        self.assertEqual(reg[0]['register'], 'М7')
        self.assertIn('BR150', reg[0]['load_labels'])
        self.assertEqual(reg[0]['line'], 1)
        self.assertEqual(reg[0]['other_line'], 3)

    def test_compound_expression_is_not_a_small_constant(self):
        self.assertEqual(EOS._plain_small_tokens('СДА 64+4'), [])
        self.assertEqual(EOS._plain_small_tokens('44(М1)'), ['44'])


class EndToEndTests(unittest.TestCase):
    def _mini_repo(self, d):
        (pathlib.Path(d) / 'bemsh').mkdir()
        (pathlib.Path(d) / 'docs').mkdir()
        (pathlib.Path(d) / 'bemsh' / 'MBE-Z0144.be').write_text(
            "* mini zone\n"
            "BR122 ЭКВ '122'\n"
            "B211 ЭКВ '11'\n"
            "Z0144   СТАРТ 1\n"
            "        ПО   BR122(М2)  , перейти на BR122\n"
            "        ЗП   B211       , записать B211 (ячейка)\n",
            encoding='utf-8')
        (pathlib.Path(d) / 'docs' / 'PROCEDURES-B.md').write_text(
            "0144:0122-0127  size=006  BRANCH  ОСН\n"
            "  вход: ВЕТВ×5@0144:0106\n", encoding='utf-8')

    def test_scan_end_to_end(self):
        with tempfile.TemporaryDirectory(prefix='eos-e2e-') as d:
            self._mini_repo(d)
            res = EOS.scan(d, ['BR122', 'B211'])
        by = {r['label']: r for r in res['rows']}
        self.assertEqual(by['BR122']['verdict'], 'LOCAL_ADDR')
        self.assertEqual(by['B211']['verdict'], 'PLAIN_CONSTANT')
        self.assertEqual(by['BR122']['usages'][0]['file'], 'MBE-Z0144.be')
        self.assertEqual(by['BR122']['usages'][0]['text'].strip(),
                         'ПО   BR122(М2)  , перейти на BR122')
        self.assertEqual(res['usage_verdict_counts'].get('LOCAL_ADDR'), 1)

    def test_cli_with_labels_file(self):
        with tempfile.TemporaryDirectory(prefix='eos-cli-') as d:
            self._mini_repo(d)
            labelfile = os.path.join(d, 'labels.txt')
            with open(labelfile, 'w', encoding='utf-8') as fh:
                fh.write('# only one label\nBR122\n')
            script = str(ROOT / 'tools' / 'external_offset_scan.py')
            out = subprocess.run(
                [sys.executable, script, '--root', d, '--labels', labelfile],
                capture_output=True, text=True, check=True).stdout
        self.assertIn('BR122', out)
        self.assertIn('LOCAL_ADDR', out)
        self.assertNotIn('B211 |', out)

    def test_default_label_list_matches_operator_list(self):
        # The operator said "30 labels" but enumerated 32; all are kept.
        self.assertEqual(len(EOS.DEFAULT_LABELS), 32)
        self.assertEqual(len(set(EOS.DEFAULT_LABELS)), 32)
        self.assertIn('AM10', EOS.DEFAULT_LABELS)
        self.assertIn('BR150', EOS.DEFAULT_LABELS)


if __name__ == '__main__':
    unittest.main()
