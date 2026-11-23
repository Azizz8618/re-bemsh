#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Статические тесты загрузчика БЕМШ: зоны 0137, 0140-0143.

Static tests read repo files only. Volume tests are optional
and use besmtool dump on read-only images, stdout only.
"""
import hashlib
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GOLD = REPO / 'gold'
DIS = REPO / 'dis'
BE = REPO / 'bemsh'
SEM = REPO / 'docs' / 'SEMANTIC'

LOADER = ('0137', '0140', '0141', '0142', '0143')
ZONE_BYTES = 6144
N_ZONES = 33
CONCAT_BYTES = N_ZONES * ZONE_BYTES

VOLUMES = ('2048', '2148', '2248')
IMAGE_ROOT = os.environ.get('BESM6_PATH',
                            '/usr/local/share/besm6')
BESMTOOL = shutil.which('besmtool')
HAS_IMAGES = all((Path(IMAGE_ROOT) / d).is_file()
                 for d in VOLUMES)

MD5_CONCAT = {
    '2048': '2f503f5b8f8fb6ad12632fed6f8cf17f',
    '2148': '90434226c98df1c40bbb8d76e1560613',
    '2248': '90434226c98df1c40bbb8d76e1560613',
}

CALL_RE = re.compile(r'\t(пв|вжм)\t')


def asm(zone):
    """Read a BEMSH disassembly, BOM removed."""
    path = DIS / ('MBE-Z%s-L1.asm' % zone)
    return path.read_text(encoding='utf-8-sig')


def gold(zone):
    """Read a 6144-byte gold zone."""
    path = GOLD / ('MBE-Z%s-L1.bin' % zone)
    return path.read_bytes()


def word(blob, addr):
    """Six raw bytes of one word, addr is octal."""
    i = int(addr, 8) * 6
    return blob[i:i + 6]


def code_addrs(text):
    """Word addresses printed as code, not конд/пам."""
    out = []
    for line in text.splitlines():
        if '\tконд\t' in line or '\tпам\t' in line:
            continue
        head = line.split('\t', 1)[0]
        f = head.split()
        if len(f) == 4 and f[0].isdigit():
            out.append(int(f[0], 8))
    return out


def calls(text):
    """CALL lines of a disassembly."""
    return [line for line in text.splitlines()
            if CALL_RE.search(line)]


def stamp_free(text):
    """No 0147 version stamp text in a zone."""
    return ("п'ИПМ МА'" not in text
            and "п'КРО-БЕ'" not in text
            and "п'МШ ВЕР'" not in text
            and "п'.06/78'" not in text)


class TestGoldFiles(unittest.TestCase):
    def test_five_loader_gold_files_exist(self):
        for z in LOADER:
            p = GOLD / ('MBE-Z%s-L1.bin' % z)
            self.assertTrue(p.is_file(), str(p))

    def test_each_loader_gold_is_6144_bytes(self):
        for z in LOADER:
            p = GOLD / ('MBE-Z%s-L1.bin' % z)
            self.assertEqual(p.stat().st_size,
                             ZONE_BYTES, z)

    def test_full_concat_is_33_zones(self):
        p = GOLD / 'MBE-full.bin'
        self.assertTrue(p.is_file())
        self.assertEqual(p.stat().st_size, CONCAT_BYTES)

    def test_manifest_lists_all_five_gold_zones(self):
        text = (REPO / 'manifest.sha256').read_text(
            encoding='utf-8')
        for z in LOADER:
            self.assertIn('gold/MBE-Z%s-L1.bin' % z, text)


class TestZone0137(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = asm('0137')
        cls.blob = gold('0137')

    def test_init_code_is_five_words(self):
        self.assertEqual(code_addrs(self.text),
                         [0, 1, 2, 3, 4])

    def test_syscall_and_const_constants(self):
        head = '\n'.join(self.text.splitlines()[:20])
        self.assertIn("зп\t'70000'", head)
        self.assertIn("рег\t'3554'", head)
        self.assertIn('D00003', head)

    def test_break_at_m3(self):
        lines = [ln for ln in self.text.splitlines()
                 if '\tпб\t(М3)' in ln]
        self.assertEqual(len(lines), 1)
        self.assertIn('03 30 00000', lines[0])

    def test_koi7_table_bytes_in_gold(self):
        expected = {
            '0057': '7a7020200100',
            '0061': '437e4d200403',
            '0062': '436c20201004',
            '0120': '7042202002c8',
            '0121': '63694b6c01f8',
        }
        for addr, hexval in expected.items():
            self.assertEqual(word(self.blob, addr).hex(),
                             hexval, addr)

    def test_koi7_mnemonics_in_be(self):
        text = (BE / 'MBE-Z0137.be').read_text(
            encoding='utf-8')
        for name in ('ЗП', 'СЧМ', 'ЦИКЛ', 'ПБ', 'ПВ'):
            self.assertIn(name, text)

    def test_doc_states_51_mnemonics(self):
        text = (SEM / 'Z0137.md').read_text(
            encoding='utf-8')
        self.assertIn('51 мнемоника KOI-7', text)


class TestZone0140(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = asm('0140')

    def test_eight_code_words(self):
        self.assertEqual(code_addrs(self.text),
                         list(range(8)))

    def test_common_call_and_exit(self):
        self.assertIn("пв\t'34562'(М16)", self.text)
        self.assertIn("пб\t'77430'(М7)", self.text)
        self.assertEqual(len(calls(self.text)), 1)

    def test_passport_table_words(self):
        self.assertIn("нтж\t'150'(М7)", self.text)
        self.assertIn("сда\t64-23", self.text)


class TestZone0141(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = asm('0141')
        cls.blob = gold('0141')

    def test_three_code_words(self):
        self.assertEqual(code_addrs(self.text), [0, 1, 2])

    def test_two_calls_and_targets(self):
        lines = calls(self.text)
        self.assertEqual(len(lines), 2)
        joined = '\n'.join(lines)
        self.assertIn("пв\t'14342'(М16)", joined)
        self.assertIn("пв\t'40540'(М16)", joined)

    def test_exit_77260(self):
        self.assertIn("пб\t'77260'(М7)", self.text)

    def test_descriptor_prefix_7400000x(self):
        self.assertEqual(word(self.blob, '0003')[:3].hex(),
                         'f00005')
        self.assertEqual(word(self.blob, '0004')[:3].hex(),
                         'f00006')

    def test_no_version_stamp(self):
        self.assertTrue(stamp_free(self.text))


class TestZone0142(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = asm('0142')
        cls.blob = gold('0142')

    def test_eighteen_code_words(self):
        self.assertEqual(len(code_addrs(self.text)), 18)
        self.assertEqual(code_addrs(self.text)[0], 0)
        self.assertEqual(code_addrs(self.text)[-1],
                         0o21)

    def test_two_calls_and_targets(self):
        lines = calls(self.text)
        self.assertEqual(len(lines), 2)
        joined = '\n'.join(lines)
        self.assertIn("пв\t'34417'(М16)", joined)
        self.assertIn("пв\t'34562'(М16)", joined)

    def test_reloc_base_36436_three_times(self):
        lines = [ln for ln in self.text.splitlines()
                 if "\tмода\t'36436'" in ln]
        self.assertEqual(len(lines), 3)
        for addr in ('0005', '0006', '0012'):
            tail = word(self.blob, addr)[3:].hex()
            self.assertEqual(tail, '093d1e', addr)

    def test_descriptor_prefix_00430016(self):
        self.assertEqual(word(self.blob, '0024')[:3].hex(),
                         '02300e')

    def test_return_via_m16(self):
        self.assertIn("\tпб\t(М16)", self.text)

    def test_no_version_stamp(self):
        self.assertTrue(stamp_free(self.text))


class TestZone0143(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = asm('0143')
        cls.blob = gold('0143')

    def test_sixteen_code_words(self):
        self.assertEqual(len(code_addrs(self.text)), 16)

    def test_two_calls_including_common(self):
        lines = calls(self.text)
        self.assertEqual(len(lines), 2)
        joined = '\n'.join(lines)
        self.assertIn("пв\t'4231'(М16)", joined)
        self.assertIn("пв\t'34562'(М16)", joined)

    def test_exit_76720(self):
        self.assertIn("пб\t'76720'(М7)", self.text)

    def test_koi7_fragment_bytes(self):
        self.assertEqual(word(self.blob, '1222').hex(),
                         '7a704d200401')
        self.assertEqual(word(self.blob, '1243').hex(),
                         '7042202002c8')

    def test_no_version_stamp(self):
        self.assertTrue(stamp_free(self.text))


class TestLoaderCommon(unittest.TestCase):
    def test_loader_is_five_zones(self):
        self.assertEqual(len(LOADER), 5)

    def test_common_call_34562_in_0140_0142_0143(self):
        for z in ('0140', '0142', '0143'):
            self.assertIn("пв\t'34562'(М16)", asm(z), z)

    def test_common_call_absent_in_0141(self):
        self.assertNotIn('34562', asm('0141'))

    def test_no_stamp_in_any_loader_zone(self):
        for z in LOADER:
            self.assertTrue(stamp_free(asm(z)), z)

    def test_version_stamp_in_kernel_0147(self):
        text = asm('0147')
        for frag in ("п'ИПМ МА'", "п'КРО-БЕ'",
                     "п'МШ ВЕР'", "п'.06/78'"):
            self.assertIn(frag, text)
        stamp = GOLD / 'MBE-Z0147-L1.bin'
        self.assertTrue(stamp.is_file())


def dump_zones(disk, start, length):
    """besmtool dump to stdout; never writes to an image."""
    cmd = [BESMTOOL, 'dump', disk,
           '--start=' + start,
           '--length=' + str(length),
           '--to-file=-']
    r = subprocess.run(cmd, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode('utf-8',
                                            'replace'))
    want = length * ZONE_BYTES
    if len(r.stdout) < want:
        raise AssertionError('short dump: %d'
                             % len(r.stdout))
    if not r.stdout[want:].startswith(b'Writing '):
        raise AssertionError('unexpected dump trailer')
    return r.stdout[:want]


NEED = 'need besmtool and volumes 2048/2148/2248'

@unittest.skipUnless(BESMTOOL and HAS_IMAGES, NEED)
class TestReferenceVolumes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.concat = {}
        for disk in VOLUMES:
            cls.concat[disk] = dump_zones(
                disk, '0137', N_ZONES)

    def md5_of(self, disk):
        return hashlib.md5(self.concat[disk]).hexdigest()

    def test_concat_md5_2048(self):
        self.assertEqual(self.md5_of('2048'),
                         MD5_CONCAT['2048'])

    def test_concat_md5_2148(self):
        self.assertEqual(self.md5_of('2148'),
                         MD5_CONCAT['2148'])

    def test_concat_md5_2248(self):
        self.assertEqual(self.md5_of('2248'),
                         MD5_CONCAT['2248'])

    def test_concat_length_202752(self):
        for disk in VOLUMES:
            self.assertEqual(len(self.concat[disk]),
                             CONCAT_BYTES)

    def test_2148_and_2248_concat_identical(self):
        self.assertEqual(self.concat['2148'],
                         self.concat['2248'])

    def test_loader_zones_differ_about_5300_bytes(self):
        a = dump_zones('2048', '0137', 5)
        b = dump_zones('2248', '0137', 5)
        for i, z in enumerate(LOADER):
            n = sum(x != y for x, y in zip(
                a[i * ZONE_BYTES:(i + 1) * ZONE_BYTES],
                b[i * ZONE_BYTES:(i + 1) * ZONE_BYTES]))
            self.assertGreater(n, 5000, z)
            self.assertLess(n, 5500, z)

    def test_kernel_diff_exceptions_match_doc(self):
        a = dump_zones('2048', '0144', 28)
        b = dump_zones('2248', '0144', 28)
        diff = {}
        for i in range(28):
            lo, hi = i * ZONE_BYTES, (i + 1) * ZONE_BYTES
            n = sum(x != y for x, y in
                    zip(a[lo:hi], b[lo:hi]))
            if n:
                diff[0o144 + i] = n
        self.assertEqual(diff,
                         {0o147: 1977, 0o151: 3, 0o176: 1})

    def test_gold_loader_zones_match_2048(self):
        for z in LOADER:
            want = dump_zones('2048', z, 1)
            self.assertEqual(gold(z), want, z)


if __name__ == '__main__':
    unittest.main()
