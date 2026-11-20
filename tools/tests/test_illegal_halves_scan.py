#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты tools/illegal_halves_scan.py (stdlib, unittest).

Запуск:
  python3 -m unittest \
    tools.tests.test_illegal_halves_scan -v
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(
    Path(__file__).resolve().parents[1]))

import illegal_halves_scan as IS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

# Слова 0137:0061..0065, см. Z0137.md:138-144.
WORDS = {
    0o61: ("2067711510002003", "СЧМ"),
    0o62: ("2066604010010004", "СЛ"),
    0o63: ("2047704010010005", "ВЧ"),
    0o64: ("2047711730410006", "ВЧОБ"),
    0o65: ("2047710130410007", "ВЧАБ"),
}


class FieldDecodeTests(unittest.TestCase):
    def test_left_halves_none_and_fields(self):
        expected = {
            0o63: (4, 0o47, 0o7040),
            0o64: (4, 0o47, 0o7117),
            0o65: (4, 0o47, 0o7101),
        }
        for addr, values in expected.items():
            with self.subTest(addr=oct(addr)):
                raw = WORDS[addr][0]
                left = IS.decode_half(
                    int(raw[:8], 8))
                self.assertIsNone(left["name"])
                self.assertEqual(left["kind"],
                                 "illegal")
                got = (left["reg"], left["op"],
                       left["arg"])
                self.assertEqual(got, values)
                self.assertEqual(left["exp"], 0)
                self.assertEqual(left["struct"], 0)

    def test_word_61_left_is_legal_e67(self):
        raw = WORDS[0o61][0]
        left = IS.decode_half(int(raw[:8], 8))
        self.assertEqual(left["name"], "Э67")
        self.assertEqual(left["kind"], "addrex")
        self.assertEqual(left["op"], 0o67)

    def test_right_halves_match_user(self):
        expected = {
            0o61: ("зп", 0o2003),
            0o62: ("зпм", 4),
            0o63: ("зпм", 5),
            0o64: ("уим", 6),
            0o65: ("уим", 7),
        }
        for addr, values in expected.items():
            with self.subTest(addr=oct(addr)):
                raw = WORDS[addr][0]
                right = IS.decode_half(
                    int(raw[8:], 8))
                self.assertEqual(right["name"],
                                 values[0])
                self.assertEqual(right["arg"],
                                 values[1])

    def test_fallback_matches_siprod(self):
        for raw, _text in WORDS.values():
            for part in (raw[:8], raw[8:]):
                half = int(part, 8)
                with self.subTest(half=part):
                    got = IS.decode_fallback(half)
                    self.assertEqual(got,
                                     IS.decode_half(half))


class Koi7Tests(unittest.TestCase):
    def test_koi7_text_of_five_words(self):
        for addr, item in WORDS.items():
            raw, text = item
            with self.subTest(addr=oct(addr)):
                got = IS.koi7_text(int(raw, 8))
                self.assertEqual(got, text)

    def test_verdict_is_data_koi7(self):
        for raw, _text in WORDS.values():
            info = IS.describe_word(int(raw, 8))
            self.assertEqual(info["verdict"],
                             "DATA KOI7")

    def test_pattern_key(self):
        raw = "2047704010010005"
        self.assertEqual(
            IS.pattern_key(int(raw, 8)), "2047xxxx")
        raw = "2067711510002003"
        self.assertEqual(
            IS.pattern_key(int(raw, 8)), "2067xxxx")


class ByteProofTests(unittest.TestCase):
    @staticmethod
    def pack(half):
        dec = IS.decode_half(half)
        word = ((dec["reg"] << 20) |
                (dec["op"] << 12) |
                (dec["arg"] & 0o7777))
        if dec["dms"]:
            word |= 0x200000
        if dec["exp"]:
            word |= 0x40000
        return word

    def test_split_lines_are_byte_identical(self):
        raw = WORDS[0o62][0]
        word = int(raw, 8)
        left = self.pack(word >> 24)
        right = self.pack(word & 0xFFFFFF)
        self.assertEqual((left << 24) | right, word)

    def test_gold_bytes_match_table(self):
        zone = ROOT / "gold/MBE-Z0137-L1.bin"
        with open(zone, "rb") as handle:
            data = handle.read()
        for addr, item in WORDS.items():
            raw = item[0]
            with self.subTest(addr=oct(addr)):
                got = data[addr * 6:addr * 6 + 6].hex()
                self.assertEqual(
                    got, format(int(raw, 8), "012x"))

    def test_exp_bit_zero_in_2047_pattern(self):
        for addr in (0o63, 0o64, 0o65):
            raw = WORDS[addr][0]
            half = int(raw[:8], 8)
            self.assertEqual(
                IS.decode_half(half)["exp"], 0)


class ScanTests(unittest.TestCase):
    def test_scan_finds_target_word(self):
        rows = IS.scan(str(ROOT))
        target = "2047704010010005"
        hits = [r for r in rows if r["raw"] == target]
        self.assertTrue(hits)
        sample = hits[0]
        self.assertEqual(sample["file"],
                         "bemsh/MBE-Z0137.be")
        self.assertGreater(sample["line"], 0)
        self.assertEqual(sample["verdict"],
                         "DATA KOI7")
        self.assertIsNone(sample["left_name"])

    def test_group_2047_is_all_koi7(self):
        rows = IS.scan(str(ROOT))
        groups = IS.group_rows(rows)
        group = groups["2047xxxx"]
        self.assertGreaterEqual(group["count"], 30)
        self.assertTrue(all(
            r["verdict"] == "DATA KOI7"
            for r in group["rows"]))
        texts = {r["koi7"].strip()
                 for r in group["rows"]}
        self.assertEqual(texts, {"ВЧ", "ВЧОБ", "ВЧАБ"})

    def test_all_mode_includes_e67(self):
        rows = IS.scan(str(ROOT), only_none=False)
        target = "2067711510002003"
        hits = [r for r in rows if r["raw"] == target]
        self.assertTrue(hits)
        self.assertEqual(hits[0]["left_name"], "Э67")

    def test_temp_fixture_line_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bemsh"
            path.mkdir()
            line = ("        КОНД "
                    "В'2047704010010005'"
                    "    ,тест\n")
            (path / "T.be").write_text(
                line, encoding="utf-8")
            pat = ("bemsh/*.be",)
            rows = IS.scan(tmp, patterns=pat)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["line"], 1)
            self.assertEqual(rows[0]["file"],
                             "bemsh/T.be")

    def test_cli_filter_json(self):
        buf = io.StringIO()
        args = ["--repo", str(ROOT),
                "--filter", "2047", "--json"]
        with redirect_stdout(buf):
            code = IS.main(args)
        self.assertEqual(code, 0)
        text = buf.getvalue().split("ИТОГО:")[0]
        payload = json.loads(text)
        self.assertIn("2047xxxx",
                      payload["groups"])
        self.assertGreater(payload["total"], 0)
        rows = payload["groups"]["2047xxxx"]["rows"]
        self.assertNotIn("left", rows[0])


if __name__ == "__main__":
    unittest.main()
