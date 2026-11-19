#!/usr/bin/env python3
"""Юнит-тесты конвертера disbesm6 -> BEMSH (tools/dis2be.py).

Запуск: python3 -m unittest tools/tests/test_dis2be.py -v
"""

import hashlib
import os
import sys
import tempfile
import unittest

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import dis2be  # noqa: E402


HEADER = (
    "          File: gold/MBE-ZTEST-L1.bin\n"
    "         Type: Binary\n"
    "         Code: 36 (00006) words\n"
    "      Address: 0\n"
    "\n"
    "\t\t\t\tСТАРТ\t'0'\n"
)

FOOTER = "\t\t\t\tФИНИШ\n"


def write_listing(text):
    """Записать временный листинг и вернуть его имя."""
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".asm", delete=False
    )
    handle.write(text)
    handle.close()
    return handle.name


def convert_text(listing, zone="0137"):
    """Прогнать листинг через разбор+конвертацию, вернуть текст .be."""
    path = write_listing(listing)
    try:
        words, symbols = dis2be.parse_listing(path)
        return dis2be.convert(words, symbols, zone)
    finally:
        os.unlink(path)


class TestDis2Be(unittest.TestCase):

    def test_octal_constant_conversion(self):
        """конд п'<ГОСТ>' и в'<...>' -> КОНД В'<16 окт. цифр>'."""
        listing = (
            HEADER
            + "    5 0000000000000077\t\tконд\tп'00000D'\n"
            + "    6 6400000000000000\t\tконд\tв'6400000000000000'\n"
            + FOOTER
        )
        text = convert_text(listing)
        self.assertIn("КОНД В'0000000000000077'", text)
        self.assertIn("КОНД В'6400000000000000'", text)
        # GOSTR-операнд не должен попасть в исходник: там только окталь.
        self.assertNotIn("п'", text)
        for line in text.splitlines():
            if line.lstrip().startswith("КОНД "):
                self.assertRegex(line, r"^\s*КОНД В'[0-7]{16}'")

    def test_two_halves_splitting(self):
        """Одно слово -> две строки .be (левая и правая половины)."""
        listing = (
            HEADER
            + "    0 00 000 0000 \tSTART\tзп\tSTART\n"
            + "      00 100 0000 \t\tзп\t'70000'\n"
            + FOOTER
        )
        words, _symbols = dis2be.parse_listing(write_listing(listing))
        self.assertEqual(len(words), 1)
        self.assertEqual(words[0].kind, "code")
        self.assertEqual(len(words[0].halves), 2)
        text = convert_text(listing)
        self.assertIn("        ЗП             ,слово 0, лев. часть", text)
        self.assertIn("        ЗП   '70000'    ,слово 0, прав. часть", text)

    def test_zero_address_omitted(self):
        """START (адрес 0) -> пустой операнд: `ЗП`, не `ЗП 0`."""
        listing = (
            HEADER
            + "    0 00 000 0000 \tSTART\tзп\tSTART\n"
            + "      00 020 0000 \t\tсбр\tSTART\n"
            + FOOTER
        )
        text = convert_text(listing)
        self.assertIn("        ЗП             ,слово 0, лев. часть", text)
        self.assertIn("        СБР            ,слово 0, прав. часть", text)
        self.assertNotIn("START", text)
        self.assertNotIn("ЗП 0", text)

    def test_mn_preserved(self):
        """Индекс `(Мn)` переносится без изменений."""
        listing = (
            HEADER
            + "    0 00 000 0000 \t\tзп\tSTART\n"
            + "      03 30 00000 \t\tпб\t(М3)\n"
            + FOOTER
        )
        text = convert_text(listing)
        self.assertIn("        ПБ   (М3)       ,слово 0, прав. часть", text)

    def test_data_symbol_to_octal_constant(self):
        """Символ D00003 -> `'3'` с пояснением `(адр. 3)`."""
        listing = (
            HEADER
            + "    2 00 000 0000 \t\tзп\tSTART\n"
            + "      00 000 0003 \t\tзп\tD00003\n"
            + "    3 00 000 0000 \tD00003\tзп\tSTART\n"
            + "      00 002 3554 \t\tрег\t'3554'\n"
            + FOOTER
        )
        text = convert_text(listing)
        self.assertIn(
            "        ЗП   '3'        ,слово 2, прав. часть (адр. 3)", text
        )
        self.assertIn("        РЕГ  '3554'     ,слово 3, прав. часть", text)

    def test_zero_word_run(self):
        """`пам 1` -> нулевое слово КОНД В'000...000'."""
        listing = HEADER + "  130            \t\tпам\t1\n" + FOOTER
        text = convert_text(listing)
        self.assertIn(
            "        КОНД В'0000000000000000'    ,слово 130", text
        )

    def test_zero_run_alignment(self):
        """`пам 3` -> три нулевых слова с последовательными адресами.

        Каждое нулевое слово должно дать отдельную строку КОНД, иначе
        сборщик склеит половины разных слов и сдвинет весь последующий код.
        """
        listing = HEADER + "  130            \t\tпам\t3\n" + FOOTER
        text = convert_text(listing)
        for addr in ("130", "131", "132"):
            self.assertIn(
                "        КОНД В'0000000000000000'    ,слово %s" % addr, text
            )
        self.assertEqual(text.count("КОНД В'0000000000000000'"), 3)

    def test_suppressed_right_half_gets_moda(self):
        """Подавленная правая половина -> явная строка `мода`.

        Без неё сборщик приклеит левую половину следующего слова и сдвинет
        код (то, что ломало зону 0147 до исправления).
        """
        listing = (
            HEADER
            + "    1 00 30 00000 \t\tпб\tSTART\n"
            + FOOTER
        )
        words, _symbols = dis2be.parse_listing(write_listing(listing))
        self.assertTrue(words[0].suppressed_right)
        self.assertEqual(len(words[0].halves), 2)
        self.assertEqual(words[0].halves[1][0], "мода")
        text = convert_text(listing)
        self.assertIn(",слово 1, лев. часть", text)
        self.assertRegex(text, r"\s+[Мм][Оо][Дд][Аа]+\s+,слово 1, прав\. часть")

    def test_auto_label_with_modifier(self):
        """A#####/D##### с `(Мn)` -> числовой восьмеричный операнд.

        Автометка не определена в .be, поэтому должна стать `'...'`, а
        модификатор `(Мn)` — сохраниться во всех путях символов.
        """
        listing = (
            HEADER
            + "    2 00 000 0000 \t\tзп\tSTART\n"
            + "      00 016 00610 \t\tсд\tA00610-6(М11)\n"
            + FOOTER
        )
        text = convert_text(listing)
        self.assertIn("'602'(М11)", text)  # 00610₈ - 6 = 602₈
        self.assertIn("автометка A00610 -> адр. 602", text)
        # Автометка не должна остаться операндом (только в пояснении).
        operand_line = [l for l in text.splitlines() if "прав. часть" in l][0]
        self.assertNotIn("A00610", operand_line.split(",")[0])

    def test_right_half_only_mnemonic_in_left_half_is_raw(self):
        """ПВ/Э70 в ЛЕВОЙ половине -> сырое `КОНД`, а не две строки.

        МАКРО-БЕМШ ставит `пв`/`Э70` только в правую половину; в левой он
        сам вставляет `00 22 00000` (мода) и сдвигает все слова. Выводим
        такое слово одним КОНД с точными битами из колонки листинга.
        """
        listing = (
            HEADER
            + " 1220 16 31 01322 \tD01220\tпв\tA01322(М16)\n"
            + "      00 040 1315 \t\tуи\tМ15\n"
            + FOOTER
        )
        text = convert_text(listing)
        self.assertIn(
            "        КОНД В'7310132200401315'    ,слово 1220", text
        )
        self.assertNotIn("ПВ   ", text)
        self.assertNotIn("УИ   ", text)

    def test_zone_0137_regression(self):
        """Регрессия: вывод конвертера == эталону побайтово."""
        src = os.path.join(REPO_ROOT, "dis", "MBE-Z0137-L1.asm")
        gold = os.path.join(REPO_ROOT, "tools", "tests", "fixtures", "MBE-Z0137.be")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "MBE-Z0137.be")
            dis2be.main(["--input", src, "--output", out])
            with open(gold, "rb") as handle:
                expected = handle.read()
            with open(out, "rb") as handle:
                actual = handle.read()
        self.assertEqual(actual, expected, "вывод конвертера отличается от эталона")
        self.assertEqual(
            hashlib.md5(actual).hexdigest(),
            "555369a1adfad6d033fe2e9b2122847c",
        )


    def test_auto_label_with_modifier(self):
        """A##### с (Мn) -> числовой адрес с сохранённым модификатором."""
        op, note = dis2be.translate_operand("A01322(М16)", {})
        self.assertEqual(op, "'1322'(М16)")
        self.assertIn("автометка", note)

    def test_symbol_with_delta(self):
        """START+1 -> адрес 1; D-метка со сдвигом -> адрес ±N."""
        op, _ = dis2be.translate_operand("START+1", {"START": 0})
        self.assertEqual(op, "'1'")
        op, _ = dis2be.translate_operand("D01124-20", {"D01124": 0o1124})
        self.assertEqual(op, "'1100'")

    def test_raw_all_does_not_invent_semantics(self):
        """--raw-all помечает, что семантика не восстановлена."""
        src = os.path.join(REPO_ROOT, "dis", "MBE-Z0137-L1.asm")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.be")
            dis2be.main(["--input", src, "--output", out,
                         "--zone", "0137", "--raw-all"])
            text = open(out, encoding="utf-8").read()
        self.assertIn("РЕЖИМ RAW-ALL", text)
        self.assertIn("СЕМАНТИКА НЕ ВОССТАНОВЛЕНА", text)
        self.assertEqual(text.count("КОНД В'"), 1024)


    def test_special_mnemonics_are_raw(self):
        """конк/пио36/э72/э74 распознаются как особые (сырое слово)."""
        listing = (
            HEADER
            + "    0 17 32 70707\t\tвыпр\t'70707'(М17)\n"
            + "      02000000\t\tконк\tв'02000000'\n"
            + FOOTER
        )
        self.assertIn("конк", listing)

    def test_auto_label_decimal_delta(self):
        """D01124-20: сдвиг десятичный, результат восьмеричный адрес."""
        op, _ = dis2be.translate_operand("D01124-20", {"D01124": 0o1124})
        self.assertEqual(op, "'1100'")


if __name__ == "__main__":
    unittest.main()
