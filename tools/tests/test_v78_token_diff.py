#!/usr/bin/env python3
"""Tests for tools/v78_token_diff.py.

Synthetic traces are written to temp files. Two integration
tests use a real paired token trace under /var/tmp and skip
when it is absent. Temp dirs fall back to the repo root if
/tmp is full, as in test_rvs_trace.py.
"""
import contextlib
import glob
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v78_token_diff as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
_HOLDERS = []


def all_real_pairs():
    """Locate all four P*a/P*b trace pairs from phase 2A."""
    base = '/var/tmp/v78-syntax/token-exp'
    pairs = []
    for number in (1, 2, 3, 4):
        left = '%s/P%da.trace' % (base, number)
        right = '%s/P%db.trace' % (base, number)
        if (os.path.isfile(left) and
                os.path.isfile(right)):
            pairs.append((number, left, right))
    return pairs


REAL_PAIRS = all_real_pairs()
REAL_REPORTS = {}


def real_report(number):
    """Parse one real pair once for integration tests."""
    if number not in REAL_REPORTS:
        for item in REAL_PAIRS:
            if item[0] == number:
                _, left, right = item
                REAL_REPORTS[number] = m.analyze(
                    left, right)
    return REAL_REPORTS[number]


class TempMixin:
    """Temp dir that works if the temp fs is full."""

    def make_temp_dir(self):
        bases = (None, str(ROOT))
        for base in bases:
            try:
                holder = tempfile.TemporaryDirectory(
                    prefix='v78diff-', dir=base)
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

    def pair(self, text_a, text_b):
        return (self.write_fixture('a.trace.txt', text_a),
                self.write_fixture('b.trace.txt', text_b))


def run_cli(argv):
    """Capture main() return code and both streams."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        try:
            code = m.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class Guarded:
    """File stand-in that forbids bulk reads."""

    def __init__(self, text):
        self._io = io.StringIO(text)

    def __iter__(self):
        return iter(self._io)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._io.close()

    def read(self, *args):
        self.fail('read() called')

    def readlines(self, *args):
        self.fail('readlines() called')

    def fail(self, name):
        raise AssertionError('not streaming: ' + name)


TRACE_A = """\
03766: atx 1
       00000: store 0000000000000000
DD pc=70142L r016=71706 u=43 z=0144 RD
03767: atx 2
03770: vlm 3
"""

TRACE_B = """\
03766: atx 1
       00000: store 0000000000000000
DD pc=70142L r016=71706 u=43 z=0144 RD
03767: atx 2
03770: vlm 3
"""


class TestLineParsing(unittest.TestCase):
    def test_executed_pc_line(self):
        kind, pc, word = m.classify(
            '03766: atx 2250 (=0) acc=1')
        self.assertEqual((kind, oct(pc), word),
                         ('exec', '0o3766', 'atx'))

    def test_mnemonic_punctuation(self):
        for word in ('*70', 'a-x', 'x-a', 'a+x'):
            kind, _, got = m.classify(
                '70142: %s 71706' % word)
            self.assertEqual((kind, got), ('exec', word))

    def test_store_five_digits_at_col_zero(self):
        kind, pc, word = m.classify(
            '00000: store 0000000000000000')
        self.assertEqual((kind, pc, word),
                         ('store', 0, None))

    def test_store_six_digits_indented(self):
        kind, pc, word = m.classify(
            '       165465: store 2031463100000000')
        self.assertEqual((kind, pc, word),
                         ('store', 0o165465, None))

    def test_dd_event_is_not_pc(self):
        kind, pc, word = m.classify(
            'DD pc=70142L r016=71706 u=43 z=0144 RD')
        self.assertEqual((kind, pc, word),
                         ('dd', 0o70142, None))

    def test_dd_with_leading_spaces(self):
        kind, pc, _ = m.classify(
            '   DD pc=00010L u=43 z=0144')
        self.assertEqual((kind, pc), ('dd', 0o10))

    def test_dd_without_pc(self):
        kind, pc, _ = m.classify('DD timeout')
        self.assertEqual((kind, pc), ('dd', None))

    def test_other_line(self):
        kind, pc, word = m.classify(
            'KCNT: on_pc=00000 env=(none)')
        self.assertEqual((kind, pc, word),
                         ('other', None, None))

    def test_empty_mnemonic_is_other(self):
        kind, _, _ = m.classify('03766:   ')
        self.assertEqual(kind, 'other')

    def test_bom_stripped_by_normalize(self):
        text = m.normalize('\ufeff03766: atx 1\r\n')
        self.assertEqual(text, '03766: atx 1')
        self.assertEqual(m.classify(text)[0], 'exec')

    def test_octstr_formats(self):
        self.assertEqual(m.octstr(0o3766, 5), '03766')
        self.assertEqual(m.octstr(0o3766), '3766')


class TestDiffs(TempMixin, unittest.TestCase):
    def test_identical_traces_have_no_diff(self):
        report = m.analyze(*self.pair(TRACE_A, TRACE_B))
        self.assertIsNone(report['first_line_diff'])
        self.assertIsNone(report['pc_seq_diff'])
        self.assertTrue(all(
            row['delta'] == 0
            for row in report['count_delta_top']))

    def test_first_line_diff_reports_both_lines(self):
        left = TRACE_A.replace('03767: atx 2',
                               '03767: atx 9')
        report = m.analyze(*self.pair(left, TRACE_B))
        diff = report['first_line_diff']
        self.assertEqual(diff['line'], 4)
        self.assertIn('atx 9', diff['a'])
        self.assertIn('atx 2', diff['b'])

    def test_first_line_diff_eof(self):
        report = m.analyze(
            *self.pair(TRACE_A, '03766: atx 1\n'))
        diff = report['first_line_diff']
        self.assertEqual(diff['b'], m.EOF_MARK)
        self.assertEqual(diff['line'], 2)

    def test_store_lines_do_not_shift_pc_sequence(self):
        left = ('03766: atx 1\n'
                '       00000: store 0000\n'
                '03767: atx 2\n')
        right = '03766: atx 1\n03767: atx 2\n'
        report = m.analyze(*self.pair(left, right))
        self.assertIsNone(report['pc_seq_diff'])
        self.assertIsNotNone(
            report['first_line_diff'])

    def test_dd_lines_do_not_shift_pc_sequence(self):
        left = ('DD pc=00010L u=1 z=0144\n'
                '03766: atx 1\n')
        right = ('DD pc=00020L u=2 z=0144\n'
                 '03766: atx 1\n')
        report = m.analyze(*self.pair(left, right))
        self.assertIsNone(report['pc_seq_diff'])
        self.assertIsNotNone(
            report['first_line_diff'])

    def test_pc_sequence_diff_by_mnemonic(self):
        left = '03766: atx 1\n03767: atx 2\n'
        right = '03766: atx 1\n03767: vlm 2\n'
        report = m.analyze(*self.pair(left, right))
        seq = report['pc_seq_diff']
        self.assertEqual(seq['index'], 2)
        self.assertEqual(seq['a']['mnemonic'], 'atx')
        self.assertEqual(seq['b']['mnemonic'], 'vlm')
        self.assertEqual(seq['a']['pc'], '03767')

    def test_pc_sequence_diff_by_pc(self):
        left = '03766: atx 1\n03767: atx 2\n'
        right = '03766: atx 1\n03770: atx 2\n'
        report = m.analyze(*self.pair(left, right))
        seq = report['pc_seq_diff']
        self.assertEqual(seq['index'], 2)
        self.assertEqual(seq['a']['pc'], '03767')
        self.assertEqual(seq['b']['pc'], '03770')

    def test_pc_sequence_diff_ignores_store_and_dd(self):
        left = ('DD pc=00001L z=0144\n'
                '00000: store 0000\n'
                '03766: atx 1\n')
        right = ('DD pc=00002L z=0144\n'
                 '00000: store 0000\n'
                 '03767: atx 1\n')
        report = m.analyze(*self.pair(left, right))
        self.assertEqual(
            report['pc_seq_diff']['index'], 1)

    def test_pc_sequence_length_mismatch(self):
        left = '03766: atx 1\n03767: atx 2\n'
        right = '03766: atx 1\n'
        report = m.analyze(*self.pair(left, right))
        seq = report['pc_seq_diff']
        self.assertEqual(seq['index'], 2)
        self.assertEqual(seq['a']['pc'], '03767')
        self.assertIsNone(seq['b'])


class TestCounts(TempMixin, unittest.TestCase):
    def test_count_deltas_and_one_sided_pcs(self):
        left = '03766: atx 1\n' * 3 + '03767: atx 2\n'
        right = '03766: atx 1\n' + '03770: atx 3\n' * 2
        report = m.analyze(*self.pair(left, right))
        s = report['summary']
        self.assertEqual((s['exec_a'], s['exec_b']),
                         (4, 3))
        self.assertEqual((s['distinct_pcs_a'],
                          s['distinct_pcs_b']), (2, 2))
        self.assertEqual(s['common_pcs'], 1)
        rows = {r['pc']: r for r in
                report['count_delta_top']}
        self.assertEqual(rows['03766']['delta'], -2)
        self.assertEqual(rows['03770']['delta'], 2)
        self.assertEqual(rows['03767']['delta'], -1)
        self.assertEqual(
            report['only_a_top'][0]['pc'], '03767')
        self.assertEqual(
            report['only_b_top'][0]['pc'], '03770')

    def test_delta_order_is_by_absolute_value(self):
        left = ('03766: atx 1\n' * 5 +
                '03767: atx 2\n' * 3)
        right = '03770: atx 3\n' * 4
        report = m.analyze(*self.pair(left, right))
        rows = report['count_delta_top']
        self.assertEqual(
            [abs(r['delta']) for r in rows],
            [5, 4, 3])

    def test_tables_are_capped_at_twenty(self):
        left = ''.join('%05o: atx 1\n' % (0o100 + i)
                       for i in range(25))
        right = ''
        report = m.analyze(*self.pair(left, right))
        self.assertEqual(
            len(report['count_delta_top']), m.TOP_N)
        self.assertEqual(
            len(report['only_a_top']), m.TOP_N)
        self.assertEqual(
            report['only_b_top'], [])

    def test_summary_classifies_every_line(self):
        report = m.analyze(*self.pair(TRACE_A, TRACE_B))
        s = report['summary']
        self.assertEqual((s['lines_a'], s['lines_b']),
                         (5, 5))
        self.assertEqual((s['exec_a'], s['exec_b']),
                         (3, 3))
        self.assertEqual((s['store_a'], s['store_b']),
                         (1, 1))
        self.assertEqual((s['dd_a'], s['dd_b']),
                         (1, 1))
        self.assertEqual(s['other_a'], 0)
        self.assertEqual(s['seq_compared'], 3)

    def test_skip_ignores_boot_noise(self):
        boot = '00001: atx 9\n00002: atx 9\n'
        left = boot + '03766: atx 1\n'
        right = boot + '03766: vlm 1\n'
        paths = self.pair(left, right)
        plain = m.analyze(*paths)
        self.assertEqual(
            plain['pc_seq_diff']['index'], 3)
        skipped = m.analyze(*paths, skip=2)
        self.assertEqual(
            skipped['pc_seq_diff']['index'], 1)
        self.assertEqual(
            skipped['summary']['skipped_a'], 2)
        self.assertEqual(
            skipped['summary']['skipped_b'], 2)

    def test_skip_excludes_boot_from_histograms(self):
        boot = '00001: atx 9\n00002: atx 9\n'
        left = boot + '03766: atx 1\n'
        right = boot + '03766: atx 1\n'
        report = m.analyze(*self.pair(left, right),
                           skip=2)
        self.assertEqual(
            report['summary']['exec_a'], 1)
        self.assertEqual(
            report['only_a_top'], [])
        self.assertEqual(
            report['only_b_top'], [])


class TestCheck(TempMixin, unittest.TestCase):
    def test_check_ok_on_valid_traces(self):
        report = m.analyze(*self.pair(TRACE_A, TRACE_B))
        result = m.check(report)
        self.assertTrue(result['ok'])
        self.assertEqual(result['violations_total'], 0)
        self.assertEqual(result['violations'], [])

    def test_check_flags_dd_pc_out_of_range(self):
        left = ('DD pc=777777L z=0144\n'
                '03766: atx 1\n')
        report = m.analyze(*self.pair(left, TRACE_A))
        result = m.check(report)
        self.assertFalse(result['ok'])
        kinds = {v['invariant']
                 for v in result['violations']}
        self.assertIn('pc_range', kinds)

    def test_check_flags_store_addr_out_of_range(self):
        left = ('       777777: store 0000\n'
                '03766: atx 1\n')
        report = m.analyze(*self.pair(left, TRACE_A))
        result = m.check(report)
        kinds = {v['invariant']
                 for v in result['violations']}
        self.assertIn('pc_range', kinds)

    def test_check_flags_malformed_dd_pc(self):
        left = 'DD pc=XYZ z=0144\n03766: atx 1\n'
        report = m.analyze(*self.pair(left, TRACE_A))
        kinds = {v['invariant'] for v in
                 m.check(report)['violations']}
        self.assertIn('malformed_dd_pc', kinds)

    def test_check_flags_empty_instruction(self):
        left = '03766:   \n03767: atx 1\n'
        report = m.analyze(*self.pair(left, TRACE_A))
        kinds = {v['invariant'] for v in
                 m.check(report)['violations']}
        self.assertIn('malformed_pc_line', kinds)

    def test_negative_delta_is_not_violation(self):
        left = '03766: atx 1\n' * 5
        right = '03766: atx 1\n03767: atx 2\n'
        report = m.analyze(*self.pair(left, right))
        self.assertTrue(any(
            row['delta'] < 0
            for row in report['count_delta_top']))
        self.assertTrue(m.check(report)['ok'])

    def test_check_truncates_long_violation_list(self):
        left = '03766:   \n' * 35 + '03767: atx 1\n'
        report = m.analyze(*self.pair(left, TRACE_A))
        result = m.check(report)
        self.assertEqual(
            result['violations_total'], 35)
        self.assertEqual(len(result['violations']),
                         m.VIOLATION_N)
        self.assertEqual(result['truncated'], 5)


class TestCli(TempMixin, unittest.TestCase):
    def test_cli_help(self):
        code, out, err = run_cli(['--help'])
        self.assertEqual(code, 0)
        self.assertIn('--skip', out)
        self.assertIn('--check', out)

    def test_cli_text_exit_zero(self):
        paths = self.pair(TRACE_A, TRACE_B)
        code, out, err = run_cli(list(paths))
        self.assertEqual(code, 0)
        self.assertIn('V78 TOKEN DIFF', out)
        self.assertEqual(err, '')

    def test_cli_json_schema(self):
        paths = self.pair(TRACE_A, TRACE_B)
        code, out, err = run_cli(
            list(paths) + ['--format', 'json'])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        for key in ('sources', 'skip', 'summary',
                    'first_line_diff', 'pc_seq_diff',
                    'count_delta_top', 'only_a_top',
                    'only_b_top', 'parse'):
            self.assertIn(key, payload)
        self.assertNotIn('check', payload)

    def test_cli_check_json_exit_one(self):
        left = 'DD pc=XYZ z=0144\n03766: atx 1\n'
        paths = self.pair(left, TRACE_A)
        code, out, err = run_cli(
            list(paths) + ['--check', '--format',
                           'json'])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertFalse(payload['check']['ok'])

    def test_cli_bad_skip_exit_two(self):
        paths = self.pair(TRACE_A, TRACE_B)
        code, out, err = run_cli(
            list(paths) + ['--skip', '-1'])
        self.assertEqual(code, 2)
        self.assertIn('skip', err)

    def test_cli_missing_file_exit_two(self):
        path = self.write_fixture('only.trace.txt',
                                  TRACE_A)
        code, out, err = run_cli(
            [path, path + '.absent'])
        self.assertEqual(code, 2)
        self.assertIn('error', err)

    def test_cli_missing_args_exit_two(self):
        code, out, err = run_cli(['one.trace.txt'])
        self.assertEqual(code, 2)

    def test_inputs_are_not_modified(self):
        left = self.write_fixture('a.trace.txt',
                                  TRACE_A)
        right = self.write_fixture('b.trace.txt',
                                   TRACE_B)

        def snapshot(path):
            with open(path, 'rb') as handle:
                return (handle.read(),
                        os.stat(path).st_mtime_ns)

        before = [snapshot(p) for p in (left, right)]
        m.analyze(left, right)
        run_cli([left, right, '--check'])
        after = [snapshot(p) for p in (left, right)]
        self.assertEqual(before, after)


class TestStreaming(TempMixin, unittest.TestCase):
    def test_never_bulk_reads_files(self):
        paths = self.pair(TRACE_A, TRACE_B)
        texts = {}
        for path in paths:
            with open(path, encoding='utf-8') as handle:
                texts[path] = handle.read()
        with mock.patch.object(
                m, 'open_trace',
                side_effect=lambda p: Guarded(texts[p])):
            report = m.analyze(*paths)
        self.assertEqual(
            report['summary']['exec_a'], 3)

    def test_guarded_result_matches_plain(self):
        paths = self.pair(TRACE_A, TRACE_B)
        plain = m.analyze(*paths, skip=1)
        texts = {}
        for path in paths:
            with open(path, encoding='utf-8') as handle:
                texts[path] = handle.read()
        with mock.patch.object(
                m, 'open_trace',
                side_effect=lambda p: Guarded(texts[p])):
            guarded = m.analyze(*paths, skip=1)
        self.assertEqual(plain['summary'],
                         guarded['summary'])
        self.assertEqual(plain['count_delta_top'],
                         guarded['count_delta_top'])


@unittest.skipUnless(len(REAL_PAIRS) == 4,
                     'four real pairs not present')
class TestIntegrationPaired(unittest.TestCase):
    def test_real_pairs_analyze(self):
        self.assertEqual(len(REAL_PAIRS), 4)
        for number, left, right in REAL_PAIRS:
            report = real_report(number)
            s = report['summary']
            self.assertEqual(
                report['sources']['a'], left)
            self.assertGreater(s['lines_a'], 0)
            self.assertGreater(s['lines_b'], 0)
            self.assertLessEqual(
                len(report['count_delta_top']),
                m.TOP_N)
            rows = report['count_delta_top']
            self.assertEqual(
                [abs(r['delta']) for r in rows],
                sorted((abs(r['delta'])
                        for r in rows), reverse=True))
            seq = report['pc_seq_diff']
            if seq is not None:
                self.assertGreaterEqual(seq['index'], 1)

    def test_pair3_has_no_pc_divergence(self):
        report = real_report(3)
        self.assertIsNone(report['pc_seq_diff'])
        s = report['summary']
        self.assertEqual(s['exec_a'], s['exec_b'])
        self.assertEqual(s['store_a'], s['store_b'])
        self.assertEqual(s['common_pcs'],
                         s['distinct_pcs_a'])
        self.assertTrue(all(
            row['delta'] == 0 for row in
            report['count_delta_top']))

    def test_real_pairs_cli_json(self):
        for number, left, right in REAL_PAIRS:
            code, out, err = run_cli(
                [left, right, '--format', 'json'])
            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertEqual(
                payload['summary'],
                real_report(number)['summary'])
            self.assertIn('first_line_diff', payload)


if __name__ == '__main__':
    unittest.main()
