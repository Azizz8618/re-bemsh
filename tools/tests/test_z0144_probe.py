#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for tools/z0144_probe.py (read-only GOST probe).

Synthetic tests use temp files only. Integration tests read
gold/MBE-Z0144-L1.bin and skip when absent. No writes
to gold/, no emulator and no image access.

Run: python3 -m unittest tools/tests/test_z0144_probe.py -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import text_decode_all as T  # noqa: E402
import z0144_probe as P  # noqa: E402

GOLD = os.path.join(ROOT, 'gold', 'MBE-Z0144-L1.bin')
PROBE = os.path.join(TOOLS, 'z0144_probe.py')


def word_of(hexbytes):
    return int(hexbytes.replace(' ', ''), 16)


def write_bin(path, words):
    """Write hex strings as 6-byte words."""
    with open(path, 'wb') as handle:
        for item in words:
            handle.write(bytes.fromhex(item))


def anchored_bin(path):
    """A 1024-word bin with text at all 7 doc anchors."""
    words = ['000000000000'] * 1024
    at = {
        0o275: ['0f2d25222530', '2d3a290f2024'],
        0o314: ['2f302e233020', '2c2c200f2d25'],
        0o543: ['2f302f2b2d0f', '3220212b0f2c'],
        0o1211: ['0f2d25320f22', '352e242d0e2c'],
        0o1224: ['2e3828212a20', '0f2d20270f0f'],
        0o1434: ['2d200f2c2b0f', '2d250f2e2a2e'],
        0o1765: ['27202c000000', '27202c0f0f0f'],
    }
    for addr, pieces in at.items():
        for off, piece in enumerate(pieces):
            assert words[addr + off] == '000000000000'
            words[addr + off] = piece
    write_bin(path, words)


def run_cli(path, *extra):
    return subprocess.run(
        [sys.executable, PROBE, path] + list(extra),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True)


class DecoderTest(unittest.TestCase):

    def test_01_decode_gost_identity(self):
        """GOST bytes map 1:1, no bias or rotation."""
        self.assertEqual(
            T.decode_gost(word_of('0f2d25222530')),
            ' НЕВЕР')
        self.assertEqual(
            T.decode_gost(word_of('2f302e233020')),
            'ПРОГРА')
        self.assertEqual(
            P.hexbytes(word_of('0f2d25222530')),
            '0f2d25222530')

    def test_02_decode_all_encodings(self):
        """decode_all: 4 encodings, others noise."""
        dec = T.decode_all(word_of('0f2d25222530'))
        self.assertEqual(
            set(dec), {'GOST', 'KOI7', 'TEXT', 'ITM'})
        self.assertEqual(dec['GOST'], ' НЕВЕР')
        self.assertNotEqual(dec['KOI7'], ' НЕВЕР')
        self.assertNotEqual(dec['TEXT'], ' НЕВЕР')

    def test_03_numeric_word_rejected(self):
        """F00900 passes GOST bytes but is a number."""
        self.assertFalse(P.is_text_word(
            word_of('400000090000')))
        self.assertFalse(P.is_extension(
            word_of('400000090000')))

    def test_04_interspersed_digits(self):
        """A digit before a Cyrillic letter means a mask."""
        self.assertTrue(P.interspersed('А3ОЛ3А'))
        self.assertTrue(P.interspersed('М2В900'))
        self.assertFalse(P.interspersed('ПФГП00'))
        self.assertFalse(P.is_text_word(
            word_of('20032e2b0320')))

    def test_05_stamp_word_accepted(self):
        """Letters plus trailing digits form a stamp."""
        self.assertTrue(P.is_text_word(
            word_of('27202c000000')))
        self.assertTrue(P.is_text_word(
            word_of('2f34232f0000')))

    def test_06_extension_word(self):
        """Date suffix glues on; zero word does not."""
        self.assertTrue(P.is_extension(
            word_of('1f01000c0705')))
        self.assertFalse(P.is_extension(
            word_of('000000000000')))
        self.assertFalse(P.is_extension(
            word_of('400000090000')))

    def test_07_no_glyph_word_rejected(self):
        """A byte above 0x7f yields no GOST glyph."""
        self.assertIn(
            '\0', T.decode_gost(word_of('ff0000000000')))
        self.assertFalse(P.is_text_word(
            word_of('ff0000000000')))

    def test_08_address_format(self):
        """Word addresses use 4 octal digits."""
        self.assertEqual(P.addr(0o275), '0144.0275')
        self.assertEqual(P.addr(0), '0144.0000')
        self.assertEqual(P.addr(0o1775), '0144.1775')

    def test_09_classify_kinds(self):
        """Keyword heuristic maps text to 5 classes."""
        self.assertEqual(
            P.classify('ОШИБКА НАЗ МДЛ'), 'error')
        self.assertEqual(
            P.classify('НЕТ ВХОДН.МЕТКИ'), 'error')
        self.assertEqual(
            P.classify('***ЗП НА МЛ НЕ ОКОНЧЕНА'),
            'diagnostic')
        self.assertEqual(P.classify('ВНЕШ.МЕТКА'), 'name')
        self.assertEqual(P.classify('ПРПЛН ТАБЛ'),
                         'table')
        self.assertEqual(P.classify('ЗАМ000 КОНЕЦ'),
                         'status')
        self.assertEqual(P.classify('< НАМ'), 'unknown')


class MessageTest(unittest.TestCase):

    def test_10_synthetic_two_messages(self):
        """Two spaced messages get two spans and texts."""
        words = [word_of(x) for x in (
            '000000000000', '0f2d25222530',
            '2d3a290f2024', '000000000000',
            '2e3828212a20', '0f2d20270f0f',
            '000000000000')]
        msgs = P.find_messages(words)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(
            (msgs[0]['start_idx'], msgs[0]['end_idx']),
            (1, 2))
        self.assertEqual(msgs[0]['span'], 2)
        self.assertEqual(msgs[1]['start_idx'], 4)
        self.assertEqual(msgs[0]['text'],
                         'НЕВЕР НЫЙ АД')

    def test_11_report_counts(self):
        """Report counts words, bytes and text words."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'syn.bin')
            write_bin(path, ['000000000000'] * 16 + [
                '0f2d25222530', '2d3a290f2024',
                '000000000000'])
            rep = P.build_report(path)
        self.assertEqual(rep['size_bytes'], 114)
        self.assertEqual(rep['word_count'], 19)
        self.assertEqual(rep['message_count'], 1)
        self.assertEqual(rep['gost_word_count'], 2)
        self.assertEqual(rep['zone'], '0144')
        self.assertIsNone(rep['check'])

    def test_12_report_schema(self):
        """JSON report has all required report keys."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'syn.bin')
            write_bin(path, ['0f2d25222530',
                             '000000000000'])
            rep = P.build_report(path)
        self.assertEqual(
            set(rep), {'path', 'zone', 'size_bytes',
                       'word_count', 'message_count',
                       'gost_word_count', 'addresses',
                       'messages', 'check'})
        msg = rep['messages'][0]
        self.assertEqual(
            set(msg), {'start', 'end', 'span', 'text',
                       'kind', 'words'})
        self.assertEqual(msg['words'][0]['hex'],
                         '0f2d25222530')

    def test_13_text_render(self):
        """Text output shows counts and addresses."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'syn.bin')
            write_bin(path, ['0f2d25222530',
                             '000000000000'])
            text = P.render_text(P.build_report(path))
        self.assertIn('zone: 0144', text)
        self.assertIn('messages: 1', text)
        self.assertIn('0144.0000', text)
        self.assertIn('НЕВЕР', text)

    def test_14_multiword_join_collapses_spaces(self):
        """Padding spaces do not duplicate in text."""
        words = [word_of(x) for x in (
            '2f302e233020', '2c2c200f2d25',
            '0f3020272c25')]
        text = P.find_messages(words)[0]['text']
        self.assertNotIn('  ', text)
        self.assertIn('ПРОГРА', text)
        self.assertIn('РАЗМЕ', text)

    def test_15_empty_bin(self):
        """Zero-length input decodes to zero messages."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'empty.bin')
            open(path, 'wb').close()
            rep = P.build_report(path)
        self.assertEqual(rep['message_count'], 0)
        self.assertEqual(rep['addresses'], [])

    def test_16_anchor_constants(self):
        """Seven anchors, window, zone size are fixed."""
        self.assertEqual(len(P.ANCHOR_ADDRS), 7)
        self.assertEqual(P.ANCHOR_ADDRS[0], '0275')
        self.assertEqual(P.ANCHOR_ADDRS[-1], '1765')
        self.assertEqual(P.ZONE_SIZE, 6144)
        self.assertEqual(P.ANCHOR_WINDOW, 0o10)

    def test_17_check_pass_synthetic(self):
        """Anchored synthetic bin passes --check logic."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'anch.bin')
            anchored_bin(path)
            rep = P.build_report(path, True)
        chk = rep['check']
        self.assertTrue(chk['ok'])
        self.assertTrue(chk['size_ok'])
        self.assertEqual(chk['anchor_count'], 7)
        self.assertTrue(all(a['ok']
                            for a in chk['anchors']))
        self.assertTrue(chk['anchors'][1]['near_start'])


class CliTest(unittest.TestCase):

    def test_18_cli_help(self):
        """--help lists both formats and --check."""
        proc = subprocess.run(
            [sys.executable, PROBE, '--help'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn('usage:', proc.stdout)
        self.assertIn('--format', proc.stdout)
        self.assertIn('--check', proc.stdout)

    def test_19_cli_json(self):
        """--format json emits parseable UTF-8 JSON."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'one.bin')
            write_bin(path, ['0f2d25222530',
                             '000000000000'])
            proc = run_cli(path, '--format', 'json')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data['message_count'], 1)
        self.assertEqual(
            data['addresses'], ['0144.0000'])

    def test_20_cli_check_pass(self):
        """CLI returns 0 when all invariants hold."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'anch.bin')
            anchored_bin(path)
            proc = run_cli(path, '--check',
                           '--format', 'json')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data['check']['ok'])

    def test_21_cli_check_fail_size(self):
        """Wrong size fails the check with exit 1."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'small.bin')
            write_bin(path, ['0f2d25222530'])
            proc = run_cli(path, '--check',
                           '--format', 'json')
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertFalse(data['check']['ok'])
        self.assertFalse(data['check']['size_ok'])
        self.assertTrue(any(
            'size' in x
            for x in data['check']['failures']))

    def test_22_cli_check_fail_anchor(self):
        """6144 zero bytes fail all 7 anchor checks."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'zero.bin')
            write_bin(path, ['000000000000'] * 1024)
            proc = run_cli(path, '--check',
                           '--format', 'json')
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        chk = data['check']
        self.assertTrue(chk['size_ok'])
        self.assertFalse(any(a['ok']
                             for a in chk['anchors']))

    def test_23_cli_errors(self):
        """Bad path and bad size use exit code 2."""
        proc = run_cli('/no/such/file.bin')
        self.assertEqual(proc.returncode, 2)
        self.assertIn('z0144_probe:', proc.stderr)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'bad.bin')
            with open(path, 'wb') as handle:
                handle.write(b'\x00' * 7)
            proc = run_cli(path)
        self.assertEqual(proc.returncode, 2)
        self.assertIn('multiple', proc.stderr)

    def test_24_cli_default_text(self):
        """Without --format the CLI prints text."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'one.bin')
            write_bin(path, ['0f2d25222530'])
            proc = run_cli(path)
        self.assertEqual(proc.returncode, 0)
        self.assertIn('zone: 0144', proc.stdout)
        self.assertNotIn('"message_count"', proc.stdout)

    def test_25_no_emulator_call(self):
        """Probe imports no emulator or external tools."""
        with open(PROBE, encoding='utf-8') as handle:
            src = handle.read()
        self.assertNotIn('subprocess', src)
        self.assertNotIn('besmtool', src)
        self.assertNotIn('os.system', src)
        self.assertIn('import json', src)


@unittest.skipUnless(os.path.isfile(GOLD),
                     'gold/MBE-Z0144-L1.bin absent')
class IntegrationTest(unittest.TestCase):

    def test_26_real_bin_counts(self):
        """Real zone 0144: 6144 bytes, 32 msgs, 66 words."""
        rep = P.build_report(GOLD)
        self.assertEqual(rep['size_bytes'], 6144)
        self.assertEqual(rep['word_count'], 1024)
        self.assertEqual(rep['message_count'], 32)
        self.assertEqual(rep['gost_word_count'], 66)
        starts = rep['addresses']
        for want in ('0144.0275', '0144.0314',
                     '0144.0543', '0144.1211',
                     '0144.1224', '0144.1433',
                     '0144.1765'):
            self.assertIn(want, starts)
        first = rep['messages'][0]
        self.assertEqual(first['end'], '0144.0300')
        self.assertIn('НЕВЕР', first['text'])

    def test_27_real_bin_cli_check(self):
        """CLI --check passes on the real gold dump."""
        proc = run_cli(GOLD, '--check',
                       '--format', 'json')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        chk = data['check']
        self.assertTrue(chk['ok'])
        self.assertEqual(chk['anchor_count'], 7)
        self.assertEqual(
            [a['addr'] for a in chk['anchors']],
            ['0144.' + a for a in P.ANCHOR_ADDRS])
        texts = {m['start']: m['text']
                 for m in data['messages']}
        self.assertIn('ОШИБКА', texts['0144.1224'])
        self.assertIn('ЗОНГП=', texts['0144.1455'])
        self.assertIn('ПФГП00', texts['0144.1765'])

    def test_28_real_bin_new_strings(self):
        """New strings found by search are decoded."""
        rep = P.build_report(GOLD)
        text = '\n'.join(m['text']
                         for m in rep['messages'])
        for want in ('ШИБКА:', 'ОШ.ПК', 'Р В С',
                     'ЗОНГП=', 'АМИН', 'АМАКС',
                     'АСВОБ', 'ДЛ МДЛ', '> ДОП.'):
            self.assertIn(want, text, want)


if __name__ == '__main__':
    unittest.main()
