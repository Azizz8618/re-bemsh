#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты релок-различий зон 0137-0143 томов 2048/2148/2248.

Юнит-тесты работают на синтетических байтах, без эмулятора.
Интеграция включается только при наличии besmtool и томов.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import loader_reloc_probe as m  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TOOL = HERE.parent / 'loader_reloc_probe.py'
ROOT = os.environ.get('BESM6_PATH', m.DEFAULT_ROOT)
DISKS = m.DEFAULT_DISKS
BESMTOOL = shutil.which('besmtool') or 'besmtool'
HAS_TOOL = shutil.which('besmtool') is not None
HAS_VOLUMES = all(os.path.isfile(os.path.join(ROOT, d))
                  for d in DISKS)
GOLD_0137 = REPO / 'gold' / 'MBE-Z0137-L1.bin'

MD5_2048 = '2f503f5b8f8fb6ad12632fed6f8cf17f'
MD5_2148 = '90434226c98df1c40bbb8d76e1560613'

SYNTH_TEXT = (
    "выпр '70707'(М17)\n"
    "зп '70000'\n"
    "мода '36436'\n"
    "пб (М3)\n"
)


class TestZoneHelpers(unittest.TestCase):
    def test_zone_dec_octal_and_decimal(self):
        self.assertEqual(m.zone_dec('0137'), 95)
        self.assertEqual(m.zone_dec('0143'), 99)
        self.assertEqual(m.zone_dec('95'), 95)

    def test_zone_oct(self):
        self.assertEqual(m.zone_oct(95), '0137')
        self.assertEqual(m.zone_oct(127), '0177')

    def test_zone_list_loader_is_five_zones(self):
        self.assertEqual(m.zone_list('0137', '0143'),
                         [95, 96, 97, 98, 99])

    def test_zone_list_all_is_33_zones(self):
        zones = m.zone_list(m.ZONE_FIRST, m.ZONE_LAST)
        self.assertEqual(len(zones), 33)
        self.assertEqual(zones[-1], 127)

    def test_zone_list_rejects_bad_range(self):
        with self.assertRaises(ValueError):
            m.zone_list('0143', '0137')


class TestSyntheticBytes(unittest.TestCase):
    def test_md5_concat_matches_hashlib(self):
        a = bytes(range(256)) * 24
        b = b'\x00' * 6144
        want = hashlib.md5(a + b).hexdigest()
        self.assertEqual(m.md5_concat([a, b]), want)

    def test_md5_concat_order_matters(self):
        a, b = b'\x01' * 8, b'\x02' * 8
        self.assertNotEqual(m.md5_concat([a, b]),
                            m.md5_concat([b, a]))

    def test_diff_bytes_identical(self):
        self.assertEqual(m.diff_bytes(b'abc', b'abc'), 0)

    def test_diff_bytes_one_byte(self):
        self.assertEqual(m.diff_bytes(b'abc', b'abd'), 1)

    def test_diff_bytes_length_mismatch(self):
        self.assertEqual(m.diff_bytes(b'ab', b'a'), 1)
        self.assertEqual(m.diff_bytes(b'ab', b'c'), 2)

    def test_diff_map_reports_only_differing_zones(self):
        a = {95: b'\x00', 96: b'\x01'}
        b = {95: b'\x00', 96: b'\x02', 97: b'\x03'}
        self.assertEqual(m.diff_map(a, b), {96: 1, 97: 1})

    def test_is_loader_boundary(self):
        self.assertTrue(m.is_loader(95))
        self.assertTrue(m.is_loader(99))
        self.assertFalse(m.is_loader(100))
        self.assertFalse(m.is_loader(127))

    def test_reloc_hits_all_and_missing(self):
        hits = m.reloc_hits(SYNTH_TEXT)
        self.assertTrue(all(hits.values()))
        partial = m.reloc_hits("зп '70000'\n")
        self.assertFalse(partial["'36436'"])
        self.assertTrue(partial["зп '70000'"])

    def test_build_report_synthetic(self):
        zones = m.zone_list('0137', '0143')
        base = {z: bytes([z]) * 8 for z in zones}
        other = dict(base)
        other[95] = b'\xAA' * 8
        dumps = {'2048': base, '2148': other}
        rep = m.build_report(dumps, '0137', '0143')
        self.assertEqual(rep['zones'],
                         ['0137', '0140', '0141',
                          '0142', '0143'])
        self.assertEqual(rep['concat_bytes'], 5 * 6144)
        self.assertEqual(rep['diffs']['2148'], {'0137': 8})

    def test_format_text_synthetic(self):
        zones = m.zone_list('0137', '0143')
        base = {z: bytes([z]) * 8 for z in zones}
        other = dict(base)
        other[95] = b'\xAA' * 8
        rep = m.build_report({'2048': base, '2148': other},
                             '0137', '0143')
        text = m.format_text(rep)
        self.assertIn('2048 md5 concat:', text)
        self.assertIn('0137 loader 8 bytes', text)
        for line in text.splitlines():
            self.assertLessEqual(len(line), 60)


class TestGuardAndCli(unittest.TestCase):
    def test_guard_refuses_default_image_root(self):
        with self.assertRaises(m.GuardError):
            m.guard_output('/usr/local/share/besm6/x.json')

    def test_guard_refuses_usr_local_share(self):
        with self.assertRaises(m.GuardError):
            m.guard_output('/usr/local/share/x.json')

    def test_guard_allows_tmp(self):
        self.assertTrue(m.guard_output('/tmp/x.json'))

    def test_guard_custom_root(self):
        with self.assertRaises(m.GuardError):
            m.guard_output('/my/root/2048', root='/my/root')
        self.assertTrue(m.guard_output(
            '/tmp/2048', root='/my/root'))

    def test_guard_none_is_noop(self):
        self.assertTrue(m.guard_output(None))

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOL)] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)

    def test_cli_dry_run_json_does_not_need_tool(self):
        r = self.run_cli('--dry-run', '--format', 'json')
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertTrue(data['dry_run'])
        self.assertEqual(len(data['commands']), 3 * 33)

    def test_cli_dry_run_text_lists_zones(self):
        r = self.run_cli('--dry-run')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('--start=0137', r.stdout)
        self.assertIn('--start=0177', r.stdout)

    def test_cli_refuses_output_in_image_root(self):
        r = self.run_cli(
            '--output', '/usr/local/share/besm6/x.json',
            '--dry-run')
        self.assertEqual(r.returncode, 3)
        self.assertIn('REFUSE', r.stderr)


@unittest.skipUnless(HAS_TOOL and HAS_VOLUMES,
                     'need besmtool and 3 volumes')
class TestRealVolumes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = '/tmp/.private/azizz'
        parent = base if os.path.isdir(base) else None
        cls.tmp = tempfile.TemporaryDirectory(
            prefix='loader-reloc-test-', dir=parent)
        cls.zones = m.zone_list(m.ZONE_FIRST, m.ZONE_LAST)
        cls.dumps = {}
        for disk in DISKS:
            cls.dumps[disk] = m.dump_zones(
                disk, cls.zones, ROOT, BESMTOOL,
                cls.tmp.name)
        cls.dm_2148 = m.diff_map(
            cls.dumps['2048'], cls.dumps['2148'])
        cls.dm_2248 = m.diff_map(
            cls.dumps['2048'], cls.dumps['2248'])
        cls.dm_2148_2248 = m.diff_map(
            cls.dumps['2148'], cls.dumps['2248'])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def md5_of(self, disk):
        return m.md5_concat(
            [self.dumps[disk][z] for z in self.zones])

    def test_concat_md5_2048(self):
        self.assertEqual(self.md5_of('2048'), MD5_2048)

    def test_concat_md5_2148(self):
        self.assertEqual(self.md5_of('2148'), MD5_2148)

    def test_concat_md5_2248(self):
        self.assertEqual(self.md5_of('2248'), MD5_2148)

    def test_concat_length_is_202752(self):
        for disk in DISKS:
            blob = b''.join(
                self.dumps[disk][z] for z in self.zones)
            self.assertEqual(len(blob), 202752)

    def test_loader_zones_differ_about_5300_bytes(self):
        for z in m.zone_list('0137', '0143'):
            n = self.dm_2248[z]
            msg = 'zone ' + m.zone_oct(z)
            self.assertGreater(n, 5000, msg)
            self.assertLess(n, 5500, msg)

    def test_kernel_diff_exceptions_match_doc(self):
        kernel = {z: n for z, n in self.dm_2248.items()
                  if not m.is_loader(z)}
        self.assertEqual(kernel, {
            m.zone_dec('0147'): 1977,
            m.zone_dec('0151'): 3,
            m.zone_dec('0176'): 1,
        })

    def test_kernel_zone_0154_matches(self):
        z = m.zone_dec('0154')
        digests = {
            d: hashlib.md5(self.dumps[d][z]).hexdigest()
            for d in DISKS
        }
        self.assertEqual(len(set(digests.values())), 1)

    def test_2148_and_2248_identical(self):
        self.assertEqual(self.dm_2148_2248, {})

    def test_0137_first_words(self):
        self.assertEqual(self.dumps['2048'][95][:6],
                         bytes.fromhex('000000040000'))
        for disk in ('2148', '2248'):
            self.assertEqual(self.dumps[disk][95][:6],
                             bytes.fromhex('000707070707'))

    @unittest.skipUnless(GOLD_0137.is_file(),
                         'gold/MBE-Z0137-L1.bin missing')
    def test_gold_0137_matches_2048_dump(self):
        with open(GOLD_0137, 'rb') as fh:
            data = fh.read()
        self.assertEqual(data, self.dumps['2048'][95])


if __name__ == '__main__':
    unittest.main()
