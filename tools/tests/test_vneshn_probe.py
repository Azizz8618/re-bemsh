#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты tools/vneshn_probe.sh (парсер листинга, сверка, размещение).

Запуск: python3 -m unittest tools/tests/test_vneshn_probe.py -v
"""

import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TOOL = os.path.join(TOOLS, 'vneshn_probe.sh')

BASE = '/tmp/.private/azizz/vneshn-probe'


class VneshnProbeTest(unittest.TestCase):

    def setUp(self):
        os.makedirs(BASE, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='vneshn-test-', dir=BASE)
        self.d = self.tmp.name
        self.env = dict(os.environ)
        self.env['VNESHN_PROBE_WORK'] = self.d

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data, binary=False):
        path = os.path.join(self.d, name)
        with open(path, 'wb' if binary else 'w',
                  encoding=None if binary else 'utf-8') as fh:
            fh.write(data)
        return path

    def run_tool(self, *args, env=None):
        return subprocess.run(
            ['bash', TOOL] + list(args), env=env or self.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)

    def json_out(self, *args):
        result = self.run_tool(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    # (a) Задание: комментарии отбрасываются, каждая строка получает '^'.
    def test_job_drops_comments_and_appends_caret(self):
        be = self.write('src.be', '* комментарий\nZ0147   СТАРТ 1\n'
                                 '        Е\n        ФИНИШ\n')
        result = self.run_tool('job', be)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertNotIn('* комментарий^', lines)
        self.assertIn('Z0147   СТАРТ 1^', lines)
        self.assertIn('        Е^', lines)
        self.assertIn('        ФИНИШ^', lines)
        self.assertEqual(lines[0], 'шифр 419999^')
        self.assertEqual(lines[-1], '_$ЕКОНЕЦ')

    # (b) Сводка листинга с латинскими омоглифами разбирается верно.
    def test_parse_listing_homoglyph_summary(self):
        listing = self.write(
            'listing.out',
            'ДЛИHA ПPOГ=02000 BXOДH=00001 BHEШH=00002 '
            'ЧИCЛO METOK=00451\n'
            'ЧИCЛO OШИБOK=0000. MAKC CEPЬEЗH=0.\n')
        data = self.json_out('parse', listing)
        self.assertEqual(data['errors'], 0)
        self.assertEqual(data['program_length_octal'], '02000')
        self.assertEqual(data['vhodn'], 1)
        self.assertEqual(data['vneshn'], 2)
        self.assertEqual(data['listing_lines'], 2)

    # (c) Ненулевое число ошибок транслятора фиксируется.
    def test_parse_listing_error_count(self):
        listing = self.write('listing.out', 'ЧИCЛO OШИБOK=0001.\n')
        data = self.json_out('parse', listing)
        self.assertEqual(data['errors'], 1)
        self.assertIsNone(data['program_length_octal'])
        self.assertIsNone(data['vhodn'])

    # (d) Побайтовая сверка: совпадение и одно отличие.
    def test_compare_identical_and_single_byte_diff(self):
        gold = self.write('gold.bin', bytes(range(12)) * 1, binary=True)
        same = self.write('same.bin', bytes(range(12)), binary=True)
        diff = bytearray(range(12))
        diff[7] = 0xFF
        other = self.write('other.bin', bytes(diff), binary=True)
        ok = self.json_out('compare', gold, same)
        self.assertTrue(ok['identical'])
        self.assertEqual(ok['matched_bytes'], 12)
        self.assertEqual(ok['different_bytes'], 0)
        bad = self.json_out('compare', gold, other)
        self.assertFalse(bad['identical'])
        self.assertEqual(bad['matched_bytes'], 11)
        self.assertEqual(bad['different_bytes'], 1)
        self.assertEqual(bad['first_different_word'], 1)

    # (e) Из листинга извлекается объектное слово и пишется silver.bin.
    def test_extract_word_from_listing(self):
        word = '0000000100000002'
        # Парсер читает адрес из фиксированных колонок 25-29 листинга.
        listing = self.write(
            'listing.out', ' ' * 25 + '00001 ' + word + '\n')
        expected = int(word, 8).to_bytes(6, 'big')
        gold = self.write('gold.bin', expected, binary=True)
        silver = os.path.join(self.d, 'silver.bin')
        data = self.json_out('extract', listing, gold, silver)
        self.assertEqual(data['words'], 1)
        self.assertEqual(data['matched_words'], 1)
        self.assertEqual(data['bad_words'], 0)
        with open(silver, 'rb') as fh:
            self.assertEqual(fh.read(), expected)

    # (f) Три размещения вставляют директиву в нужное место.
    def test_variant_placements(self):
        src = self.write(
            'src.be',
            '* шапка\nZ0147   СТАРТ 1\n        Е\n        М\n'
            '        ЗП              ,слово 1\n        ФИНИШ\n')
        for place, anchor in (('before-start', 'Z0147   СТАРТ 1'),
                              ('after-m', '        М'),
                              ('before-finish', '        ФИНИШ')):
            result = self.run_tool('variant', src, '0147', 'B', 't' + place,
                                   place, 'NEWX ВНЕШН MBE.NEWX')
            self.assertEqual(result.returncode, 0, result.stderr)
            path = result.stdout.strip()
            with open(path, encoding='utf-8') as fh:
                lines = fh.read().splitlines()
            i = lines.index('NEWX ВНЕШН MBE.NEWX')
            j = lines.index(anchor)
            if place == 'before-start':
                self.assertEqual(i, j - 1)
            elif place == 'after-m':
                self.assertEqual(i, j + 1)
            else:
                self.assertEqual(i, j - 1)
        with open(src, encoding='utf-8') as fh:
            self.assertNotIn('ВНЕШН', fh.read())

    # (g) Guard отказывается работать с настоящим каталогом образов.
    def test_guard_refuses_real_image_directory(self):
        env = dict(self.env)
        env['VNESHN_PROBE_WORK'] = '/usr/local/share/besm6'
        be = self.write('src.be', 'Z0147   СТАРТ 1\n        ФИНИШ\n')
        result = self.run_tool('job', be, env=env)
        self.assertEqual(result.returncode, 3)
        self.assertIn('REFUSE', result.stderr)

    # (h) probe не принимает исходник вне рабочего каталога.
    def test_probe_refuses_external_source(self):
        result = self.run_tool('probe', '/tmp/outside.be', '0147', 'B', 'x')
        self.assertEqual(result.returncode, 3)
        self.assertIn('REFUSE', result.stderr)

    # (i) Одиночное ВНЕШН вместо ЭКВ принято.
    #     4 слова меняются корректно, METK YЖE 0П0
    #     относился к двойному объявлению, отозван.
    def test_single_vneshn_declaration_foreign_symbol(self):
        listing = self.write(
            'listing.out',
            'ЧYЖOЙ CИMBOЛ                  0261  0191 '
            'X2000  BHEШH MBE.X2000\n'
            'ЧИCЛO OШИБOK=0001. MAKC CEPЬEЗH=0.\n'
            'ДЛИHA ПPOГ=02000 BXOДH=00000 '
            'BHEШH=00001 ЧИCЛO METOK=00451\n'
            'X2000  00001CA  DAT730 00730 A\n')
        data = self.json_out('parse', listing)
        self.assertEqual(data['errors'], 1)
        self.assertEqual(data['program_length_octal'],
                         '02000')
        self.assertEqual(data['vhodn'], 0)
        self.assertEqual(data['vneshn'], 1)
        with open(listing, encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('ЧYЖOЙ CИMBOЛ', text)
        self.assertIn('X2000  00001CA', text)
        self.assertNotIn('METK YЖE 0П0', text)

        # Адреса 4 ссылок ПБ X2000 из analysis/ §5.
        fill = int('0300200002200000', 8).to_bytes(6, 'big')
        gold = bytearray(fill * 1024)
        silver = bytearray(gold)
        bad_words = (0o1236, 0o1276, 0o1310, 0o1314)
        for w in bad_words:
            silver[w * 6 + 4] ^= 0x0F
            silver[w * 6 + 5] ^= 0xF0
        gp = self.write('gold.bin', bytes(gold),
                        binary=True)
        sp = self.write('silver.bin', bytes(silver),
                        binary=True)
        res = self.json_out('compare', gp, sp)
        self.assertEqual(res['matched_bytes'], 6136)
        self.assertEqual(res['different_bytes'], 8)
        self.assertEqual(res['first_different_word'],
                         0o1236)
        diffs = [i for i in range(res['compared_bytes'])
                 if gold[i] != silver[i]]
        self.assertEqual({i // 6 for i in diffs},
                         set(bad_words))


if __name__ == '__main__':
    unittest.main()
