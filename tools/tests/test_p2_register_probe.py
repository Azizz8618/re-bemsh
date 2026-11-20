#!/usr/bin/env python3
"""Тесты парсеров tools/p2_register_probe.sh (только stdlib, unittest).

Парсер встроен в shell-скрипт и извлекается через --emit-parser,
поэтому тесты проверяют тот же код, что запускает рабочий скрипт.
"""
import contextlib
import io
import subprocess
import types
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
SCRIPT = TOOLS / "p2_register_probe.sh"


def load_parser():
    src = subprocess.check_output(["bash", str(SCRIPT), "--emit-parser"],
                                  text=True)
    mod = types.ModuleType("p2reg_parse")
    exec(compile(src, str(SCRIPT), "exec"), mod.__dict__)
    return mod


p = load_parser()


class TestTraceParsing(unittest.TestCase):
    def test_parse_trace_line_with_register(self):
        rec = p.parse_trace_line(
            "03651: wtc 2157(1)          (=6040000000065366) "
            "acc=2031463100000000 r[1]=00141")
        self.assertIsNotNone(rec)
        addr, mnem, regs = rec
        self.assertEqual(addr, "03651")
        self.assertEqual(mnem, "wtc")
        self.assertEqual(regs, [("M1", 0o141)])

    def test_parse_trace_line_octal_register_number(self):
        # dispak prints the 4-bit field in octal: r[15] is M15, not decimal 15.
        rec = p.parse_trace_line("01413: atx 12000(15) r[15]=04000 r[17]=1")
        self.assertEqual(rec[2], [("M15", 0o4000), ("M17", 1)])

    def test_parse_trace_line_without_registers(self):
        rec = p.parse_trace_line("00010: ntr 7 (=0) acc=2031463100000000")
        self.assertEqual(rec[2], [])

    def test_parse_trace_line_rejects_noise(self):
        self.assertIsNone(p.parse_trace_line("  acc = 000... Y = 000..."))
        self.assertIsNone(p.parse_trace_line(""))
        self.assertIsNone(p.parse_trace_line("not an address: text"))

    def test_run_trace_end_to_end(self):
        sample = [
            "03651: wtc 2157(1) r[1]=00141\n",
            "02000: xta 6065(15) r[15]=77772\n",
            "14054: vtm 4000(2) r[2]=00000\n",
        ]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            p.run_trace(sample)
        text = out.getvalue()
        self.assertIn("instructions = 3", text)
        self.assertIn("top5=00141:1", text)
        self.assertIn("0154 editor @02000", text)
        self.assertIn("77772:1", text)


class TestBreakpointParsing(unittest.TestCase):
    def test_bp_index_to_label(self):
        self.assertEqual(p.bp_index_to_label(1), "M1")
        self.assertEqual(p.bp_index_to_label(7), "M7")
        self.assertEqual(p.bp_index_to_label(8), "M10")
        self.assertEqual(p.bp_index_to_label(9), "M11")
        self.assertEqual(p.bp_index_to_label(15), "M17")
        self.assertEqual(p.bp_index_to_label(0), "M?")
        self.assertEqual(p.bp_index_to_label(16), "M?")

    def test_parse_bp_dump(self):
        block = [
            "-  02000: 00 010 6065\txta",
            "  acc = 0010130000301762 Y = 0000000000000000 R = 000111",
            "       76626 01723 00000 00005 75636 14021 00000 70000",
            "       75734 75665 77711 77065 77772 00001 70010",
        ]
        addr, regs = p.parse_bp_dump(block)
        self.assertEqual(addr, "02000")
        self.assertEqual(len(regs), 15)
        self.assertEqual(regs["M1"], 0o76626)
        self.assertEqual(regs["M13"], 0o77711)
        self.assertEqual(regs["M15"], 0o77772)
        self.assertEqual(regs["M16"], 0o00001)
        self.assertEqual(regs["M17"], 0o70010)

    def test_parse_bp_dump_rejects_malformed(self):
        self.assertIsNone(p.parse_bp_dump(["-  02000: insn", "acc = 0"]))
        bad = ["-  02000: insn", "  acc = 0", "1 2 3", "4 5 6"]
        self.assertIsNone(p.parse_bp_dump(bad))


class TestHelpers(unittest.TestCase):
    def test_region_of(self):
        self.assertEqual(p.region_of("01322"), "0147 core @00000")
        self.assertEqual(p.region_of("02000"), "0154 editor @02000")
        self.assertEqual(p.region_of("24001"), "0161 @24000")
        self.assertEqual(p.region_of("30000"), "")

    def test_summarize(self):
        d, n, top = p.summarize([1, 1, 2, 2, 2, 3])
        self.assertEqual((d, n), (3, 6))
        self.assertEqual(top[0], (2, 3))
        self.assertEqual(dict(top), {1: 2, 2: 3, 3: 1})

    def test_fmt_oct(self):
        self.assertEqual(p.fmt_oct(0o141), "00141")
        self.assertEqual(p.fmt_oct(0o77777), "77777")


class TestGuard(unittest.TestCase):
    def test_guard_refuses_real_image_dir(self):
        env = {"BESM6_PATH": "/usr/local/share/besm6", "PATH": "/usr/bin:/bin"}
        r = subprocess.run(["bash", str(SCRIPT)], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 3)
        self.assertIn("real image directory", r.stderr)

    def test_guard_refuses_missing_path(self):
        env = {"PATH": "/usr/bin:/bin"}
        r = subprocess.run(["bash", str(SCRIPT)], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 3)
        self.assertIn("BESM6_PATH not set", r.stderr)


if __name__ == "__main__":
    unittest.main()
