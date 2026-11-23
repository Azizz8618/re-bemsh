#!/usr/bin/env python3
"""Tests for tools/rvs_trace.py.

Synthetic fixtures are written to temp files or fed to the
Accumulator directly. Two integration tests use the real
/var/tmp/siprod-rvs-min files and skip when absent.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rvs_trace as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REAL_TRACE = Path('/var/tmp/siprod-rvs-min/link-dd.err')
REAL_CATALOG = Path('/var/tmp/siprod-rvs-min/z0001.txt')
_REAL_REPORT = None
_HOLDERS = []

TRACE = """\
KCNT: on_pc=00000 env=(none)
03766: atx 2250 (=0000000000000000) acc=001
       102251: store 0000000000000000
DD pc=70142L r016=71706 u=43 z=0144 RD
70142: *70 71706 (=0000000000000000) acc=002
       00000: store 0000000000000000
E70at 70141R r016=00000
"""

CATALOG = ('МДЛ   СБОР80 421260\u203eНАЗ   000001\u203e'
           'ЗОНГП 430400 01\u203e'
           'МДЛ   ГЕН   421652\u203eНАЗ   070000\u203e'
           'ЗОНГП 430461 03\u203e'
           'МДЛ   БОП2  421412\u203eНАЗ   НС24400\u203e'
           'ЗОНГП 430000 01\u203e'
           'МДЛ   ИТОГ  421272\u203eНАЗ   000001\u203e'
           'ЗОНГП 430407 01')


class TempMixin:
    """Temp dir that works if the temp fs is full."""

    def make_temp_dir(self):
        bases = (None, str(ROOT))
        for base in bases:
            try:
                holder = tempfile.TemporaryDirectory(
                    prefix='rvs-', dir=base)
            except OSError:
                continue
            if hasattr(self, 'addCleanup'):
                self.addCleanup(holder.cleanup)
            else:
                _HOLDERS.append(holder)
            return holder.name
        self.fail('no writable temp directory')

    def write_fixture(self, name, text):
        path = os.path.join(self.make_temp_dir(), name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        return path


def feed_lines(lines):
    """Feed a list of lines directly into an Accumulator."""
    acc = m.Accumulator([], None)
    for idx, line in enumerate(lines, 1):
        acc.feed(line, 'test', idx)
    return acc


class TestLineParsing(unittest.TestCase):
    def test_executed_pc_line(self):
        acc = feed_lines(['03766: atx 2250 (=0) acc=1'])
        self.assertEqual(acc.instructions, 1)
        self.assertEqual(acc.pc_counts[0o3766], 1)
        self.assertEqual(
            acc.pc_mnemonics[0o3766]['atx'], 1)
        self.assertEqual(acc.stores, 0)

    def test_mnemonics_with_punctuation(self):
        acc = feed_lines(['70142: *70 1', '71447: a-x',
                          '71446: x-a', '71450: a+x'])
        self.assertEqual(acc.instructions, 4)
        names = sorted(
            token for counts in acc.pc_mnemonics.values()
            for token in counts)
        self.assertEqual(
            names, ['*70', 'a+x', 'a-x', 'x-a'])

    def test_store_five_digits_is_not_pc(self):
        acc = feed_lines([
            '       00000: store 0000000000000000'])
        self.assertEqual(acc.stores, 1)
        self.assertEqual(acc.instructions, 0)
        self.assertEqual(acc.store_counts[0], 1)

    def test_store_six_digits_is_not_pc(self):
        acc = feed_lines([
            '       165465: store 2031463100000000'])
        self.assertEqual(acc.stores, 1)
        self.assertEqual(acc.instructions, 0)
        self.assertEqual(acc.store_counts[0o165465], 1)

    def test_store_at_column_zero_is_not_pc(self):
        acc = feed_lines(['00000: store 0000000000000000'])
        self.assertEqual(acc.stores, 1)
        self.assertEqual(acc.instructions, 0)

    def test_dd_event_is_not_pc(self):
        acc = feed_lines([
            'DD pc=70142L r016=71706 u=43 z=0144 RD'])
        self.assertEqual(acc.dd_events, 1)
        self.assertEqual(acc.instructions, 0)
        self.assertEqual(acc.dd_u['043'], 1)
        self.assertEqual(acc.dd_z['0144'], 1)
        self.assertEqual(acc.dd_pair['043/0144'], 1)
        self.assertEqual(acc.dd_pc_min, 0o70142)

    def test_dd_without_u_or_z(self):
        acc = feed_lines(['DD pc=01001L РД'])
        self.assertEqual(acc.dd_events, 1)
        self.assertEqual(acc.dd_u['-'], 1)
        self.assertEqual(acc.dd_z['-'], 1)

    def test_unparsed_lines_have_bounded_samples(self):
        lines = ['KCNT: on_pc=00000', 'E70at 70141R'] + [
            'E70at 70142R' for _ in range(20)]
        acc = feed_lines(lines)
        self.assertEqual(acc.unparsed, len(lines))
        self.assertEqual(len(acc.samples), m.SAMPLE_N)

    def test_non_octal_and_short_pc_rejected(self):
        acc = feed_lines(['00088: atx 1', '0123: atx 1',
                          '0177777: atx 1'])
        self.assertEqual(acc.instructions, 0)
        self.assertEqual(acc.unparsed, 3)

    def test_bom_and_crlf(self):
        acc = feed_lines(['\ufeff03766: atx 1\r'])
        self.assertEqual(acc.instructions, 1)
        self.assertEqual(acc.pc_counts[0o3766], 1)

    def test_page_is_pc_shift_nine(self):
        acc = feed_lines(['70142: vlm 1'])
        page = next(iter(acc.page_counts))
        self.assertEqual(m.octstr(page, 3), '070')
        acc.feed_pc('177777', 'ntr', 'test', 2)
        self.assertEqual(acc.page_counts[0o177], 1)


class TestAggregation(unittest.TestCase):
    def test_min_max_and_top_ordering(self):
        acc = feed_lines(['00010: ntr 1', '03766: atx 1',
                          '03766: atx 2', '03766: uj 3'])
        result = acc.result(['test'], None)
        self.assertEqual(result['pc_min'], '00010')
        self.assertEqual(result['pc_max'], '03766')
        top = result['top_pcs'][0]
        self.assertEqual(top['pc'], '03766')
        self.assertEqual(top['mnemonic'], 'atx')
        self.assertEqual(top['count'], 3)

    def test_first_and_last_line_per_module(self):
        mods = m.parse_catalog(CATALOG)
        acc = m.Accumulator(mods, m.build_index(mods))
        for line_no, line in enumerate(
                ['00001: ntr 1', '70001: vlm 1',
                 '00002: ntr 1'], 1):
            acc.feed(line, 'test', line_no)
        rows = {r['name']: r for r in
                acc.result(['test'], 'cat')['modules']}
        self.assertEqual(rows['СБОР80']['count'], 2)
        self.assertEqual(rows['СБОР80']['first_line'], 1)
        self.assertEqual(rows['СБОР80']['last_line'], 3)
        self.assertEqual(rows['ГЕН']['first_line'], 2)

    def test_two_sources_sum_counts(self):
        holder = TempMixin()
        a = holder.write_fixture('a.txt', TRACE)
        b = holder.write_fixture('b.txt', TRACE)
        result = m.analyze([a, b])
        self.assertEqual(
            result['counts']['instructions'], 4)
        self.assertEqual(result['counts']['dd_events'], 2)
        self.assertEqual(result['lines_total'], 14)


class TestCatalog(unittest.TestCase):
    def test_basic_fields(self):
        mods = m.parse_catalog(CATALOG)
        self.assertEqual(len(mods), 4)
        first = mods[0]
        self.assertEqual(first['name'], 'СБОР80')
        self.assertEqual(first['code'], '421260')
        self.assertEqual(first['naz'], '000001')
        self.assertEqual(first['zone'], '430400')
        self.assertEqual(first['start'], '000001')
        self.assertEqual(first['end'], '001001')
        self.assertTrue(first['valid'])

    def test_name_ending_with_digits(self):
        mods = m.parse_catalog(CATALOG)
        self.assertEqual(mods[1]['name'], 'ГЕН')
        self.assertEqual(mods[1]['code'], '421652')
        self.assertEqual(mods[0]['name'], 'СБОР80')
        self.assertEqual(mods[0]['code'], '421260')

    def test_newlines_and_lowercase_keywords(self):
        text = ('\ufeffмдл   тест 421300\n'
                'наз   010000\n'
                'зонгп 430500 2\n')
        mods = m.parse_catalog(text, 'x')
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0]['name'], 'тест')
        self.assertEqual(mods[0]['zones'], 2)
        self.assertEqual(mods[0]['end'], '012000')

    def test_non_octal_naz_is_invalid(self):
        mods = m.parse_catalog(CATALOG)
        third = mods[2]
        self.assertEqual(third['naz'], 'НС24400')
        self.assertFalse(third['valid'])
        self.assertIsNone(third['start'])

    def test_range_from_zone_count(self):
        mods = m.parse_catalog(CATALOG)
        gen = mods[1]
        self.assertEqual(gen['zones'], 3)
        self.assertEqual(gen['end'], '073000')

    def test_boundaries_start_inclusive_end_exclusive(self):
        mods = m.parse_catalog(CATALOG)
        acc = m.Accumulator(mods, m.build_index(mods))
        acc.feed_pc('000001', 'ntr', 't', 1)
        acc.feed_pc('001000', 'ntr', 't', 2)
        acc.feed_pc('001001', 'ntr', 't', 3)
        row = [r for r in acc.result(['t'], 'c')['modules']
               if r['name'] == 'СБОР80'][0]
        self.assertEqual(row['count'], 2)

    def test_overlap_prefers_narrowest_range(self):
        text = ('МДЛ   ШИР 421000\u203eНАЗ 010000\u203e'
                'ЗОНГП 430001 02\u203e'
                'МДЛ   УЗК 421001\u203eНАЗ 010100\u203e'
                'ЗОНГП 430002 01')
        mods = m.parse_catalog(text)
        acc = m.Accumulator(mods, m.build_index(mods))
        acc.feed_pc('010100', 'ntr', 't', 1)
        rows = acc.result(['t'], 'c')['modules']
        counts = {r['name']: r['count'] for r in rows}
        self.assertEqual(counts['УЗК'], 1)
        self.assertEqual(counts['ШИР'], 0)


class TestCheck(unittest.TestCase):
    def setUp(self):
        holder = TempMixin()
        self.path = holder.write_fixture('trace.txt', TRACE)
        self.report = m.analyze([self.path],
                                holder.write_fixture(
                                    'cat.txt', CATALOG))

    def test_clean_report(self):
        result = m.check(m.analyze([self.path]))
        self.assertTrue(result['ok'])
        self.assertEqual(result['violations_total'], 0)

    def test_negative_count_detected(self):
        bad = dict(self.report)
        bad['counts'] = dict(self.report['counts'])
        bad['counts']['instructions'] = -1
        result = m.check(bad)
        self.assertFalse(result['ok'])
        self.assertTrue(any(
            v['invariant'] == 'no_negative_counts'
            for v in result['violations']))

    def test_pc_out_of_range_detected(self):
        bad = dict(self.report)
        bad['pc_max'] = '200000'
        result = m.check(bad)
        self.assertTrue(any(
            v['invariant'] == 'pc_range'
            for v in result['violations']))

    def test_module_overlap_detected(self):
        result = m.check(self.report)
        names = [v['invariant']
                 for v in result['violations']]
        self.assertIn('module_no_overlap', names)
        self.assertFalse(result['ok'])

    def test_violations_are_bounded(self):
        bad = dict(self.report)
        bad['modules'] = list(self.report['modules'])
        for idx in range(50):
            row = dict(bad['modules'][0])
            row['name'] = 'М%02d' % idx
            bad['modules'].append(row)
        result = m.check(bad)
        self.assertGreater(
            result['violations_total'], m.VIOLATION_N)
        self.assertEqual(
            len(result['violations']), m.VIOLATION_N)
        self.assertGreater(result['truncated'], 0)

    def test_text_table_fits_sixty_columns(self):
        result = m.check(self.report)
        text = m.format_text(self.report, result)
        for row in text.splitlines():
            self.assertLessEqual(len(row), 60)


class TestCli(unittest.TestCase):
    def setUp(self):
        holder = TempMixin()
        self.path = holder.write_fixture('trace.txt', TRACE)
        self.catalog = holder.write_fixture(
            'cat.txt', CATALOG)

    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = m.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as caught:
            with contextlib.redirect_stdout(io.StringIO()):
                m.main(['--help'])
        self.assertEqual(caught.exception.code, 0)

    def test_json_format(self):
        code, out, _ = self.run_cli(
            [self.path, '--format', 'json'])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(
            payload['counts']['instructions'], 2)
        self.assertEqual(payload['dd']['total'], 1)
        self.assertEqual(payload['page_shift'], 9)

    def test_json_with_check(self):
        code, out, _ = self.run_cli(
            [self.path, '--catalog', self.catalog,
             '--format', 'json', '--check'])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertFalse(payload['check']['ok'])
        self.assertIn('modules', payload)

    def test_clean_check_exits_zero(self):
        code, out, _ = self.run_cli(
            [self.path, '--check'])
        self.assertEqual(code, 0)
        self.assertIn('ПРОВЕРКА OK', out)

    def test_missing_file_exits_two(self):
        code, out, err = self.run_cli(
            ['/no/such/trace.txt', '--format', 'json'])
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('error:', err)


REAL_REPORT = None


def real_report():
    """Parse the real trace once for integration tests."""
    global REAL_REPORT
    if REAL_REPORT is None:
        REAL_REPORT = m.analyze(
            [str(REAL_TRACE)], str(REAL_CATALOG))
    return REAL_REPORT


@unittest.skipUnless(REAL_TRACE.is_file(),
                     'real trace not present')
class TestIntegrationTrace(unittest.TestCase):
    def test_real_trace_counts(self):
        report = real_report()
        counts = report['counts']
        self.assertEqual(report['lines_total'], 4058804)
        self.assertEqual(counts['instructions'], 4038477)
        self.assertEqual(counts['dd_events'], 241)
        self.assertEqual(counts['pc_out_of_range'], 0)
        self.assertEqual(report['dd']['by_z']['0144'], 2)
        self.assertEqual(report['pc_min'], '00010')
        self.assertEqual(report['pc_max'], '72353')

    def test_real_trace_top_page_and_pc(self):
        report = real_report()
        self.assertEqual(report['pages'][0]['page'], '071')
        top = report['top_pcs'][0]
        self.assertEqual(top['pc'], '71211')
        self.assertEqual(top['mnemonic'], 'vlm')
        self.assertGreater(top['count'], 3000000)


@unittest.skipUnless(REAL_CATALOG.is_file(),
                     'real catalog not present')
class TestIntegrationCatalog(unittest.TestCase):
    def test_catalog_parses_and_attributes(self):
        report = real_report()
        self.assertEqual(report['counts']['modules'], 146)
        rows = {r['name']: r for r in report['modules']}
        self.assertEqual(rows['СБОР80']['naz'], '000001')
        self.assertEqual(rows['ГЕН']['count'], 3928380)
        self.assertEqual(rows['ГЕН']['start'], '070000')
        self.assertEqual(rows['ГЕН']['end'], '073000')

    def test_real_check_flags_only_catalog_overlaps(self):
        report = real_report()
        result = m.check(report)
        kinds = {v['invariant']
                 for v in result['violations']}
        self.assertEqual(kinds, {'module_no_overlap'})
        self.assertFalse(result['ok'])


if __name__ == '__main__':
    unittest.main()
