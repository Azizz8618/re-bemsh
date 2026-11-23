#!/usr/bin/env python3
"""Unit tests for tools/text_pool_probe.py.

Fixtures are synthetic words, .be lines and trace
lines. Two optional integration tests use real files.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text_pool_probe as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REAL_BE = ROOT / 'bemsh' / 'MBE-Z0154.be'
REAL_REPORTS = (
    ROOT / 'analysis' / 'POOL-DESCRIPTOR-FIELDS.md',
    ROOT / 'analysis' / 'TEXT-POOL-06445.md',
)

GOOD_TEXT = """\
MB2006 ЭКВ '72000'
C6402 ЭКВ '6402'
C6445 ЭКВ '6445'
06061: atx 72000(16) acc=2010000100052003 r[16]=0
72003: store 2010000200052003
72006  2010 0003 0005 2002
"""

BAD_TEXT = """\
2010 0001 0005 2003
2010 0002 0005 2006
2010 0001 0005 2002
"""


class TempMixin:
    """Temp dir that works if the temp fs is full."""

    def make_temp_dir(self):
        bases = (None, str(ROOT))
        for base in bases:
            try:
                holder = tempfile.TemporaryDirectory(
                    prefix='tpp-', dir=base)
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


class TestDecode(unittest.TestCase):
    def test_known_descriptor(self):
        d = m.decode_word(0o2010000100052003)
        self.assertEqual(d['word'], '2010000100052003')
        self.assertEqual(d['flag'], '2010')
        self.assertEqual(d['N'], '0001')
        self.assertEqual(d['tag'], '0005')
        self.assertEqual(d['words_field'], '2003')
        self.assertEqual(d['K'], 3)
        self.assertTrue(d['k_ok'])

    def test_short_record_k2(self):
        d = m.decode_word(0o2010000300052002)
        self.assertEqual(d['N'], '0003')
        self.assertEqual(d['K'], 2)
        self.assertTrue(d['k_ok'])

    def test_long_record_k5(self):
        d = m.decode_word(0o2010000500052005)
        self.assertEqual(d['K'], 5)
        self.assertTrue(d['k_ok'])

    def test_prefix_2000_word(self):
        d = m.decode_word(0o2000000300052002)
        self.assertEqual(d['flag'], '2000')
        self.assertEqual(d['tag'], '0005')
        self.assertEqual(d['K'], 2)

    def test_bad_k_out_of_range(self):
        d = m.decode_word(0o2010000100052006)
        self.assertEqual(d['K'], 6)
        self.assertFalse(d['k_ok'])

    def test_bad_k_below_base(self):
        d = m.decode_word(0o2010000100051777)
        self.assertIsNone(d['K'])
        self.assertFalse(d['k_ok'])

    def test_mask_01762_constant(self):
        self.assertEqual(m.MASK_OCT, '0000000000052000')
        self.assertEqual(
            int(m.MASK_OCT, 8),
            (m.TAG_0005 << 12) | m.BASE_2000)

    def test_fields_roundtrip(self):
        d = m.decode_fields(0o2010, 0o11, 0o5, 0o2004)
        self.assertEqual(d['word'], '2010001100052004')
        self.assertEqual(d['N'], '0011')

    def test_flag_from_base_or(self):
        d = m.decode_fields(0o2000, 1, m.TAG_0005, 0o2003)
        word = int(d['word'], 8) | (0o10 << 36)
        self.assertEqual(
            '%016o' % word, '2010000100052003')


class TestScan(unittest.TestCase):
    def test_be_equ_lines(self):
        r = m.scan_text("MB6445 ЭКВ '6445'\n", 'x.be')
        self.assertEqual(len(r['symbols']), 1)
        self.assertEqual(r['symbols'][0]['symbol'], '6445')
        self.assertEqual(r['symbols'][0]['role'], 'define')
        self.assertEqual(r['descriptors'], [])

    def test_symbol_no_substring_false_positive(self):
        r = m.scan_text('76445 26445 C6402 06402\n', 'x.be')
        names = sorted(s['symbol'] for s in r['symbols'])
        self.assertEqual(names, ['6402'])

    def test_trace_word_and_write_role(self):
        line = ('06061: atx 72000(16) '
                'acc=2010000100052003 r[16]=0')
        r = m.scan_text(line + '\n', 'trace.txt')
        self.assertEqual(len(r['descriptors']), 1)
        self.assertEqual(r['descriptors'][0]['K'], 3)
        self.assertTrue(any(
            s['symbol'] == '72000' and
            s['role'] == 'write'
            for s in r['symbols']))

    def test_spaced_dump_fields(self):
        line = '72006  2010 0003 0005 2002 дескриптор'
        r = m.scan_text(line + '\n', 'dump.out')
        self.assertEqual(len(r['descriptors']), 1)
        self.assertEqual(r['descriptors'][0]['N'], '0003')
        self.assertEqual(r['descriptors'][0]['K'], 2)
        self.assertEqual(r['symbols'], [])

    def test_prefix_2000_is_separate(self):
        text = ('2010000100052003\n'
                '2000000300052002\n')
        r = m.scan_text(text, 'x')
        self.assertEqual(len(r['descriptors']), 1)
        self.assertEqual(len(r['prefix_2000']), 1)
        self.assertEqual(
            r['prefix_2000'][0]['flag'], '2000')

    def test_bom_is_stripped(self):
        self.assertEqual(
            m.scan_text('\ufeff' + GOOD_TEXT, 'x'),
            m.scan_text(GOOD_TEXT, 'x'))


class TestCheck(unittest.TestCase):
    def test_check_good(self):
        r = m.scan_text(GOOD_TEXT, 'good.txt')
        result = m.check(r)
        self.assertTrue(result['ok'])
        self.assertEqual(result['checked'], 3)
        self.assertEqual(result['violations'], [])

    def test_check_bad_k(self):
        result = m.check(m.scan_text(BAD_TEXT, 'bad.txt'))
        names = [v['invariant']
                 for v in result['violations']]
        self.assertIn('K_2_5', names)
        self.assertFalse(result['ok'])

    def test_check_nonmonotonic(self):
        result = m.check(m.scan_text(BAD_TEXT, 'bad.txt'))
        names = [v['invariant']
                 for v in result['violations']]
        self.assertIn('N_monotonic', names)

    def test_check_bad_tag(self):
        text = '2010 0001 0006 2003\n'
        result = m.check(m.scan_text(text, 'bad.txt'))
        names = [v['invariant']
                 for v in result['violations']]
        self.assertIn('tag_0005', names)

    def test_check_bad_flag_direct(self):
        record = m.decode_fields(
            0o2011, 1, m.TAG_0005, 0o2003)
        record['source'] = 'x'
        record['line'] = 1
        result = m.check({'descriptors': [record]})
        names = [v['invariant']
                 for v in result['violations']]
        self.assertIn('flag_2010', names)

    def test_check_empty_input(self):
        result = m.check(m.scan_text('nothing\n', 'x'))
        self.assertFalse(result['ok'])
        self.assertEqual(result['checked'], 0)
        self.assertEqual(
            result['violations'][0]['invariant'],
            'descriptor_present')

    def test_monotonic_per_source(self):
        first = m.scan_text(GOOD_TEXT, 'a.txt')
        second = m.scan_text(GOOD_TEXT, 'b.txt')
        records = (first['descriptors'] +
                   second['descriptors'])
        result = m.check({'descriptors': records})
        self.assertTrue(result['ok'])
        self.assertEqual(result['checked'], 6)


class TestCLI(TempMixin, unittest.TestCase):
    def test_help(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as caught:
                m.main(['--help'])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn('--format', out.getvalue())
        self.assertIn('--check', out.getvalue())

    def test_text_format_width(self):
        path = self.write_fixture('good.txt', GOOD_TEXT)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = m.main([path])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn('TEXT POOL PROBE', text)
        for line in text.splitlines():
            self.assertLessEqual(len(line), 60)

    def test_json_format(self):
        path = self.write_fixture('good.txt', GOOD_TEXT)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = m.main([path, '--format', 'json'])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data['counts']['descriptors'], 3)
        self.assertEqual(
            data['counts']['symbols']['72000'], 2)
        self.assertNotIn('check', data)

    def test_check_exit_codes(self):
        good = self.write_fixture('good.txt', GOOD_TEXT)
        bad = self.write_fixture('bad.txt', BAD_TEXT)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(m.main([good, '--check']), 0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main([bad, '--check']), 1)

    def test_missing_file_guard(self):
        path = os.path.join(
            self.make_temp_dir(), 'no-such-file')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = m.main([path])
        self.assertEqual(code, 2)
        self.assertIn('error:', err.getvalue())

    def test_deterministic_json(self):
        path = self.write_fixture('good.txt', GOOD_TEXT)
        outputs = []
        for _ in range(2):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                m.main([path, '--format', 'json',
                        '--check'])
            outputs.append(out.getvalue())
        self.assertEqual(outputs[0], outputs[1])


@unittest.skipUnless(
    REAL_BE.exists(), 'real MBE-Z0154.be not present')
class TestRealBe(unittest.TestCase):
    def test_probe_real_be(self):
        result = m.probe([str(REAL_BE)])
        self.assertGreater(result['lines_total'], 100)
        self.assertGreater(
            result['counts']['symbols']['72000'], 0)
        self.assertGreater(
            result['counts']['symbols']['6445'], 0)
        self.assertEqual(result['sources'], [str(REAL_BE)])


@unittest.skipUnless(
    all(p.exists() for p in REAL_REPORTS),
    'real analysis reports not present')
class TestRealReports(unittest.TestCase):
    def test_probe_real_reports(self):
        paths = [str(p) for p in REAL_REPORTS]
        result = m.probe(paths)
        self.assertGreaterEqual(
            result['counts']['descriptors'], 3)
        self.assertGreater(
            result['counts']['prefix_2000'], 0)
        self.assertTrue(m.check(result)['ok'])

    def test_known_word_from_report(self):
        with open(REAL_REPORTS[0],
                  encoding='utf-8') as handle:
            result = m.scan_text(
                handle.read(), str(REAL_REPORTS[0]))
        words = [d['word']
                 for d in result['descriptors']]
        self.assertIn('2010000100052003', words)


if __name__ == '__main__':
    unittest.main()
