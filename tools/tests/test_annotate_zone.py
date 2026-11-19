#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты tools/annotate_zone.py.

Запуск: python3 -m unittest tools/tests/test_annotate_zone.py -v
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
TOOL = os.path.join(TOOLS, 'annotate_zone.py')

BOM = b'\xef\xbb\xbf'

# Синтетический листинг в стиле disbesm6 (BOM + LF, метки/мнемоники/числа).
LISTING = (
    '          File: gold/MBE-Z0147-L1.bin\n'
    '         Type: Binary\n'
    '\n'
    '    0 00 000 0000 \tSTART\tзп\tSTART\n'
    '      00 123 4567 \t\tуиа\tD00641\n'
    '    1 01 24 14000 \tA00001\tуиа\t\'14000\'(М1)'
)

HEADER = (
    '* АННОТАЦИЯ ЗОНЫ (тест)\n'
    '* Числовые поля не изменяются.\n'
)


class AnnotateZoneTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='annotate-zone-')
        self.d = self.tmp.name
        self.src = os.path.join(self.d, 'src.asm')
        self.out = os.path.join(self.d, 'out.asm')
        with open(self.src, 'wb') as fh:
            fh.write(BOM + LISTING.encode('utf-8'))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text, bom=False):
        path = os.path.join(self.d, name)
        data = text.encode('utf-8')
        with open(path, 'wb') as fh:
            fh.write((BOM if bom else b'') + data)
        return path

    def run_tool(self, *extra):
        return subprocess.run(
            [sys.executable, TOOL, '--input', self.src,
             '--output', self.out] + list(extra),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)

    # (a) Полный цикл: аннотирование + обратная проверка.
    def test_roundtrip(self):
        cmap = self.write('comments.tab',
                          '0\tНАЧАЛО ПРОГРАММЫ\n'
                          '1\tВТОРАЯ КОМАНДА\n')
        hdr = self.write('header.txt', HEADER)
        r = self.run_tool('--comment-file', cmap, '--header', hdr)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.out, 'rb') as fh:
            raw = fh.read()
        self.assertTrue(raw.startswith(BOM), 'BOM потерян')
        text = raw[len(BOM):].decode('utf-8')
        lines = text.split('\n')
        self.assertTrue(lines[0].startswith('*'), 'шапка не вставлена')
        self.assertTrue(any(' , НАЧАЛО ПРОГРАММЫ' in l for l in lines))
        self.assertTrue(any(' , ВТОРАЯ КОМАНДА' in l for l in lines))
        # Немные строки без адреса остаются без комментария.
        self.assertFalse(' ,' in lines[4])

        v = self.run_tool('--verify-only')
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)
        self.assertIn('0 differences', v.stdout)

    # (b) Слишком длинный комментарий — отказ с кодом 2.
    def test_comment_length_rejected(self):
        cmap = self.write('long.tab', '0\t' + 'Х' * 56 + '\n')
        r = self.run_tool('--comment-file', cmap)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertFalse(os.path.exists(self.out))
        self.assertIn('комментарий', r.stderr)

    # (c) Изменение числового поля обнаруживается верификатором.
    def test_numeric_mutation_detected(self):
        cmap = self.write('comments.tab', '0\tКОММЕНТАРИЙ\n')
        r = self.run_tool('--comment-file', cmap)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.out, 'r', encoding='utf-8-sig') as fh:
            text = fh.read()
        self.assertIn('4567', text)
        mutated = text.replace('4567', '4560', 1)
        with open(self.out, 'w', encoding='utf-8', newline='') as fh:
            fh.write(mutated)
        v = self.run_tool('--verify-only')
        self.assertEqual(v.returncode, 2)
        self.assertIn('difference', v.stdout)
        self.assertIn('4567', v.stdout)
        self.assertIn('4560', v.stdout)

    # (d) Отказ перезаписать существующий файл без --force.
    def test_refuse_overwrite(self):
        with open(self.out, 'w', encoding='utf-8') as fh:
            fh.write('СОХРАНИ МЕНЯ')
        cmap = self.write('comments.tab', '0\tКОММЕНТАРИЙ\n')
        r = self.run_tool('--comment-file', cmap)
        self.assertEqual(r.returncode, 1, r.stderr)
        with open(self.out, 'r', encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'СОХРАНИ МЕНЯ')
        r2 = self.run_tool('--comment-file', cmap, '--force')
        self.assertEqual(r2.returncode, 0, r2.stderr)

    # (e) Слишком длинная строка шапки — отказ с кодом 2.
    def test_header_length_rejected(self):
        cmap = self.write('comments.tab', '0\tОК\n')
        hdr = self.write('header.txt', '*' + 'Ш' * 59 + '\n')
        r = self.run_tool('--comment-file', cmap, '--header', hdr)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertFalse(os.path.exists(self.out))

    # (f) usage-ошибка (нет --input) даёт код 1, а не 2.
    def test_usage_error_code(self):
        r = subprocess.run([sys.executable, TOOL, '--output', self.out],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True)
        self.assertEqual(r.returncode, 1)


if __name__ == '__main__':
    unittest.main()
