#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for tools/v78_operand_probe.py.

Synthetic fixtures cover each form and each CLI flag.
Two integration tests use real files and skip if absent.
No input file is ever modified.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v78_operand_probe as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parents[1]
TOOL = TOOLS / 'v78_operand_probe.py'
REAL_BE = ROOT / 'bemsh' / 'MBE-Z0137.be'
REAL_CATALOG = Path(
    '/home/azizz/Yandex.Disk/re-dispak/macros.be')

GOOD = """\
Z0137   СТАРТ '10000'
X4231X ВНЕШН Z0155.Z0155A
AM10 ЭКВ '10'
        СЧМР 64         , счётчик
        ЗП   D00100+40   , ячейка
        ПБ   (М3)        , возврат
        ЦИКЛ -1(М17)     , повтор
D00024  КОНД В'7600000000000000' , слово
        УИА  MB6263(М7)  , индекс
        М
"""


def parts(operand, mnemonic='ЭКВ'):
    """Classify one operand string for direct tests."""
    reg, core = m.split_register(operand)
    form = m.classify(core, reg, mnemonic)
    return form, m.value_of(form, core), reg, core


class TempMixin:
    """Temp dir that works if the temp fs is full."""

    def make_temp_dir(self):
        bases = (None, str(ROOT))
        for base in bases:
            try:
                holder = tempfile.TemporaryDirectory(
                    prefix='opprobe-', dir=base)
            except OSError:
                continue
            self.addCleanup(holder.cleanup)
            return holder.name
        self.fail('no writable temp directory')

    def write_fixture(self, name, text):
        path = os.path.join(self.make_temp_dir(), name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        return path


class TestForms(TempMixin, unittest.TestCase):
    def test_bare_decimal(self):
        form, value, _, _ = parts('64', 'СЧМР')
        self.assertEqual(form, 'bare_number')
        self.assertEqual(value['radix'], 'decimal')
        self.assertEqual(value['decimal'], 64)
        self.assertEqual(value['octal'], '100')

    def test_negative_bare(self):
        form, value, _, _ = parts('-1', 'ЦИКЛ')
        self.assertEqual(form, 'bare_number')
        self.assertEqual(value['decimal'], -1)

    def test_quoted_octal(self):
        form, value, _, _ = parts("'1173'")
        self.assertEqual(form, 'quoted_number')
        self.assertEqual(value['radix'], 'octal')
        self.assertEqual(value['decimal'], 0o1173)

    def test_quoted_non_octal_rejected(self):
        form, _, _, _ = parts("'128'")
        self.assertNotEqual(form, 'quoted_number')

    def test_cell_ref_minus_base(self):
        form, value, _, core = parts('D00003-З', 'ЗП')
        self.assertEqual(form, 'cell_ref')
        self.assertTrue(value['minus_overlay_base'])
        self.assertEqual(
            m.symbol_of(form, core), 'D00003')

    def test_cell_offset_octal_result(self):
        form, value, _, _ = parts('D00100+40', 'ЗП')
        self.assertEqual(form, 'cell_ref')
        self.assertEqual(value['base_decimal'], 0o100)
        self.assertEqual(value['offset_decimal'], 40)
        self.assertEqual(value['decimal'], 0o150)
        self.assertEqual(value['octal'], '00150')

    def test_cell_negative_offset(self):
        form, value, _, _ = parts('D00656-З-30', 'ЗП')
        self.assertEqual(form, 'cell_ref')
        self.assertEqual(value['base_decimal'], 0o656)
        self.assertEqual(value['decimal'], 0o656 - 30)

    def test_register_m(self):
        form, _, reg, _ = parts('(М4)', 'ЗП')
        self.assertEqual(form, 'register')
        self.assertEqual(reg, 'М4')

    def test_register_number(self):
        form, _, reg, _ = parts('(13)', 'ПВ')
        self.assertEqual(form, 'register')
        self.assertEqual(reg, '13')

    def test_register_latin_m_normalized(self):
        form, _, reg, _ = parts('(M16)', 'УИА')
        self.assertEqual(form, 'register')
        self.assertEqual(reg, 'М16')

    def test_string_prefixes(self):
        for prefix in m.STRING_PREFIXES:
            with self.subTest(prefix=prefix):
                form, value, _, _ = parts(
                    prefix + "'123'")
                self.assertEqual(form, 'string_constant')
                self.assertEqual(value['radix'], 'octal')
                self.assertEqual(value['decimal'], 0o123)

    def test_string_text_content(self):
        form, value, _, _ = parts("П'ШИФР  4199'")
        self.assertEqual(form, 'string_constant')
        self.assertEqual(value['radix'], 'text')
        self.assertIn('ШИФР', value['text'])

    def test_bad_string_prefix(self):
        form, _, _, _ = parts("Г'123'")
        self.assertNotEqual(form, 'string_constant')

    def test_equiv_macro_expression(self):
        form, value, _, _ = parts("'103'+48-∧N")
        self.assertEqual(form, 'equiv_expr')
        self.assertEqual(value['radix'], 'octal')
        self.assertEqual(value['decimal'], 0o103 + 48)
        self.assertEqual(value['octal'], '163')
        self.assertEqual(value['symbols'], ['∧N'])

    def test_decimal_arithmetic_expression(self):
        form, value, _, _ = parts('64-5', 'СДА')
        self.assertEqual(form, 'equiv_expr')
        self.assertEqual(value['radix'], 'decimal')
        self.assertEqual(value['decimal'], 59)

    def test_macro_param(self):
        form, value, _, _ = parts('∧А')
        self.assertEqual(form, 'macro_param')
        self.assertEqual(value['radix'], 'symbolic')

    def test_macro_param_range(self):
        form, _, _, _ = parts('∧М..∧А(N’∧А)')
        self.assertEqual(form, 'macro_param')

    def test_external_form(self):
        fields = m.split_fields(
            'X4231X ВНЕШН Z0155.Z0155A')
        self.assertEqual(fields[0], 'ВНЕШН')
        form = m.classify(fields[1], None, 'ВНЕШН')
        self.assertEqual(form, 'external')
        self.assertEqual(
            m.symbol_of(form, fields[1]), 'Z0155.Z0155A')

    def test_label_with_dot(self):
        form, _, _, _ = parts('Z0155.Z0155A')
        self.assertEqual(form, 'label')

    def test_mnemonic_as_operand(self):
        form, _, _, _ = parts('КО', 'ПВ')
        self.assertEqual(form, 'mnemonic_operand')

    def test_register_pairs(self):
        form, _, _, _ = parts('(М1,1),(М2,2)')
        self.assertEqual(form, 'register_pair')

    def test_no_operand(self):
        self.assertEqual(
            m.split_fields('        Е'), ('Е', ''))
        form, _, _, _ = parts('')
        self.assertEqual(form, 'none')

    def test_malformed_operand(self):
        form, _, _, _ = parts('$$$')
        self.assertEqual(form, 'unknown')

    def test_comment_without_space(self):
        fields = m.split_fields(
            "X35340 ЭКВ '35340' ,стр.16 CALL-OUT")
        self.assertEqual(fields[1], "'35340'")

    def test_macro_comma_list(self):
        fields = m.split_fields('∧М ВНЕШ ∧А,∧Б')
        self.assertEqual(fields[0], 'ВНЕШ')
        self.assertEqual(fields[1], '∧А,∧Б')

    def test_inline_note_dropped(self):
        fields = m.split_fields(
            '∧В SЕТА 0     ДЛЯ ТРУБКА.ТАШКЕНТ')
        self.assertEqual(fields[1], '0')

    def test_bom_stripped(self):
        records, count = m.scan_text(
            '\ufeff        ЗП 64', 'x.be')
        self.assertEqual(count, 1)
        self.assertEqual(records[0]['operand'], '64')

    def test_output_classes(self):
        cases = (
            ('ЗП', 'code_word'),
            ('КОНД', 'data_word'),
            ('ЭКВ', 'directive_no_word'),
            ('МАСRО', 'macro_time'),
            ('NOP', 'unknown'),
        )
        for mnem, expected in cases:
            with self.subTest(mnem=mnem):
                self.assertEqual(
                    m.output_class(mnem), expected)


class TestCLI(TempMixin, unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOL)] + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, encoding='utf-8')

    def test_json_structure(self):
        path = self.write_fixture('good.be', GOOD)
        done = self.run_cli(path, '--format', 'json')
        self.assertEqual(done.returncode, 0)
        data = json.loads(done.stdout)
        for key in ('sources', 'records', 'form_counts',
                    'class_counts', 'unclassified'):
            self.assertIn(key, data)
        self.assertTrue(data['records'])

    def test_text_header(self):
        path = self.write_fixture('good.be', GOOD)
        done = self.run_cli(path)
        self.assertEqual(done.returncode, 0)
        self.assertIn('V78 OPERAND PROBE', done.stdout)

    def test_summary_flag(self):
        path = self.write_fixture('good.be', GOOD)
        done = self.run_cli(path, '--summary')
        self.assertIn('СВОДКА ПО ФОРМАМ', done.stdout)
        self.assertIn('cell_ref', done.stdout)

    def test_form_filter(self):
        path = self.write_fixture('good.be', GOOD)
        done = self.run_cli(
            path, '--format', 'json', '--form', 'cell_ref')
        data = json.loads(done.stdout)
        self.assertTrue(data['records'])
        self.assertTrue(all(
            r['form'] == 'cell_ref'
            for r in data['records']))
        self.assertEqual(data['filter'], 'cell_ref')

    def test_check_ok(self):
        path = self.write_fixture('good.be', GOOD)
        done = self.run_cli(path, '--check')
        self.assertEqual(done.returncode, 0)
        self.assertIn('CHECK OK', done.stdout)

    def test_check_violation(self):
        path = self.write_fixture(
            'bad.be', '        СЧ $$$ , плохо\n')
        done = self.run_cli(path, '--check')
        self.assertEqual(done.returncode, 1)
        data = json.loads(self.run_cli(
            path, '--check', '--format', 'json'
        ).stdout)
        self.assertFalse(data['check']['ok'])
        names = [v['invariant']
                 for v in data['check']['violations']]
        self.assertIn('no_unclassified', names)

    def test_help(self):
        done = self.run_cli('--help')
        self.assertEqual(done.returncode, 0)
        self.assertIn('usage:', done.stdout)

    def test_missing_file(self):
        done = self.run_cli('/no/such/file.be')
        self.assertEqual(done.returncode, 2)

    def test_no_input(self):
        done = self.run_cli('--format', 'json')
        self.assertEqual(done.returncode, 2)

    def test_catalog_flag(self):
        path = self.write_fixture('good.be', GOOD)
        done = self.run_cli(
            path, '--catalog', path, '--format', 'json')
        data = json.loads(done.stdout)
        self.assertEqual(len(data['sources']), 2)
        self.assertEqual(data['catalog'], path)

    def test_read_only(self):
        path = self.write_fixture('good.be', GOOD)
        before = os.stat(path).st_mtime_ns
        digest_before = Path(path).read_bytes()
        self.run_cli(path, '--check', '--format', 'json')
        self.assertEqual(
            os.stat(path).st_mtime_ns, before)
        self.assertEqual(
            Path(path).read_bytes(), digest_before)

    def test_deterministic(self):
        path = self.write_fixture('good.be', GOOD)
        a = self.run_cli(path, '--format', 'json').stdout
        b = self.run_cli(path, '--format', 'json').stdout
        self.assertEqual(a, b)


@unittest.skipUnless(REAL_BE.exists(), 'no real zone file')
class TestIntegrationZone(unittest.TestCase):
    def test_real_zone(self):
        result = m.probe([str(REAL_BE)])
        self.assertGreater(result['lines_total'], 2000)
        self.assertGreater(
            result['form_counts'].get('cell_ref', 0), 30)
        self.assertEqual(result['unclassified'], 0)
        checked = m.check(result)
        self.assertTrue(checked['ok'])

    def test_real_offset_arithmetic(self):
        result = m.probe([str(REAL_BE)])
        offsets = [
            r for r in result['records']
            if r['form'] == 'cell_ref'
            and r['value']['offset_decimal'] > 0
        ]
        self.assertTrue(offsets)
        for rec in offsets:
            value = rec['value']
            self.assertEqual(
                value['decimal'],
                value['base_decimal']
                + value['offset_decimal'])


@unittest.skipUnless(
    REAL_CATALOG.exists(), 'no real catalog')
class TestIntegrationCatalog(unittest.TestCase):
    def test_real_catalog(self):
        result = m.probe([], catalog=str(REAL_CATALOG))
        self.assertGreater(
            result['form_counts'].get('macro_param', 0), 10)
        pairs = result['form_counts'].get(
            'register_pair', 0)
        self.assertGreaterEqual(pairs, 4)
        self.assertEqual(result['unclassified'], 0)
        self.assertTrue(m.check(result)['ok'])

    def test_macro_equiv_expression(self):
        result = m.probe([], catalog=str(REAL_CATALOG))
        exprs = [
            r for r in result['records']
            if r['form'] == 'equiv_expr'
            and '48' in r['operand']
        ]
        self.assertTrue(exprs)
        self.assertEqual(
            exprs[0]['value']['decimal'], 0o103 + 48)


if __name__ == '__main__':
    unittest.main()
