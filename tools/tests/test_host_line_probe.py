#!/usr/bin/env python3
"""Unit tests for tools/host_line_probe.py.

All fixtures are synthetic card strings. No emulator, no disk
image and no writes to any reference file.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_line_probe as m  # noqa: E402


S1 = 'ПРОГ\tСТАРТ\t512\n'
S2 = 'ПРОГ         СТАРТ         512\n'
SAME_TOKENS = 'ПРОГ СТАРТ 512'


class PackTest(unittest.TestCase):

    def test_word_width(self):
        for w in m.pack_text(S1):
            self.assertEqual(len(w), 6)

    def test_newline_is_skipped(self):
        a = m.pack_text('АБВГ')
        b = m.pack_text('АБ\nВГ')
        self.assertEqual(a, b)

    def test_tab_is_space(self):
        self.assertEqual(m.pack_text('А\tБ'),
                         m.pack_text('А Б'))

    def test_known_bytes(self):
        words = m.pack_text('012345')
        self.assertEqual(words[0], bytes([0, 1, 2, 3, 4, 5]))

    def test_partial_word_is_right_padded(self):
        words = m.pack_text('АБ')
        self.assertEqual(words, [bytes([0o40, 0o41, 0, 0, 0, 0])])

    def test_space_only_change_keeps_tokens(self):
        wa = m.pack_text(S1)
        wb = m.pack_text(S2)
        self.assertNotEqual(wa, wb)
        self.assertEqual(m.nonspace_stream(wa),
                         m.nonspace_stream(wb))

    def test_space_byte_count_differs(self):
        ca = sum(w.count(m.SPACE) for w in m.pack_text(S1))
        cb = sum(w.count(m.SPACE) for w in m.pack_text(S2))
        self.assertLess(ca, cb)

    def test_itm_mode_is_not_faked(self):
        with self.assertRaises(NotImplementedError):
            m.pack_text(S1, 'itm')


class HostSplitTest(unittest.TestCase):

    def test_no_field_split(self):
        for s in ('', SAME_TOKENS, 'МЕТКА ОПЕРАЦИЯ ОПЕРАНД ; КОММ'):
            self.assertIsNone(m.host_fields(s))

    def test_dispatcher_markers_are_text(self):
        r = m.markers_in_text('ВВД$$$\nКВЧ$$$')
        self.assertEqual(r['vvd'], 1)
        self.assertEqual(r['kvch'], 1)
        self.assertEqual(r['diamond_count'], 6)
        self.assertIn('none', r['host_action'])

    def test_overlay_byte(self):
        self.assertEqual(m.GOST['↑'], m.OVERLINE)
        self.assertEqual(m.GOST['^'], m.OVERLINE)


class PunchImageTest(unittest.TestCase):

    def test_blank_card(self):
        self.assertEqual(m.prettycard(['.' * 80] * 12), [0] * 24)

    def test_first_hole_position(self):
        rows = ['O' + '.' * 79] + ['.' * 80] * 11
        words = m.prettycard(rows)
        self.assertEqual(words[0], 1 << 39)
        self.assertEqual(words[1:], [0] * 23)

    def test_chad_diagnostics(self):
        _i, _w, line, sym = m.chad(0, 0, 'O')
        self.assertEqual((line, sym), (1, 1))
        _i, _w, line, sym = m.chad(0, 95, 'O')
        self.assertEqual((line, sym), (2, 2))

    def test_bad_punch_value(self):
        with self.assertRaises(ValueError):
            m.chad(0, 0, 'X')


class CheckCliTest(unittest.TestCase):

    def test_check_passes(self):
        self.assertEqual(m.check(), [])

    def test_main_check(self):
        self.assertEqual(m.main(['--check']), 0)

    def test_main_json(self):
        fd, path = tempfile.mkstemp(suffix='.txt')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(S1)
            self.assertEqual(m.main([path, '--json']), 0)
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
