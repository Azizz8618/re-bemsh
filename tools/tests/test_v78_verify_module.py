#!/usr/bin/env python3
"""Unit tests for tools/v78_verify_module.py (verify.pl methodology)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v78_verify_module as m  # noqa: E402


class JobGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, 'mod.be')
        with open(self.src, 'w', encoding='utf-8') as h:
            h.write('MODUL СТАРТ 10000\n')
            h.write('        ВНЕШН MODUL.A\n')
            h.write("        КОНД П'ТЕКСТ'  , комментарий\n")
            h.write('        ФИНИШ\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_job_has_one_to_one(self):
        job = m.asm_job(self.src, '0100', 1)
        self.assertIn('1-1^', job)

    def test_job_has_zone_mod(self):
        job = m.asm_job(self.src, '0100', 1)
        self.assertIn('ЗОНМОД430100 001^', job)

    def test_job_has_input_markers(self):
        job = m.asm_job(self.src, '0100', 1)
        self.assertIn('ВВД$$$^', job)
        self.assertIn('КВЧ$$$^', job)

    def test_job_keeps_vneshn(self):
        job = m.asm_job(self.src, '0100', 1)
        self.assertIn('ВНЕШН MODUL.A^', job)

    def test_job_strips_spaced_comment(self):
        job = m.asm_job(self.src, '0100', 1)
        self.assertIn("КОНД П'ТЕКСТ'^", job)
        self.assertNotIn('комментарий', job)

    def test_no_start_raises(self):
        bad = os.path.join(self.tmp.name, 'bad.be')
        open(bad, 'w').write('ПУСТО\n')
        with self.assertRaises(RuntimeError):
            m.asm_job(bad, '0100', 1)


class SectorCompare(unittest.TestCase):
    def test_equal(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, 'a')
            b = os.path.join(tmp, 'b')
            open(a, 'wb').write(b'\0' * 3000)
            open(b, 'wb').write(b'\0' * 3000)
            self.assertEqual(m.compare(a, b), ([], 0))

    def test_one_sector_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, 'a')
            b = os.path.join(tmp, 'b')
            data = bytearray(3000)
            data[10] = 7
            open(a, 'wb').write(bytes(data))
            open(b, 'wb').write(bytes(3000))
            sectors, total = m.compare(a, b)
            self.assertEqual(sectors, [(0, 1)])
            self.assertEqual(total, 1)

    def test_second_sector(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, 'a')
            b = os.path.join(tmp, 'b')
            data = bytearray(4000)
            data[2000] = 3
            open(a, 'wb').write(bytes(data))
            open(b, 'wb').write(bytes(4000))
            self.assertEqual(m.compare(a, b), ([(1, 1)], 1))


class Guard(unittest.TestCase):
    def test_refuses_share(self):
        with self.assertRaises(RuntimeError):
            m.guard('/usr/local/share/besm6/2348')

    def test_allows_tmp(self):
        self.assertEqual(m.guard('/var/tmp/x'), '/var/tmp/x')


if __name__ == '__main__':
    unittest.main()
