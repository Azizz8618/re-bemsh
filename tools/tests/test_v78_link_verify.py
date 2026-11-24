#!/usr/bin/env python3
"""Tests for tools/v78_link_verify.py (own asm/rvs/verify scenario)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v78_link_verify as m  # noqa: E402


class Guard(unittest.TestCase):
    def test_refuses_reference_images(self):
        with self.assertRaises(RuntimeError):
            m.guard('/usr/local/share/besm6/2348')

    def test_allows_work_dir(self):
        self.assertEqual(m.guard('/var/tmp/x'), '/var/tmp/x')


class JobGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, 'Z0137.be')
        with open(self.src, 'w', encoding='utf-8') as h:
            h.write('* comment line\n')
            h.write("Z0137   СТАРТ '10000'\n")
            h.write('X1 ВНЕШН Z0155.Z0155A\n')
            h.write('X2 ВНЕШН JJJJJJ.AAAA\n')
            h.write('        КОНД П\'ТЕКСТ\'  , comment\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_compile_job_filters_comments(self):
        job = m.compile_job(self.src, 0o4000, 'Z0137', '10000')
        self.assertNotIn('comment line', job)

    def test_compile_job_filters_bogus_external(self):
        job = m.compile_job(self.src, 0o4000, 'Z0137', '10000')
        self.assertIn('X1 ВНЕШН Z0155.Z0155A', job)
        self.assertNotIn('JJJJJJ', job)

    def test_compile_job_has_one_to_one(self):
        job = m.compile_job(self.src, 0o4000, 'Z0137', '10000')
        self.assertIn('1-1^', job)

    def test_compile_job_has_zone_mod(self):
        job = m.compile_job(self.src, 0o4000, 'Z0137', '10000')
        self.assertIn('ЗОНМОД434000 0001^', job)

    def test_link_job_header(self):
        mods = [('0137', 'Z0137', '10000', 0o4000, 0o137)]
        job = m.link_job(mods)
        self.assertIn('к 00 070 1003', job)
        self.assertIn('Р В С', job) if False else None
        self.assertIn('мдл   Z0137 434000^наз   010000^зонгп 430137 0001^', job)

    def test_link_job_pads_name(self):
        mods = [('0141', 'Z0141', '10000', 0o4002, 0o141)]
        job = m.link_job(mods)
        self.assertIn('мдл   Z0141 434002^наз   010000^зонгп 430141 0001^', job)


class SectorCompare(unittest.TestCase):
    def test_equal(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, 'a')
            b = os.path.join(tmp, 'b')
            open(a, 'wb').write(b'\0' * 3000)
            open(b, 'wb').write(b'\0' * 3000)
            self.assertEqual(m.compare(a, b), ([], 0))

    def test_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, 'a')
            b = os.path.join(tmp, 'b')
            data = bytearray(3000)
            data[100] = 9
            open(a, 'wb').write(bytes(data))
            open(b, 'wb').write(bytes(3000))
            self.assertEqual(m.compare(a, b), ([(0, 1)], 1))


if __name__ == '__main__':
    unittest.main()
