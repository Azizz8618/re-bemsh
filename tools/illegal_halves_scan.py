#!/usr/bin/env python3
"""Сканер слов КОНД с неразбираемой левой половиной.

Левая половина считается illegal, когда
siprod_asm.decode() возвращает name=None. Причины:
opcode отсутствует в таблице OPS (например 047 = Э47,
отключённый в disbesm6.c:84), либо слово вообще не
команда, а данные KOI-7.

Выход: группы по шаблону старших 4 восьмеричных цифр
слова (2047xxxx, 2067xxxx, ...) с доказательствами
file:line.
"""

import argparse
import glob
import os
import re
import sys

SIPROD_TOOLS = os.path.expanduser(
    "~/Yandex.Disk/re-siprod/tools")
try:
    if SIPROD_TOOLS not in sys.path:
        sys.path.insert(0, SIPROD_TOOLS)
    from siprod_asm import decode as _decode  # noqa: E402
except Exception:  # pragma: no cover - зависит от окружения
    _decode = None

DEFAULT_GLOBS = (
    "bemsh/*.be",
    "dis/*.asm",
    "dis-forced/*.asm",
    "tools/tests/fixtures/*.be",
)

RE_WORD = re.compile(r"(?<![0-7])([0-7]{16})(?![0-7])")

# Таблица из disbesm6.c:45-128 и siprod_asm.py:41-80.
# Запасной декодер на случай отсутствия re-siprod.
M2 = 0x0bf000  # маска 2-й структуры
M1 = 0x0f8000  # маска 1-й структуры
OPS_LOCAL = [
    ("зп", 0x000000, M2, "str1"),
    ("зпм", 0x001000, M2, "str1"),
    ("рег", 0x002000, M2, "imm"),
    ("счм", 0x003000, M2, "str1"),
    ("сл", 0x004000, M2, "str1"),
    ("вч", 0x005000, M2, "str1"),
    ("вчоб", 0x006000, M2, "str1"),
    ("вчаб", 0x007000, M2, "str1"),
    ("сч", 0x008000, M2, "str1"),
    ("и", 0x009000, M2, "str1"),
    ("нтж", 0x00a000, M2, "str1"),
    ("слц", 0x00b000, M2, "str1"),
    ("знак", 0x00c000, M2, "str1"),
    ("или", 0x00d000, M2, "str1"),
    ("дел", 0x00e000, M2, "str1"),
    ("умн", 0x00f000, M2, "str1"),
    ("сбр", 0x010000, M2, "str1"),
    ("рзб", 0x011000, M2, "str1"),
    ("чед", 0x012000, M2, "str1"),
    ("нед", 0x013000, M2, "str1"),
    ("слп", 0x014000, M2, "str1"),
    ("вчп", 0x015000, M2, "str1"),
    ("сд", 0x016000, M2, "str1"),
    ("рж", 0x017000, M2, "str1"),
    ("счрж", 0x018000, M2, "imm"),
    ("счмр", 0x019000, M2, "imm64"),
    ("увв", 0x01b000, M2, "imm"),
    ("слпа", 0x01c000, M2, "imm64"),
    ("вчпа", 0x01d000, M2, "imm64"),
    ("сда", 0x01e000, M2, "imm64"),
    ("ржа", 0x01f000, M2, "imm"),
    ("уи", 0x020000, M2, "reg1"),
    ("уим", 0x021000, M2, "reg1"),
    ("счи", 0x022000, M2, "reg1"),
    ("счим", 0x023000, M2, "reg1"),
    ("уии", 0x024000, M2, "reg1"),
    ("сли", 0x025000, M2, "reg1"),
    ("Э50", 0x028000, M2, "immex"),
    ("Э51", 0x029000, M2, "immex"),
    ("Э52", 0x02a000, M2, "immex"),
    ("Э53", 0x02b000, M2, "immex"),
    ("Э54", 0x02c000, M2, "immex"),
    ("Э55", 0x02d000, M2, "immex"),
    ("Э56", 0x02e000, M2, "immex"),
    ("Э57", 0x02f000, M2, "immex"),
    ("Э60", 0x030000, M2, "addrex"),
    ("Э61", 0x031000, M2, "addrex"),
    ("Э62", 0x032000, M2, "immex"),
    ("Э63", 0x033000, M2, "immex"),
    ("Э64", 0x034000, M2, "addrex"),
    ("Э65", 0x035000, M2, "immex"),
    ("Э66", 0x036000, M2, "immex"),
    ("Э67", 0x037000, M2, "addrex"),
    ("Э70", 0x038000, M2, "addrex"),
    ("Э71", 0x039000, M2, "addrex"),
    ("Э72", 0x03a000, M2, "addrex"),
    ("Э73", 0x03b000, M2, "addrex"),
    ("Э74", 0x03c000, M2, "stop"),
    ("Э75", 0x03d000, M2, "addrex"),
    ("Э76", 0x03e000, M2, "immex"),
    ("Э77", 0x03f000, M2, "immex"),
    ("мода", 0x090000, M1, "addrmod"),
    ("мод", 0x098000, M1, "addrmod"),
    ("уиа", 0x0a0000, M1, "reg2"),
    ("слиа", 0x0a8000, M1, "reg2"),
    ("по", 0x0b0000, M1, "branch"),
    ("пе", 0x0b8000, M1, "branch"),
    ("пб", 0x0c0000, M1, "jump"),
    ("пв", 0x0c8000, M1, "call"),
    ("выпр", 0x0d0000, M1, "iret"),
    ("стоп", 0x0d8000, M1, "imm2"),
    ("пио", 0x0e0000, M1, "branch"),
    ("пино", 0x0e8000, M1, "branch"),
    ("пио36", 0x0f0000, M1, "branch"),
    ("цикл", 0x0f8000, M1, "branch"),
]

# KOI-7 по docs/SEMANTIC/Z0137.md:138-163.
# Включены только встречающиеся знаки.
KOI7 = {
    0x20: " ", 0x30: "0", 0x31: "1", 0x32: "2",
    0x33: "3", 0x34: "4", 0x35: "5", 0x36: "6",
    0x37: "7", 0x38: "8", 0x39: "9", 0x41: "А",
    0x42: "В", 0x43: "С", 0x44: "Д", 0x45: "Е",
    0x48: "Н", 0x49: "И", 0x4A: "Й", 0x4B: "К",
    0x4C: "Л", 0x4D: "М", 0x4F: "О", 0x54: "Т",
    0x59: "У", 0x62: "Б", 0x63: "Ц", 0x64: "Д",
    0x69: "И", 0x6C: "Л", 0x70: "П", 0x76: "Ж",
    0x7A: "З", 0x7C: "Э", 0x7E: "Ч",
}

CYRILLIC = "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ"


def decode_fallback(half):
    """Разбор половины без внешней зависимости."""
    name, kind = None, "illegal"
    for entry in OPS_LOCAL:
        n, code, mask, k = entry
        if half & mask == code:
            name, kind = n, k
            break
    reg = (half >> 20) & 0xF
    dms = 1 if half & 0x200000 else 0
    struct = 1 if half & 0x80000 else 0
    if struct:
        op = (half >> 15) & 0o17
        addr = half & 0o77777
        exp = 0
    else:
        op = (half >> 12) & 0o77
        exp = 1 if half & 0x40000 else 0
        addr = (half & 0o7777) + (0o700000 if exp else 0)
    return dict(name=name, kind=kind, reg=reg, arg=addr,
                dms=dms, exp=exp, op=op, struct=struct,
                raw=half)


def decode_half(half):
    """Декодер: siprod_asm, при отсутствии -- запасной."""
    return _decode(half) if _decode is not None \
        else decode_fallback(half)


def koi7_text(word):
    """Первые 4 байта KOI-7 как текст мнемоники."""
    data = word.to_bytes(6, "big")[:4]
    return "".join(KOI7.get(b, "·") for b in data).rstrip()


def pattern_key(word):
    """Старшие 4 восьмеричные цифры слова + xxxx."""
    return format(word >> 36, "04o") + "xxxx"


def describe_word(word):
    """Поля половин и диагноз для 48-битного слова."""
    left = decode_half(word >> 24)
    right = decode_half(word & 0xFFFFFF)
    txt = koi7_text(word)
    letters = sum(1 for c in txt if c in CYRILLIC)
    verdict = "DATA KOI7" if letters >= 2 else "НЕИЗВ"
    return dict(raw=format(word, "016o"),
                pattern=pattern_key(word),
                left_name=left["name"],
                right_name=right["name"],
                left=left, right=right, koi7=txt,
                verdict=verdict)


def scan(repo, patterns=DEFAULT_GLOBS, only_none=True):
    """Слова с name=None слева, либо все."""
    repo = os.path.abspath(repo)
    rows, seen = [], set()
    for pattern in patterns:
        mask = os.path.join(repo, pattern)
        for path in sorted(glob.glob(mask)):
            with open(path, encoding="utf-8",
                      errors="replace") as handle:
                scan_lines(handle, path, repo, rows,
                           seen, only_none)
    return rows


def scan_lines(handle, path, repo, rows, seen, only_none):
    """Обход строк одного файла."""
    for lineno, line in enumerate(handle, 1):
        matches = dict.fromkeys(
            m.group(1) for m in RE_WORD.finditer(line))
        for match in matches:
            add_row(match, path, lineno, repo, rows,
                    seen, only_none)


def add_row(match, path, lineno, repo, rows, seen,
            only_none):
    """Добавить одну строку в результат."""
    word = int(match, 8)
    info = describe_word(word)
    if only_none and info["left"]["name"] is not None:
        return
    key = (match, path, lineno)
    if key in seen:
        return
    seen.add(key)
    info.update(raw=match,
                file=os.path.relpath(path, repo),
                line=lineno)
    rows.append(info)


def group_rows(rows):
    """Группировка по pattern_key."""
    groups = {}
    for row in rows:
        item = groups.setdefault(row["pattern"],
                                 dict(count=0, rows=[]))
        item["count"] += 1
        item["rows"].append(row)
    return dict(sorted(groups.items(),
                       key=lambda kv: -kv[1]["count"]))


def print_groups(groups, limit):
    """Сводка по группам."""
    print("шаблон   всего  KOI7  file:line")
    print("-" * 60)
    for pattern, item in list(groups.items())[:limit]:
        sample = item["rows"][0]
        print("%-8s %5d  %-5s %s:%d" % (
            pattern, item["count"], sample["koi7"],
            sample["file"], sample["line"]))


def print_rows(rows):
    """Построчный список с полями левой половины."""
    print("слово              шаблон   reg op адр  EXP KOI")
    print("-" * 60)
    for row in rows:
        left = row["left"]
        print("%s %-8s %o  %02o %04o %d  %s" % (
            row["raw"], row["pattern"], left["reg"],
            left["op"], left["arg"] & 0o7777,
            left["exp"], row["koi7"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".",
                    help="корень репозитория")
    ap.add_argument("--pattern", action="append",
                    default=None,
                    help="шаблон glob файлов")
    ap.add_argument("--filter", default=None,
                    help="только группы с префиксом")
    ap.add_argument("--all", action="store_true",
                    help="включать обычные левые половины")
    ap.add_argument("--rows", action="store_true",
                    help="печать строк вместо сводки")
    ap.add_argument("--limit", type=int, default=30,
                    help="число групп в сводке")
    ap.add_argument("--json", action="store_true",
                    help="вывод JSON")
    args = ap.parse_args(argv)
    patterns = tuple(args.pattern) if args.pattern \
        else DEFAULT_GLOBS
    rows = scan(args.repo, patterns,
                only_none=not args.all)
    if args.filter:
        rows = [r for r in rows
                if r["pattern"].startswith(args.filter)]
    groups = group_rows(rows)
    if args.json:
        emit_json(groups)
    elif args.rows:
        print_rows(rows)
    else:
        print_groups(groups, args.limit)
    print("\nИТОГО: %d слов, %d групп" %
          (len(rows), len(groups)))
    return 0


def emit_json(groups):
    """Печать JSON без полей left/right."""
    import json
    out = {}
    for key, item in groups.items():
        clean = []
        for row in item["rows"]:
            clean.append({k: v for k, v in row.items()
                          if k not in ("left", "right")})
        out[key] = dict(count=item["count"], rows=clean)
    total = sum(item["count"]
                for item in groups.values())
    payload = dict(total=total, groups=out)
    print(json.dumps(payload,
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
