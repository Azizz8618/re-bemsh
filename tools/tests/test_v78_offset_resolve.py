#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for tools/v78_offset_resolve.py.

Synthetic cases cover radix rules, every address form,
scope classification, label matching and the CLI.
Two integration tests use the real MBE-Z0137.be and a
synthetic label index; they skip when the source is absent.
No input file is ever modified.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v78_offset_resolve as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parents[1]
TOOL = TOOLS / 'v78_offset_resolve.py'
REAL_BE = ROOT / 'bemsh' / 'MBE-Z0137.be'
BASE_MAP = ROOT / 'analysis' / 'ZONE-BASE-MAP.md'
SCRATCH = Path('/var/tmp/v78-offsets/resolve')

BASES = {
    '0137': (None, 'Н'),
    '0147': (0o00000, 'Ф'),
    '0154': (0o02000, 'Ф'),
    '0155': (0o04000, 'Ф'),
    '0157': (0o76000, 'Ф'),
    '0547': (None, 'Н'),
}

IDX_DATA = {'labels': [
    {'name': 'SUB_I_1036', 'zone': '0137',
     'address': '1036',
     'status': 'ГИПОТЕЗА'},
    {'name': 'INIT_ZERO', 'zone': '0137', 'absolute': '3',
     'status': 'ПОДТВЕРЖДЕНО'},
    {'name': 'SUB_E_76267', 'zone': '0157',
     'absolute': '76267', 'status': 'ФАКТ'},
    {'name': 'Z0155.Z0155A', 'zone': '0155',
     'address': '355', 'status': 'ГИПОТЕЗА'},
]}


def expr(operand):
    """Extract expressions, dropping the position field."""
    rows = m.extract_expressions(operand)
    return [row[1:] for row in rows]


class ScratchMixin:
    """Scratch: task folder when writable."""

    def make_dir(self):
        for base in (str(SCRATCH), None):
            try:
                if base:
                    os.makedirs(base, exist_ok=True)
                holder = tempfile.TemporaryDirectory(
                    prefix='offres-', dir=base)
            except OSError:
                continue
            self.addCleanup(holder.cleanup)
            return holder.name
        self.fail('no writable scratch directory')

    def write(self, name, text):
        path = os.path.join(self.make_dir(), name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        return path


class TestRadix(ScratchMixin, unittest.TestCase):
    """Radix rules proven in OPERAND-CATALOG.md §4."""

    def test_01_bare_is_decimal(self):
        self.assertEqual(expr('64'),
                         [('64', 64, 'decimal', 64)])

    def test_02_quoted_is_octal(self):
        self.assertEqual(expr("'76267'"),
                         [("'76267'", 0o76267, 'octal',
                           0o76267)])

    def test_03_cell_plus_decimal(self):
        row = expr('D00100+40')[0]
        self.assertEqual(row[0], 'D00100')
        self.assertEqual(row[1], 40)
        self.assertEqual(row[3], 0o150)

    def test_04_cell_overlay_subtraction(self):
        row = expr('D00003-З')[0]
        self.assertEqual(row[0], 'D00003-З')
        self.assertEqual(row[3], 3)

    def test_05_overlay_with_offset(self):
        row = expr('A01036-З+10(М2)')[0]
        self.assertEqual(row[0], 'A01036-З')
        self.assertEqual(row[1], 10)
        self.assertEqual(row[3], 0o1036 + 10)

    def test_06_quoted_plus_decimal(self):
        row = expr("'103'+48-↑N")[0]
        self.assertEqual(row[1], 48)
        self.assertEqual(row[3], 0o103 + 48)
        self.assertEqual(row[3], 0o163)

    def test_07_external_label_octal(self):
        row = expr('X76267(М7)')[0]
        self.assertEqual(row[0], 'X76267')
        self.assertEqual(row[2], 'octal')
        self.assertEqual(row[3], 0o76267)

    def test_08_bare_arithmetic(self):
        self.assertEqual(expr('64-6')[0][3], 58)
        self.assertEqual(expr('64+16')[0][3], 80)

    def test_09_negative_offset_not_address(self):
        self.assertEqual(expr('-1(М17)')[0][3], None)

    def test_10_page_formula(self):
        row = expr('37*02000+1234')[0]
        self.assertEqual(row[0], 'page37')
        self.assertEqual(row[3], 0o37 * 0o2000 + 1234)

    def test_11_page_formula_unicode(self):
        row = expr('37×02000+1234')[0]
        self.assertEqual(row[3], 0o37 * 0o2000 + 1234)

    def test_12_long_word_not_address(self):
        self.assertEqual(expr("'02000000'")[0][3], None)

    def test_13_register_stripped(self):
        names = [row[0] for row in expr('D00100+40(М7)')]
        self.assertEqual(names, ['D00100'])

    def test_14_all_cell_prefixes(self):
        for prefix in 'DAGI':
            rows = expr(prefix + '00100')
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][3], 0o100)


class TestParsing(unittest.TestCase):
    """Line splitting and index/base-map loaders."""

    def test_15_split_label_column(self):
        fields = m.split_fields(
            'D00001  ЗП  D00003-З , комментарий')
        self.assertEqual(fields, ('ЗП', 'D00003-З'))

    def test_16_split_comment_preserves_register(self):
        fields = m.split_fields('ПБ (М1,1) , переход')
        self.assertEqual(fields[1], '(М1,1)')

    def test_17_star_line_ignored(self):
        self.assertIsNone(m.split_fields('* комментарий'))

    def test_18_asm_line(self):
        fields = m.split_asm_fields(
            '  265 07 012 0150 \tнтж D00100+40(М7)')
        self.assertEqual(fields[0], 'нтж')
        self.assertEqual(fields[1], 'D00100+40(М7)')

    def test_19_base_map_parse(self):
        bases = m.parse_base_map(str(BASE_MAP))
        self.assertEqual(bases['0154'][0], 0o2000)
        self.assertIsNone(bases['0137'][0])
        self.assertEqual(bases['0157'][1], 'Ф')

    def test_20_index_list_form(self):
        idx = m.load_label_index(None)
        with tempfile.NamedTemporaryFile(
                'w', suffix='.json', delete=False) as fh:
            json.dump(IDX_DATA['labels'], fh)
            path = fh.name
        self.addCleanup(os.unlink, path)
        idx = m.load_label_index(path)
        self.assertIn(0o76267, idx['by_absolute'])
        self.assertIn('Z0155.Z0155A', idx['by_name'])

    def test_21_index_zone_keyed_form(self):
        data = {'0137': [{'name': 'L', 'address': '10'}]}
        with tempfile.NamedTemporaryFile(
                'w', suffix='.json', delete=False) as fh:
            json.dump(data, fh)
            path = fh.name
        self.addCleanup(os.unlink, path)
        idx = m.load_label_index(path)
        self.assertEqual(idx['entries'][0]['zone'], '0137')
        self.assertIn(('0137', 8), idx['by_zone_addr'])

    def test_22_index_base_restore(self):
        data = {'labels': [{'name': 'M', 'zone': '0154',
                            'address': '10'}]}
        with tempfile.NamedTemporaryFile(
                'w', suffix='.json', delete=False) as fh:
            json.dump(data, fh)
            path = fh.name
        self.addCleanup(os.unlink, path)
        idx = m.load_label_index(path, BASES)
        self.assertEqual(
            idx['by_absolute'][0o2010][0]['name'], 'M')

    def test_23_short_status(self):
        self.assertEqual(m.short_status('ФАКТ'), 'Ф')
        self.assertEqual(m.short_status('ГИПОТЕЗА'), 'Г')
        self.assertEqual(m.short_status('НЕ ИЗВЕСТНО'), 'Н')
        self.assertEqual(
            m.short_status('ПОДТВЕРЖДЕНО'), 'Ф')

    def test_23b_parallel_index_schema(self):
        row = {'label': 'D00022', 'zone': '0154',
               'base': '02000', 'offset': '00022',
               'absolute': '02022', 'kind': 'data',
               'file': 'bemsh/MBE-Z0154.be', 'line': 10}
        with tempfile.NamedTemporaryFile(
                'w', suffix='.json', delete=False) as fh:
            json.dump([row], fh)
            path = fh.name
        self.addCleanup(os.unlink, path)
        idx = m.load_label_index(path)
        self.assertEqual(idx['by_name']['D00022'][0][
            'absolute'], 0o2022)
        self.assertIn(0o2022, idx['by_absolute'])


class TestScope(ScratchMixin, unittest.TestCase):
    """Scope classification and label matching."""

    def setUp(self):
        path = self.write('idx.json', json.dumps(IDX_DATA))
        self.idx = m.load_label_index(path, BASES)

    def record(self, operand, zone='0137', mnem='ЗП'):
        return m.scan_text(
            '        %s %s , тест\n' % (mnem, operand),
            'MBE-Z%s.be' % zone, zone, BASES,
            self.idx)[0]

    def test_24_scope_local(self):
        rec = self.record('D00003-З')
        self.assertEqual(rec['scope'], 'local')
        self.assertEqual(rec['target_label'], 'INIT_ZERO')

    def test_25_scope_interzone(self):
        rec = self.record('X76267')
        self.assertEqual(rec['scope'], 'interzone')
        self.assertEqual(rec['target_zone'], '0157')
        self.assertEqual(rec['target_label'], 'SUB_E_76267')

    def test_26_scope_external(self):
        rec = self.record("'50000'")
        self.assertEqual(rec['scope'], 'external')
        self.assertIsNone(rec['target_label'])
        self.assertEqual(rec['status'], 'Н')

    def test_27_scope_by_base_window(self):
        rec = self.record("'2040'")
        self.assertEqual(rec['target_zone'], '0154')
        self.assertEqual(rec['scope'], 'interzone')

    def test_28_label_by_zone_offset(self):
        rec = self.record('ПВ A01036-З(М16)', mnem='ПВ')
        self.assertEqual(rec['target_label'], 'SUB_I_1036')
        self.assertEqual(rec['scope'], 'local')

    def test_29_name_adopts_absolute(self):
        rec = self.record('Z0155.Z0155A', mnem='ВНЕШН')
        self.assertEqual(
            rec['target_label'], 'Z0155.Z0155A')
        self.assertIsNotNone(rec['absolute'])
        self.assertEqual(rec['scope'], 'interzone')

    def test_30_schema_exact(self):
        rec = self.record('64')
        self.assertEqual(set(rec), {
            'file', 'line', 'mnemonic', 'operand_raw',
            'base_symbol', 'offset_value', 'offset_radix',
            'absolute', 'target_label', 'scope',
            'target_zone', 'status'})

    def test_31_no_target_label_without_absolute(self):
        rec = self.record('Z9999.NOPE', mnem='ВНЕШН')
        self.assertIsNone(rec['target_label'])
        self.assertIsNone(rec['absolute'])

    def test_32_b2_zone_is_interzone(self):
        bases = dict(BASES)
        bases['0547'] = (0o60000, 'Н')
        idx = m.load_label_index(None)
        rec = m.scan_text(
            "        ЗП '60123' , тест\n", 'MBE-Z0137.be',
            '0137', bases, idx)[0]
        self.assertEqual(rec['scope'], 'interzone')
        self.assertEqual(rec['target_zone'], '0547')

    def test_33_check_detects_bad_range(self):
        rec = self.record('64')
        rec['absolute'] = m.MAX_ADDR + 1
        result = {'records': [rec], 'resolved': 1}
        checked = m.check(result)
        self.assertFalse(checked['ok'])
        self.assertIn(
            'absolute_range',
            [v['invariant'] for v in checked['violations']])

    def test_34_check_min_resolved(self):
        result = {'records': [], 'resolved': 999}
        checked = m.check(result)
        self.assertEqual(
            checked['violations'][0]['invariant'],
            'min_resolved')

    def test_35_check_label_without_absolute(self):
        rec = self.record('64')
        rec['target_label'] = 'X'
        rec['absolute'] = None
        checked = m.check({'records': [rec], 'resolved': 0})
        names = [v['invariant']
                 for v in checked['violations']]
        self.assertIn('label_without_absolute', names)


class TestCLI(ScratchMixin, unittest.TestCase):
    """CLI flags, exit codes, determinism, read-only."""

    def run_tool(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOL)] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)

    def test_36_help(self):
        proc = self.run_tool('--help')
        self.assertEqual(proc.returncode, 0)
        self.assertIn('--labels', proc.stdout)
        self.assertIn('--scope', proc.stdout)

    def test_37_json_output(self):
        src = self.write(
            't.be', "Z0137 СТАРТ '10000'\n"
                    "        ЗП D00100+40 , тест\n")
        proc = self.run_tool(src, '--format', 'json')
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(len(data['records']), 2)
        self.assertEqual(
            data['records'][1]['absolute'], 0o150)

    def test_38_text_summary(self):
        src = self.write('t.be', "        ЗП 64 , тест\n")
        proc = self.run_tool(src, '--summary')
        self.assertEqual(proc.returncode, 0)
        self.assertIn('СВОДКА ПО ОБЛАСТИ', proc.stdout)
        self.assertIn('СВОДКА ПО СТАТУСУ', proc.stdout)

    def test_39_scope_filter(self):
        src = self.write(
            't.be', "        ЗП '50000' , тест\n")
        proc = self.run_tool(
            src, '--scope', 'external', '--format', 'json')
        data = json.loads(proc.stdout)
        self.assertTrue(data['records'])
        self.assertEqual(
            {r['scope'] for r in data['records']},
            {'external'})

    def test_40_check_exit_zero(self):
        proc = self.run_tool(
            '--check', '--format', 'json',
            '--root', str(ROOT))
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertTrue(data['check']['ok'])

    def test_41_check_exit_one(self):
        src = self.write('t.be', "        ЗП 64 , тест\n")
        proc = self.run_tool(src, '--check')
        self.assertEqual(proc.returncode, 1)
        self.assertIn('CHECK FAIL', proc.stdout)

    def test_42_missing_file_exit_two(self):
        proc = self.run_tool('/нет/такого/файла.be')
        self.assertEqual(proc.returncode, 2)
        self.assertIn('error:', proc.stderr)

    def test_43_determinism(self):
        a = self.run_tool('--format', 'json')
        b = self.run_tool('--format', 'json')
        self.assertEqual(a.stdout, b.stdout)

    def test_44_no_input_writes(self):
        src = self.write('t.be', "        ЗП 64 , тест\n")
        before = os.stat(src).st_mtime_ns
        size = os.stat(src).st_size
        self.run_tool(src, '--check', '--summary')
        self.assertEqual(os.stat(src).st_mtime_ns, before)
        self.assertEqual(os.stat(src).st_size, size)


class TestIntegration(ScratchMixin, unittest.TestCase):
    """Real corpus with a synthetic label index."""

    @classmethod
    def setUpClass(cls):
        if not REAL_BE.is_file():
            raise unittest.SkipTest('MBE-Z0137.be absent')

    def idx_file(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        path = SCRATCH / 'test-labels.json'
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(IDX_DATA, handle, ensure_ascii=False)
        self.addCleanup(path.unlink, missing_ok=True)
        return str(path)

    def test_45_real_z0137_with_labels(self):
        proc = subprocess.run(
            [sys.executable, str(TOOL), str(REAL_BE),
             '--labels', self.idx_file(),
             '--format', 'json'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertGreater(len(data['records']), 1000)
        local = [r for r in data['records']
                 if r['scope'] == 'local']
        self.assertTrue(local)
        sub = [r for r in local
               if r['target_label'] == 'INIT_ZERO']
        self.assertTrue(sub)
        self.assertEqual(sub[0]['absolute'], 3)
        inter = [r for r in data['records']
                 if r['target_label'] == 'SUB_E_76267']
        self.assertTrue(inter)
        self.assertEqual(inter[0]['target_zone'], '0157')

    def test_46_full_corpus_check(self):
        proc = subprocess.run(
            [sys.executable, str(TOOL), '--check',
             '--format', 'json', '--root', str(ROOT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertGreaterEqual(data['resolved'], 1000)
        self.assertTrue(data['check']['ok'])
        scopes = data['scope_counts']
        self.assertEqual(
            sum(scopes.values()), data['records_total'])
        self.assertEqual(
            set(scopes), {'local', 'interzone', 'external'})


if __name__ == '__main__':
    unittest.main()
