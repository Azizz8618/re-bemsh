#!/usr/bin/env python3
"""Unit tests for tools/asm_proc_comments.py.

Fixtures are synthetic; the real doc is read read-only.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asm_proc_comments as m  # noqa: E402

REAL_DOC = Path(__file__).resolve().parents[2] / "docs" / "PROCEDURES-ASM.md"

SYNTH_DOC = [
    "## 5. ЗОНА 0055",
    "",
    "### 5.1 Тестовый каталог (синтетический)",
    "",
    "Формат: `старт-конец разм вх выход вызывающие`.",
    "",
    "```",
    "0220-0221 001 C2  -      0300 0323",
    "0232-0235 004 C1  X0235  0201",
    "0276-0277 002 C1  -      0411",
    "```",
]


def assert_block_clean(testcase, block):
    testcase.assertTrue(all(len(l) <= 55 and not any(c in l for c in m.BAD)
                            for l in block))


class TestParseZone(unittest.TestCase):
    def test_parse_synthetic(self):
        recs = m.parse_zone("0055", SYNTH_DOC)
        self.assertEqual([r["start"] for r in recs], ["0220", "0232", "0276"])
        self.assertEqual(recs[0]["end"], "0221")
        self.assertEqual(recs[0]["size"], "001")
        self.assertEqual(recs[0]["kind"], "C2")
        self.assertEqual(recs[1]["exit_tok"], "X0235")
        self.assertEqual(recs[0]["note"], "")


class TestGenerate(unittest.TestCase):
    def test_generate_synthetic(self):
        recs, block = m.generate("0055", SYNTH_DOC)
        self.assertEqual(len(recs), 3)
        self.assertIn(m.LEGEND[0], block)
        self.assertIn("* Всего процедур: 3 (кандидаты §5.1; детали §5.2).",
                      block)
        self.assertIn("* ПРОЦ 0220-0221 size=001 C2", block)
        self.assertIn("*   ВХ 0220; ВЫХ нет (fallthrough)", block)
        self.assertIn("*   ВХ 0232; ВЫХ X0235 (уход из зоны)", block)
        self.assertIn("*   РЕГ -", block)
        self.assertTrue(any("D00720" in l for l in block))
        assert_block_clean(self, block)


class TestRealDoc(unittest.TestCase):
    def test_zone_0055_real_doc(self):
        lines = REAL_DOC.read_text(encoding="utf-8").splitlines()
        recs = m.parse_zone("0055", lines)
        self.assertGreater(len(recs), 0)
        self.assertIn("0220", [r["start"] for r in recs])
        recs2, block = m.generate("0055", lines)
        self.assertEqual(len(recs2), len(recs))
        assert_block_clean(self, block)


if __name__ == "__main__":
    unittest.main()
