#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for tools/v78_fsm_probe.py.

Synthetic traces are written to temp files. Two integration
tests use the real P2a/P2b traces under /var/tmp and skip
when they are absent. Temp dirs fall back to the repo root
if /tmp is full, as in test_v78_token_diff.py.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v78_fsm_probe as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRACE_BASE = '/var/tmp/v78-syntax/token-exp'
P2A = TRACE_BASE + '/P2a.trace'
P2B = TRACE_BASE + '/P2b.trace'
GOLD = ROOT / 'gold' / 'MBE-Z0152-L1.bin'
_HOLDERS = []

# One discriminating instruction for every named state.
ALL_OPS = (
    (0o76604, 'apx'), (0o76611, 'aex'),
    (0o76612, 'xta'), (0o76615, 'vlm'),
    (0o76621, 'aux'), (0o01412, 'xta'),
    (0o01413, 'atx'), (0o75353, 'aex'),
    (0o75356, 'aex'), (0o75377, 'utm'),
    (0o77320, 'xta'), (0o06061, 'atx'),
    (0o01534, 'xta'),
)


def op(pc, mnemonic, tail='(=0) acc=0'):
    """One executed-instruction trace line."""
    return '%05o: %-6s %s\n' % (pc, mnemonic, tail)


ALL_TRACE = ''.join(op(pc, word)
                    for pc, word in ALL_OPS)


class TempMixin:
    """Temp dir that works if the temp fs is full."""

    def make_temp_dir(self):
        bases = (None, str(ROOT))
        for base in bases:
            try:
                holder = tempfile.TemporaryDirectory(
                    prefix='v78fsm-', dir=base)
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

    def write_masks(self, values=None):
        """Synthetic zone 0152 image with mask words."""
        size = (0o76317 - m.ZONE_BASE + 1) * m.WORD_BYTES
        data = bytearray(size)
        defaults = {0o76315: 0xbe, 0o76316: 0xbf,
                    0o76317: 0x40}
        if values is not None:
            defaults.update(values)
        for addr, byte in defaults.items():
            off = (addr - m.ZONE_BASE) * m.WORD_BYTES
            data[off] = byte
        path = os.path.join(self.make_temp_dir(),
                            'zone0152.bin')
        with open(path, 'wb') as handle:
            handle.write(data)
        return path


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


class TestDefinitions(unittest.TestCase):
    def test_state_keys_are_unique(self):
        keys = [s.key for s in m.STATES]
        self.assertEqual(len(keys), len(set(keys)))

    def test_state_pcs_in_range(self):
        for state in m.STATES:
            self.assertTrue(
                0 <= state.pc < m.PC_LIMIT,
                state.key)

    def test_state_refs_match_pcs(self):
        for state in m.STATES:
            self.assertEqual(
                int(state.ref, 8), state.pc)

    def test_counter_map_covers_all_states(self):
        keys = set(s.key for s in m.STATES)
        mapped = set(key for _, key in m.COUNTER_MAP)
        self.assertEqual(keys, mapped)

    def test_mask_specs_are_be_bf_40(self):
        values = [(ref, byte)
                  for _, byte, ref in m.MASK_SPECS]
        self.assertEqual(values, [
            ('076315', 0xbe),
            ('076316', 0xbf),
            ('076317', 0x40),
        ])

    def test_mask_refs_point_to_states(self):
        keys = set(s.key for s in m.STATES)
        for key in m.MASK_REFS:
            self.assertIn(key, keys)


class TestMatching(unittest.TestCase):
    def test_exact_pc_and_mnemonic(self):
        state = m.match_state(0o76612, 'xta', 0)
        self.assertIsNotNone(state)
        self.assertEqual(state.key, 'RLE_SPACE')

    def test_wrong_mnemonic_does_not_match(self):
        self.assertIsNone(
            m.match_state(0o76612, 'vlm', 0))

    def test_case_insensitive_mnemonic(self):
        state = m.match_state(0o76612, 'XTA', 0)
        self.assertEqual(state.key, 'RLE_SPACE')

    def test_none_mnemonic_does_not_match(self):
        self.assertIsNone(
            m.match_state(0o76612, None, 0))

    def test_tolerance_accepts_nearby_pc(self):
        state = m.match_state(0o76613, 'xta', 2)
        self.assertEqual(state.key, 'RLE_SPACE')

    def test_tolerance_rejects_far_pc(self):
        self.assertIsNone(
            m.match_state(0o76617, 'xta', 1))

    def test_nearest_pc_wins_in_classifier(self):
        left = m.match_state(0o75354, 'aex', 2)
        right = m.match_state(0o75355, 'aex', 2)
        self.assertEqual(left.key, 'CLS_A')
        self.assertEqual(right.key, 'CLS_B')

    def test_zero_tolerance_needs_exact_pc(self):
        self.assertIsNone(
            m.match_state(0o76613, 'xta', 0))


class TestCounters(TempMixin, unittest.TestCase):
    def test_all_state_counters_are_one(self):
        report = m.analyze(
            self.write_fixture('all.trace', ALL_TRACE))
        self.assertTrue(all(
            value == 1
            for value in report['counters'].values()))

    def test_summary_counts_executed_lines(self):
        report = m.analyze(
            self.write_fixture('all.trace', ALL_TRACE))
        s = report['summary']
        self.assertEqual(s['executed'], len(ALL_OPS))
        self.assertEqual(s['assigned'], len(ALL_OPS))
        self.assertEqual(s['lines'], len(ALL_OPS))

    def test_shared_pc_disambiguated_by_mnemonic(self):
        text = (op(0o06061, 'atx') +
                op(0o06061, 'vjm') * 6)
        report = m.analyze(
            self.write_fixture('shared.trace', text))
        self.assertEqual(
            report['counters']['descriptor_write'], 1)

    def test_shared_metka_pc_disambiguated(self):
        text = (op(0o75377, 'vlm') * 5 +
                op(0o75377, 'utm'))
        report = m.analyze(
            self.write_fixture('metka.trace', text))
        self.assertEqual(
            report['counters']['metka_read'], 1)

    def test_repeated_state_has_one_visit(self):
        text = op(0o76612, 'xta') * 3
        report = m.analyze(
            self.write_fixture('repeat.trace', text))
        rows = {r['key']: r for r in report['states']}
        self.assertEqual(rows['RLE_SPACE']['hits'], 3)
        self.assertEqual(rows['RLE_SPACE']['visits'], 1)

    def test_return_increments_visit(self):
        text = (op(0o76612, 'xta') * 2 +
                op(0o76611, 'aex') +
                op(0o76612, 'xta') * 2)
        report = m.analyze(
            self.write_fixture('return.trace', text))
        rows = {r['key']: r for r in report['states']}
        self.assertEqual(rows['RLE_SPACE']['hits'], 4)
        self.assertEqual(rows['RLE_SPACE']['visits'], 2)

    def test_store_dd_and_other_are_not_pcs(self):
        text = ('KCNT: on_pc=00000 env=(none)\n'
                'DD pc=00010L z=0144\n'
                '       00000: store 2031\n' +
                op(0o76612, 'xta'))
        report = m.analyze(
            self.write_fixture('mixed.trace', text))
        s = report['summary']
        self.assertEqual(
            (s['executed'], s['stores'],
             s['dd'], s['other']), (1, 1, 1, 1))
        self.assertEqual(
            report['counters']['rle_space_branch'], 1)

    def test_tolerance_widens_state_window(self):
        text = op(0o76613, 'xta')
        path = self.write_fixture('near.trace', text)
        plain = m.analyze(path)
        wide = m.analyze(path, tolerance=1)
        self.assertEqual(
            plain['counters']['rle_space_branch'], 0)
        self.assertEqual(
            wide['counters']['rle_space_branch'], 1)

    def test_compare_reports_deltas(self):
        left = self.write_fixture(
            'a.trace', op(0o76612, 'xta') * 3)
        right = self.write_fixture(
            'b.trace', op(0o76612, 'xta'))
        report = m.analyze(left, right)
        rows = {
            r['key']: r
            for r in report['compare']['counter_delta']
        }
        self.assertEqual(rows['rle_space_branch']['a'], 3)
        self.assertEqual(rows['rle_space_branch']['b'], 1)
        self.assertEqual(
            rows['rle_space_branch']['delta'], -2)
        self.assertEqual(
            report['compare']['summary']['executed'], 1)


class TestMasks(TempMixin, unittest.TestCase):
    def test_valid_gold_image(self):
        report = m.analyze(
            self.write_fixture('a.trace', ALL_TRACE),
            masks_path=self.write_masks())
        masks = report['masks']
        self.assertTrue(masks['ok'])
        self.assertTrue(masks['size_ok'])
        self.assertEqual(
            [w['actual'] for w in masks['words']],
            ['be', 'bf', '40'])

    def test_wrong_mask_byte(self):
        masks = m.read_masks(self.write_masks(
            {0o76316: 0xbe}))
        self.assertFalse(masks['ok'])
        self.assertFalse(masks['words'][1]['ok'])
        self.assertEqual(
            masks['words'][1]['expected'], 'bf')

    def test_short_image(self):
        path = os.path.join(self.make_temp_dir(),
                            'short.bin')
        with open(path, 'wb') as handle:
            handle.write(b'\xbe' * 6)
        masks = m.read_masks(path)
        self.assertFalse(masks['size_ok'])
        self.assertEqual(
            masks['words'][2]['actual'], None)

    def test_word_offset_decoding(self):
        path = self.write_masks({0o76317: 0x41})
        masks = m.read_masks(path)
        self.assertEqual(masks['words'][2]['actual'], '41')
        self.assertEqual(masks['words'][0]['actual'], 'be')

    def test_real_gold_if_present(self):
        if not GOLD.is_file():
            self.skipTest('gold zone image absent')
        masks = m.read_masks(str(GOLD))
        self.assertTrue(masks['ok'])
        self.assertEqual(masks['size'], 6144)


class TestCheck(TempMixin, unittest.TestCase):
    def report(self, text=ALL_TRACE):
        return m.analyze(
            self.write_fixture('a.trace', text))

    def test_check_ok_on_valid_trace(self):
        result = m.check(self.report())
        self.assertTrue(result['ok'])
        self.assertEqual(result['violations_total'], 0)
        self.assertEqual(result['violations'], [])

    def test_check_flags_negative_count(self):
        report = self.report()
        report['counters']['descriptor_write'] = -1
        result = m.check(report)
        self.assertFalse(result['ok'])
        kinds = set(v['invariant']
                    for v in result['violations'])
        self.assertIn('no_negative_counts', kinds)

    def test_check_flags_descriptor_bound(self):
        report = self.report()
        report['counters']['descriptor_write'] = (
            m.DESC_WRITE_MAX + 1)
        result = m.check(report)
        kinds = set(v['invariant']
                    for v in result['violations'])
        self.assertIn('descriptor_write_bound', kinds)

    def test_check_flags_missing_classifier(self):
        report = self.report(op(0o06061, 'atx'))
        result = m.check(report)
        kinds = set(v['invariant']
                    for v in result['violations'])
        self.assertIn('classifier_present', kinds)

    def test_check_flags_out_of_range_dd_pc(self):
        report = self.report(
            'DD pc=777777L z=0144\n' + ALL_TRACE)
        result = m.check(report)
        kinds = set(v['invariant']
                    for v in result['violations'])
        self.assertIn('pc_range', kinds)
        self.assertEqual(report['summary'][
            'parse_violations_total'], 1)

    def test_check_flags_bad_masks(self):
        report = m.analyze(
            self.write_fixture('a.trace', ALL_TRACE),
            masks_path=self.write_masks(
                {0o76315: 0x00}))
        result = m.check(report)
        kinds = set(v['invariant']
                    for v in result['violations'])
        self.assertIn('mask_words', kinds)

    def test_check_both_compare_sides(self):
        left = self.write_fixture('a.trace', ALL_TRACE)
        right = self.write_fixture(
            'b.trace', op(0o06061, 'atx'))
        report = m.analyze(left, right)
        result = m.check(report)
        kinds = set(v['invariant']
                    for v in result['violations'])
        self.assertIn('classifier_present', kinds)
        sides = set(v['side']
                    for v in result['violations'])
        self.assertEqual(sides, {'b'})

    def test_check_truncates_long_violation_list(self):
        text = 'DD pc=777777L z=0144\n' * 35 + ALL_TRACE
        result = m.check(self.report(text))
        self.assertEqual(
            result['violations_total'], 35)
        self.assertEqual(len(result['violations']),
                         m.VIOLATION_N)
        self.assertEqual(result['truncated'], 5)


class TestCli(TempMixin, unittest.TestCase):
    def setUp(self):
        self.trace = self.write_fixture(
            'a.trace', ALL_TRACE)

    def test_cli_help(self):
        code, out, err = run_cli(['--help'])
        self.assertEqual(code, 0)
        self.assertIn('--compare', out)
        self.assertIn('--masks-from', out)
        self.assertIn('--check', out)

    def test_cli_text_exit_zero(self):
        code, out, err = run_cli([self.trace])
        self.assertEqual(code, 0)
        self.assertIn('V78 FSM PROBE', out)
        self.assertEqual(err, '')

    def test_cli_json_schema(self):
        code, out, err = run_cli(
            [self.trace, '--format', 'json'])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        for key in ('sources', 'tolerance', 'states',
                    'counters', 'summary', 'parse',
                    'masks', 'compare'):
            self.assertIn(key, payload)
        self.assertIsNone(payload['compare'])
        self.assertNotIn('check', payload)

    def test_cli_check_json(self):
        code, out, err = run_cli(
            [self.trace, '--check', '--format', 'json'])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload['check']['ok'])

    def test_cli_check_exit_one(self):
        path = self.write_fixture(
            'bad.trace', op(0o06061, 'atx'))
        code, out, err = run_cli(
            [path, '--check', '--format', 'json'])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertFalse(payload['check']['ok'])

    def test_cli_compare_text(self):
        other = self.write_fixture('b.trace', ALL_TRACE)
        code, out, err = run_cli(
            [self.trace, '--compare', other])
        self.assertEqual(code, 0)
        self.assertIn('СЧЁТЧИКИ', out)
        counter_lines = [
            row for row in out.splitlines()
            if row.strip().startswith(
                'classifier_mask_a')]
        self.assertEqual(len(counter_lines), 1)
        self.assertIn('+0', counter_lines[0])

    def test_cli_compare_json_deltas(self):
        other = self.write_fixture('b.trace', ALL_TRACE)
        code, out, err = run_cli(
            [self.trace, '--compare', other,
             '--format', 'json'])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        rows = payload['compare']['counter_delta']
        self.assertEqual(len(rows),
                         len(m.COUNTER_MAP))
        self.assertTrue(all(r['delta'] == 0
                            for r in rows))

    def test_cli_masks_from(self):
        masks = self.write_masks()
        code, out, err = run_cli(
            [self.trace, '--masks-from', masks,
             '--format', 'json'])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload['masks']['ok'])

    def test_cli_bad_tolerance_exit_two(self):
        code, out, err = run_cli(
            [self.trace, '--tolerance', '-1'])
        self.assertEqual(code, 2)
        self.assertIn('tolerance', err)

    def test_cli_missing_file_exit_two(self):
        code, out, err = run_cli(
            [self.trace + '.absent'])
        self.assertEqual(code, 2)
        self.assertIn('error', err)

    def test_cli_missing_args_exit_two(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)

    def test_inputs_are_not_modified(self):
        other = self.write_fixture('b.trace', ALL_TRACE)
        masks = self.write_masks()

        def snapshot(path):
            with open(path, 'rb') as handle:
                return (handle.read(),
                        os.stat(path).st_mtime_ns)

        before = [snapshot(p)
                  for p in (self.trace, other, masks)]
        m.analyze(self.trace, other,
                  masks_path=masks)
        run_cli([self.trace, '--compare', other,
                 '--masks-from', masks, '--check'])
        after = [snapshot(p)
                 for p in (self.trace, other, masks)]
        self.assertEqual(before, after)


class TestStreaming(TempMixin, unittest.TestCase):
    def guarded_run(self, texts, path_a, path_b=None):
        with mock.patch.object(
                m, 'open_trace',
                side_effect=lambda p: Guarded(texts[p])):
            return m.analyze(path_a, path_b)

    def test_never_bulk_reads_trace(self):
        path = self.write_fixture(
            'a.trace', ALL_TRACE)
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
        report = self.guarded_run({path: text}, path)
        self.assertEqual(
            report['summary']['executed'], len(ALL_OPS))

    def test_guarded_compare_matches_plain(self):
        left = self.write_fixture('a.trace', ALL_TRACE)
        right = self.write_fixture('b.trace', ALL_TRACE)
        texts = {}
        for path in (left, right):
            with open(path, encoding='utf-8') as handle:
                texts[path] = handle.read()
        plain = m.analyze(left, right)
        guarded = self.guarded_run(texts, left, right)
        self.assertEqual(plain['counters'],
                         guarded['counters'])
        self.assertEqual(
            plain['compare']['counter_delta'],
            guarded['compare']['counter_delta'])


@unittest.skipUnless(
    os.path.isfile(P2A) and os.path.isfile(P2B),
    'real P2 traces not present')
class TestIntegration(unittest.TestCase):
    def test_real_trace_counters(self):
        report = m.analyze(P2A)
        counters = report['counters']
        self.assertGreater(
            counters['classifier_mask_a'], 0)
        self.assertGreater(
            counters['classifier_mask_b'], 0)
        self.assertGreater(
            counters['rle_space_branch'], 0)
        self.assertGreater(
            counters['rle_nonspace_branch'], 0)
        self.assertGreater(
            counters['descriptor_write'], 0)
        self.assertEqual(
            report['summary']['assigned'],
            sum(counters.values()))

    def test_real_compare_p2(self):
        code, out, err = run_cli(
            [P2A, '--compare', P2B, '--check',
             '--format', 'json'])
        self.assertEqual(code, 0)
        self.assertEqual(err, '')
        payload = json.loads(out)
        rows = payload['compare']['counter_delta']
        self.assertEqual(len(rows), len(m.COUNTER_MAP))
        self.assertTrue(all(
            isinstance(r['delta'], int) for r in rows))
        self.assertTrue(payload['check']['ok'])
        code, text_out, _ = run_cli(
            [P2A, '--compare', P2B])
        self.assertEqual(code, 0)
        self.assertTrue(all(
            len(line) <= 60
            for line in text_out.splitlines()
            if '/var/tmp/' not in line))


if __name__ == '__main__':
    unittest.main()
