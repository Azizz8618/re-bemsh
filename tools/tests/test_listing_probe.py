#!/usr/bin/env python3
"""Unit tests for tools/listing_probe.py.

Fixtures are synthetic listing text plus one optional real listing.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import listing_probe as m  # noqa: E402

REAL_LISTING = '/tmp/.private/azizz/rebuild-all/0137/listing.out'


def header_line():
    """Synthetic header with tokens at the canonical start columns."""
    cells = [' '] * 100
    for name, start in m.DEFAULT_COLUMNS.items():
        for i, ch in enumerate(name):
            cells[start + i] = ch
    return ''.join(cells).rstrip()


class TestColumns(unittest.TestCase):
    def test_header_positions(self):
        line, cols = m.find_header([header_line()])
        self.assertEqual(line, 1)
        self.assertEqual(cols['ОШИБКИ'], 0)
        self.assertEqual(cols['ПЕРЕМ'], 19)
        self.assertEqual(cols['АДРЕС'], 25)
        self.assertEqual(cols['КОМАНДА'], 31)
        self.assertEqual(cols['А ИСП'], 42)
        self.assertEqual(cols['МЕТКА'], 60)
        self.assertEqual(cols['КОММЕНТАРИЙ'], 86)

    def test_header_with_omoglyphs(self):
        line = ('OШИБKИ   HПK  CBOБ ПEPEM AДPEC KOMAHДA'
                '    A ИCП N ГEH N ИCX METKA  OПEPAЦИЯ'
                ' OПEPAHД   KOMMEHTAPИЙ')
        _, cols = m.find_header([line])
        self.assertEqual(cols['АДРЕС'], 25)
        self.assertEqual(cols['КОМАНДА'], 31)
        self.assertEqual(cols['МЕТКА'], 60)

    def test_no_header_falls_back_to_defaults(self):
        r = m.probe('some random text\n')
        self.assertFalse(r['columns_from_header'])
        self.assertEqual(r['columns'], m.DEFAULT_COLUMNS)


class TestWords(unittest.TestCase):
    def test_whole_word(self):
        line = ' ' * 25 + '10024' + ' 7600000000000000'
        p = m.parse_words([line])
        self.assertEqual(p['whole_words'], 1)
        self.assertEqual(p['half_pairs'], 0)
        self.assertEqual(p['addresses'], [0o10024])
        self.assertEqual(p['values'][0o10024], 0o7600000000000000)

    def test_half_pair_five_digit_field(self):
        l1 = ' ' * 25 + '01036' + ' 13 30 00012'
        l2 = ' ' * 25 + '     ' + ' 16 31 00003'
        p = m.parse_words([l1, l2])
        h1 = (0o13 << 20) | (0o30 << 15) | 0o12
        h2 = (0o16 << 20) | (0o31 << 15) | 0o3
        self.assertEqual(p['half_pairs'], 1)
        self.assertEqual(p['words_total'], 1)
        self.assertEqual(p['values'][0o1036], (h1 << 24) | h2)

    def test_half_pair_four_digit_field(self):
        # 4-digit address field uses the 12-bit op shift.
        l1 = ' ' * 25 + '00010' + ' 00 26 1234'
        l2 = ' ' * 25 + '     ' + ' 00 30 4321'
        p = m.parse_words([l1, l2])
        h1 = (0o26 << 12) | 0o1234
        h2 = (0o30 << 12) | 0o4321
        self.assertEqual(p['values'][0o10], (h1 << 24) | h2)

    def test_relocation_field_is_not_an_address(self):
        left = '008+ 0016-00001'        # 15 chars, inside [0:25]
        line = left + ' ' * (25 - len(left)) + '50052' + '  00 010 0000'
        p = m.parse_words([line])
        self.assertEqual(p['addresses'], [0o50052])
        self.assertEqual(p['non_address_lines'], 0)

    def test_bad_address_line(self):
        line = ' ' * 25 + '8xxxx' + ' 7600000000000000'
        p = m.parse_words([line])
        self.assertEqual(p['non_address_lines'], 1)
        self.assertEqual(p['words_total'], 0)

    def test_address_is_octal_not_base_resolved(self):
        # The probe reports base+index as printed; it does not apply base.
        p = m.parse_words([' ' * 25 + '10024' + ' 0000000000000000'])
        self.assertEqual(p['addresses'][0], 0o10024)
        self.assertEqual(p['addresses'][0], 4116)


class TestBannersAndFooter(unittest.TestCase):
    def test_bom_and_omoglyph_banners(self):
        text = ('\ufeffИПM MAKPO-БEMШ BEP.06/78\n'
                'APAП BAP.04/78\n'
                'ЧИCЛO OШИБOK=0000. MAKC CEPЬEЗH=0.\n')
        r = m.probe(text)
        self.assertEqual(r['lines'], 3)
        self.assertTrue(any('ИПМ МАКРО-БЕМШ' in b
                            for b in r['banners']))
        self.assertTrue(any('АРАП ВАР.04/78' in b
                            for b in r['banners']))
        self.assertEqual(r['footer']['errors'], 0)
        self.assertEqual(r['footer']['serious'], 0)

    def test_footer_nonzero(self):
        r = m.probe('ЧИCЛO OШИБOK=0012. MAKC CEPЬEЗH=2.\n')
        self.assertEqual(r['footer']['errors'], 12)
        self.assertEqual(r['footer']['serious'], 2)

    def test_no_footer(self):
        self.assertIsNone(m.probe('nothing here\n')['footer'])


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(prefix='listing-probe-')
        self.addCleanup(self.d.cleanup)
        self.path = os.path.join(self.d.name, 'listing.out')
        with open(self.path, 'w', encoding='utf-8') as fh:
            fh.write(header_line() + '\n')
            fh.write(' ' * 25 + '10024' + ' 7600000000000000\n')
            fh.write('ЧИCЛO OШИБOK=0000. MAKC CEPЬEЗH=0.\n')

    def test_missing_file(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            code = m.main([os.path.join(self.d.name, 'no')])
        self.assertEqual(code, 2)
        self.assertIn('error:', buf.getvalue())

    def test_text_format(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = m.main([self.path])
        self.assertEqual(code, 0)
        self.assertIn('LISTING PROBE', buf.getvalue())

    def test_json_format(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = m.main([self.path, '--format', 'json'])
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data['parse']['whole_words'], 1)
        self.assertEqual(data['footer']['errors'], 0)


@unittest.skipUnless(os.path.exists(REAL_LISTING),
                     'real 0137 listing not present')
class TestRealListing(unittest.TestCase):
    def test_probe_real_listing(self):
        with open(REAL_LISTING, encoding='utf-8') as fh:
            r = m.probe(fh.read())
        self.assertTrue(r['columns_from_header'])
        self.assertEqual(r['columns']['АДРЕС'], 25)
        self.assertIsNotNone(r['footer'])
        self.assertEqual(r['footer']['errors'], 0)
        self.assertGreater(r['parse']['words_total'], 100)
        self.assertTrue(any('АРАП ВАР.04/78' in b
                            for b in r['banners']))


if __name__ == '__main__':
    unittest.main()
