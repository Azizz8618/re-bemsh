#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты tools/module_call_graph.py.

Запуск: python3 -m unittest tools/tests/test_module_call_graph.py -v

Логика проверяется на синтетических листингах. Интеграционные
тесты читают реальные dis/*.asm только для трёх известных фактов.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import module_call_graph as mcg  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TOOL = Path(__file__).resolve().parents[1] / 'module_call_graph.py'

# Синтетический листинг в стиле disbesm6 (TAB-поля, 5-й полей адрес).
LISTING = (
    '          File: gold/MBE-Z0147-L1.bin\n'
    '    0 00 000 0000 \tSTART\tпв\tA00477(М15)\n'
    '      00 000 0000 \t\tпв\t\'7417\'\n'
    '    1 00 000 0000 \t\tпв\t(М16)\n'
    '    2 00 000 0000 \t\tпб\t(М15)\n'
    '    3 00 000 0000 \t\tпб\t\'2757\'\n'
    '    4 00 000 0000 \t\tэ70\tD00643\n'
)

BASES = {
    '0147': {'base': 0, 'candidate': False, 'status': 'ФАКТ'},
    '0156': {'base': 0o6000, 'candidate': False, 'status': 'ФАКТ'},
}


class TestSyntheticParsing(unittest.TestCase):

    def test_call_and_link_records(self):
        recs = mcg.parse_listing(LISTING, '0147', 'unit.asm', BASES)
        kinds = [r['kind'] for r in recs]
        self.assertEqual(
            kinds,
            ['internal', 'external', 'indirect', 'indirect',
             'branch', 'internal'])
        self.assertEqual(recs[0]['target'], 'A00477')
        self.assertEqual(recs[0]['target_zone'], '0147')
        self.assertEqual(recs[1]['target_zone'], '0156')
        self.assertEqual(recs[-1]['evidence'], 'unit.asm:7')

    def test_label_is_always_local(self):
        r = mcg.classify('пв', 'A01322(М16)', '0145', BASES)
        self.assertEqual(r['kind'], 'internal')
        self.assertEqual(r['target_zone'], '0145')
        self.assertEqual(r['addr'], 0o1322)

    def test_literal_uses_base_window(self):
        r = mcg.classify('пв', "'7417'", '0147', BASES)
        self.assertEqual(r['kind'], 'external')
        self.assertEqual(r['target_zone'], '0156')
        self.assertEqual(r['addr'], 0o7417)

    def test_small_literal_unknown_without_base(self):
        r = mcg.classify('пв', "'477'", '0145', BASES)
        self.assertEqual(r['kind'], 'unknown')
        self.assertEqual(r['note'], 'SMALL_LITERAL_BASE_UNKNOWN')

    def test_indirect_link_call(self):
        r = mcg.classify('пв', '(М16)', '0162', BASES)
        self.assertEqual(r['kind'], 'indirect')
        self.assertEqual(r['note'], 'LINK_CALL')

    def test_unparsed_operand(self):
        r = mcg.classify('пв', 'PRINT8', '0147', BASES)
        self.assertEqual(r['kind'], 'unknown')
        self.assertEqual(r['note'], 'UNPARSED_OPERAND')


class TestCatalogAndBaseMap(unittest.TestCase):

    def test_catalog_has_69_zones(self):
        cat = mcg.zone_catalog()
        self.assertEqual(len(cat), 69)
        self.assertEqual(len({z for z, _g, _f in cat}), 69)
        groups = {}
        for z, g, _f in cat:
            groups[g] = groups.get(g, 0) + 1
        self.assertEqual(groups, {'ASM': 4, 'B': 33, 'B2': 32})
        self.assertEqual(cat[0][0], '0055')
        self.assertEqual(cat[-1][0], '0577')

    def test_read_base_map_synthetic(self):
        text = (
            ' 0055,-,НЕ ИЗВЕСТНО\n'
            ' 0147,00000,ФАКТ\n'
            ' 0174,72000?,ГИПОТЕЗА\n'
        )
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'ZONE-BASE-MAP.md')
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write(text)
            bm = mcg.read_base_map(p)
        self.assertEqual(bm['0055']['base'], None)
        self.assertEqual(bm['0147']['base'], 0)
        self.assertEqual(bm['0174']['base'], 0o72000)
        self.assertTrue(bm['0174']['candidate'])

    def test_zones_for_addr_overlap(self):
        self.assertEqual(
            mcg.zones_for_addr(0o2751, BASES | {
                '0154': {'base': 0o2000, 'candidate': False,
                         'status': 'ФАКТ'}}),
            ['0154'])


class TestCountingAndRendering(unittest.TestCase):

    def test_call_count_respects_as_data_marker(self):
        text = (
            '* next insn used as data\n'
            '    0 00 000 0000 \t\tпв\tA00001\n'
            '    1 00 000 0000 \t\tпв\tA00002\n'
        )
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, 'X.asm'), 'w',
                      encoding='utf-8') as fh:
                fh.write(text)
            files, total, raw = mcg.count_all_asm_calls(d)
        self.assertEqual(files, 1)
        self.assertEqual(total, 1)
        self.assertEqual(raw, 2)

    def test_render_text_is_narrow(self):
        graph = {
            'meta': {
                'zones_total': 69, 'asm_files_all': 75,
                'xref_stale': {'files': 71, 'calls': 123},
                'call_lines_all_asm': 344, 'call_lines_raw': 348,
                'call_lines_forced': 3696,
            },
            'zones': {'0147': {
                'group': 'B', 'base': 0, 'base_status': 'ФАКТ',
                'candidate': False,
                'counts': {'internal': 2, 'external': 0,
                           'indirect': 1, 'unknown': 0},
            }},
            'adjacency': [{'caller': '0147', 'target': '0147',
                           'kind': 'internal', 'count': 2,
                           'evidence': ['x.asm:1']}],
            'top_procedures': [],
        }
        out = mcg.render_text(graph, '0147')
        self.assertTrue(all(len(line) <= 60 for line in out.splitlines()))
        self.assertNotIn('^', out)
        self.assertIn('ФАКТ', out)


class TestRealDisassembly(unittest.TestCase):
    """Три независимых факта из реальных dis/*.asm."""

    @classmethod
    def setUpClass(cls):
        cls.graph = mcg.build()

    def test_zone_0147_calls_00477_at_least_ten_times(self):
        z = self.graph['zones']['0147']
        hits = [t for t in z['targets'] if t['target'] == 'A00477']
        self.assertEqual(len(hits), 1)
        self.assertGreaterEqual(hits[0]['count'], 10)
        self.assertTrue(all(e.startswith('dis/MBE-Z0147-L1.asm:')
                            for e in hits[0]['evidence']))

    def test_zone_0154_has_branch_to_2757(self):
        hits = [b for b in self.graph['zones']['0154']['branches']
                if b['target'] == "'2757'"]
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]['evidence'], 'dis/MBE-Z0154-L1.asm:9')

    def test_asm_zone_0055_cli_exit_zero(self):
        self.assertTrue(
            (ROOT / 'dis' / 'ASM-Z0055-L1.asm').is_file())
        proc = subprocess.run(
            [sys.executable, str(TOOL), '--format', 'json',
             '--zone', '0055'],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(list(data['zones']), ['0055'])
        self.assertEqual(data['meta']['zones_total'], 69)


if __name__ == '__main__':
    unittest.main()
