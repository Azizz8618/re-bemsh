#!/usr/bin/env python3
"""Автоматический конвертер листингов disbesm6 в исходники МАКРО-БЕМШ (.be).

Вход:  dis/MBE-Z<зона>-L1.asm   (листинг disbesm6 -a0 -e0)
Выход: bemsh/MBE-Z<зона>-L1.be  (исходник для транслятора БЕМШ 06/78)

Правила (проверены на зоне 0137, см. docs/REBUILD-0137.md):

* 48-битное слово disbesm6 печатает двумя строками (левая/правая
  половина); каждая половина становится отдельной строкой .be.
* `конд в'<16 окт>'` / `конд п'<ГОСТ>'` → `КОНД В'<16 окт>'`.
  Берётся СЫРОЕ слово из второй колонки листинга: символы GOSTR
  могут быть шестнадцатеричными и дать `ЧУЖОЙ СИМВОЛ` в трансляторе.
* `пам N` / `nop N` (нулевые слова) → `КОНД В'0000000000000000'`.
* Нулевой адрес не печатается (`ЗП`, а не `ЗП 0`): символ `START`
  (адрес 0) в операнде опускается.
* Символ данных `D<восьм>` → `'<восьм>'` с пояснением `(адр. <восьм>)`.
* `(Мn)` и восьмеричные константы `'...'` сохраняются как есть.

Таблица `OPS` импортируется из `re-siprod/tools/siprod_asm.py`
(через sys.path, без копирования) и используется для канонизации
мнемоник и проверки, что мнемоника известна disbesm6.
"""

import argparse
import os
import re
import sys

# Импорт таблицы OPS без копирования — через sys.path.
SIPROD_TOOLS = os.path.expanduser("~/Yandex.Disk/re-siprod/tools")
if SIPROD_TOOLS not in sys.path:
    sys.path.insert(0, SIPROD_TOOLS)
try:
    from siprod_asm import OPS, OPCODE_BY_NAME  # noqa: F401
except Exception as exc:  # pragma: no cover - зависит от окружения
    OPS = []
    OPCODE_BY_NAME = {}
    OPS_IMPORT_ERROR = exc
else:
    OPS_IMPORT_ERROR = None

ZERO_WORD = "0" * 16
# Мнемоники из таблицы OPS (источник — siprod_asm.py).
MNEMONICS = {name.upper() for name, _code, _mask, _kind in OPS}
UNKNOWN_MNEMONICS = set()

# Типы команд, которые МАКРО-БЕМШ 06/78 умеет ставить только в ПРАВУЮ
# половину слова. Если такая мнемоника оказывается в ЛЕВОЙ половине,
# транслятор сам вставляет слово `00 22 00000` (мода) и сдвигает все
# последующие слова — реконструкция перестаёт быть побайтовой. Такие
# слова выводятся сырым `КОНД В'...'` (см. raw_word_from_halves).
RIGHT_HALF_KINDS = frozenset(("call", "addrex", "immex", "stop"))
# Резервный список на случай, когда siprod_asm недоступен.
RIGHT_HALF_FALLBACK = frozenset(
    ["ПВ"] + ["Э%02d" % n for n in range(50, 78)]
)


def half_value_from_bits(bits):
    """24-битное значение полукоманды из колонки бит листинга disbesm6.

    `bits` выглядит как `16 31 01322` (reg, op, адрес). Кодировка та же,
    что и у парсера листинга в tools/rebuild-zone.sh: reg сдвинут на 20,
    op — на 15 для 5-значного адреса и на 12 для 4-значного.
    """
    parts = bits.split()
    if len(parts) != 3:
        return None
    try:
        reg = int(parts[0], 8)
        op = int(parts[1], 8)
        addr = int(parts[2], 8)
    except ValueError:
        return None
    shift = 15 if len(parts[2]) == 5 else 12
    return ((reg << 20) | (op << shift) | addr) & 0xFFFFFF


def is_right_half_only(mnem):
    """True, если мнемоника ставится транслятором только в правую половину."""
    upper = mnem.upper()
    entry = OPCODE_BY_NAME.get(upper)
    if entry is not None:
        return entry[2] in RIGHT_HALF_KINDS
    return upper in RIGHT_HALF_FALLBACK

# Стрoki шапки, которые disbesm6 печатает до кода.
_SKIP_PREFIXES = (
    "File:", "Type:", "Code:", "Address:",
)
_SKIP_EXACT = (
    "* next insn used as data",
)


class Word:
    """Одно 48-битное слово листинга."""

    __slots__ = (
        "addr", "addr_int", "kind", "halves", "half_bits", "raw", "count",
        "label", "suppressed_right",
    )

    def __init__(self, addr, addr_int, kind):
        self.addr = addr            # восьмеричный адрес как в листинге
        self.addr_int = addr_int    # тот же адрес числом
        self.kind = kind            # 'code' | 'data' | 'zero'
        self.halves = []            # [(мнемоника, операнд), ...] для 'code'
        self.half_bits = []         # сырые колонки бит для каждой половины
        self.raw = None             # 16 окт. цифр для 'data'
        self.count = 1              # число нулевых слов для 'zero'
        self.label = None           # метка, объявленная на этом слове
        self.suppressed_right = False  # правая половина подавлена disbesm6


def canonical_mnemonic(name):
    """Привести мнемонику disbesm6 к верхнему регистру по таблице OPS."""
    upper = name.upper()
    # OPS содержит и строчные (`зп`), и заглавные (`Э50`) имена;
    # ключи OPCODE_BY_NAME — уже верхний регистр.
    if MNEMONICS and upper not in MNEMONICS:
        UNKNOWN_MNEMONICS.add(upper)
    return upper


def parse_listing(path):
    """Разобрать листинг disbesm6 в список слов и таблицу символов.

    Возвращает (words, symbols), где symbols: имя -> адрес (int).
    """
    with open(path, "r", encoding="utf-8-sig") as handle:
        lines = handle.read().splitlines()

    words = []
    symbols = {}
    current = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in _SKIP_EXACT:
            continue
        if any(stripped.startswith(p) for p in _SKIP_PREFIXES):
            continue
        if stripped.startswith("СТАРТ") or stripped.startswith("ФИНИШ"):
            continue
        if stripped.startswith("*"):
            continue

        cols = line.split("\t")
        first = cols[0]
        label = cols[1].strip() if len(cols) > 1 else ""
        mnem = cols[2].strip() if len(cols) > 2 else ""
        operand = cols[3].strip() if len(cols) > 3 else ""
        if not mnem:
            continue

        # Первая колонка: адрес занимает фиксированные 5 символов.
        # У правой половины первые 5 символов — пробелы: адреса нет.
        addr_field = first[:5]
        tail = first[5:].strip()
        addr = addr_field.strip()
        bits = tail
        addr_int = int(addr, 8) if re.fullmatch(r"[0-7]+", addr) else None

        if label and addr_int is not None:
            symbols[label] = addr_int

        if mnem in ("конд", "КОНД"):
            if not re.fullmatch(r"[0-7]{16}", bits):
                raise ValueError(
                    "строка %r: ожидалось 16 восьмеричных цифр, получено %r"
                    % (line, bits)
                )
            word = Word(addr, addr_int, "data")
            word.raw = bits
            word.label = label or None
            words.append(word)
            current = word
            continue

        if mnem in ("пам", "nop", "ПАМ", "NOP"):
            count = int(operand, 10) if operand.isdigit() else 1
            for offset in range(count):
                word = Word(
                    oct(addr_int + offset)[2:] if addr_int is not None else addr,
                    addr_int + offset if addr_int is not None else None,
                    "zero",
                )
                word.label = label or None if offset == 0 else None
                words.append(word)
            current = None
            continue

        # Обычная команда: Half-строка disbesm6.
        if addr_int is not None:
            # Строка с адресом — левая половина нового слова.
            word = Word(addr, addr_int, "code")
            word.label = label or None
            words.append(word)
            current = word
        elif current is None or current.kind != "code":
            raise ValueError("правая половина без левой: %r" % line)

        current.halves.append((canonical_mnemonic(mnem), operand))
        current.half_bits.append(bits)

    # disbesm6 подавляет правую половину, если она равна 0 или 02200000₈
    # ( guide: W_NORIGHT). В БЕМШ 02200000₈ = МОДА с нулевым адресом.
    # Без явной строки сборщик склеит половины разных слов и сдвинет код.
    for word in words:
        if word.kind == "code" and len(word.halves) == 1:
            word.halves.append(("мода", ""))
            word.half_bits.append("00 22 00000")
            word.suppressed_right = True

    return words, symbols


def translate_operand(operand, symbols):
    """Перевести операнд disbesm6 в операнд БЕМШ.

    Возвращает (операнд, пояснение) — пояснение добавляется в комментарий.
    """
    if not operand:
        return "", None

    # Модификатор (Мn) всегда сохраняется — он часть машинного слова.
    mmod = re.fullmatch(r"(.*?)(\(М[0-7]+\))?$", operand, re.S)
    core, modifier = mmod.group(1), mmod.group(2) or ""

    # Голый (Мn), восьмеричная константа или уже числовой адрес.
    if re.fullmatch(r"'[0-7]+'", core) or not core:
        return core + modifier, None

    # Символ из таблицы: адрес 0 не печатается, остальные — как 'восьм'.
    if core in symbols:
        addr = symbols[core]
        if addr == 0 and not modifier:
            return "", None
        oct_addr = oct(addr)[2:]
        return "'%s'%s" % (oct_addr, modifier), "адр. %s" % oct_addr

    # Автометики disbesm6 A#####/D##### — это ВОСЬМЕРИЧНЫЙ адрес внутри зоны.
    # В .be их нельзя оставлять как метки: они не определены в исходнике.
    # Преобразуем в числовой операнд '...', сохраняя (Мn) и фuzz-сдвиг +N.
    m = re.fullmatch(r"([AD])([0-7]{5})(([+-])([0-9]+))?", core)
    if m:
        addr = int(m.group(2), 8)
        delta = int(m.group(5)) if m.group(5) else 0
        if m.group(4) == "-":
            addr -= delta
        else:
            addr += delta
        addr %= 32768
        note = "автометка %s -> адр. %o" % (m.group(1) + m.group(2), addr)
        return "'%o'%s" % (addr, modifier), note

    # Символ со смещением: START+1, NAME-2 (сдвиг — десятичный, fuzz=64).
    m = re.fullmatch(r"([A-Za-zА-Яа-я*][\w*]*)([+-])(\d+)", core)
    if m and (m.group(1) in symbols or m.group(1) == "START"):
        base = 0 if m.group(1) == "START" else symbols[m.group(1)]
        delta = int(m.group(3))
        addr = (base + delta if m.group(2) == "+" else base - delta) % 32768
        note = "%s%s%s -> адр. %o" % (m.group(1), m.group(2), m.group(3), addr)
        return "'%o'%s" % (addr, modifier), note

    # Неизвестный символ: оставить как есть (отмечается как ограничение).
    return operand, None


def format_code_line(mnem, operand, word_addr, side, note=None):
    """Одна строка .be для половины команды (выравнивание как в эталоне)."""
    mnem_field = mnem.ljust(5)
    if operand:
        op_field = operand.ljust(11)   # запятая в колонке 24
    else:
        op_field = " " * 10           # запятая в колонке 23
    comment = ",слово %s, %s. часть" % (word_addr, side)
    if note:
        comment += " (%s)" % note
    line = "        " + mnem_field + op_field + comment
    # МАКРО-БЕМШ 06/78 ломает строку ровно в 80 колонок: комментарий
    # переходит на новую строку и даёт «ОПЕРАЦИИ НЕТ». Держим <=78.
    if len(line) > 79:
        base = "        " + mnem_field + op_field + comment.split(" (")[0]
        if note:
            room = 79 - len(base) - 3
            if room > 3:
                line = base + " (" + note[:room] + ")"
            else:
                line = base
        else:
            line = base[:78]
    return line


def format_data_line(raw, word_addr):
    """Одна строка .be для слова данных."""
    return "        КОНД В'%s'    ,слово %s" % (raw, word_addr)


def build_header(zone, nwords, last_code_addr, data_addrs=None,
                 source="original"):
    """Шапка исходника (точно как в bemsh/MBE-Z0137.be).

    ``data_addrs`` — фактические адреса слов данных/забелов (числа).
    Диапазон данных НЕ выводится из ``nwords``: в принудительном листинге
    код занимает все адреса, и наивный расчёт даёт бредовый ``1024-1023``.
    Пустой список означает «данных нет», ``None`` сохраняет старое
    поведение для режима ``--raw-all`` (там адреса не разбираются).
    ``source='full'`` добавляет пометку о принудительной трассировке.
    """
    nbytes = nwords * 6
    lines = [
        "***************************************************",
        "* MBE-Z{0} — реконструкция зоны {0}₈ ({1} слова)".format(zone, nwords),
        "*   ТРАНСЛЯТОР С М/К БЕМШ ВЕР.06/78, том 2348.",
        "*   Эталон: gold/MBE-Z{0}-L1.bin ({1} байт).".format(zone, nbytes),
        "*   Слова 0-%s — команды (сверены побайтово)." % (
            last_code_addr if last_code_addr is not None else -1
        ),
    ]

    if data_addrs is None:
        # Устаревший путь (--raw-all): фактические адреса неизвестны.
        first_data = (last_code_addr + 1) if last_code_addr is not None else 0
        last_data = nwords - 1
    else:
        data_addrs = sorted(data_addrs)
        first_data = data_addrs[0] if data_addrs else None
        last_data = data_addrs[-1] if data_addrs else None

    if data_addrs is not None and not data_addrs:
        lines.append("*   Данных/забелов нет: все слова восстановлены как код.")
    elif first_data is not None and first_data <= last_data:
        lines.append(
            "*   Слова %s-%s — КОНД: таблицы, данные, забелы."
            % (first_data, last_data)
        )
    # first_data > last_data — строку диапазона не печатаем вовсе.

    if source == "full":
        lines.append("*   Источник: принудительная трассировка (все адреса W_CODE).")
        lines.append(
            "*   ВНИМАНИЕ: разбиение на код/данные навязано принудительно,"
        )
        lines.append("*             а не вычислено по достижимости.")

    lines.extend([
        "*   Сборка и сверка: tools/rebuild-zone.sh %s B" % zone,
        "*   Статус: ПОДЛЕЖИТ ПРОВЕРКЕ (rebuild-zone.sh).",
        "***************************************************",
        "*** КОД МОДУЛЯ",
        "*",
        "Z%s   СТАРТ 1" % zone,
        "        Е",
        "        М",
    ])
    return lines


def raw_word_from_halves(word):
    """Собрать 16 окт. цифр слова из сырых колонок бит его половин.

    Возвращает None, если хотя бы одной половины нет в листинге (например,
    подавленная правая половина) или колонка бит неразбираема.
    """
    if len(word.half_bits) != len(word.halves):
        return None
    values = [half_value_from_bits(bits) for bits in word.half_bits]
    if any(value is None for value in values):
        return None
    left, right = (values + [0, 0])[:2]
    return "%016o" % (((left & 0xFFFFFF) << 24) | (right & 0xFFFFFF))


def convert(words, symbols, zone, gold_path=None, source="original"):
    """Собрать текст .be из разобранных слов.

    Если задан gold-дамп, подавленная disbesm6 правая половина берётся
    оттуда: это может быть 0 (`зп`) или 02200000₈ (`мода`).
    ``source`` ('original'|'full') управляет пометкой в шапке: полный
    листинг получен принудительной трассировкой всех адресов как W_CODE.
    """
    gold = None
    if gold_path and os.path.exists(gold_path):
        with open(gold_path, "rb") as handle:
            gold = handle.read()
    for word in words:
        if getattr(word, "suppressed_right", False) and gold is not None:
            addr = word.addr_int
            if addr is not None and (addr + 1) * 6 <= len(gold):
                value = int.from_bytes(gold[addr * 6:addr * 6 + 6], "big")
                right = value & 0xFFFFFF
                if right == 0:
                    word.halves[1] = ("зп", "")
                elif right == 0o2200000:
                    word.halves[1] = ("мода", "")
                # иные значения оставляем как есть (мода) — редкий случай

    out = []
    code_addrs = [w.addr_int for w in words if w.kind == "code" and w.addr_int is not None]
    data_addrs = [
        w.addr_int for w in words
        if w.kind in ("data", "zero") and w.addr_int is not None
    ]
    last_code_addr = max(code_addrs) if code_addrs else None
    out.extend(build_header(
        zone, len(words), last_code_addr,
        data_addrs=data_addrs, source=source,
    ))

    for word in words:
        if word.kind == "data":
            out.append(format_data_line(word.raw, word.addr))
        elif word.kind == "zero":
            out.append(format_data_line(ZERO_WORD, word.addr))
        else:
            # Подавленная disbesm6 правая половина неизвестна из
            # листинга, но доступна в gold. Выводим всё слово сырым КОНД —
            # это точно сохраняет байты и исключает авто-вставку `00 22`.
            if (
                getattr(word, "suppressed_right", False)
                and gold is not None
                and word.addr_int is not None
                and (word.addr_int + 1) * 6 <= len(gold)
            ):
                value = int.from_bytes(
                    gold[word.addr_int * 6:word.addr_int * 6 + 6], "big"
                )
                out.append(format_data_line("%016o" % value, word.addr))
                continue
            # `конк` — неиспользуемый/незаконный код половины; `пио36`
            # без адреса транслируется ошибкой «ОПЕРАЦИИ НЕТ».
            # В обоих случаях выводим всё слово сырым КОНД.
            if any(h[0].lower() in ("конк", "пио36", "э72", "э74") for h in word.halves):
                if (
                    gold is not None
                    and word.addr_int is not None
                    and (word.addr_int + 1) * 6 <= len(gold)
                ):
                    value = int.from_bytes(
                        gold[word.addr_int * 6:word.addr_int * 6 + 6], "big"
                    )
                    out.append(format_data_line("%016o" % value, word.addr))
                    continue
            # Команда, которая БЕМШ ставит только в правую половину, в левой
            # половине вызывает авто-вставку `00 22` и сдвиг кода. Такую
            # пару половин выводим одним сырым словом КОНД.
            if word.halves and is_right_half_only(word.halves[0][0]):
                raw = raw_word_from_halves(word)
                if raw is not None:
                    out.append(format_data_line(raw, word.addr))
                    continue
            for index, (mnem, operand) in enumerate(word.halves):
                op, note = translate_operand(operand, symbols)
                side = "лев" if index == 0 else "прав"
                out.append(
                    format_code_line(mnem, op, word.addr, side, note)
                )

    out.append("        ФИНИШ")
    return "\n".join(out) + "\n"


def zone_from_input(path):
    """Вывести номер зоны (восьмеричный) из имени файла листинга."""
    match = re.search(
        r"(?:(?:MBE|MBE2|ASM)-)?Z([0-7]+)(?:-L1|-full)?\.asm$",
        os.path.basename(path),
    )
    if not match:
        raise ValueError("не удалось определить зону из имени %r" % path)
    return match.group(1)


def source_from_input(path):
    """Автоопределение источника листинга: 'full' или 'original'.

    Полным считается листинг с суффиксом ``-full.asm`` и листинг из
    каталога ``dis-forced/`` (там все адреса помечены как W_CODE).
    """
    base = os.path.basename(path)
    if re.search(r"-full\.asm$", base):
        return "full"
    normalized = path.replace("\\", "/")
    if re.search(r"(?:^|/)dis-forced/Z[0-7]+\.asm$", normalized):
        return "full"
    return "original"


def default_output(path):
    """Выходной путь по умолчанию: bemsh/<имя>.be."""
    base = os.path.basename(path)
    name = base[:-4] + ".be" if base.endswith(".asm") else base + ".be"
    return os.path.join("bemsh", name)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Конвертер disbesm6-листинга в исходник МАКРО-БЕМШ (.be)"
    )
    parser.add_argument("--input", required=True, help="листинг disbesm6 (.asm)")
    parser.add_argument("--output", help="выходной .be (по умолчанию из имени входа)")
    parser.add_argument("--zone", help="номер зоны (восьмеричный); иначе из имени")
    parser.add_argument(
        "--source",
        choices=("full", "original"),
        default=None,
        help="тип листинга: full — принудительная трассировка (все адреса "
             "W_CODE), original — обычная. По умолчанию из имени файла.",
    )
    parser.add_argument(
        "--raw-all",
        action="store_true",
        help="аварийный режим: всё слово как КОНД из gold (байты точны, семантика НЕ восстановлена)",
    )
    args = parser.parse_args(argv)

    zone = args.zone or zone_from_input(args.input)
    output = args.output or default_output(args.input)
    source = args.source or source_from_input(args.input)

    if OPS_IMPORT_ERROR is not None:
        print(
            "warning: не удалось импортировать OPS из %s: %s"
            % (SIPROD_TOOLS, OPS_IMPORT_ERROR),
            file=sys.stderr,
        )

    gold_path = os.path.join(
        "gold", os.path.basename(args.input)[:-4] + ".bin"
    )
    # Шапка зависит от транслируемого объекта: зоны 0055-0060 — автокод ИТМ,
    # 0137-0177 — МАКРО-БЕМШ 06/78, 0540-0577 — ВАР.12/77.
    base = os.path.basename(args.input)
    if base.startswith("ASM-"):
        text_prefix, kind = "ASM", "ASM"
        product = "ТРАНСЛЯТОР С А/К И Т М (автокод ИТМ, .75)"
    elif base.startswith("MBE2-"):
        text_prefix, kind = "MBE2", "MBE2"
        product = "ТРАНСЛЯТОР С М/К БЕМШ ВАР.12/77"
    else:
        text_prefix, kind = "MBE", "B"
        product = "ТРАНСЛЯТОР С М/К БЕМШ ВЕР.06/78"

    def fix_header(text):
        return (text
            .replace("MBE-Z", text_prefix + "-Z")
            .replace("ТРАНСЛЯТОР С М/К БЕМШ ВЕР.06/78", product)
            .replace("gold/MBE-Z", "gold/" + text_prefix + "-Z")
            .replace("rebuild-zone.sh %s B" % zone,
                     "rebuild-zone.sh %s %s" % (zone, kind)))

    if args.raw_all:
        if not os.path.exists(gold_path):
            parser.error("нет gold-дампа для --raw-all: %s" % gold_path)
        with open(gold_path, "rb") as handle:
            blob = handle.read()
        nwords = len(blob) // 6
        out = list(build_header(zone, nwords, None, source=source))
        rebuild = "*   Сборка и сверка: tools/rebuild-zone.sh %s B" % zone
        out[out.index(rebuild)] = (
            "*   РЕЖИМ RAW-ALL: байты точны, СЕМАНТИКА НЕ ВОССТАНОВЛЕНА."
        )
        out.append("*** КОД МОДУЛЯ")
        out.append("*")
        for i in range(nwords):
            value = int.from_bytes(blob[i * 6:i * 6 + 6], "big")
            out.append(format_data_line("%016o" % value, oct(i)[2:]))
        out.append("        ФИНИШ")
        text = "\n".join(out) + "\n"
        nwords_out = nwords
    else:
        words, symbols = parse_listing(args.input)
        text = convert(words, symbols, zone, gold_path, source=source)
        nwords_out = len(words)

    text = fix_header(text)

    if UNKNOWN_MNEMONICS:
        print(
            "warning: мнемоники вне таблицы OPS: %s"
            % ", ".join(sorted(UNKNOWN_MNEMONICS)),
            file=sys.stderr,
        )

    out_dir = os.path.dirname(os.path.abspath(output))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)

    print("Зона %s: %d слов -> %s" % (zone, nwords_out, output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
