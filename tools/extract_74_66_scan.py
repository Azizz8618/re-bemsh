#!/usr/bin/env python3
"""Сканер пропусков Э74/Э66/Э72 в отчётах разбора КОНД.

Вход: docs/SEMANTIC/B-KOND-DECODE-{1,2,3}.md и gold/MBE-Z<зона>-L1.bin.
Выход: таблица `зона | адрес | слово | половина | причина | замена | байты`.

Правило байтовой безопасности выведено из 20 полных пересборок зон
через dispak (см. docs/EXTRACT-74-66-DECODE-FIX.md): левая половина
типа addrex/stop/call вызывает авто-вставку `мода` и сдвиг слов;
immex в левой половине и любая мнемоника в правой сдвига не дают.
"""

import argparse
import os
import re
import sys

# Локальный путь к эталонной таблице OPS (siprod_asm.decode).
SIPROD_TOOLS = os.path.expanduser("~/Yandex.Disk/re-siprod/tools")
try:
    if SIPROD_TOOLS not in sys.path:
        sys.path.insert(0, SIPROD_TOOLS)
    from siprod_asm import decode as _decode  # noqa: E402
except Exception:  # pragma: no cover - зависит от окружения
    _decode = None

REPORT_NAMES = (
    "docs/SEMANTIC/B-KOND-DECODE-1.md",
    "docs/SEMANTIC/B-KOND-DECODE-2.md",
    "docs/SEMANTIC/B-KOND-DECODE-3.md",
)
TARGETS = ("Э66", "Э72", "Э74")
# Типы, которые МАКРО-БЕМШ ставит только в правую половину.
LEFT_UNSAFE_KINDS = frozenset(("addrex", "stop", "call"))
RE_WORD = re.compile(r"([0-7]{16})")


def decode(half):
    """Разбор 24-битной половины. Возвращает имя, тип, адрес, регистр, EXP."""
    if _decode is not None:
        return _decode(half)
    # Минимальный запасной декодер, если re-siprod недоступен.
    table = (
        ("Э66", 0x036000, "immex"), ("Э72", 0x03a000, "addrex"),
        ("Э74", 0x03c000, "stop"), ("Э73", 0x03b000, "addrex"),
        ("мода", 0x090000, "addrmod"), ("уиа", 0x0a0000, "reg2"),
        ("зп", 0, "str1"), ("сбр", 0x010000, "str1"),
        ("пб", 0x0c0000, "jump"),
    )
    struct = 1 if half & 0x80000 else 0
    exp = 1 if half & 0x40000 else 0
    op = (half >> 15) & 0o17 if struct else (half >> 12) & 0o77
    code = ((0o100000 if struct else 0) |
            (0o040000 if exp else 0) | (op << 12))
    name, kind = "illegal", "illegal"
    for n, c, k in table:
        if c == (code & 0o177000):
            name, kind = n, k
            break
    return dict(name=name, kind=kind, reg=(half >> 20) & 0o17,
                arg=(half & 0o7777) + (0o700000 if exp else 0),
                exp=exp, raw=half, struct=struct)


def format_half(half):
    """Печатная форма одной 24-битной команды для исходника .be."""
    d = decode(half)
    name = d["name"].upper()
    if name == "МОДА" and half == 0o02200000:
        return "МОДА"
    idx = "(М%o)" % d["reg"] if d["reg"] else ""
    kind = d["kind"]
    if kind == "reg1":
        return ("%s М%o%s" % (name, d["arg"], idx)).rstrip()
    if kind == "reg2":
        return ("%s %d%s" % (name, d["arg"], idx)).rstrip()
    arg = d["arg"]
    if d["exp"]:
        lit = "'7%04o'" % (arg & 0o7777)
    elif arg == 0 and kind in ("str1", "st2"):
        lit = ""
    else:
        lit = "'%04o'" % arg
    return ("%s %s%s" % (name, lit, idx)).rstrip()


def parse_report(path):
    """Достать строки пропусков с Э66/Э72/Э74 из таблицы отчёта."""
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|\n").split("|")]
            if len(cells) < 5 or not cells[0].isdigit():
                continue
            zone, addr, raw_cell, _halves, reason = cells[:5]
            if "пропуск" not in reason:
                continue
            m = RE_WORD.search(raw_cell)
            if m is None:
                continue
            raw = m.group(1)
            hits = [t for t in TARGETS if t in reason]
            if not hits:
                continue
            rows.append(dict(zone=zone, address=int(addr), raw=raw,
                             reason=reason, targets=hits,
                             source=os.path.basename(path)))
    return rows


def read_gold_word(repo, zone, address):
    """Прочитать 48-битное слово из эталона зоны по адресу-индексу."""
    for prefix in ("MBE", "MBE2", "ASM"):
        path = os.path.join(repo, "gold",
                            "%s-Z%s-L1.bin" % (prefix, zone))
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as handle:
            data = handle.read()
        if (address + 1) * 6 > len(data):
            return None, path
        word = int.from_bytes(data[address * 6:address * 6 + 6], "big")
        return word, path
    return None, None


def byte_safety(left_half):
    """Вернуть (флаг, причина) по типу ЛЕВОЙ половины."""
    d = decode(left_half)
    if d["kind"] in LEFT_UNSAFE_KINDS:
        return (False, "авто-мода: %s (%s) слева" % (d["name"], d["kind"]))
    return (True, "сдвига нет: %s (%s) слева" % (d["name"], d["kind"]))


def enrich(repo, row):
    """Добавить к строке данные из gold и предложенную замену."""
    left = int(row["raw"][:8], 8)
    right = int(row["raw"][8:], 8)
    word, gold_path = read_gold_word(repo, row["zone"], row["address"])
    row["gold_match"] = (word == int(row["raw"], 8))
    row["gold_path"] = gold_path
    row["left"] = format_half(left)
    row["right"] = format_half(right)
    row["halves"] = "%s / %s" % (row["left"], row["right"])
    safe, why = byte_safety(left)
    row["byte_safe"] = safe
    row["why"] = why
    return row


def scan(repo, report_names=REPORT_NAMES):
    """Просканировать отчёты и эталоны. Вернуть список строк."""
    repo = os.path.abspath(repo)
    seen = set()
    out = []
    for name in report_names:
        for row in parse_report(os.path.join(repo, name)):
            key = (row["zone"], row["address"], row["raw"])
            if key in seen:
                continue
            seen.add(key)
            out.append(enrich(repo, row))
    return out


def print_table(rows):
    """Печать таблицы в фиксированных колонках."""
    head = ("зона", "адрес", "сырое слово", "Э-половина",
            "причина пропуска", "предложенная замена", "байты")
    print(" | ".join(head))
    print("-" * 118)
    for r in rows:
        print(" | ".join((
            r["zone"], str(r["address"]), r["raw"],
            ",".join(r["targets"]),
            r["reason"].replace("пропуск: ", ""),
            r["halves"],
            "OK" if r["byte_safe"] else "НЕТ (%s)" % r["why"],
        )))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".",
                    help="корень репозитория (по умолчанию текущий каталог)")
    ap.add_argument("--report", action="append", default=None,
                    help="путь отчёта относительно repo (можно повторять)")
    ap.add_argument("--json", action="store_true",
                    help="печать JSON вместо таблицы")
    args = ap.parse_args(argv)
    reports = args.report or list(REPORT_NAMES)
    rows = scan(args.repo, reports)
    if args.json:
        import json
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print_table(rows)
    ok = sum(1 for r in rows if r["byte_safe"])
    print("\nИТОГО: %d случаев, байтово безопасно %d, остаться КОНД %d" %
          (len(rows), ok, len(rows) - ok))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
