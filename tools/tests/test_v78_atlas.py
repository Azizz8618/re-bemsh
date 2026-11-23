#!/usr/bin/env python3
"""Tests for tools/v78_atlas.py.

Synthetic event fixtures are written to temp files. Two
integration tests skip when no event fixtures from the
runner are present. Temp dirs fall back to the repo root.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v78_atlas as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
_HOLDERS = []


def ev(n, pc, mn='uza', kind='exec', phase='RLE',
       operand='76230', acc='0'):
    """Build one shared-schema event."""
    return {'n': n, 'kind': kind, 'pc': pc, 'mn': mn,
            'operand': operand, 'acc': acc, 'phase': phase}


def text(rows):
    """Serialize events as JSONL text."""
    return ''.join(json.dumps(row) + '\n' for row in rows)


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


def find_real_fixtures():
    """Locate event fixtures produced by the runner."""
    bases = (
        ROOT / 'tests' / 'decks' / 'events',
        ROOT / 'tools' / 'tests' / 'fixtures' / 'events',
        Path('/var/tmp/v78-runner'),
        Path('/var/tmp/v78-syntax/events'),
    )
    found = []
    for base in bases:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*.jsonl')):
            found.append(str(path))
    return found


REAL_FIXTURES = find_real_fixtures()


class TempMixin:
    """Temp dir that works if the temp fs is full."""

    def make_temp_dir(self):
        bases = (None, str(ROOT))
        for base in bases:
            try:
                holder = tempfile.TemporaryDirectory(
                    prefix='v78atlas-', dir=base)
            except OSError:
                continue
            if hasattr(self, 'addCleanup'):
                self.addCleanup(holder.cleanup)
            else:
                _HOLDERS.append(holder)
            return holder.name
        self.fail('no writable temp directory')

    def write_fixture(self, name, rows):
        path = os.path.join(self.make_temp_dir(), name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text(rows))
        return path

    def raw_fixture(self, name, body):
        path = os.path.join(self.make_temp_dir(), name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(body)
        return path

    def pair(self, rows_a, rows_b):
        return (self.write_fixture('a.jsonl', rows_a),
                self.write_fixture('b.jsonl', rows_b))


class TestCli(TempMixin, unittest.TestCase):
    def test_help(self):
        code, out, err = run_cli(['--help'])
        self.assertEqual(code, 0)
        self.assertIn('usage', out)
        self.assertIn('--catalog', out)

    def test_missing_positional(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)
        self.assertIn('required', err)

    def test_only_one_positional(self):
        path = self.write_fixture(
            'a.jsonl', [ev(1, '076505')])
        code, out, err = run_cli([path])
        self.assertEqual(code, 2)

    def test_missing_file(self):
        path = self.write_fixture(
            'a.jsonl', [ev(1, '076505')])
        code, out, err = run_cli(
            [path, path + '.absent'])
        self.assertEqual(code, 2)
        self.assertIn('error', err)

    def test_format_json(self):
        path = self.write_fixture(
            'a.jsonl', [ev(1, '076505')])
        code, out, err = run_cli(
            [path, path, '--format', 'json'])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report['mode'], 'pair')
        self.assertIn('coverage', report)

    def test_format_text(self):
        path = self.write_fixture(
            'a.jsonl', [ev(1, '076505')])
        code, out, err = run_cli([path, path])
        self.assertEqual(code, 0)
        self.assertIn('V78', out)
        self.assertIn('ПОКРЫТИЕ СЕГМЕНТОВ', out)

    def test_malformed_json(self):
        left = self.raw_fixture('bad.jsonl', '{oops\n')
        path = self.write_fixture(
            'a.jsonl', [ev(1, '076505')])
        code, out, err = run_cli([left, path])
        self.assertEqual(code, 2)
        self.assertIn('JSON', err)

    def test_non_object_line(self):
        left = self.raw_fixture('arr.jsonl', '[1,2]\n')
        path = self.write_fixture(
            'a.jsonl', [ev(1, '076505')])
        code, out, err = run_cli([left, path])
        self.assertEqual(code, 2)
        self.assertIn('object', err)

    def test_missing_field(self):
        rows = [{'n': 1, 'kind': 'exec', 'pc': '076505'}]
        left = self.write_fixture('short.jsonl', rows)
        path = self.write_fixture(
            'a.jsonl', [ev(1, '076505')])
        code, out, err = run_cli([left, path])
        self.assertEqual(code, 2)
        self.assertIn('missing', err)

    def test_no_writes_to_inputs(self):
        left, right = self.pair(
            [ev(1, '076505')], [ev(1, '076505')])
        before = []
        for path in (left, right):
            with open(path, 'rb') as handle:
                before.append(hashlib.sha256(
                    handle.read()).hexdigest())
        run_cli([left, right, '--format', 'json'])
        for path, digest in zip((left, right), before):
            with open(path, 'rb') as handle:
                self.assertEqual(hashlib.sha256(
                    handle.read()).hexdigest(), digest)


class TestStrict(TempMixin, unittest.TestCase):
    def test_check_accepts_valid(self):
        path = self.write_fixture('a.jsonl', [
            ev(1, '076505'), ev(2, '076031')])
        code, out, err = run_cli(
            [path, path, '--check', '--format', 'json'])
        self.assertEqual(code, 0)
        self.assertEqual(err, '')

    def test_check_accepts_runner_dd(self):
        """dd events from the runner carry null fields."""
        rows = [
            {'n': 1, 'kind': 'exec', 'pc': '076505',
             'mn': 'uza', 'operand': '76230',
             'acc': None, 'phase': 'RLE'},
            {'n': 2, 'kind': 'dd', 'pc': None,
             'mn': None, 'operand': 'RD',
             'acc': None, 'phase': 'RLE'},
        ]
        path = self.write_fixture('dd.jsonl', rows)
        code, out, err = run_cli(
            [path, path, '--check', '--format', 'json'])
        self.assertEqual(code, 0)
        self.assertEqual(err, '')

    def test_check_rejects_n(self):
        rows = [ev(2, '076505'), ev(2, '076031')]
        path = self.write_fixture('a.jsonl', rows)
        code, out, err = run_cli([path, path, '--check'])
        self.assertEqual(code, 2)
        self.assertIn('increasing', err)

    def test_check_rejects_kind(self):
        rows = [ev(1, '076505', kind='jump')]
        path = self.write_fixture('a.jsonl', rows)
        code, out, err = run_cli([path, path, '--check'])
        self.assertEqual(code, 2)
        self.assertIn('kind', err)

    def test_check_rejects_phase(self):
        rows = [ev(1, '076505', phase='GHOST')]
        path = self.write_fixture('a.jsonl', rows)
        code, out, err = run_cli([path, path, '--check'])
        self.assertEqual(code, 2)
        self.assertIn('phase', err)

    def test_check_rejects_pc(self):
        rows = [ev(1, '08zzzz')]
        path = self.write_fixture('a.jsonl', rows)
        code, out, err = run_cli([path, path, '--check'])
        self.assertEqual(code, 2)
        self.assertIn('pc', err)

    def test_lenient_unknown_phase(self):
        rows = [ev(1, '076505', phase='GHOST')]
        path = self.write_fixture('a.jsonl', rows)
        report = m.compare(path, path)
        self.assertEqual(
            report['phase_counts'][0]['phase'], 'UNKNOWN')


class TestComparison(TempMixin, unittest.TestCase):
    def test_identical_no_divergence(self):
        rows = [ev(1, '076505'), ev(2, '076031')]
        left, right = self.pair(rows, rows)
        report = m.compare(left, right)
        self.assertIsNone(report['first_line_diff'])
        self.assertIsNone(report['pc_seq_diff'])
        code, out, err = run_cli([left, right])
        self.assertEqual(code, 0)

    def test_first_divergence_line(self):
        left, right = self.pair(
            [ev(1, '076505'), ev(2, '076031')],
            [ev(1, '076505'), ev(2, '076032')])
        report = m.compare(left, right)
        first = report['first_line_diff']
        self.assertEqual(first['line'], 2)
        self.assertEqual(first['a']['pc'], '76031')
        self.assertEqual(first['b']['pc'], '76032')

    def test_first_divergence_length_mismatch(self):
        left, right = self.pair(
            [ev(1, '076505')],
            [ev(1, '076505'), ev(2, '076031')])
        report = m.compare(left, right)
        first = report['first_line_diff']
        self.assertEqual(first['line'], 2)
        self.assertIsNone(first['a'])
        self.assertEqual(first['b']['pc'], '76031')

    def test_pc_seq_exec_only(self):
        rows_a = [ev(1, '076505'),
                  ev(2, '076031', kind='store'),
                  ev(3, '076031'), ev(4, '076505')]
        rows_b = [ev(1, '076505'),
                  ev(2, '076031', kind='store'),
                  ev(3, '076032'), ev(4, '076505')]
        left, right = self.pair(rows_a, rows_b)
        report = m.compare(left, right)
        seq = report['pc_seq_diff']
        self.assertEqual(seq['index'], 2)
        self.assertEqual(seq['a']['pc'], '76031')
        self.assertEqual(seq['b']['pc'], '76032')
        self.assertEqual(
            report['first_line_diff']['line'], 3)

    def test_pc_seq_length_mismatch(self):
        left, right = self.pair(
            [ev(1, '076505'), ev(2, '076031')],
            [ev(1, '076505')])
        seq = m.compare(left, right)['pc_seq_diff']
        self.assertEqual(seq['index'], 2)
        self.assertEqual(seq['a']['pc'], '76031')
        self.assertIsNone(seq['b'])

    def test_empty_files(self):
        left, right = self.pair([], [])
        report = m.compare(left, right)
        self.assertEqual(report['summary']['events_a'], 0)
        code, out, err = run_cli([left, right])
        self.assertEqual(code, 0)

    def test_delta_histogram(self):
        rows_a = [ev(1, '076505'), ev(2, '076505'),
                  ev(3, '076031')]
        rows_b = [ev(1, '076505'), ev(2, '076032'),
                  ev(3, '076032')]
        left, right = self.pair(rows_a, rows_b)
        rows = m.compare(left, right)['count_delta_top']
        by_pc = dict((row['pc'], row) for row in rows)
        self.assertEqual(by_pc['76505']['delta'], -1)
        self.assertEqual(by_pc['76031']['delta'], -1)
        self.assertEqual(by_pc['76032']['delta'], 2)
        self.assertEqual(rows[0]['pc'], '76032')

    def test_delta_top20_limit(self):
        rows_a = [ev(i + 1, '%05o' % (0o10000 + i))
                  for i in range(25)]
        rows_b = []
        left, right = self.pair(rows_a, rows_b)
        rows = m.compare(left, right)['count_delta_top']
        self.assertEqual(len(rows), 20)

    def test_one_sided_both_directions(self):
        left, right = self.pair(
            [ev(1, '076505'), ev(2, '076505'),
             ev(3, '076031')],
            [ev(1, '076505'), ev(2, '076032')])
        report = m.compare(left, right)
        self.assertEqual(
            report['only_a_top'][0]['pc'], '76031')
        self.assertEqual(
            report['only_b_top'][0]['pc'], '76032')

    def test_one_sided_top20_limit(self):
        rows_a = [ev(i + 1, '%05o' % (0o10000 + i))
                  for i in range(25)]
        left, right = self.pair(rows_a, [])
        report = m.compare(left, right)
        self.assertEqual(len(report['only_a_top']), 20)
        self.assertEqual(report['only_b_top'], [])


class TestPhases(TempMixin, unittest.TestCase):
    def test_phase_counts(self):
        rows_a = [ev(1, '076505', phase='RLE'),
                  ev(2, '076031', phase='INPUT'),
                  ev(3, '076031', phase='INPUT')]
        rows_b = [ev(1, '076505', phase='RLE'),
                  ev(2, '076031', phase='EDITOR')]
        left, right = self.pair(rows_a, rows_b)
        rows = m.compare(left, right)['phase_counts']
        by_phase = dict((r['phase'], r) for r in rows)
        self.assertEqual(by_phase['RLE']['a'], 1)
        self.assertEqual(by_phase['INPUT']['a'], 2)
        self.assertEqual(by_phase['INPUT']['b'], 0)
        self.assertEqual(by_phase['EDITOR']['b'], 1)

    def test_first_divergence_phase(self):
        left, right = self.pair(
            [ev(1, '076505', phase='BOOT'),
             ev(2, '076031', phase='RLE')],
            [ev(1, '076505', phase='BOOT'),
             ev(2, '076032', phase='INPUT')])
        self.assertEqual(
            m.compare(left, right)[
                'first_divergence_phase'], 'RLE')

    def test_first_phase_per_side(self):
        rows_a = [ev(1, '076505', phase='BOOT'),
                  ev(2, '076031', phase='RLE')]
        rows_b = [ev(1, '076505', phase='LISTING'),
                  ev(2, '076031', phase='RLE')]
        left, right = self.pair(rows_a, rows_b)
        s = m.compare(left, right)['summary']
        self.assertEqual(s['first_phase_a'], 'BOOT')
        self.assertEqual(s['first_phase_b'], 'LISTING')
        self.assertEqual(s['phases_a'], 2)


class TestSegments(TempMixin, unittest.TestCase):
    def test_all_builtin_segments(self):
        segments = m.load_segments()
        checks = (
            ('S-INPUT', '076505'),
            ('S-DISPATCH', '076031'),
            ('S-PACK', '077421'),
            ('S-MARK', '075344'),
            ('S-METKA', '075353'),
            ('S-SLOT', '04200'),
            ('S-DESCR', '06061'),
        )
        for name, text_pc in checks:
            value = m.parse_pc(text_pc)
            self.assertIn(
                name, m.segments_for(value, segments))

    def test_overlap_mark_metka(self):
        segments = m.load_segments()
        names = m.segments_for(
            m.parse_pc('075355'), segments)
        self.assertIn('S-MARK', names)
        self.assertIn('S-METKA', names)

    def test_descr_is_discrete(self):
        segments = m.load_segments()
        self.assertIn(
            'S-DESCR',
            m.segments_for(m.parse_pc('006061'), segments))
        self.assertNotIn(
            'S-DESCR',
            m.segments_for(m.parse_pc('006062'), segments))

    def test_octal_normalization(self):
        self.assertEqual(
            m.parse_pc('076505'), m.parse_pc('76505'))
        self.assertEqual(m.oct5(m.parse_pc('076505')),
                         '76505')

    def test_segment_coverage_counts(self):
        rows_a = [ev(1, '076505'), ev(2, '076505'),
                  ev(3, '075355')]
        rows_b = [ev(1, '076031'), ev(2, '075355')]
        left, right = self.pair(rows_a, rows_b)
        cov = m.compare(left, right)['coverage']
        by_name = dict((r['segment'], r)
                       for r in cov['segments'])
        self.assertEqual(by_name['S-INPUT']['a_pcs'], 1)
        self.assertEqual(by_name['S-INPUT']['a_hits'], 2)
        self.assertEqual(by_name['S-INPUT']['b_pcs'], 0)
        self.assertEqual(by_name['S-DISPATCH']['b_pcs'], 1)
        self.assertEqual(by_name['S-MARK']['a_pcs'], 1)
        self.assertEqual(by_name['S-METKA']['b_pcs'], 1)

    def test_unmapped_pcs(self):
        rows = [ev(1, '076505'), ev(2, '001234')]
        path = self.write_fixture('a.jsonl', rows)
        cov = m.compare(path, path)['coverage']
        self.assertEqual(cov['unmapped_count'], 1)
        self.assertEqual(cov['unmapped_top'], ['01234'])

    def test_custom_segments_json(self):
        spec = self.raw_fixture(
            'seg.json', json.dumps(
                {'Z-ONE': ['076505-076642']}))
        segments = m.load_segments(spec)
        self.assertEqual(
            m.segments_for(m.parse_pc('076505'), segments),
            ['Z-ONE'])

    def test_custom_segments_text(self):
        spec = self.raw_fixture(
            'seg.txt', '# comment\nZ-TWO 006061\n')
        segments = m.load_segments(spec)
        self.assertEqual(
            m.segments_for(m.parse_pc('006061'), segments),
            ['Z-TWO'])

    def test_bad_segments_range(self):
        spec = self.raw_fixture(
            'bad.txt', 'Z 076642-076505\n')
        with self.assertRaises(m.InputError):
            m.load_segments(spec)


class TestCandidates(TempMixin, unittest.TestCase):
    def test_parse_report_candidates(self):
        path = ROOT / 'analysis' / 'V78-FSM-VALIDATION.md'
        with open(path, encoding='utf-8') as handle:
            values, meta = m.parse_report_candidates(
                handle.read())
        self.assertEqual(meta['declared_total'], 84)
        self.assertGreaterEqual(meta['explicit_count'], 55)
        self.assertNotIn(m.parse_pc('040034'), values)
        self.assertNotIn(m.parse_pc('042007'), values)
        self.assertEqual(len(meta['clusters']), 7)
        self.assertIn(m.parse_pc('075344'), values)

    def test_builtin_fallback(self):
        with mock.patch.object(
                m, 'DEFAULT_REPORT', '/no/such/report.md'):
            values, meta = m.load_candidates()
        self.assertEqual(meta['source'], 'builtin')
        self.assertEqual(len(values), 64)

    def test_catalog_uncovered(self):
        folder = self.make_temp_dir()
        self.write_fixture(
            os.path.join(folder, 'f1.jsonl'),
            [ev(1, '076505'), ev(2, '076505')])
        candidates = self.raw_fixture(
            'cand.txt',
            '076505\n076031\n077421\n')
        report = m.catalog(folder, candidates)
        self.assertEqual(report['fixture_count'], 1)
        self.assertEqual(report['covered_pcs'], 1)
        self.assertEqual(report['uncovered'],
                         ['76031', '77421'])

    def test_catalog_cli(self):
        folder = self.make_temp_dir()
        self.write_fixture(
            os.path.join(folder, 'f1.jsonl'),
            [ev(1, '076505')])
        candidates = self.raw_fixture(
            'cand.txt', '076505\n076031\n')
        code, out, err = run_cli([
            '--catalog', folder,
            '--candidates', candidates,
            '--format', 'json'])
        self.assertEqual(code, 1)
        report = json.loads(out)
        self.assertEqual(report['mode'], 'catalog')
        self.assertEqual(report['uncovered'], ['76031'])

    def test_catalog_empty_dir(self):
        folder = self.make_temp_dir()
        candidates = self.raw_fixture(
            'cand.txt', '076031\n')
        report = m.catalog(folder, candidates)
        self.assertEqual(report['uncovered'], ['76031'])

    def test_catalog_all_covered(self):
        folder = self.make_temp_dir()
        self.write_fixture(
            os.path.join(folder, 'f1.jsonl'),
            [ev(1, '076031')])
        candidates = self.raw_fixture(
            'cand.txt', '076031\n')
        code, out, err = run_cli([
            '--catalog', folder,
            '--candidates', candidates])
        self.assertEqual(code, 0)
        self.assertIn('нет', out)

    def test_catalog_bad_dir(self):
        with self.assertRaises(m.InputError):
            m.catalog('/no/such/dir')

    def test_catalog_rejects_positional(self):
        code, out, err = run_cli([
            '--catalog', str(ROOT),
            '/tmp/a', '/tmp/b'])
        self.assertEqual(code, 2)

    def test_catalog_strict_bad_event(self):
        folder = self.make_temp_dir()
        self.raw_fixture(
            os.path.join(folder, 'bad.jsonl'),
            '{"n": 1, "kind": "jump", "pc": "076505", '
            '"mn": "uza", "phase": "RLE"}\n')
        candidates = self.raw_fixture(
            'cand.txt', '076031\n')
        with self.assertRaises(m.InputError):
            m.catalog(folder, candidates, strict=True)


class TestStep3Segments(TempMixin, unittest.TestCase):
    """STEP 3: extended table, overlaps and --segments."""

    def test_new_segments_registered(self):
        segments = m.load_segments()
        names = []
        for name, _, _ in segments:
            if name not in names:
                names.append(name)
        old = ('S-INPUT', 'S-DISPATCH', 'S-PACK',
               'S-MARK', 'S-METKA', 'S-SLOT',
               'S-DESCR')
        for name in old:
            self.assertIn(name, names)
        new = ('S-BRIDGE', 'S-COPY', 'S-LOOPS',
               'S-BRANCH', 'S-AREA', 'S-BOOT')
        for name in new:
            self.assertIn(name, names)
        self.assertEqual(len(names), 13)

    def test_bridge_core_pages(self):
        segments = m.load_segments()
        for pc in ('012000', '072000'):
            self.assertEqual(
                m.segments_for(m.parse_pc(pc), segments),
                ['S-BRIDGE'])

    def test_bridge_drum_pcs(self):
        segments = m.load_segments()
        pcs = ('01433', '01715', '05755', '05756',
               '06006', '06007', '01573', '01574')
        for pc in pcs:
            self.assertIn(
                'S-BRIDGE',
                m.segments_for(m.parse_pc(pc), segments))

    def test_copy_all_pcs(self):
        segments = m.load_segments()
        pcs = ('077316', '077320', '077322',
               '03461', '04754')
        for pc in pcs:
            self.assertEqual(
                m.segments_for(m.parse_pc(pc), segments),
                ['S-COPY'])

    def test_copy_distinct_from_pack(self):
        segments = m.load_segments()
        self.assertNotIn(
            'S-PACK',
            m.segments_for(m.parse_pc('077316'),
                           segments))
        self.assertNotIn(
            'S-COPY',
            m.segments_for(m.parse_pc('077421'),
                           segments))

    def test_loops_ranges(self):
        segments = m.load_segments()
        for pc in ('075000', '075016', '075750',
                   '075757'):
            self.assertEqual(
                m.segments_for(m.parse_pc(pc), segments),
                ['S-LOOPS'])
        self.assertNotIn(
            'S-LOOPS',
            m.segments_for(m.parse_pc('075020'),
                           segments))

    def test_branch_pcs(self):
        segments = m.load_segments()
        for pc in ('076141', '076147', '076161',
                   '076230'):
            self.assertEqual(
                m.segments_for(m.parse_pc(pc), segments),
                ['S-BRANCH'])
        self.assertNotIn(
            'S-BRANCH',
            m.segments_for(m.parse_pc('076123'),
                           segments))

    def test_area_discrete(self):
        segments = m.load_segments()
        for pc in ('04064', '04065', '04066'):
            self.assertEqual(
                m.segments_for(m.parse_pc(pc), segments),
                ['S-AREA'])
        self.assertEqual(
            m.segments_for(m.parse_pc('04067'),
                           segments), [])

    def test_boot_anchors(self):
        segments = m.load_segments()
        for pc in ('00110', '064000', '064077'):
            self.assertEqual(
                m.segments_for(m.parse_pc(pc), segments),
                ['S-BOOT'])
        self.assertEqual(
            m.segments_for(m.parse_pc('064100'),
                           segments), [])

    def test_phase_overlaps_parsed(self):
        rows = m.load_phase_overlaps()
        labels = [row[0] for row in rows]
        self.assertEqual(labels, ['PAGE37', 'P02000'])
        names, zones = m.overlaps_for(
            m.parse_pc('076505'), rows,
            m.load_segments())
        self.assertEqual(names, ['S-INPUT'])
        self.assertEqual(zones, ['PAGE37'])

    def test_mark_metka_reports_all(self):
        path = self.write_fixture(
            'a.jsonl', [ev(1, '075355')])
        cov = m.compare(path, path)['coverage']
        row = cov['overlap_pcs'][0]
        self.assertEqual(row['pc'], '75355')
        self.assertEqual(
            row['segments'], ['S-MARK', 'S-METKA'])
        self.assertEqual(row['zones'], [])

    def test_page37_zone_label(self):
        path = self.write_fixture(
            'a.jsonl', [ev(1, '076505')])
        cov = m.compare(path, path)['coverage']
        row = cov['overlap_pcs'][0]
        self.assertEqual(row['segments'], ['S-INPUT'])
        self.assertEqual(row['zones'], ['PAGE37'])

    def test_p02000_shared(self):
        path = self.write_fixture(
            'a.jsonl', [ev(1, '02000')])
        cov = m.compare(path, path)['coverage']
        row = cov['overlap_pcs'][0]
        self.assertEqual(row['pc'], '02000')
        self.assertEqual(row['segments'], [])
        self.assertEqual(row['zones'], ['P02000'])

    def test_overlap_text_section(self):
        path = self.write_fixture(
            'a.jsonl', [ev(1, '075355')])
        code, out, err = run_cli([path, path])
        self.assertEqual(code, 0)
        self.assertIn('ПЕРЕКРЫТИЯ PC: 1', out)
        self.assertIn('75355', out)
        self.assertIn('S-MARK,S-METKA', out)

    def test_custom_segments_cli(self):
        spec = self.raw_fixture(
            'seg.json', json.dumps(
                {'Z-CUSTOM': ['012000']}))
        path = self.write_fixture(
            'a.jsonl', [ev(1, '012000')])
        code, out, err = run_cli([
            path, path, '--segments', spec,
            '--format', 'json'])
        self.assertEqual(code, 0)
        cov = json.loads(out)['coverage']
        names = [r['segment'] for r in cov['segments']]
        self.assertEqual(names, ['Z-CUSTOM'])
        self.assertEqual(cov['unmapped_count'], 0)

    def test_custom_segments_missing_file(self):
        path = self.write_fixture(
            'a.jsonl', [ev(1, '076505')])
        code, out, err = run_cli([
            path, path, '--segments',
            path + '.noseg'])
        self.assertEqual(code, 2)
        self.assertIn('error', err)

    def test_custom_segments_overlap_logic(self):
        spec = self.raw_fixture(
            'seg.json', json.dumps(
                {'Z-A': ['075344-075401'],
                 'Z-B': ['075353-075377']}))
        path = self.write_fixture(
            'a.jsonl', [ev(1, '075355')])
        segments = m.load_segments(spec)
        report = m.compare(path, path,
                           segments=segments)
        row = report['coverage']['overlap_pcs'][0]
        self.assertEqual(
            row['segments'], ['Z-A', 'Z-B'])


class TestIntegration(TempMixin, unittest.TestCase):
    def test_real_event_pair(self):
        if len(REAL_FIXTURES) < 2:
            self.skipTest('нет event-фикстур раннера')
        report = m.compare(REAL_FIXTURES[0],
                           REAL_FIXTURES[1])
        self.assertEqual(report['mode'], 'pair')
        self.assertGreater(
            report['summary']['events_a'], 0)

    def test_real_catalog(self):
        if len(REAL_FIXTURES) < 1:
            self.skipTest('нет event-фикстур раннера')
        folder = str(Path(REAL_FIXTURES[0]).parent)
        report = m.catalog(folder)
        self.assertEqual(report['mode'], 'catalog')
        self.assertGreaterEqual(
            report['fixture_count'], 1)


if __name__ == '__main__':
    unittest.main()
