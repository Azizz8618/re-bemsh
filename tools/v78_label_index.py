#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v78_label_index.py - глобальный индекс меток БЕМШ 06/78.

Только чтение. Собирает метки первого поля bemsh/*Z*.be и
вычисляет абсолют: база зоны плюс номер слова из имени метки
(восьмеричная арифметика).

Базы: analysis/ZONE-BASE-MAP.md, картированные базы B2/ASM,
СТАРТ из .be для зон без физической базы, особые случаи.
Вывод детерминирован. Входные файлы не изменяются.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_OFFSET = 0o1777
MIN_LABELS = 2000

LABEL_RE = re.compile(r"\A([ADG])([0-7]{5})(?=\s|\Z)")
MALFORMED_RE = re.compile(r"\A[ADG][0-9]{5}(?=\s|\Z)")
ZONE4_RE = re.compile(r"\A[0-7]{4}\Z")
ZONE_FILE_RE = re.compile(r"Z([0-7]{4})\.be\Z")
START_RE = re.compile(r"\bСТАРТ\s+'?([0-7]{1,6})'?")
ASM_LABEL_RE = re.compile(r"\b[ADG][0-7]{5}\b")

MAP_REL = Path("analysis") / "ZONE-BASE-MAP.md"
BE_REL = "bemsh"
ASM_REL = "dis-forced"
FILE_GLOBS = (("MBE-Z*.be", "B"), ("MBE2-Z*.be", "B2"),
              ("ASM-Z*.be", "ASM"))
MAPPED_BASE = "10000"
SPECIAL_BASES = {"0137": "00000"}
EXTERNAL_BASE = "030000"
KINDS = ("code", "data")


def oct_text(value, width=5):
    """Восьмеричная строка фиксированной ширины."""
    return format(value, "0%do" % width)


def add_octal(base, offset):
    """Сложить восьмеричные строки.

    Пустая база даёт пустой адрес.
    """
    if not base or not offset:
        return ""
    return oct_text(int(base, 8) + int(offset, 8), 5)


def normalize_base(token):
    """Привести базу к 5 цифрам.

    '-' и внешний регион не являются базами.
    """
    text = token.strip().strip("?")
    if not text or text == "-":
        return None
    if text == EXTERNAL_BASE:
        return None
    if not all(ch in "01234567" for ch in text):
        return None
    return oct_text(int(text, 8), 5)


def parse_base_map(text):
    """Разобрать Приложение A и таблицу §3 карты зон."""
    found = {}
    for line in text.splitlines():
        cells = [c.strip() for c in
                 line.strip().strip("|").split("|")]
        if len(cells) >= 2 and ZONE4_RE.match(cells[0]):
            status = cells[-1] if len(cells) > 4 else ""
            base = normalize_base(cells[1])
            found.setdefault(cells[0], (base, status))
        parts = [c.strip() for c in line.strip().split(",")]
        if len(parts) >= 3 and ZONE4_RE.match(parts[0]):
            found[parts[0]] = (normalize_base(parts[1]),
                               parts[2].strip("?"))
    return found


def parse_start(text):
    """Найти первый СТАРТ в .be (условная база сборки)."""
    match = START_RE.search(text)
    if not match:
        return None
    return normalize_base(match.group(1))


def resolve_base(zone, family, base_map, start):
    """Вернуть (база, источник) для зоны."""
    if zone in SPECIAL_BASES:
        return SPECIAL_BASES[zone], "SPECIAL"
    if family in ("B2", "ASM"):
        if start == "00001":
            return start, "MAPPED-HAM"
        return MAPPED_BASE, "MAPPED"
    base, status = base_map.get(zone, (None, ""))
    if base:
        return base, status or "MAP"
    if start:
        return start, "START"
    return "", "NONE"


def input_files(root):
    """Список (путь, семейство, зона) по порядку путей."""
    found = []
    for pattern, family in FILE_GLOBS:
        for path in sorted((root / BE_REL).glob(pattern)):
            match = ZONE_FILE_RE.search(path.name)
            if match:
                found.append((path, family, match.group(1)))
    return sorted(found, key=lambda item: str(item[0]))


def read_text(path):
    """Читать файл как текст, не изменяя его."""
    return path.read_text(encoding="utf-8",
                          errors="replace")


def records_for(path, root, zone, base):
    """Извлечь записи из .be.

    Возвращает (записи, подозрения).
    """
    records = []
    bad = []
    rel = path.relative_to(root).as_posix()
    text = read_text(path)
    for number, line in enumerate(text.splitlines(), 1):
        field = line.lstrip()
        match = LABEL_RE.match(field)
        if not match:
            broken = MALFORMED_RE.match(field)
            if broken:
                bad.append("%s:%d (%s)" % (
                    rel, number, broken.group(0)))
            continue
        offset = match.group(2)
        prefix = match.group(1)
        kind = "code" if prefix in "AG" else "data"
        records.append({
            "label": prefix + offset,
            "zone": zone,
            "base": base,
            "offset": offset,
            "absolute": add_octal(base, offset),
            "kind": kind,
            "file": rel,
            "line": number,
        })
    return records, bad


def build_index(root, asm_check=False):
    """Построить индекс.

    Возвращает (записи, предупреждения).
    """
    root = Path(root)
    map_path = root / MAP_REL
    base_map = parse_base_map(read_text(map_path))
    files = input_files(root)
    if not files:
        raise ValueError("нет входных файлов .be")
    starts = {}
    records = []
    warnings = []
    for path, family, zone in files:
        if path not in starts:
            starts[path] = parse_start(read_text(path))
        base, _source = resolve_base(
            zone, family, base_map, starts[path])
        found, bad = records_for(path, root, zone, base)
        records.extend(found)
        for item in bad:
            warnings.append("неверная метка: " + item)
        if not base:
            warnings.append("нет базы: зона " + zone)
    if asm_check:
        warnings.extend(asm_warnings(root, records))
    records.sort(key=sort_key)
    return records, sorted(set(warnings))


def sort_key(record):
    """Ключ стабильной сортировки записей."""
    return (record["zone"], int(record["offset"], 8),
            record["label"], record["file"], record["line"])


def asm_warnings(root, records):
    """Сверить метки с необязательными dis-forced/Z*.asm."""
    warnings = []
    known = {}
    for zone in sorted({r["zone"] for r in records}):
        path = root / ASM_REL / ("Z%s.asm" % zone)
        if path.is_file():
            known[zone] = set(
                ASM_LABEL_RE.findall(read_text(path)))
    for record in records:
        labels = known.get(record["zone"])
        if labels is None or record["label"] in labels:
            continue
        warnings.append("нет в dis-forced: %s зона %s" %
                        (record["label"], record["zone"]))
    return warnings


def validate(records):
    """Проверить уникальность, границы, базы и счёт."""
    errors = set()
    seen = {}
    for record in records:
        key = (record["zone"], record["offset"])
        if key in seen and seen[key] != record["label"]:
            errors.add("конфликт %s:%s: %s / %s" % (
                key[0], key[1], seen[key], record["label"]))
        else:
            seen[key] = record["label"]
        if int(record["offset"], 8) > MAX_OFFSET:
            errors.add("смещение >01777: %s %s" %
                       (record["zone"], record["label"]))
        if not record["base"]:
            errors.add("нет базы: зона " + record["zone"])
    if len(records) < MIN_LABELS:
        errors.add("меток %d, нужно >=%d" %
                   (len(records), MIN_LABELS))
    return sorted(errors)


def summarize(records):
    """Счётчики по зонам и видам."""
    zones = Counter(r["zone"] for r in records)
    kinds = Counter(r["kind"] for r in records)
    return {
        "total": len(records),
        "zones": len(zones),
        "by_kind": {kind: kinds.get(kind, 0)
                    for kind in KINDS},
        "by_zone": {zone: zones[zone]
                    for zone in sorted(zones)},
    }


def render_text(records, summary=None):
    """Текстовый вывод: шапка, записи, итоги."""
    lines = ["МЕТКА    ЗОНА БАЗА  СМЕЩ  АДРЕС ВИД  "
             "ФАЙЛ:СТРОКА"]
    for record in records:
        lines.append("%-8s %4s %5s %5s %5s %-4s %s:%d" % (
            record["label"], record["zone"], record["base"],
            record["offset"], record["absolute"],
            record["kind"], record["file"], record["line"]))
    if summary is not None:
        lines.append("")
        lines.append("ИТОГО: %d меток, %d зон" %
                     (summary["total"], summary["zones"]))
        lines.append("ПО ВИДУ: code=%d data=%d" % (
            summary["by_kind"]["code"],
            summary["by_kind"]["data"]))
        lines.append("ПО ЗОНАМ:")
        for zone in sorted(summary["by_zone"]):
            lines.append("  %s: %d" %
                         (zone, summary["by_zone"][zone]))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Глобальный индекс меток БЕМШ 06/78 "
                    "(только чтение)")
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="корень репозитория")
    parser.add_argument("--format",
                        choices=("json", "text"),
                        default="text",
                        help="формат вывода")
    parser.add_argument("--check", action="store_true",
                        help="проверить целостность")
    parser.add_argument("--kind", choices=KINDS,
                        help="фильтр вида метки")
    parser.add_argument("--zone", metavar="Z",
                        help="зона: 4 восьмеричные цифры")
    parser.add_argument("--summary", action="store_true",
                        help="печать счётчиков")
    parser.add_argument("--asm-check", action="store_true",
                        help="сверка с dis-forced")
    args = parser.parse_args(argv)
    if args.zone and not ZONE4_RE.match(args.zone):
        parser.error("зона: 4 восьмеричные цифры")
    try:
        records, warnings = build_index(
            args.root, args.asm_check)
    except (OSError, ValueError) as exc:
        print("ОШИБКА: %s" % exc, file=sys.stderr)
        return 2
    selected = records
    if args.kind:
        selected = [r for r in selected
                    if r["kind"] == args.kind]
    if args.zone:
        selected = [r for r in selected
                    if r["zone"] == args.zone]
    if args.check:
        errors = validate(records)
        for warning in warnings:
            print("ВНИМАНИЕ: " + warning, file=sys.stderr)
        for error in errors:
            print("ОШИБКА: " + error, file=sys.stderr)
        counts = summarize(records)
        print("ПРОВЕРКА: %s; меток %d; зон %d; ошибок %d"
              % ("PASS" if not errors else "FAIL",
                 counts["total"], counts["zones"],
                 len(errors)))
        return 1 if errors else 0
    summary = summarize(selected) if args.summary else None
    if args.format == "json":
        payload = ({"records": selected, "summary": summary}
                   if summary is not None else selected)
        print(json.dumps(payload, ensure_ascii=False,
                         indent=2))
    else:
        print(render_text(selected, summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
