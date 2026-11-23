#!/usr/bin/env python3
"""Тесты tools/v78_deckgen.py.

Синтетические тесты не пишут в репозиторий. Два integration
теста пропускаются, если скретч-шаблон или эталон отсутствуют.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import v78_deckgen as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = TOOLS / 'v78_deckgen.py'
MANIFEST = ROOT / 'tests' / 'decks' / 'manifest.json'
TEMPLATE = Path('/var/tmp/v78-syntax/token-exp/P1a.job.b6')


class Synthetic(unittest.TestCase):
    """Тесты на манифесте, мутациях, guard и CLI."""

    @classmethod
    def setUpClass(cls):
        cls.cases = m.load_manifest(MANIFEST)

    def case(self, cid):
        for case in self.cases:
            if case['id'] == cid:
                return case
        self.fail('нет случая ' + cid)

    def test_01_manifest_is_list_of_120(self):
        self.assertEqual(len(self.cases), 120)

    def test_02_ids_unique(self):
        ids = [c['id'] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_03_required_keys(self):
        for case in self.cases:
            for key in ('id', 'group', 'base_deck',
                        'mutation', 'expect'):
                self.assertIn(key, case)
            for key in ('kind', 'value'):
                self.assertIn(key, case['mutation'])
            for key in ('feature', 'note'):
                self.assertIn(key, case['expect'])

    def test_04_group_counts(self):
        groups = {}
        for case in self.cases:
            groups[case['group']] = groups.get(
                case['group'], 0) + 1
        self.assertEqual(groups['prior-token'], 8)
        self.assertEqual(groups['prior-column'], 9)
        self.assertEqual(groups['prior-char'], 32)
        self.assertEqual(groups['prior-1967'], 11)
        self.assertEqual(groups['pair'], 60)

    def test_05_all_dimensions_mutated(self):
        kinds = set(c['mutation']['kind']
                    for c in self.cases)
        self.assertTrue(set(m.DIMS).issubset(kinds))

    def test_06_all_pairs_covered(self):
        self.assertEqual(m.pairs_missing(self.cases), [])

    def test_07_all_pairs_detects_gap(self):
        subset = [dict(c, dims={}) for c in self.cases]
        self.assertTrue(m.pairs_missing(subset))

    def test_08_normalize_character_class(self):
        case = self.case('CD-M')
        self.assertEqual(m.normalize(case),
                         ('character_class', 'digit'))
        self.assertEqual(m.normalize(self.case(
            'R1A')), None)

    def test_09_leading_space_one_byte(self):
        base = m.BASE_DECK
        on = m.deck_bytes(self.case('P1a'))
        off = m.deck_bytes(self.case('P1b'))
        self.assertEqual(on, base)
        self.assertEqual(len(off), len(base) - 1)

    def test_10_label_separator_one_byte(self):
        a = m.deck_bytes(self.case('P2a'))
        b = m.deck_bytes(self.case('P2b'))
        self.assertEqual(len(a), len(b))
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        self.assertEqual(len(diff), 1)

    def test_11_comment_separator_one_byte(self):
        a = m.deck_bytes(self.case('P3a'))
        b = m.deck_bytes(self.case('P3b'))
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        self.assertEqual(len(diff), 1)
        self.assertEqual(a[diff[0]], ord(';'))
        self.assertEqual(b[diff[0]], ord(','))

    def test_12_label_length(self):
        a = m.deck_bytes(self.case('P4a')).decode('utf-8')
        b = m.deck_bytes(self.case('P4b')).decode('utf-8')
        self.assertIn('ZLBL16', a)
        self.assertIn('ZLBL167', b)
        self.assertNotIn('ZLBL1 ', a.split('\n')[21])

    def test_13_token_column(self):
        for col in ('1', '3', '30'):
            case = next(c for c in self.cases
                        if c['mutation']['kind'] ==
                        'token_column'
                        and c['mutation']['value'] == col)
            line = m.deck_bytes(case).decode(
                'utf-8').split('\n')[21]
            self.assertEqual(len(line), 41)
            self.assertIn('QQQQ', line)

    def test_14_character_class_fields(self):
        for cid in ('CD-M', 'CD-O', 'CD-R', 'CD-C'):
            line = m.deck_bytes(self.case(cid)).decode(
                'utf-8').split('\n')[21]
            self.assertEqual(line.count('7'), 1)

    def test_15_macro_params(self):
        seen = {}
        for case in self.cases:
            if case['mutation']['kind'] == 'macro_params':
                seen[case['mutation']['value']] = True
                text = m.deck_bytes(case).decode('utf-8')
                self.assertIn('∧М ZMAC01', text)
        self.assertTrue(set(seen).issubset(
            set(m.DIMS['macro_params'])))

    def test_16_macro_body_line_count(self):
        base_n = len(m.BASE_DECK.decode(
            'utf-8').split('\n'))
        for value in ('1', '3', '6'):
            case = next(c for c in self.cases
                        if c['mutation']['kind'] ==
                        'macro_body'
                        and c['mutation']['value'] == value)
            text = m.deck_bytes(case).decode('utf-8')
            self.assertEqual(len(text.split('\n')),
                             base_n + int(value) - 1)

    def test_17_nesting_levels(self):
        base_n = len(m.BASE_DECK.decode(
            'utf-8').split('\n'))
        for value, delta in (('0', -3), ('1', 0), ('2', 3)):
            case = next(c for c in self.cases
                        if c['mutation']['kind'] == 'nesting'
                        and c['mutation']['value'] == value)
            text = m.deck_bytes(case).decode('utf-8')
            self.assertEqual(len(text.split('\n')),
                             base_n + delta)

    def test_18_line_kind(self):
        for value in m.DIMS['line_kind']:
            case = next(c for c in self.cases
                        if c['mutation']['kind'] ==
                        'line_kind'
                        and c['mutation']['value'] == value)
            text = m.deck_bytes(case).decode('utf-8')
            self.assertIn(m.KIND_LINE[value], text)

    def test_19_directive(self):
        for value in m.DIMS['directive']:
            case = next(c for c in self.cases
                        if c['mutation']['kind'] ==
                        'directive'
                        and c['mutation']['value'] == value)
            text = m.deck_bytes(case).decode('utf-8')
            self.assertIn(value + '^', text)

    def test_20_custom_prior(self):
        self.assertIn('ZL    BL1', m.deck_bytes(
            self.case('R3A')).decode('utf-8'))
        self.assertIn(':ZOPC1', m.deck_bytes(
            self.case('R1B')).decode('utf-8'))

    def test_21_all_decks_are_utf8(self):
        for case in self.cases:
            data = m.deck_bytes(case)
            self.assertIsInstance(data, bytes)
            self.assertIn('ЕКОНЕЦ',
                          data.decode('utf-8'))

    def test_22_determinism(self):
        self.assertEqual(m.plan(self.cases),
                         m.plan(self.cases))

    def test_23_base_md5(self):
        self.assertEqual(m.check_all(self.cases)[
            'base_md5'], '0681dd780329790f8de0601d94ff10d2')

    def test_24_guard_refuses(self):
        with self.assertRaises(m.GuardError):
            m.guard_path('/usr/local/share/besm6')
        with self.assertRaises(m.GuardError):
            m.guard_path('/usr/local/share/besm6/2048')

    def test_25_guard_allows_scratch(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(m.guard_path(tmp).startswith(
                '/tmp') or m.guard_path(tmp).startswith(
                '/var/tmp'))

    def test_26_emit_writes_only_to_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            names = m.emit(self.cases, tmp)
            self.assertEqual(len(names), 120)
            files = sorted(os.listdir(tmp))
            self.assertEqual(sorted(names), files)
            self.assertEqual((Path(tmp) / 'P1a.job.b6'
                              ).read_bytes(),
                             m.deck_bytes(self.case('P1a')))

    def test_27_emit_refuses_protected(self):
        with self.assertRaises(m.GuardError):
            m.emit(self.cases, '/usr/local/share/besm6')

    def test_28_cli_help(self):
        result = self.run_cli('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('--emit', result.stdout)

    def test_29_cli_default_text(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertIn('P1a', result.stdout)
        self.assertIn('prior-token', result.stdout)

    def test_30_cli_json_format(self):
        result = self.run_cli('--format', 'json')
        self.assertEqual(result.returncode, 0)
        rows = json.loads(result.stdout)
        self.assertEqual(len(rows), 120)
        self.assertIn('md5', rows[0])

    def test_31_cli_check(self):
        result = self.run_cli('--check', '--format', 'json')
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report['pairs_missing'], 0)
        self.assertEqual(report['violations'], [])

    def test_32_cli_malformed_manifest(self):
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json',
                encoding='utf-8', delete=False) as handle:
            json.dump({'not': 'a list'}, handle)
            path = handle.name
        try:
            result = self.run_cli('--manifest', path)
            self.assertEqual(result.returncode, 2)
            self.assertIn('ERROR', result.stderr)
        finally:
            os.unlink(path)

    def test_33_duplicate_id_rejected(self):
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json',
                encoding='utf-8', delete=False) as handle:
            bad = [dict(c) for c in self.cases[:2]]
            bad[1]['id'] = bad[0]['id']
            json.dump(bad, handle)
            path = handle.name
        try:
            with self.assertRaises(m.DeckError):
                m.load_manifest(path)
        finally:
            os.unlink(path)

    def test_34_reference_md5_values(self):
        self.assertEqual(m.check_reference()['images'], {
            '2048': 'ok', '2053': 'ok',
            '2099': 'ok', '2248': 'ok'})

    @staticmethod
    def run_cli(*args):
        return subprocess.run(
            [sys.executable, str(SCRIPT)] + list(args),
            capture_output=True, text=True, cwd=str(ROOT))


class Integration(unittest.TestCase):
    """Два теста на внешние артефакты, пропуск при отсутствии."""

    def test_01_original_template_if_present(self):
        if not TEMPLATE.is_file():
            self.skipTest('скретч-шаблон P1a отсутствует')
        data = TEMPLATE.read_bytes()
        self.assertIn(b'ZLBL1', data)
        self.assertTrue(440 <= len(data) <= 470)

    def test_02_reference_images_if_present(self):
        if not Path('/usr/local/share/besm6').is_dir():
            self.skipTest('эталонные образы недоступны')
        report = m.check_reference()
        self.assertTrue(report['guard_refuses_reference'])
        self.assertNotIn('mismatch',
                         report['images'].values())


if __name__ == '__main__':
    unittest.main()
