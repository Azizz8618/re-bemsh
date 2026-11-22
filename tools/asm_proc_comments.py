#!/usr/bin/env python3
"""Генерация блоков описаний процедур для ASM .be модулей.

Промотировано из /tmp/.private/azizz/gen_asm_proc_comments.py.
Функции parse_zone/generate/exit_text и данные FUNC/REG/LEGEND
перенесены без изменений; main() теперь печатает блоки на stdout
вместо записи в bemsh/*.be.
"""
import re
import sys
import textwrap

DOC = "/home/azizz/Yandex.Disk/re-bemsh/docs/PROCEDURES-ASM.md"

# Human-function summaries transcribed from sections 5.2 / 6.2 / 7.2 / 8.2.
# Em/en dashes replaced with ASCII; "x" used instead of multiplication sign.
FUNC = {
    "0055": {
        "0220": "преамбула shared-хелпера: сч и зп D00720, переход в 0221",
        "0221": "сч (М2), пв A0302(М1), зп D5, пе A00225; выход пб 5620",
        "0232": "читает D00710, зп D00713, пб A00221/4622",
        "0276": "уиа A0301(М3), сч D00720, пб A00321; настройка индекса",
        "0300": "пв A00220(М3), вход в блок 0301-0314",
        "0301": "сч D00711, уиа A0302+3(М1); работа с D00720/21/6720",
        "0321": "сда 64-8, или D00722, зп D00720, пб A00221",
        "0343": "уиа D00315(М3), счи М4, зп D00717/D00724; цикл по М4",
        "0366": "уиа A0301(М3), счи М4, пб A00344; CALL 220/221",
        "0402": "уиа D00725(М2), пб A00533, зп D00711/13/25/24",
    },
    "0056": {
        "0021": "numeric-вход: слц 50(М15), инициализация индексов",
        "0060": "numeric-вход: зп ,6777 с пустым адресом",
        "0220": "преамбула shared-хелпера; побайтово = 0055.0220",
        "0221": "сч (М2), пв A0302(М1); выход 5620/6003; = 0055.0221",
        "0302": "рзб 6257, уи М17, пб (М1)",
        "0320": "уиа D00315(М3), сч D00720; вход бит-блока 0321-0334",
        "0533": "зп 16(М3), сд 5(М11), зп D00603(М15); инициализация пар 0560/0565, 603/602",
        "0561": "и A00561-5(М15), мода (М2), перебор D01035+4(М15); выход пб 6153",
        "0662": "конк в 76116220, зп 70000, сч 4520, сда 64-21, или 4521",
        "0403": "блок печати ошибки: ОШИБКА В ОБРАЩЕНИИ К СП 40; данные 0436-0453 в коде",
    },
    "0057": {
        "0220": "уиа 50000(М1), мод D00703; НЕ совпадает с 0055/0056.0220",
        "0221": "уиа 0(М3), сч (М3), зп D00743; копирование/цикл, 7 CALL; выход 4551/3762; НЕ = 0055.0221",
        "0301": "зп D00734, пб 5577, затем зп 3265 x2 и пб 3762",
        "0533": "уи М3, пб A00001, зп (М15); короткий trampoline на старт",
        "0561": "нтж 6771, пе 6674, зп 6770, пб 6175; CALL 3604",
        "0637": "нтж 4657, по 4644, тест 0237/0252; пб 5435/5451; 5 CALL",
        "0641": "нтж D00252, пб 5435; вложенный вход в 0637; общий выход 4642",
        "0662": "сч D00163, пв A00637(М1), пв A00662(М1); рекурсивный wrapper; затем CALL 221",
    },
    "0060": {
        "0020": "пб (М1); dispatching-островок, цель CALL из слова 5",
        "0034": "трамплин: пв A00641(М1)",
        "0064": "сч D00723; работа с 0723",
        "0065": "пе 3751 (условие)",
        "0220": "зп 2(М13), зпм, зп 6770; НЕ = 0055/0056.0220",
        "0221": "сч, зп, пе 4642, зп 6770/71",
        "0301": "уи М16, сда 64+18, слиа 50000(М16), пио 6311(М5); НЕ = 0055/0056.0301",
        "0533": "по 6417, сч D00720, зп 7263; работа с 7260-7271, цикл по М1",
        "0641": "сда 64+4, и D00262, нтж D00262, сли М1(М4); пб 6577",
        "0661": "слиа 46050(М2), пино 6663, уиа 76020(М2), Э71 4323",
        "0662": "уиа 76020(М2), Э71 4323, слиа 31760(М2), сч 5726; CALL 3604; вложен в 0661",
    },
}

REG = {
    "0055": {
        "0220": "-", "0221": "М1,М2", "0232": "М2,М3", "0276": "М3", "0300": "М3",
        "0301": "М1", "0321": "-", "0343": "М3,М4", "0366": "М3,М4", "0402": "М2,М4",
    },
    "0056": {
        "0021": "М15", "0060": "нет", "0220": "-", "0221": "М1,М2", "0302": "М1",
        "0320": "М3", "0533": "М1,2,3,4,10,11,14,15,17", "0561": "М2,3,4,5,15",
        "0662": "М7,10,12,13,14", "0403": "М2,4,12,13,15,17",
    },
    "0057": {
        "0220": "М1", "0221": "М1,М3,М4", "0301": "-", "0533": "М15", "0561": "-",
        "0637": "-", "0641": "-", "0662": "М1,М3,М4",
    },
    "0060": {
        "0020": "-", "0034": "-", "0064": "-", "0065": "-", "0220": "М13", "0221": "-",
        "0301": "М5,6,7,16", "0533": "-", "0641": "М4", "0661": "М1,2,3,16",
        "0662": "М1,2,3,16",
    },
}

SECTION = {"0055": "5", "0056": "6", "0057": "7", "0060": "8"}
ROW = re.compile(r"^(\d{4})-(\d{4})\s+(\d{3})\s+(\S+)\s+(\S+)(?:\s+(.*))?$")
CALLERS = re.compile(r"^[0-7\s]+$")


def ascii_clean(s):
    # Replace any em/en dash and multiplication sign with plain ASCII.
    return (s.replace("\u2014", " - ").replace("\u2013", "-")
             .replace("\u00d7", "x").replace("\u2212", "-").strip())


def wrap(text, p1, p2, width=55):
    # Wrap by character count; Cyrillic is one column in a monospace font.
    parts = textwrap.wrap(text, width=width - len(p1),
                          break_long_words=True, break_on_hyphens=False)
    if not parts:
        parts = [""]
    return [(p1 if i == 0 else p2) + p for i, p in enumerate(parts)]


def get_table(doc_lines, sec):
    start = None
    for i, l in enumerate(doc_lines):
        if re.match(r"### " + re.escape(sec) + r"\.1 ", l):
            start = i
            break
    if start is None:
        raise RuntimeError("section not found: " + sec)
    fence = None
    for i in range(start, len(doc_lines)):
        if doc_lines[i].strip() == "```":
            fence = i
            break
    rows = []
    for l in doc_lines[fence + 1:]:
        if l.strip() == "```":
            break
        rows.append(l)
    return rows


def parse_zone(zone, doc_lines):
    rows = get_table(doc_lines, SECTION[zone])
    # Table rows wrap onto following indented physical lines. Join them so
    # notes and caller lists are captured in full.
    logical = []
    cur = None
    for raw in rows:
        if ROW.match(raw.rstrip()):
            if cur is not None:
                logical.append(cur)
            cur = raw.rstrip()
        elif cur is not None and raw.strip():
            cur += " " + raw.strip()
    if cur is not None:
        logical.append(cur)
    out = []
    for raw in logical:
        m = ROW.match(raw.rstrip())
        if not m:
            continue
        start, end, size, kind, exit_tok, tail = m.groups()
        tail = ascii_clean(tail or "")
        note = "" if CALLERS.match(tail) else tail
        note = note.replace("\u00ab", "").replace("\u00bb", "")
        note = ascii_clean(note)
        out.append({
            "start": start, "end": end, "size": size, "kind": kind,
            "exit_tok": exit_tok, "note": note,
        })
    return out


def exit_text(rec):
    tok = rec["exit_tok"]
    note = rec["note"]
    m = re.search(r"выход\s+(\d{3,4})", note)
    if m:
        return m.group(1) + " (уход из зоны)"
    if tok == "\u2014" or tok == "-" or tok == "\u2013":
        return "нет (fallthrough)"
    if tok.startswith("X"):
        return tok + " (уход из зоны)"
    if tok.startswith("R"):
        return tok + " (RET)"
    return tok


def generic_meaning(rec):
    tok = rec["exit_tok"]
    note = rec["note"]
    if note:
        # Keep the source note as the mechanical description.
        return note + "; смысл ИТМ неизвестен"
    if tok.startswith("X"):
        return "уход из зоны в слове " + tok[1:] + "; смысл ИТМ неизвестен"
    if tok.startswith("R"):
        return "RET в слове " + tok[1:] + "; смысл ИТМ неизвестен"
    return "выход не найден (fallthrough); смысл ИТМ неизвестен"


LEGEND = [
    "* === ПРОЦЕДУРЫ ЗОНЫ (docs/PROCEDURES-ASM.md) ===",
    "* C<n> - входов по CALL (пв); B<n> - по ветвлению;",
    "* Rnnn - RET (пб Мn) в слове nnn; Xnnn - уход из зоны;",
    "* прочерк в ВЫХ - выход не найден (fallthrough);",
    "* все СМЫСЛ - ГИП (исходника ИТМ на диске нет).",
]

BAD = ("\u2014", "\u2013", "\u00d7", "^")


def generate(zone, doc_lines):
    recs = parse_zone(zone, doc_lines)
    lines = list(LEGEND)
    lines.append("* Всего процедур: %d (кандидаты §%s.1; детали §%s.2)." %
                 (len(recs), SECTION[zone], SECTION[zone]))
    lines.append("*")
    for r in recs:
        st = ascii_clean(r["start"])
        lines.append("* ПРОЦ %s-%s size=%s %s" %
                     (st, ascii_clean(r["end"]), r["size"], r["kind"]))
        lines.append("*   ВХ %s; ВЫХ %s" % (st, exit_text(r)))
        reg = REG[zone].get(r["start"], "-")
        lines.append("*   РЕГ %s" % reg)
        meaning = FUNC[zone].get(r["start"])
        if meaning is None:
            meaning = generic_meaning(r)
        meaning = "ГИП: " + ascii_clean(meaning)
        lines.extend(wrap(meaning, "*   СМЫСЛ: ", "*     "))
        lines.append("*")
    # Drop a trailing bare separator to avoid a dangling '*' before КОД.
    while lines and lines[-1] == "*":
        lines.pop()
    return recs, lines


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    zones = args if args else ("0055", "0056", "0057", "0060")
    doc_lines = open(DOC, encoding="utf-8").read().splitlines()
    for zone in zones:
        recs, block = generate(zone, doc_lines)
        bad = [l for l in block if len(l) > 55 or any(c in l for c in BAD)]
        if bad:
            print("BAD LINES in zone %s:" % zone, file=sys.stderr)
            for l in bad:
                print("  len=%d %r" % (len(l), l), file=sys.stderr)
            return 1
        print("== zone %s: procs=%d ==" % (zone, len(recs)))
        print("\n".join(block))
    return 0


if __name__ == "__main__":
    sys.exit(main())
