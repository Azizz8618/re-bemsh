#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты tools/v78_label_index.py.

Запуск:
  python3 -m unittest tools/tests/test_v78_label_index.py -v
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
TOOL = TOOLS / "v78_label_index.py"
ROOT = TOOLS.parent

SPEC = importlib.util.spec_from_file_location(
    "v78_label_index", str(TOOL))
v78 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v78)

SCHEMA = ["label", "zone", "base", "offset", "absolute",
          "kind", "file", "line"]

MAP_STUB = """# Тестовая карта зон
Зона | база | рез | доказательство | статус
-----|------|-----|----------------|-------
0147 | 00000 | ДА | RZ:31 | ФАКТ
0150 | 70000 | ДА | RSM:65 | ФАКТ
0151 | - | НЕТ | RSM:66 | НЕ ИЗВЕСТНО
0152 | 76000 | ДА | RSM:67 | ФАКТ
0174 | 72000? | НЕТ | MM:122 | ГИПОТЕЗА

    0147,00000,ФАКТ
    0150,70000,ФАКТ
    0151,-,НЕ ИЗВЕСТНО
    0152,76000,ФАКТ
    0174,72000?,ГИПОТЕЗА
"""


def label_body(labels, header=""):
    """Тело .be из списка имён меток."""
    lines = [header] if header else []
    lines.extend("%s  ЗП" % name for name in labels)
    return "\n".join(lines) + "\n"


class V78LabelIndexTest(unittest.TestCase):

    def make_root(self, files=None, map_text=None):
        tmp = tempfile.TemporaryDirectory(
            prefix="v78-labels-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "bemsh").mkdir()
        (root / "analysis").mkdir()
        map_path = root / "analysis" / "ZONE-BASE-MAP.md"
        map_path.write_text(
            MAP_STUB if map_text is None else map_text,
            encoding="utf-8")
        for name, body in (files or {}).items():
            (root / "bemsh" / name).write_text(
                body, encoding="utf-8")
        return root

    def run_cli(self, root, *args):
        return subprocess.run(
            [sys.executable, str(TOOL), "--root", str(root)]
            + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)

    # --- восьмеричная арифметика ---

    def test_oct_text_padding(self):
        self.assertEqual(v78.oct_text(1), "00001")
        self.assertEqual(v78.oct_text(8, 4), "0010")

    def test_add_octal_basic(self):
        self.assertEqual(
            v78.add_octal("02000", "0011"), "02011")

    def test_add_octal_carry(self):
        self.assertEqual(
            v78.add_octal("75777", "0001"), "76000")

    def test_add_octal_b2(self):
        self.assertEqual(
            v78.add_octal("10000", "1777"), "11777")

    def test_add_octal_empty_base(self):
        self.assertEqual(v78.add_octal("", "0001"), "")

    # --- схема записи ---

    def test_record_schema(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(["D00001"])})
        records, _ = v78.build_index(root)
        self.assertEqual(len(records), 1)
        self.assertEqual(list(records[0]), SCHEMA)

    def test_kind_code_a(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(["A00001"])})
        records, _ = v78.build_index(root)
        self.assertEqual(records[0]["kind"], "code")

    def test_kind_code_g(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(["G00002"])})
        records, _ = v78.build_index(root)
        self.assertEqual(records[0]["kind"], "code")

    def test_kind_data_d(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(["D00003"])})
        records, _ = v78.build_index(root)
        self.assertEqual(records[0]["kind"], "data")

    def test_offset_from_label(self):
        root = self.make_root({
            "MBE2-Z0540.be": label_body(["A01036"])})
        records, _ = v78.build_index(root)
        self.assertEqual(records[0]["offset"], "01036")
        self.assertEqual(records[0]["absolute"], "11036")

    def test_zone_from_filename(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(["D00001"])})
        records, _ = v78.build_index(root)
        self.assertEqual(records[0]["zone"], "0147")

    def test_file_and_line(self):
        root = self.make_root({
            "MBE-Z0147.be": "Z0147 СТАРТ '10000'\n"
                            "D00007  ЗП\n"})
        records, _ = v78.build_index(root)
        self.assertEqual(records[0]["file"],
                         "bemsh/MBE-Z0147.be")
        self.assertEqual(records[0]["line"], 2)

    def test_sort_is_deterministic(self):
        root = self.make_root({
            "MBE-Z0152.be": label_body(
                ["D00003", "A00001", "D00002"])})
        first, _ = v78.build_index(root)
        second, _ = v78.build_index(root)
        self.assertEqual(first, second)
        self.assertEqual(
            [r["label"] for r in first],
            ["A00001", "D00002", "D00003"])

    # --- разбор баз ---

    def test_base_map_comma_row(self):
        data = v78.parse_base_map(MAP_STUB)
        self.assertEqual(data["0147"][0], "00000")

    def test_base_map_table_row(self):
        text = "| 0150 | 70000 | ДА | RSM:65 | ФАКТ |\n"
        data = v78.parse_base_map(text)
        self.assertEqual(data["0150"][0], "70000")
        self.assertEqual(data["0150"][1], "ФАКТ")

    def test_base_map_unknown(self):
        data = v78.parse_base_map(MAP_STUB)
        self.assertIsNone(data["0151"][0])

    def test_base_map_hypothesis(self):
        data = v78.parse_base_map(MAP_STUB)
        self.assertEqual(data["0174"][0], "72000")
        self.assertEqual(data["0174"][1], "ГИПОТЕЗА")

    def test_external_not_zone(self):
        text = "    030000,-,НЕ ИЗВЕСТНО\n"
        data = v78.parse_base_map(text)
        self.assertNotIn("030000", data)

    def test_external_not_base(self):
        self.assertIsNone(v78.normalize_base("030000"))

    def test_special_zone_0137(self):
        value, source = v78.resolve_base(
            "0137", "B", {}, None)
        self.assertEqual(value, "00000")
        self.assertEqual(source, "SPECIAL")

    def test_mapped_b2_base(self):
        value, source = v78.resolve_base(
            "0540", "B2", {}, None)
        self.assertEqual(value, "10000")
        self.assertEqual(source, "MAPPED")

    def test_b2_ham_base(self):
        value, source = v78.resolve_base(
            "0545", "B2", {}, "00001")
        self.assertEqual(value, "00001")
        self.assertEqual(source, "MAPPED-HAM")

    def test_mapped_asm_base(self):
        value, source = v78.resolve_base(
            "0055", "ASM", {}, None)
        self.assertEqual(value, "10000")
        self.assertEqual(source, "MAPPED")

    def test_start_fallback(self):
        value, source = v78.resolve_base(
            "0151", "B", {"0151": (None, "-")},
            "10000")
        self.assertEqual(value, "10000")
        self.assertEqual(source, "START")

    def test_parse_start_from_be(self):
        self.assertEqual(
            v78.parse_start("Z0152 СТАРТ '75777'\n"),
            "75777")

    # --- проверки ---

    def test_duplicate_conflict(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(
                ["A00001", "D00001"])})
        records, _ = v78.build_index(root)
        errors = v78.validate(records)
        self.assertTrue(
            any("конфликт" in e for e in errors))

    def test_same_label_twice_ok(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(
                ["D00001", "D00001"])})
        records, _ = v78.build_index(root)
        errors = [e for e in v78.validate(records)
                  if "конфликт" in e]
        self.assertEqual(errors, [])

    def test_offset_out_of_range(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(["D02000"])})
        records, _ = v78.build_index(root)
        errors = v78.validate(records)
        self.assertTrue(
            any("01777" in e for e in errors))

    def test_missing_base_detected(self):
        root = self.make_root({
            "MBE-Z0555.be": label_body(["D00001"])})
        records, _ = v78.build_index(root)
        errors = v78.validate(records)
        self.assertTrue(
            any("нет базы" in e for e in errors))

    def test_malformed_first_field(self):
        root = self.make_root({
            "MBE-Z0147.be": "D00008  ЗП\n"})
        records, warnings = v78.build_index(root)
        self.assertEqual(records, [])
        self.assertTrue(
            any("D00008" in w for w in warnings))

    def test_asm_check_warning(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(
                ["A00001", "D00002"])})
        asm = root / "dis-forced"
        asm.mkdir()
        (asm / "Z0147.asm").write_text(
            "A00001  сч 1\n", encoding="utf-8")
        _records, warnings = v78.build_index(root, True)
        self.assertTrue(
            any("D00002" in w and "dis-forced" in w
                for w in warnings))

    # --- CLI ---

    def test_cli_help(self):
        result = subprocess.run(
            [sys.executable, str(TOOL), "--help"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--kind", result.stdout)
        self.assertIn("--asm-check", result.stdout)

    def test_cli_json_records(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(
                ["A00001", "D00002"])})
        result = self.run_cli(root, "--format", "json")
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload), 2)
        self.assertEqual(list(payload[0]), SCHEMA)

    def test_cli_text_format(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(["D00001"])})
        result = self.run_cli(root, "--format", "text")
        self.assertEqual(result.returncode, 0)
        self.assertIn("D00001", result.stdout)
        self.assertIn("ФАЙЛ:СТРОКА", result.stdout)

    def test_cli_kind_filter(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(
                ["A00001", "D00002"])})
        result = self.run_cli(
            root, "--format", "json", "--kind", "data")
        payload = json.loads(result.stdout)
        self.assertEqual(
            [r["label"] for r in payload], ["D00002"])

    def test_cli_zone_filter(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(["D00001"]),
            "MBE-Z0150.be": label_body(["D00002"])})
        result = self.run_cli(
            root, "--format", "json", "--zone", "0150")
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["zone"], "0150")

    def test_cli_summary(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(
                ["A00001", "D00002"])})
        result = self.run_cli(
            root, "--format", "json", "--summary")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["summary"]["total"], 2)
        self.assertEqual(
            payload["summary"]["by_kind"],
            {"code": 1, "data": 1})
        self.assertEqual(
            payload["summary"]["by_zone"], {"0147": 2})

    def test_cli_check_pass(self):
        files = {}
        for zone in ("0147", "0150", "0152"):
            names = ["D" + format(num, "05o")
                     for num in range(700)]
            files["MBE-Z%s.be" % zone] = label_body(names)
        result = self.run_cli(self.make_root(files),
                              "--check")
        self.assertEqual(result.returncode, 0,
                         result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertIn("меток 2100", result.stdout)

    def test_cli_check_fail_low_count(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(["D00001"])})
        result = self.run_cli(root, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("нужно >=2000", result.stderr)

    def test_cli_check_fail_conflict(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(
                ["A00001", "D00001"])})
        result = self.run_cli(root, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("конфликт", result.stderr)

    def test_cli_bad_zone_exit_two(self):
        root = self.make_root()
        result = self.run_cli(root, "--zone", "12345")
        self.assertEqual(result.returncode, 2)

    def test_cli_missing_root_exit_two(self):
        result = self.run_cli(ROOT / "нет-такого-каталога")
        self.assertEqual(result.returncode, 2)

    def test_cli_read_only(self):
        root = self.make_root({
            "MBE-Z0147.be": label_body(["D00001"])})
        paths = [root / "bemsh" / "MBE-Z0147.be",
                 root / "analysis" / "ZONE-BASE-MAP.md"]
        before = [hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in paths]
        self.run_cli(root, "--format", "json")
        after = [hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in paths]
        self.assertEqual(before, after)


@unittest.skipUnless(
    (ROOT / "bemsh" / "MBE-Z0137.be").is_file(),
    "нет bemsh/MBE-Z0137.be")
class V78IntegrationTest(unittest.TestCase):

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOL), "--root", str(ROOT)]
            + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)

    def test_real_z0137(self):
        result = self.run_cli(
            "--format", "json", "--zone", "0137")
        self.assertEqual(result.returncode, 0,
                         result.stderr)
        records = json.loads(result.stdout)
        self.assertEqual(len(records), 27)
        for record in records:
            self.assertEqual(list(record), SCHEMA)
            self.assertEqual(record["zone"], "0137")
            self.assertEqual(record["base"], "00000")
            self.assertEqual(
                record["absolute"],
                v78.oct_text(int(record["offset"], 8)))
            self.assertEqual(
                record["file"], "bemsh/MBE-Z0137.be")
        self.assertIn("A01036",
                      [r["label"] for r in records])

    def test_real_zone_base_map(self):
        path = ROOT / "analysis" / "ZONE-BASE-MAP.md"
        if not path.is_file():
            self.skipTest("нет ZONE-BASE-MAP.md")
        data = v78.parse_base_map(
            path.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 69)
        self.assertEqual(data["0147"][0], "00000")
        self.assertEqual(data["0152"][0], "76000")
        self.assertEqual(data["0174"][0], "72000")
        self.assertIsNone(data["0055"][0])
        self.assertNotIn("030000", data)


if __name__ == "__main__":
    unittest.main()
