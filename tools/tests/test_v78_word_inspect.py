#!/usr/bin/env python3
"""Unit tests for tools/v78_word_inspect.py.

Fixtures are synthetic 48-bit words and tiny binary
images. One optional integration test uses a real gold
zone dump.
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
import v78_word_inspect as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / 'gold' / 'MBE-Z0152-L1.bin'


class ParseWord(unittest.TestCase):
    def test_octal_one(self):
        self.assertEqual(m.parse_word('1'), 1)

    def test_octal_sixteen(self):
        self.assertEqual(m.parse_word('2000000000000000'), 1 << 46)

    def test_hex(self):
        self.assertEqual(m.parse_word('0x40'), 0x40)

    def test_hex_upper(self):
        self.assertEqual(m.parse_word('0XBF'), 0xbf)

    def test_spaces(self):
        self.assertEqual(m.parse_word(' 0 4 0 '), 0o40)

    def test_bad_char(self):
        with self.assertRaises(ValueError):
            m.parse_word('0o777')

    def test_too_big(self):
        with self.assertRaises(ValueError):
            m.parse_word('0x1000000000000')

    def test_negative(self):
        with self.assertRaises(ValueError):
            m.parse_word('-1')


class BytesAndDecode(unittest.TestCase):
    def test_bytes_order(self):
        self.assertEqual(m.TD.bytes8(0x010203040506),
                         [1, 2, 3, 4, 5, 6])

    def test_byte_rows_count(self):
        self.assertEqual(len(m.byte_rows(0)), 6)

    def test_byte_row_formula(self):
        row = m.byte_rows(0x400000000000)[0]
        self.assertEqual(row['hex'], '0x40')

    def test_decode_keys(self):
        self.assertEqual(set(m.decode(0)), {'GOST', 'KOI7', 'TEXT', 'ITM'})

    def test_gost_rvs(self):
        text = m.decode(0x300f220f310f)['GOST']['text']
        self.assertIn('Р', text)

    def test_text_zero(self):
        self.assertEqual(m.decode(0)['TEXT']['text'], '        ')

    def test_no_glyph(self):
        info = m.decode(0xffffffffffff)['GOST']
        self.assertEqual(info['verdict'], 'НЕТ_ГЛИФА')


class GuardAndSearch(unittest.TestCase):
    def test_guard_ok(self):
        self.assertEqual(m.guard('/tmp/x'), '/tmp/x')

    def test_guard_refuses(self):
        with self.assertRaises(m.GuardError):
            m.guard('/usr/local/share/besm6/2348')

    def test_search_synthetic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, '2048')
            data = bytearray(b'\xff' * (m.ZONE_BYTES * 2))
            data[m.ZONE_BYTES + 6 * 3: m.ZONE_BYTES + 6 * 4] = \
                b'\x40\0\0\0\0\0'
            with open(path, 'wb') as handle:
                handle.write(data)
            hits = m.search_image(path, (0x400000000000).to_bytes(6, 'big'))
            self.assertEqual(hits[0]['zone'], '0001')
            self.assertEqual(hits[0]['word'], '0003')

    def test_search_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, '2048')
            with open(path, 'wb') as handle:
                handle.write(b'\xff' * m.ZONE_BYTES)
            self.assertEqual(m.search_image(path, (0x400000000000).to_bytes(6, 'big')), [])


class CLI(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = m.main(list(args))
        return rc, out.getvalue()

    def test_check_ok(self):
        rc, text = self.run_cli('--check')
        self.assertEqual(rc, 0)
        self.assertIn('OK', text)

    def test_text_output(self):
        rc, text = self.run_cli('0x40')
        self.assertEqual(rc, 0)
        self.assertIn('GOST', text)

    def test_bad_input(self):
        rc, text = self.run_cli('not-octal')
        self.assertEqual(rc, 2)

    def test_json_schema(self):
        word = m.parse_word('0x40')
        result = {'oct': '%016o' % word, 'bytes': m.byte_rows(word),
                  'decode': m.decode(word)}
        text = json.dumps(result)
        self.assertIn('GOST', text)

    def test_real_gold_word(self):
        if not GOLD.is_file():
            self.skipTest('gold zone absent')
        self.assertEqual(m.word_at(0o152, 0o317), 0x400000000000)


if __name__ == '__main__':
    unittest.main()
