# -*- coding: utf-8 -*-
"""Тесты для tools/p2_text_xref.py (только чтение эталонных файлов)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import p2_text_xref as p2  # noqa: E402


class TestParsing(unittest.TestCase):

    def test_load_catalog_only_program2(self):
        rows = p2.load_catalog()
        self.assertGreater(len(rows), 50)
        zones = {int(r['zone'], 8) for r in rows}
        self.assertTrue(all(0o137 <= z <= 0o177 for z in zones))
        stamps = [r for r in rows if 'ВЕР .06/78' in r['text']]
        self.assertEqual(len(stamps), 1)
        self.assertEqual(stamps[0]['zone'], '0147')
        self.assertEqual(stamps[0]['first'], 0o1315)

    def test_load_enrichment_messages(self):
        rows = p2.load_enrichment()
        zones = {int(r['zone'], 8) for r in rows}
        self.assertTrue(all(0o137 <= z <= 0o177 for z in zones))
        err = [r for r in rows if 'НЕВЕРНЫЙ АДРЕС' in r['text']]
        self.assertEqual(len(err), 1)
        self.assertEqual(err[0]['zone'], '0144')
        self.assertEqual(err[0]['first'], 0o275)
        # 0176.1743-763 -- сокращённая запись конца 1763.
        hdr = [r for r in rows if r['first'] == 0o1743]
        self.assertEqual(len(hdr), 1)
        self.assertEqual(hdr[0]['last'], 0o1763)

    def test_catalog_dedup(self):
        rows = p2.catalog()
        keys = [(r['zone'], r['first']) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_file_zone(self):
        self.assertEqual(p2.file_zone('Z0144.asm'), '0144')
        self.assertEqual(p2.file_zone('MBE-Z0147-L1.asm'), '0147')
        self.assertEqual(p2.file_zone('Z0055.asm'), '0055')
        self.assertEqual(p2.file_zone('ASM-Z0055-full.asm'), '0055')

    def test_parse_sources(self):
        field = 'Z0144.asm:197:сч; MBE-Z0154-L1.asm:377:пе; xxx'
        got = p2.parse_sources(field)
        self.assertEqual(got, [('0144', '197', 'сч'),
                               ('0154', '377', 'пе')])


class TestReferences(unittest.TestCase):

    def test_candidate_targets_label_and_absolute(self):
        row = {'zone': '0154', 'first': 0o751, 'last': 0o755}
        targets = dict(p2.candidate_targets(row))
        self.assertIn('D00751', targets)
        self.assertIn('A00751', targets)
        # 02000 + 0751 = 02751
        self.assertIn('OCT:2751', targets)
        self.assertEqual(targets['OCT:2751'], 'absolute')

    def test_find_refs_label_same_zone(self):
        row = {'zone': '0154', 'first': 0o751, 'last': 0o751}
        xref = {
            'D00751': [{
                'zones': {'0154', '0554'},
                'label': 'CODE_DATA[ГИПОТЕЗА]',
                'count': 2,
                'sources': 'Z0154.asm:377:пе; Z0554.asm:377:пе',
            }],
        }
        refs = p2.find_refs(row, xref)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['zone'], '0154')
        self.assertEqual(refs[0]['mnem'], 'пе')
        self.assertEqual(refs[0]['target'], 'D00751')

    def test_find_refs_absolute_is_candidate(self):
        row = {'zone': '0154', 'first': 0o1050, 'last': 0o1050}
        xref = {
            'OCT:3050': [{
                'zones': {'0154'},
                'label': 'MEM_3050_UNKNOWN[ГИПОТЕЗА]',
                'count': 5,
                'sources': 'Z0165.asm:1045:по; Z0154.asm:1060:зп',
            }],
        }
        refs = p2.find_refs(row, xref)
        self.assertTrue(refs)
        self.assertTrue(all(r['kind'] == 'absolute' for r in refs))
        self.assertTrue(all(r['confidence'] == 'низкий' for r in refs))

    def test_find_refs_empty(self):
        row = {'zone': '0137', 'first': 0o1501, 'last': 0o1501}
        refs = p2.find_refs(row, {})
        self.assertEqual(refs, [])


class TestIntegration(unittest.TestCase):

    def test_build_shape(self):
        rows = p2.build()
        self.assertGreater(len(rows), 60)
        required = {'addr', 'enc', 'text', 'meaning', 'role',
                    'ref_count', 'refs', 'catalog_conf'}
        for r in rows:
            self.assertTrue(required.issubset(r))
            self.assertIsInstance(r['refs'], list)

    def test_format_table_headers(self):
        rows = p2.build()[:3]
        table = p2.format_table(rows)
        head = table.splitlines()[0]
        for col in ('адрес текста', 'кодировка', 'расшифровка', 'смысл',
                    'ссылок', 'источники', 'уверенность'):
            self.assertIn(col, head)
        for line in table.splitlines()[2:]:
            self.assertEqual(line.count('|'), 6)

    def test_cli_out(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'table.md')
            rc = p2.main(['--out', out, '--min-refs', '1'])
            self.assertEqual(rc, 0)
            with open(out, encoding='utf-8') as fh:
                text = fh.read()
            self.assertIn('адрес текста', text)


if __name__ == '__main__':
    unittest.main()
