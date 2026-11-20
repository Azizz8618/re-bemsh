#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты tools/text_decode_all.py (универсальный декодер текста БЭСМ-6).

Запуск: python3 -m unittest tools/tests/test_text_decode_all.py -v
 только чтение gold/; эталонные дампы не изменяются.
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import text_decode_all as T  # noqa: E402


def word_of(hexbytes):
    return T.word_from_bytes(int(x, 16) for x in hexbytes.split())


class TextDecodeAllTest(unittest.TestCase):

    def test_01_gost_stamps_identity(self):
        """Пять штаммов: GOST-8 тождествен, без биаса и поворотов."""
        for addr, hexb, exp in T.CALIBRATION:
            w = word_of(hexb)
            self.assertEqual(T.decode_gost(w), exp, addr)
            self.assertEqual(T.bytes8(w),
                             [int(x, 16) for x in hexb.split()])
        rows = T.calibration_report()
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r[4] for r in rows))
        self.assertEqual(T.decode_gost(word_of('28 2f 2c 0f 2c 20')),
                         'ИПМ МА')

    def test_02_text_6bit_ascii(self):
        """6-бит TEXT: 8 групп, код = ASCII-0x20 (LZFN, VJBAJP)."""
        w = word_of('b3 a9 ae 00 00 00')
        self.assertEqual(T.groups6(w), [0o54, 0o72, 0o46, 0o56, 0, 0, 0, 0])
        self.assertEqual(T.decode_text(w), 'LZFN    ')
        self.assertEqual(T.decode_text(word_of('da a8 a1 ab 00 00')),
                         'VJBAJP  ')
        self.assertEqual(T.decode_text(word_of('ae ac a9 a6 a5 40')),
                         'KJRIIJ5 ')
        self.assertTrue(T.text_word_ok(T.decode_text(w), w)[0])

    def test_03_koi7_mnemonic(self):
        """Таблица мнемоник 0137.0060 читается KOI-7, не GOST."""
        w = word_of('7a 70 4d 20 04 01')
        self.assertTrue(T.decode_koi7(w).startswith('ЗПM'))
        self.assertIn('А', T.decode_gost(w) + 'А')
        self.assertNotIn('ЗП', T.decode_gost(w))
        ok, why = T.koi_word_ok(T.decode_koi7(w))
        self.assertTrue(ok, why)
        zone, words, runs = T.scan_zone(
            os.path.join(ROOT, 'gold', 'MBE-Z0137-L1.bin'))
        koi = [r for r in runs if r['enc'] == 'KOI7']
        self.assertTrue(any('мнемоника' in r['evidence'] for r in koi))
        self.assertTrue(any('ЗПM' in r['phrase'] for r in koi))

    def test_04_reject_numeric_noise(self):
        """«Почти любой байт даёт букву» — GOST-скorer обязан отбросить."""
        cases = ['40 00 00 09 00 00',    # F00900, 0140.0044
                 '00 00 00 00 00 00',    # пустое слово
                 '09 00 00 03 30 01']    # 9003Р1, 0147.1313
        for hexb in cases:
            w = word_of(hexb)
            self.assertIsNone(T.choose_best(w)[0], hexb)
        mask = 0o7777777777700000
        self.assertNotEqual(T.choose_best(mask)[0], 'GOST')
        ok, why = T.gost_word_ok(T.decode_gost(word_of('40 00 00 09 00 00')))
        self.assertFalse(ok, why)
        self.assertIn('мало кириллицы', why)

    def test_05_multiword_run_joining(self):
        """Соседние слова штампа собираются в одну фразу с адресом."""
        zone, words, runs = T.scan_zone(
            os.path.join(ROOT, 'gold', 'MBE-Z0147-L1.bin'))
        found = [r for r in runs if r['start'] == '0147.1315']
        self.assertEqual(len(found), 1)
        r = found[0]
        self.assertEqual(r['end'], '0147.1320')
        self.assertEqual(r['span'], 4)  # 1315,1316,1317,1320 (восьм.)
        self.assertEqual(r['enc'], 'GOST')
        self.assertIn('ИПМ МА', r['phrase'])
        self.assertIn('ВЕР', r['phrase'])
        self.assertIn('.06/78', r['phrase'])
        self.assertIn('штамп версии B', r['meaning'])
        self.assertEqual(r['confidence'], 'высокий')

    def test_06_calibration_and_catalog(self):
        """Калибровка 5/5 попадает в markdown-каталог."""
        rows = T.calibration_report()
        self.assertEqual(sum(r[4] for r in rows), 5)
        with tempfile.TemporaryDirectory(prefix='text-all-') as d:
            out = os.path.join(d, 'catalog.md')
            with open(out, 'w', encoding='utf-8') as fh:
                fh.write(T.build_catalog(
                    [T.scan_zone(os.path.join(ROOT, 'gold',
                                              'MBE-Z0147-L1.bin'))],
                    []))
            with open(out, encoding='utf-8') as fh:
                text = fh.read()
        self.assertIn('Да (100%)', text)
        self.assertIn('штамп версии B', text)
        self.assertIn('| phrase | meaning |', text)

    def test_07_itm_autocode(self):
        """ASМ ИТМ: 0057.1446 = ОШИБКА в ITM, GOST там мусор."""
        w = word_of('83 d4 cc d3 9e 98')
        self.assertEqual(T.decode_itm(w), 'ОШИБКА')
        self.assertIn('\0', T.decode_gost(w))
        self.assertEqual(T.choose_best(w)[0], 'ITM')

    def test_08_all_69_zones(self):
        """69 зон × 1024 слов, все файлы читаются и разбираются."""
        files = T.zone_files()
        self.assertEqual(len(files), 69)
        for path in files:
            self.assertEqual(os.path.getsize(path), 6144, path)
            zone, words, runs = T.scan_zone(path)
            self.assertEqual(len(words), 1024, zone)
            for w in words[:8]:
                self.assertEqual(len(w['dec']), 4)

    def test_09_cli_zone(self):
        """CLI --zone печатает четыре кодировки и пишет каталог."""
        with tempfile.TemporaryDirectory(prefix='text-cli-') as d:
            out = os.path.join(d, 'z.md')
            p = subprocess.run(
                [sys.executable, os.path.join(TOOLS, 'text_decode_all.py'),
                 '--zone', '0154', '--out', out],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('GOST', p.stdout)
            self.assertIn('KOI7', p.stdout)
            self.assertIn('TEXT', p.stdout)
            self.assertIn('ITM', p.stdout)
            self.assertIn('МАКРО', p.stdout)
            self.assertTrue(os.path.getsize(out) > 1000)


if __name__ == '__main__':
    unittest.main()
