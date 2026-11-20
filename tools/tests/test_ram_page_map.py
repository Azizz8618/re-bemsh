#!/usr/bin/env python3
"""Unit tests for tools/ram_page_map.py (stdlib unittest only).

Fixtures are synthetic: no gold file, image, or snapshot is touched.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ram_page_map as m  # noqa: E402


def word(fill=0, seed=0):
    """Build one 6-byte word as a tuple of byte ints."""
    return tuple((fill + seed + i) % 256 for i in range(6))


def make_zone(fill=0, special=None):
    """Build a 1024-word zone; special maps index -> word tuple."""
    special = special or {}
    return [special.get(i, word(fill, i)) for i in range(1024)]


def make_dump_text(words):
    """Render words in the exact dispak debugger dump format."""
    lines = []
    for start in range(0, len(words), 8):
        for j, w in enumerate(words[start:start + 8]):
            prefix = "- " if j == 0 else ""
            lines.append(prefix + " ".join("%03o" % b for b in w))
    return "\n".join(lines) + "\n"


class TestParseSnapshot(unittest.TestCase):
    def test_parse_synthetic_words(self):
        words = [word(1, i) for i in range(16)]
        got = m.parse_snapshot(make_dump_text(words), expected=16)
        self.assertEqual(got, words)

    def test_ignores_debugger_noise(self):
        words = [word(2, i) for i in range(8)]
        text = (
            "- set breakpoint on 02000\n"
            " 02000: 00 010 6065 xta\n"
            "banners and text\n"
            + make_dump_text(words)
        )
        got = m.parse_snapshot(text, expected=8)
        self.assertEqual(got, words)

    def test_wrong_word_count_raises(self):
        with self.assertRaises(ValueError):
            m.parse_snapshot(make_dump_text([word(0)] * 8), expected=16)


class TestMatching(unittest.TestCase):
    def test_exact_match(self):
        zone = make_zone(3)
        self.assertEqual(m.match_count(zone, zone), 1024)

    def test_partial_match(self):
        zone = make_zone(4)
        page = list(zone)
        for i in range(524):
            page[i] = word(99, i)
        self.assertEqual(m.match_count(page, zone), 500)

    def test_page_matches_ordering(self):
        page = make_zone(5)
        zones = {"A": make_zone(5), "B": make_zone(6)}
        scored = m.page_matches(page, zones)
        self.assertEqual(scored[0][0], 1024)
        self.assertEqual(scored[0][1], "A")
        self.assertLess(scored[1][0], 50)


class TestAmbiguityAndFill(unittest.TestCase):
    def test_duplicate_zones_are_ambiguous(self):
        zone = make_zone(7)
        page = list(zone)
        conf = m.classify(1024, 1024, False, False)
        self.assertEqual(conf, "AMBIG")
        self.assertEqual(m.match_count(page, zone), 1024)

    def test_fill_zone_detected_and_excluded(self):
        fill = [m.AA] * 512 + [m.FIVE] * 512
        self.assertTrue(m.is_fill_zone(fill))
        self.assertFalse(m.is_fill_zone(make_zone(8)))
        conf = m.classify(600, 100, True, False)
        self.assertEqual(conf, "FILL")

    def test_zero_table_classified_as_table(self):
        table = [tuple([0] * 6)] * 1024
        self.assertTrue(m.is_zero_table(table))
        conf = m.classify(950, 300, False, True)
        self.assertEqual(conf, "TABLE")

    def test_low_score_is_none(self):
        self.assertEqual(m.classify(12, 5, False, False), "NONE")

    def test_zero_page_is_not_a_zone_match(self):
        page = [tuple([0] * 6)] * 1024
        self.assertTrue(m.is_zero_page(page))
        self.assertEqual(
            m.classify(1020, 1020, False, True, True), "ZERO")
        self.assertFalse(m.is_zero_page(make_zone(11)))


class TestTableRendering(unittest.TestCase):
    def test_build_table_and_render(self):
        zone = make_zone(9)
        zones = {"MBE-0154": zone, "MBE-0155": make_zone(10)}
        mem = [tuple([0] * 6)] * (32 * 1024)
        mem[1 * 1024:2 * 1024] = zone  # page 01 = zone 0154
        rows = m.build_table("snap", mem, zones)
        self.assertEqual(len(rows), 32)
        self.assertEqual(rows[1]["zone"], "MBE-0154")
        self.assertEqual(rows[1]["count"], 1024)
        self.assertIn(rows[1]["confidence"], ("EXACT", "AMBIG"))
        text = m.render_markdown(rows)
        self.assertIn("| snapshot | page | base | zone |", text)
        self.assertEqual(text.count("\n"), 33)

    def test_summarize_found_and_excluded(self):
        rows = [
            {"confidence": "EXACT", "zone": "MBE-0154"},
            {"confidence": "FILL", "zone": "MBE-0146"},
            {"confidence": "NONE", "zone": "MBE-0137"},
        ]
        found, excluded = m.summarize(rows)
        self.assertEqual(found, {"MBE-0154"})
        self.assertEqual(excluded, {"MBE-0146"})


if __name__ == "__main__":
    unittest.main()
