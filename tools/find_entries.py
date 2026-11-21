#!/usr/bin/env python3
"""Поиск точек входа в пользовательских программах БЭСМ-6 / МАКРО-БЕМШ.

Источники (только чтение):
  * bemsh/*.be                  -- 69 реконструкций зон (СТАРТ, ВХОД*, CALL);
  * mbe60_bemsh[_list].txt      -- листинг/исходник тестовой программы ДКС.

Классы точек входа:
  PROG_ENTRY   -- точка входа пользовательской программы (ВХОДН=...);
  ZONE_START   -- СТАРТ зоны (локальный старт, не обязательно_entry модуля);
  EXT_SYMBOL   -- внешний символ из *EXECUTE / *МЕТ*.

Формат sym-таблицы: "%o %d %63s" (адрес восьм., тип, имя).
Тип 2 = W_CODE, 1 = W_DATA, 0 = эквивалентность (см. AGENTS.md §3).
"""

import argparse
import glob
import os
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BE_DIR = REPO / "bemsh"
LISTING = Path("/home/azizz/Yandex.Disk/re-dispak/testdks/mbe60_bemsh_list.txt")
SOURCE = Path("/home/azizz/Yandex.Disk/re-dispak/testdks/mbe60_bemsh.txt")

# Директивы входа МАКРО-БЕМШ (macros.be:9,10; COMMENTING-STANDARD.md:228).
ENTRY_WORDS = ("ВХОД", "ВХОДН", "ВХОДС", "ВХОДБ")
CALL_MNEMONICS = ("ПВ", "ПВО", "ВЖМ")

RE_START = re.compile(r"^\s*(\S+)\s+СТАРТ\s+'?([0-7]+)'?")
RE_ENTRY = re.compile(
    r"^\s*(?:[^\s*]+\s+)?(" + "|".join(ENTRY_WORDS) + r")\b(.*)$"
)
RE_EQU = re.compile(r"^([A-Za-z0-9_]+)\s+ЭКВ\s+'?([0-7]+)'?")
RE_CALL = re.compile(r"^\s*(" + "|".join(CALL_MNEMONICS) + r")\s+(\S+)")
RE_ZONE_IN_NAME = re.compile(r"Z(\d{4})")

# Карта «дисковая зона -> адрес ОП» из analysis/MEMORY-MAP.md §5.
# Только 12 зон привязаны; остальные помечаются как локальные (LOCAL).
LOAD_ADDR = {
    "0147": 0o00000, "0150": 0o70000, "0153": 0o74000,
    "0154": 0o02000, "0155": 0o04000, "0156": 0o06000,
    "0157": 0o76000, "0161": 0o24000, "0162": 0o26000,
    "0174": 0o72000, "0175": 0o72000, "0177": 0o72000,
}

# Подтверждённые каталогами PROCEDURES-{ASM,B,B2}.md цели CALL.
# Используются только для обоснования уверенности, не для подмены счёта.
CATALOG_CONFIRMED = {
    ("0055", 0o221), ("0056", 0o221), ("0057", 0o221), ("0060", 0o220),
    ("0147", 0o477), ("0547", 0o472), ("0551", 0o354),
}


def octal(value):
    """Восьмеричная строка без ведущего 0o."""
    return format(value, "o")


def read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def scan_be_file(path):
    """Разобрать один .be-файл.

    Возвращает словарь: zone, file, start (список), entries (список),
    calls (Counter адрес->число в зоне), defacto (адрес, число) или None,
    defacto_label, confidence.
    """
    path = Path(path)
    text = read_text(path)
    name = re.search(r"Z(\d{4})", path.name)
    zone = name.group(1) if name else "????"

    equ = {}
    starts = []
    entries = []
    call_targets = []

    # Role labels were converted from ЭКВ to real labels; their address is
    # preserved in the `* NAME (было NNN)` annotation comment.
    RE_ROLE_WAS = re.compile(r"\*\s*([A-Za-z0-9_]+)\s*\(было\s+([0-7]+)\)")
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith("*"):
            mw = RE_ROLE_WAS.match(stripped)
            if mw and mw.group(1) not in equ:
                equ[mw.group(1)] = int(mw.group(2), 8)
            continue  # комментарий, в т.ч. упоминания ВХОД в тексте
        m = RE_START.match(raw)
        if m:
            starts.append({
                "label": m.group(1),
                "value": int(m.group(2), 8),
                "line": lineno,
            })
            continue
        m = RE_ENTRY.match(raw)
        if m:
            entries.append({
                "word": m.group(1),
                "operand": m.group(2).strip(),
                "line": lineno,
            })
            continue
        m = RE_EQU.match(raw)
        if m:
            equ[m.group(1)] = int(m.group(2), 8)
            continue
        m = RE_CALL.match(raw)
        if m:
            target = re.split(r"[\.\(-]", m.group(2))[0]
            if target in equ:
                addr = equ[target]
            elif target.isdigit():
                # Числовой операнд напечатан в десятичной форме:
                # 16 -> 020к8, 17 -> 021к8, 28 -> 034к8, 53 -> 065к8
                # (AGENTS.md §2, PROCEDURES-ASM.md §10 п.8).
                addr = int(target, 10)
            else:
                continue
            if 0 <= addr <= 0o1777:  # только цели внутри зоны
                call_targets.append((addr, target))

    counts = Counter(a for a, _ in call_targets)
    defacto = None
    defacto_label = ""
    if counts:
        addr, cnt = counts.most_common(1)[0]
        defacto = (addr, cnt)
        labels = [lab for a, lab in call_targets if a == addr]
        defacto_label = labels[0] if labels else ""

    if defacto is None:
        confidence = "low"
    elif defacto[1] >= 5 or (zone, defacto[0]) in CATALOG_CONFIRMED:
        confidence = "high"
    elif defacto[1] >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    try:
        rel = str(path.relative_to(REPO))
    except ValueError:
        rel = path.name  # временный файл из тестов

    return {
        "zone": zone,
        "file": rel,
        "starts": starts,
        "entries": entries,
        "calls": counts,
        "defacto": defacto,
        "defacto_label": defacto_label,
        "confidence": confidence,
        "load_addr": LOAD_ADDR.get(zone),
    }


def scan_all_be(be_dir=None):
    be_dir = Path(be_dir) if be_dir else BE_DIR
    files = sorted(glob.glob(str(be_dir / "*.be")))
    return [scan_be_file(f) for f in files]


# ---------------------------------------------------------------------------
# Листинг пользовательской программы МВЕ60
# ---------------------------------------------------------------------------

RE_NAM = re.compile(r"\bНАМ=([0-7]+)")
RE_ENTRY_EQ = re.compile(r"\bВХОДН=([0-7]+)")
RE_EXT_EQ = re.compile(r"\bВНЕШН=([0-7]+)")
RE_ENTRY_MARK = re.compile(r"\*ENTRY\b", re.I)
# Маркер внешней ссылки в *МЕТ*: 5 восьмеричных цифр + метки С/А/В.
RE_MET_MARK = re.compile(r"^([0-7]{5})([А-ЯA-Z]{1,2})$")


def scan_listing(path=None):
    """Разобрать листинг МВЕ60: entry, внешние символы, внешние ссылки."""
    path = Path(path) if path else LISTING
    text = read_text(path)
    lines = text.splitlines()

    nam = entry_logical = ext_count = None
    summary_line = None
    star_entry = []
    in_star_entry = False
    for lineno, line in enumerate(lines, 1):
        # Сводка модуля: НАМ=…, ВХОДН=… и ВНЕШН=… могут стоять
        # на одной строке; разбираем каждое поле независимо.
        m = RE_ENTRY_EQ.search(line)
        if m and entry_logical is None:
            entry_logical = m.group(1)
            summary_line = lineno
        m = RE_NAM.search(line)
        if m and nam is None:
            nam = m.group(1)
        m = RE_EXT_EQ.search(line)
        if m and ext_count is None:
            ext_count = int(m.group(1), 8)
        # *ENTRY -- альтернативная форма объявления входа в листинге.
        # Продолжаем разбирать последующие строки "ИМЯ АДРЕС" до пустой
        # строки или следующего раздела, начинающегося с '*'.
        if RE_ENTRY_MARK.search(line):
            in_star_entry = True
            rest = RE_ENTRY_MARK.sub("", line)
            tail = [t for t in rest.split()
                    if re.fullmatch(r"\*?[A-Za-z0-9_*\/]+", t)]
            if tail:
                star_entry.append({"raw": tail[0], "line": lineno})
            continue
        if in_star_entry:
            if not line.strip() or line.lstrip().startswith("*"):
                in_star_entry = False
                continue
            parts = line.split()
            if (len(parts) >= 2
                    and re.fullmatch(r"\*?[A-Za-z0-9_*\/]+", parts[0])
                    and re.fullmatch(r"[0-7]{3,6}", parts[1])):
                star_entry.append({"raw": parts[0], "line": lineno})

    # Имена в листинге напечатаны омоглифами (кириллица вместо латиницы).
    CANON = {
        "МВЕ60": "MBE60", "РRINТ8": "PRINT8", "РRINТ80": "PRINT80",
        "*СМ400*": "*CM400*", "*РАGЕ*": "*PAGE*", "МОN*IТОR": "MON*ITOR",
        "СМ400": "CM400", "РАGЕ": "PAGE",
    }
    execute = {}
    in_execute = False
    for lineno, line in enumerate(lines, 1):
        if "*ЕХЕСUТЕ" in line or "*EXECUTE" in line:
            in_execute = True
            continue
        if not in_execute:
            continue
        if "СТР>>" in line or "КОНЕЦ ЗАДАЧИ" in line:
            break
        # Строка *EXECUTE содержит до трёх колонок:
        # "МВЕ60 01000  РLВЕG Е 04007  ОН*1 Е 04054".
        # Внутри колонки поля разделены произвольными пробелами, поэтому
        # разбираем поток токенов: ИМЯ [КВАЛИФИКАТОР] ВОСЬМЕРИЧНЫЙ_АДРЕС.
        tokens = line.split()
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if not re.fullmatch(r"\*?[A-Za-zА-Яа-я0-9_*\/]+", tok):
                i += 1
                continue
            j = i + 1
            qual = ""
            if (j + 1 < len(tokens)
                    and re.fullmatch(r"[A-ZА-Я]", tokens[j])
                    and re.fullmatch(r"[0-7]{4,6}", tokens[j + 1])):
                qual = tokens[j]
                j += 1
            if j < len(tokens) and re.fullmatch(r"[0-7]{4,6}", tokens[j]):
                execute[CANON.get(tok, tok)] = {
                    "addr": int(tokens[j], 8),
                    "qual": qual,
                    "line": lineno,
                }
                i = j + 1
            else:
                i += 1

    # Внешние ссылки (ВНЕШН): в *МЕТ* помечены суффиксом 'С'.
    met_external = []
    in_met = False
    for lineno, line in enumerate(lines, 1):
        if "*МЕТ*" in line:
            in_met = True
            continue
        if not in_met:
            continue
        if "***********" in line or "ЧИСЛО ОШИБОК" in line:
            break
        # Ищем пары вида "ИМЯ 00001СА". Токен "00001СА" -- это
        # внешняя ссылка; предыдущий токен -- имя символа.
        # Метка 'С' = внешний символ (ВНЕШН); 'А'/'В' -- др. признаки.
        tokens = line.split()
        for idx, tok in enumerate(tokens):
            m = RE_MET_MARK.match(tok)
            if not m or "С" not in m.group(2) or idx == 0:
                continue
            name = tokens[idx - 1]
            if not re.search(r"[A-Za-zА-Яа-я*]", name):
                continue  # числовой мусор вида "000000 42001СА"
            met_external.append({
                "raw": CANON.get(name, name),
                "logical": m.group(1),
                "marks": m.group(2),
                "line": lineno,
            })

    # Точка входа в памяти: символ с тем же логическим номером, что ВХОДН.
    prog_symbol = "MBE60"
    prog_entry_mem = execute.get(prog_symbol, {}).get("addr")

    return {
        "file": str(path),
        "source": str(SOURCE),
        "nam": nam,
        "entry_logical": entry_logical,
        "ext_count": ext_count,
        "summary_line": summary_line,
        "star_entry": star_entry,
        "execute": execute,
        "met_external": met_external,
        "prog_symbol": prog_symbol,
        "prog_entry_mem": prog_entry_mem,
        "start_decl": _find_start_in_source(),
    }


def _find_start_in_source():
    """Найти объявление СТАРТ в исходнике мbe60."""
    try:
        text = read_text(SOURCE)
    except OSError:
        return None
    for lineno, line in enumerate(text.splitlines(), 1):
        m = re.search(r"\b(МВE60|MBE60)\s+(СТАРТ|START)\s+([0-7]+)", line, re.I)
        if m:
            return {"value": int(m.group(3), 8), "line": lineno,
                    "raw": line.strip()}
    return None


# ---------------------------------------------------------------------------
# Формирование sym/ENTRY.tab и отчёта
# ---------------------------------------------------------------------------

def build_entry_rows(be_results, listing):
    """Построить строки sym/ENTRY.tab: (addr, type, name, role, evidence)."""
    rows = []

    # PROGRAM ENTRY
    if listing["prog_entry_mem"] is not None:
        rows.append({
            "addr": listing["prog_entry_mem"], "type": 2,
            "name": "%s_PROG_ENTRY" % listing["prog_symbol"],
            "role": "PROG_ENTRY",
            "evidence": "%s:%s ВХОДН=%s" % (
                Path(listing["file"]).name, listing["summary_line"],
                listing["entry_logical"]),
        })

    # EXTERNAL SYMBOLS
    for symbol in ("PRINT8", "*CM400*", "*PAGE*", "MON*ITOR"):
        info = listing["execute"].get(symbol)
        if info:
            rows.append({
                "addr": info["addr"], "type": 2,
                "name": "%s_EXT_SYMBOL" % symbol.replace("*", "X"),
                "role": "EXT_SYMBOL",
                "evidence": "%s:%d *EXECUTE %s" % (
                    Path(listing["file"]).name, info["line"], symbol),
            })

    # ZONE STARTS
    for r in be_results:
        if not r["starts"]:
            continue
        st = r["starts"][0]
        addr = r["load_addr"] if r["load_addr"] is not None else 0
        suffix = "" if r["load_addr"] is not None else "_LOCAL"
        rows.append({
            "addr": addr, "type": 2,
            "name": "Z%s_ZONE_START%s" % (r["zone"], suffix),
            "role": "ZONE_START",
            "evidence": "%s:%d СТАРТ %d" % (r["file"], st["line"], st["value"]),
        })

    rows.sort(key=lambda x: (x["addr"], x["role"], x["name"]))
    return rows


def format_symtab(rows, width=63):
    """Формат "%o %d %63s" (AGENTS.md §3): имя выравнивается вправо."""
    out = []
    for r in rows:
        name = r["name"][:width]
        out.append("%s %d %63s" % (octal(r["addr"]), r["type"], name))
    return "\n".join(out) + "\n"


def render_report(be_results, listing, rows):
    """Текстовый отчёт для stdout / --out."""
    L = []
    add = L.append
    add("# Точки входа (ENTRY POINTS) — отчёт tools/find_entries.py")
    add("")
    add("## 1. Пользовательская программа МВЕ60 (тест ДКС)")
    add("")
    add("Источник: %s" % listing["file"])
    add("Исходник: %s" % listing["source"])
    add("Сводка листинга (строка %s): ВХОДН=%s, ВНЕШН=%d" % (
        listing["summary_line"], listing["entry_logical"],
        listing["ext_count"]))
    add("")
    add("| Поле | Значение | Свидетельство |")
    add("|---|---|---|")
    add("| Имя модуля (НАМ) | %s | %s:%s |" % (
        listing["nam"], Path(listing["file"]).name, listing["summary_line"]))
    add("| Точка входа (ВХОДН, логич.) | %s | %s:%s |" % (
        listing["entry_logical"], Path(listing["file"]).name,
        listing["summary_line"]))
    add("| Точка входа (память) | %s₈ | *EXECUTE MBE60 01000 |" % (
        octal(listing["prog_entry_mem"]) if listing["prog_entry_mem"] is not None
        else "?"))
    add("| Число внешних ссылок (ВНЕШН) | %d | %s:%s |" % (
        listing["ext_count"], Path(listing["file"]).name,
        listing["summary_line"]))
    if listing["start_decl"]:
        add("| Объявление СТАРТ | %d | %s:%d |" % (
            listing["start_decl"]["value"], Path(listing["source"]).name,
            listing["start_decl"]["line"]))
    add("")
    add("Внешние символы *EXECUTE:")
    add("")
    add("| Символ | Адрес памяти | Квалификатор | Строка |")
    add("|---|---|---|---|")
    for symbol in ("MBE60", "PRINT8", "PRINT80", "*CM400*", "*PAGE*",
                   "MON*ITOR"):
        info = listing["execute"].get(symbol)
        if info:
            add("| %s | %s₈ | %s | %d |" % (
                symbol, octal(info["addr"]), info["qual"] or "-", info["line"]))
    add("")
    add("Внешние ссылки (*МЕТ*, суффикс С), всего %d:" % listing["ext_count"])
    add("")
    add("| Символ (raw) | Логич. | Метки | Строка |")
    add("|---|---|---|---|")
    for e in listing["met_external"]:
        add("| %s | %s | %s | %d |" % (
            e["raw"], e["logical"], e["marks"], e["line"]))
    add("")

    add("## 2. Реконструированные модули (%d .be)" % len(be_results))
    add("")
    add("| Зона | Объявленный вход | Свидетельство | De facto ( топ CALL ) | Увер. |")
    add("|---|---|---|---|---|")
    for r in be_results:
        if r["entries"]:
            decl = ", ".join(e["word"] for e in r["entries"])
        else:
            decl = "— (только СТАРТ)"
        ev = "%s:%d" % (r["file"], r["starts"][0]["line"]) if r["starts"] else "-"
        if r["defacto"]:
            addr, cnt = r["defacto"]
            defacto = "%s₈ ×%d (%s)" % (octal(addr), cnt, r["defacto_label"])
        else:
            defacto = "н/д"
        add("| %s | %s | %s | %s | %s |" % (
            r["zone"], decl, ev, defacto, r["confidence"]))
    add("")

    add("## 3. sym/ENTRY.tab (формат %%o %%d %%63s)")
    add("")
    add("```")
    for line in format_symtab(rows).splitlines():
        add(line)
    add("```")
    add("")
    add("Итого: PROG_ENTRY=%d, EXT_SYMBOL=%d, ZONE_START=%d." % (
        sum(1 for r in rows if r["role"] == "PROG_ENTRY"),
        sum(1 for r in rows if r["role"] == "EXT_SYMBOL"),
        sum(1 for r in rows if r["role"] == "ZONE_START")))
    return "\n".join(L) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="записать отчёт в файл (по умолчанию stdout)")
    parser.add_argument("--sym-out", help="записать только sym/ENTRY.tab в файл")
    parser.add_argument("--be-dir", default=str(BE_DIR), help="каталог .be")
    parser.add_argument("--listing", default=str(LISTING), help="листинг МВЕ60")
    args = parser.parse_args(argv)

    be_results = scan_all_be(args.be_dir)
    listing = scan_listing(args.listing)
    rows = build_entry_rows(be_results, listing)
    report = render_report(be_results, listing, rows)

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    if args.sym_out:
        Path(args.sym_out).write_text(format_symtab(rows), encoding="utf-8")
    if not args.out:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
