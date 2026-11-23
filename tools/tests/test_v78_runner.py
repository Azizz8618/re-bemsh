#!/usr/bin/env python3
"""Tests for tools/v78_runner.py.

Synthetic runs use a fake dispak and tiny fake volumes. Two
integration tests skip if the deck or dispak is absent.
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
import v78_runner as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DECK = '/var/tmp/v78-syntax/token-exp/P1a.job.b6'
DISPAK = m.DISPAK
HOLDERS = []

TRACE = (
    'BOOT-LINE\n'
    '00110: uj 64000\n'
    '03766: atx 2250 (=0001) acc=0002\n'
    '       102251: store 2031463100000000\n'
    'DD pc=70142L r016=71706 u=43 z=0144 RD\n'
    '76600: atx 1\n'
    '76000: ntr 3\n'
    '02000: xta 6065 (=0002) acc=0013\n'
    '02000: ntr 3 (=0003) acc=0014\n'
    '04201: uj 1000\n'
)


class TempMixin:
    """Temp dir with a repo fallback if /tmp is full."""

    def make_temp_dir(self):
        for base in (None, str(ROOT)):
            try:
                holder = tempfile.TemporaryDirectory(
                    prefix='v78run-', dir=base)
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

    def fake_ref(self):
        path = self.make_temp_dir()
        for name in m.VOLUMES:
            with open(os.path.join(path, name), 'wb') as h:
                h.write(('VOL-' + name).encode('ascii'))
        return path

    def fake_dispak(self, trace=TRACE, status=0):
        path = os.path.join(self.make_temp_dir(), 'dispak')
        with open(path, 'w', encoding='utf-8') as h:
            h.write('#!/usr/bin/env python3\n')
            h.write('import sys\n')
            h.write('sys.stdout.write("LISTING\\n")\n')
            h.write('sys.stderr.write(%r)\n' % trace)
            h.write('sys.exit(%d)\n' % status)
        os.chmod(path, 0o755)
        return path

    def deck(self, name='P1a.job.b6'):
        return self.write_fixture(name, 'шифр 419999^\n')

    def run_fake(self, trace=TRACE, **kwargs):
        ref = kwargs.pop('ref_dir', None) or self.fake_ref()
        dispak = (kwargs.pop('dispak', None) or
                  self.fake_dispak(trace))
        scratch = (kwargs.pop('scratch_root', None) or
                   self.make_temp_dir())
        out = (kwargs.pop('out_dir', None) or
               self.make_temp_dir())
        deck = kwargs.pop('deck', None) or self.deck()
        return m.run_one(deck, out_dir=out, dispak=dispak,
                         ref_dir=ref, scratch_root=scratch,
                         **kwargs)


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
    """Iterable stand-in that forbids bulk reads."""

    def __init__(self, lines):
        self._it = iter(lines)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._it)

    def read(self, *args):
        raise AssertionError('read() called')

    def readlines(self, *args):
        raise AssertionError('readlines() called')

    def close(self):
        pass


class FakeProc:
    """Minimal Popen stand-in with a streamed stderr."""

    def __init__(self, lines, status=0):
        self.stderr = Guarded(lines)
        self.status = status

    def wait(self):
        return self.status


class TestClassification(unittest.TestCase):
    def test_exec_fields(self):
        got = m.classify(
            '03766: atx 2250 (=0001) acc=0002')
        self.assertEqual(got, ('exec', 0o3766, 'atx',
                               '2250 (=0001)', '0002'))

    def test_latin_mnemonics_as_printed(self):
        for word in ('apx', 'aux', 'aex', 'vlm'):
            kind, _, mn, _, _ = m.classify(
                '03766: %s 1' % word)
            self.assertEqual((kind, mn), ('exec', word))

    def test_store_six_digits_is_not_pc(self):
        kind, pc, mn, operand, acc = m.classify(
            '       102251: store 2031463100000000')
        self.assertEqual((kind, pc, mn),
                         ('store', 0o102251, 'store'))
        self.assertEqual(operand, '2031463100000000')
        self.assertIsNone(acc)

    def test_store_at_column_zero(self):
        kind, pc, _, _, _ = m.classify(
            '00000: store 0000000000000000')
        self.assertEqual((kind, pc), ('store', 0))

    def test_dd_fields(self):
        kind, pc, mn, operand, acc = m.classify(
            'DD pc=70142L r016=71706 z=0144 RD')
        self.assertEqual((kind, pc, mn),
                         ('dd', 0o70142, None))
        self.assertIn('z=0144', operand)
        self.assertNotIn('pc=', operand)
        self.assertIsNone(acc)

    def test_dd_with_leading_spaces_no_suffix(self):
        kind, pc, _, _, _ = m.classify(
            '   DD pc=00010 u=43')
        self.assertEqual((kind, pc), ('dd', 0o10))

    def test_dd_without_pc(self):
        kind, pc, _, _, _ = m.classify('DD timeout')
        self.assertEqual((kind, pc), ('dd', None))

    def test_other_line(self):
        self.assertEqual(
            m.classify('KCNT: on_pc=00000')[0], 'other')

    def test_empty_mnemonic(self):
        self.assertEqual(
            m.classify('03766:   ')[0], 'other')

    def test_acc_with_register_tail(self):
        line = ('02452: atx (17) (=0001) '
                'acc=0200000000074037 r[17]=77000')
        _, _, _, operand, acc = m.classify(line)
        self.assertEqual(acc, '0200000000074037')
        self.assertEqual(operand, '(17) (=0001)')

    def test_octstr_width(self):
        self.assertEqual(m.octstr(0o3766), '03766')
        self.assertEqual(m.octstr(0o102251), '102251')
        self.assertIsNone(m.octstr(None))


class TestPhaseMap(TempMixin, unittest.TestCase):
    def test_default_anchors(self):
        pm = m.default_phase_map()
        self.assertEqual(len(pm.anchors), 6)
        self.assertEqual(pm.current, 'BOOT')

    def test_boot_before_first_anchor(self):
        pm = m.default_phase_map()
        parser = m.StreamParser(pm)
        event = parser.feed('03766: atx 1')
        self.assertEqual(event['phase'], 'BOOT')

    def test_rload_and_rle(self):
        pm = m.default_phase_map()
        parser = m.StreamParser(pm)
        first = parser.feed('00110: uj 64000')
        second = parser.feed('76600: atx 1')
        self.assertEqual(first['phase'], 'RLOAD')
        self.assertEqual(second['phase'], 'RLE')

    def test_input_at_arap(self):
        pm = m.default_phase_map()
        parser = m.StreamParser(pm)
        event = parser.feed('76000: ntr 3')
        self.assertEqual(event['phase'], 'INPUT')

    def test_editor_and_machine_share_pc(self):
        pm = m.default_phase_map()
        parser = m.StreamParser(pm)
        editor = parser.feed('02000: xta 6065')
        machine = parser.feed('02000: ntr 3')
        self.assertEqual(editor['phase'], 'EDITOR')
        self.assertEqual(machine['phase'], 'MACHINE')

    def test_listing_and_no_backtrack(self):
        pm = m.default_phase_map()
        parser = m.StreamParser(pm)
        for line in ('02000: xta 6065', '02000: ntr 3',
                     '00110: uj 64000', '04201: uj 1000'):
            last = parser.feed(line)
        self.assertEqual(last['phase'], 'LISTING')

    def test_custom_phase_map_file(self):
        path = self.write_fake_map({
            'initial': 'BOOT',
            'anchors': [
                {'pc': '00500', 'phase': 'RLOAD'},
                {'pc': '00600', 'mn': 'uj',
                 'phase': 'LISTING'},
            ],
        })
        parser = m.StreamParser(m.load_phase_map(path))
        a = parser.feed('00500: atx 1')
        b = parser.feed('00600: vlm 1')
        c = parser.feed('00600: uj 1')
        self.assertEqual([a['phase'], b['phase'],
                          c['phase']],
                         ['RLOAD', 'RLOAD', 'LISTING'])

    def write_fake_map(self, payload):
        return self.write_fixture('phases.json',
                                  json.dumps(payload))

    def test_bare_phase_map_file(self):
        path = self.write_fixture(
            'bare.json', '{"00110": "RLOAD"}')
        parser = m.StreamParser(m.load_phase_map(path))
        self.assertEqual(
            parser.feed('00110: uj 1')['phase'], 'RLOAD')

    def test_bad_phase_map_rejected(self):
        path = self.write_fake_map({
            'anchors': [{'pc': '88888',
                         'phase': 'RLOAD'}]})
        with self.assertRaises(ValueError):
            m.load_phase_map(path)

    def test_clone_resets_state(self):
        pm = m.default_phase_map()
        pm.update(0o2000, 'ntr')
        self.assertEqual(pm.current, 'MACHINE')
        fresh = pm.clone()
        self.assertEqual(fresh.current, 'BOOT')
        self.assertEqual(fresh.cursor, 0)


class TestStreaming(TempMixin, unittest.TestCase):
    def test_events_jsonl_schema(self):
        report = self.run_fake()
        with open(report['events'], encoding='utf-8') as h:
            rows = [json.loads(line) for line in h]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(tuple(row), m.EVENT_KEYS)
            self.assertIn(row['kind'],
                          ('exec', 'store', 'dd'))

    def test_streamed_stderr_never_bulk_read(self):
        lines = TRACE.splitlines(True)
        proc = FakeProc(lines)
        with mock.patch.object(
                m.subprocess, 'Popen', return_value=proc):
            report = self.run_fake()
        data = report['data']
        self.assertEqual(data['lines'], len(lines))
        self.assertEqual(
            data['counts']['kind']['exec'], 7)

    def test_counts_and_phase_spans(self):
        data = self.run_fake()['data']
        kinds = data['counts']['kind']
        self.assertEqual((kinds['exec'], kinds['store'],
                          kinds['dd'], kinds['other']),
                         (7, 1, 1, 1))
        self.assertEqual(data['lines'], 10)
        span = data['phase_span']['EDITOR']
        self.assertEqual(span['first'], 8)
        self.assertEqual(span['last'], 8)
        self.assertEqual(
            data['phase_first']['RLOAD']['pc'], '00110')

    def test_head_is_bounded(self):
        parser = m.StreamParser(m.default_phase_map())
        for idx in range(m.HEAD_N + 5):
            parser.feed('03766: atx %d' % idx)
        self.assertEqual(len(parser.head), m.HEAD_N)
        self.assertEqual(parser.last['operand'],
                         str(m.HEAD_N + 4))

    def test_listing_is_captured(self):
        report = self.run_fake()
        with open(report['listing'], 'rb') as h:
            self.assertIn(b'LISTING', h.read())


class TestGuard(TempMixin, unittest.TestCase):
    def test_refuse_out_under_reference(self):
        ref = self.fake_ref()
        deck = self.deck()
        with self.assertRaises(m.GuardError):
            m.run_one(deck, out_dir=os.path.join(ref, 'x'),
                      dispak=self.fake_dispak(),
                      ref_dir=ref,
                      scratch_root=self.make_temp_dir())

    def test_refuse_scratch_under_reference(self):
        ref = self.fake_ref()
        with self.assertRaises(m.GuardError):
            m.run_one(self.deck(),
                      dispak=self.fake_dispak(),
                      ref_dir=ref, scratch_root=ref)

    def test_guard_detects_changed_image(self):
        state = {}

        def fake_md5(path):
            state[path] = state.get(path, 0) + 1
            if (path.endswith('2099') and
                    state[path] == 2):
                return 'deadbeef'
            return 'a' * 32

        report = self.run_fake()
        out = os.path.dirname(report['manifest'])
        with mock.patch.object(m, 'md5_file',
                               side_effect=fake_md5):
            with self.assertRaises(m.GuardError):
                self.run_fake(out_dir=out)
        with open(os.path.join(out, 'P1a.job',
                               'manifest.json'),
                  encoding='utf-8') as h:
            manifest = json.load(h)
        row = [x for x in manifest['images']
               if x['name'] == '2099'][0]
        self.assertFalse(row['same'])

    def test_md5_file_is_chunked(self):
        path = self.write_fixture(
            'blob.bin', 'x' * 3000)
        with open(path, 'rb') as h:
            expected = hashlib.md5(h.read()).hexdigest()
        with mock.patch.object(m, 'CHUNK', 7):
            self.assertEqual(m.md5_file(path), expected)


class TestManifest(TempMixin, unittest.TestCase):
    def test_manifest_structure(self):
        data = self.run_fake()['data']
        for key in ('schema', 'event_keys', 'deck',
                    'images', 'counts', 'phase_span',
                    'phase_first',
                    'head', 'last_event', 'parse',
                    'besm6_path'):
            self.assertIn(key, data)
        self.assertEqual(
            tuple(data['event_keys']), m.EVENT_KEYS)
        self.assertTrue(all(row['same']
                            for row in data['images']))
        self.assertTrue(data['besm6_path'].startswith(
            data['scratch'] + os.pathsep))

    def test_scratch_is_removed(self):
        report = self.run_fake()
        scratch = report['data']['scratch']
        self.assertFalse(os.path.exists(scratch))
        self.assertTrue(os.path.isfile(report['events']))

    def test_check_ok_on_clean_run(self):
        result = m.check(self.run_fake())
        self.assertTrue(result['ok'])
        self.assertEqual(result['violations_total'], 0)

    def test_check_flags_malformed_lines(self):
        trace = ('DD pc=XYZ z=0144\n03766:   \n'
                 '00110: uj 1\n')
        result = m.check(self.run_fake(trace=trace))
        self.assertFalse(result['ok'])
        kinds = {v['invariant']
                 for v in result['violations']}
        self.assertIn('malformed_dd_pc', kinds)
        self.assertIn('malformed_pc_line', kinds)


class TestCli(TempMixin, unittest.TestCase):
    def cli_env(self, trace=TRACE):
        ref = self.fake_ref()
        scratch = self.make_temp_dir()
        dispak = self.fake_dispak(trace)
        deck = self.deck()
        return ref, scratch, dispak, deck

    def test_cli_help(self):
        code, out, err = run_cli(['--help'])
        self.assertEqual(code, 0)
        self.assertIn('--phase-map', out)
        self.assertIn('--out', out)

    def test_cli_json(self):
        ref, scratch, dispak, deck = self.cli_env()
        with mock.patch.object(m, 'REF_DIR', ref), \
                mock.patch.object(m, 'SCRATCH_ROOT',
                                  scratch), \
                mock.patch.object(m, 'DISPAK', dispak):
            code, out, err = run_cli(
                [deck, '--format', 'json'])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload['runs']), 1)
        self.assertNotIn('check', payload)

    def test_cli_text(self):
        ref, scratch, dispak, deck = self.cli_env()
        with mock.patch.object(m, 'REF_DIR', ref), \
                mock.patch.object(m, 'SCRATCH_ROOT',
                                  scratch), \
                mock.patch.object(m, 'DISPAK', dispak):
            code, out, err = run_cli([deck])
        self.assertEqual(code, 0)
        self.assertIn('V78 RUNNER', out)
        self.assertIn('md5 эталонов: OK', out)

    def test_cli_check_exit_one(self):
        trace = 'DD pc=XYZ\n00110: uj 1\n'
        ref, scratch, dispak, deck = self.cli_env(trace)
        with mock.patch.object(m, 'REF_DIR', ref), \
                mock.patch.object(m, 'SCRATCH_ROOT',
                                  scratch), \
                mock.patch.object(m, 'DISPAK', dispak):
            code, out, err = run_cli(
                [deck, '--check', '--format', 'json'])
        self.assertEqual(code, 1)
        self.assertFalse(
            json.loads(out)['check'][0]['ok'])

    def test_cli_bad_extension_exit_two(self):
        path = self.write_fixture('deck.txt', 'x')
        code, out, err = run_cli([path])
        self.assertEqual(code, 2)
        self.assertIn('.b6', err)

    def test_cli_missing_deck_exit_two(self):
        code, out, err = run_cli(['absent.b6'])
        self.assertEqual(code, 2)
        self.assertIn('error', err)

    def test_cli_guard_exit_three(self):
        ref, scratch, dispak, deck = self.cli_env()
        with mock.patch.object(m, 'REF_DIR', ref), \
                mock.patch.object(m, 'SCRATCH_ROOT',
                                  scratch), \
                mock.patch.object(m, 'DISPAK', dispak):
            code, out, err = run_cli(
                [deck, '--out', os.path.join(ref, 'x')])
        self.assertEqual(code, 3)
        self.assertIn('guard', err)

    def test_cli_two_decks_share_no_phase_state(self):
        ref, scratch, dispak, _ = self.cli_env()
        first = self.deck('P1.job.b6')
        second = self.deck('P2.job.b6')
        with mock.patch.object(m, 'REF_DIR', ref), \
                mock.patch.object(m, 'SCRATCH_ROOT',
                                  scratch), \
                mock.patch.object(m, 'DISPAK', dispak):
            code, out, err = run_cli(
                [first, second, '--format', 'json'])
        self.assertEqual(code, 0)
        runs = json.loads(out)['runs']
        self.assertEqual(len(runs), 2)
        for run in runs:
            self.assertEqual(
                run['data']['phase_first']['RLOAD']['pc'],
                '00110')

    def test_inputs_are_not_modified(self):
        ref, scratch, dispak, deck = self.cli_env()
        before = m.md5_file(deck)
        with mock.patch.object(m, 'REF_DIR', ref), \
                mock.patch.object(m, 'SCRATCH_ROOT',
                                  scratch), \
                mock.patch.object(m, 'DISPAK', dispak):
            run_cli([deck])
        self.assertEqual(m.md5_file(deck), before)


@unittest.skipUnless(
    os.path.isfile(DECK) and os.path.isfile(DISPAK),
    'нет колоды P1a.job.b6 или dispak с DD-хуком')
class TestIntegration(TempMixin, unittest.TestCase):
    def test_real_deck_produces_fixture(self):
        out = self.make_temp_dir()
        report = m.run_one(DECK, out_dir=out)
        data = report['data']
        self.assertTrue(all(row['same']
                            for row in data['images']))
        self.assertGreater(
            data['counts']['kind'].get('exec', 0), 0)
        self.assertTrue(os.path.isfile(report['events']))
        self.assertTrue(os.path.isfile(report['listing']))

    def test_real_run_uses_copies_first(self):
        out = self.make_temp_dir()
        before = {name: m.md5_file(
            os.path.join(m.REF_DIR, name))
            for name in m.VOLUMES}
        report = m.run_one(DECK, out_dir=out)
        after = {name: m.md5_file(
            os.path.join(m.REF_DIR, name))
            for name in m.VOLUMES}
        self.assertEqual(before, after)
        path = report['data']['besm6_path']
        self.assertTrue(path.startswith(
            report['data']['scratch'] + os.pathsep))
        self.assertIn(m.REF_DIR, path)


if __name__ == '__main__':
    unittest.main()
