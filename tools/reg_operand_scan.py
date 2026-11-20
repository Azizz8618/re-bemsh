#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Аудит аргументов команды РЕГ (opcode 002) в реконструкциях БЕМШ.

Вход:  bemsh/*.be и dis-forced/*.asm.
Выход: сводка, группировка по значениям, побайтовые доказательства для
       подозрительных вхождений и таблица предложенных правок.

Эталон диапазона: docs/REG-INSTRUCTION.md (simh besm6_cpu.c cmd_002).
Команда РЕГ пишет спец-регистр, селектор = Aex & 0377. Осмысленные
коды перечислены в VALID_SELECTORS; всё остальное (дыры 010-017,
034-035, 040-077, 0210-0236, 0240-0377, watchdog 0140-0177 и
любое значение >0377) — данные, случайно прочитанные как opcode 002.

Ни один .be, .asm или gold-файл не изменяется.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Селекторы cmd_002, которые реально что-то делают ( REG-INSTRUCTION.md §2 ).
VALID_SELECTORS = frozenset(
    list(range(0o000, 0o010))
    + list(range(0o020, 0o030))
    + list(range(0o030, 0o034))
    + [0o036, 0o037]
    + list(range(0o100, 0o140))
    + list(range(0o200, 0o210))
    + [0o237]
)
WATCHDOG_SELECTORS = frozenset(range(0o140, 0o200))  # STOP_UNIMPLEMENTED
SELECTOR_MASK = 0o377

ZONE_PREFIX = (
    (("0055", "0056", "0057", "0060"), "ASM"),
    (("0137", "0140", "0141", "0142", "0143", "0144", "0145", "0146",
      "0147", "0150", "0151", "0152", "0153", "0154", "0155", "0156",
      "0157", "0160", "0161", "0162", "0163", "0164", "0165", "0166",
      "0167", "0170", "0171", "0172", "0173", "0174", "0175", "0176",
      "0177"), "MBE"),
    (("0540", "0541", "0542", "0543", "0544", "0545", "0546", "0547",
      "0550", "0551", "0552", "0553", "0554", "0555", "0556", "0557",
      "0560", "0561", "0562", "0563", "0564", "0565", "0566", "0567",
      "0570", "0571", "0572", "0573", "0574", "0575", "0576",
      "0577"), "MBE2"),
)
_PREFIX_BY_ZONE = {z: p for zones, p in ZONE_PREFIX for z in zones}

# Полная таблица opcode из disbesm6.c (используется для альтернатив).
# (имя, код, маска, тип)
OPS = [
    ("зп", 0x000000, 0x0BF000, "str1"), ("зпм", 0x001000, 0x0BF000, "str1"),
    ("рег", 0x002000, 0x0BF000, "imm"), ("счм", 0x003000, 0x0BF000, "str1"),
    ("сл", 0x004000, 0x0BF000, "str1"), ("вч", 0x005000, 0x0BF000, "str1"),
    ("вчоб", 0x006000, 0x0BF000, "str1"), ("вчаб", 0x007000, 0x0BF000, "str1"),
    ("сч", 0x008000, 0x0BF000, "str1"), ("и", 0x009000, 0x0BF000, "str1"),
    ("нтж", 0x00A000, 0x0BF000, "str1"), ("слц", 0x00B000, 0x0BF000, "str1"),
    ("знак", 0x00C000, 0x0BF000, "str1"), ("или", 0x00D000, 0x0BF000, "str1"),
    ("дел", 0x00E000, 0x0BF000, "str1"), ("умн", 0x00F000, 0x0BF000, "str1"),
    ("сбр", 0x010000, 0x0BF000, "str1"), ("рзб", 0x011000, 0x0BF000, "str1"),
    ("чед", 0x012000, 0x0BF000, "str1"), ("нед", 0x013000, 0x0BF000, "str1"),
    ("слп", 0x014000, 0x0BF000, "str1"), ("вчп", 0x015000, 0x0BF000, "str1"),
    ("сд", 0x016000, 0x0BF000, "str1"), ("рж", 0x017000, 0x0BF000, "str1"),
    ("счрж", 0x018000, 0x0BF000, "imm"), ("счмр", 0x019000, 0x0BF000, "imm64"),
    ("увв", 0x01B000, 0x0BF000, "imm"), ("слпа", 0x01C000, 0x0BF000, "imm64"),
    ("вчпа", 0x01D000, 0x0BF000, "imm64"), ("сда", 0x01E000, 0x0BF000, "imm64"),
    ("ржа", 0x01F000, 0x0BF000, "imm"), ("уи", 0x020000, 0x0BF000, "reg1"),
    ("уим", 0x021000, 0x0BF000, "reg1"), ("счи", 0x022000, 0x0BF000, "reg1"),
    ("счим", 0x023000, 0x0BF000, "reg1"), ("уии", 0x024000, 0x0BF000, "reg1"),
    ("сли", 0x025000, 0x0BF000, "reg1"),
    ("э50", 0x028000, 0x0BF000, "immex"), ("э51", 0x029000, 0x0BF000, "immex"),
    ("э52", 0x02A000, 0x0BF000, "immex"), ("э53", 0x02B000, 0x0BF000, "immex"),
    ("э54", 0x02C000, 0x0BF000, "immex"), ("э55", 0x02D000, 0x0BF000, "immex"),
    ("э56", 0x02E000, 0x0BF000, "immex"), ("э57", 0x02F000, 0x0BF000, "immex"),
    ("э60", 0x030000, 0x0BF000, "addrex"), ("э61", 0x031000, 0x0BF000, "addrex"),
    ("э62", 0x032000, 0x0BF000, "immex"), ("э63", 0x033000, 0x0BF000, "immex"),
    ("э64", 0x034000, 0x0BF000, "addrex"), ("э65", 0x035000, 0x0BF000, "immex"),
    ("э66", 0x036000, 0x0BF000, "immex"), ("э67", 0x037000, 0x0BF000, "addrex"),
    ("э70", 0x038000, 0x0BF000, "addrex"), ("э71", 0x039000, 0x0BF000, "addrex"),
    ("э72", 0x03A000, 0x0BF000, "addrex"), ("э73", 0x03B000, 0x0BF000, "addrex"),
    ("э74", 0x03C000, 0x0BF000, "stop"), ("э75", 0x03D000, 0x0BF000, "addrex"),
    ("э76", 0x03E000, 0x0BF000, "immex"), ("э77", 0x03F000, 0x0BF000, "immex"),
    ("мода", 0x090000, 0x0F8000, "addrmod"), ("мод", 0x098000, 0x0F8000, "addrmod"),
    ("уиа", 0x0A0000, 0x0F8000, "reg2"), ("слиа", 0x0A8000, 0x0F8000, "reg2"),
    ("по", 0x0B0000, 0x0F8000, "branch"), ("пе", 0x0B8000, 0x0F8000, "branch"),
    ("пб", 0x0C0000, 0x0F8000, "jump"), ("пв", 0x0C8000, 0x0F8000, "call"),
    ("выпр", 0x0D0000, 0x0F8000, "iret"), ("стоп", 0x0D8000, 0x0F8000, "imm2"),
    ("пио", 0x0E0000, 0x0F8000, "branch"), ("пино", 0x0E8000, 0x0F8000, "branch"),
    ("пио36", 0x0F0000, 0x0F8000, "branch"), ("цикл", 0x0F8000, 0x0F8000, "branch"),
]

DMS_BIT = 0x200000
STRUCT_BIT = 0x80000
EXP_BIT = 0x040000  # BBIT(19)


def decode_half(half: int) -> dict:
    """Разбор 24-битной команды по disbesm6.c (исправленный arg1)."""
    name, kind = "?", "illegal"
    for nm, code, mask, kd in OPS:
        if half & mask == code:
            name, kind = nm, kd
            break
    reg = (half >> 20) & 0xF
    exp = 1 if half & EXP_BIT else 0
    struct = 1 if half & STRUCT_BIT else 0
    op = (half >> 15) & 0xF if struct else (half >> 12) & 0o77
    # disbesm6.c:441-443: 070000 (не 0700000, как в siprod_asm).
    arg1 = (half & 0o7777) + (0o70000 if exp else 0)
    arg2 = half & 0o77777
    return dict(name=name, kind=kind, reg=reg, exp=exp, struct=struct,
                op=op, arg1=arg1, arg2=arg2, raw=half)


def classify_operand(value: int | None) -> tuple[str, str]:
    """(класс, пояснение) по REG-INSTRUCTION.md §2 и §6."""
    if value is None:
        return "HYPOTHETICAL", "нет числового операнда (голый/символьный РЕГ)"
    sel = value & SELECTOR_MASK
    if value > SELECTOR_MASK:
        return "SUSPICIOUS", (
            "аргумент 0o%o > 0377: вне 10-битного поля селектора; "
            "Aex&0377=0o%o" % (value, sel))
    if sel in VALID_SELECTORS:
        return "VALID", "селектор 0o%o есть в cmd_002" % sel
    if sel in WATCHDOG_SELECTORS:
        return "SUSPICIOUS", (
            "селектор 0o%o = watchdog (STOP_UNIMPLEMENTED)" % sel)
    return "SUSPICIOUS", (
        "селектор 0o%o в 'дыре' cmd_002 (не перечислен)" % sel)


def be_path(zone: str, root: str = ROOT) -> str | None:
    """Найти файл .be для зоны (префикс зависит от набора)."""
    prefix = _PREFIX_BY_ZONE.get(zone)
    candidates = ([prefix] if prefix else []) + ["MBE", "ASM", "MBE2"]
    for p in candidates:
        path = os.path.join(root, "bemsh", "%s-Z%s.be" % (p, zone))
        if os.path.isfile(path):
            return path
    return None


def gold_path(zone: str, root: str = ROOT) -> str | None:
    prefix = _PREFIX_BY_ZONE.get(zone)
    if prefix is None:
        return None
    path = os.path.join(root, "gold", "%s-Z%s-L1.bin" % (prefix, zone))
    return path if os.path.isfile(path) else None


BE_RE = re.compile(
    r"^\s*РЕГ\s+(?:\(М(\d+)\)\s*)?(?:'([0-7]+)'|([^\s,]+))?"
    r"(?:\(М(\d+)\))?", re.I)
ASM_ADDR_RE = re.compile(r"[0-7]{1,5}")


def parse_be(path: str, root: str = ROOT) -> list[dict]:
    zone = re.search(r"Z(\d{4})", os.path.basename(path)).group(1)
    out = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            m = BE_RE.match(raw)
            if not m:
                continue
            reg_pre, octal, symbolic, reg_post = (
                m.group(1), m.group(2), m.group(3), m.group(4))
            reg = reg_post or reg_pre
            if octal is None and symbolic is not None:
                if re.fullmatch(r"[0-7]+", symbolic):
                    octal, symbolic = symbolic, None  # число без кавычек
                # иначе метка/символ, не число
            value = int(octal, 8) if octal is not None else None
            cls, note = classify_operand(value)
            out.append(dict(source="be", zone=zone, line=lineno, addr=None,
                            operand=octal, symbolic=symbolic, value=value,
                            reg=reg, classification=cls, note=note,
                            raw_line=raw.rstrip("\n"), file=os.path.relpath(path, root)))
    return out


def parse_asm(path: str, root: str = ROOT) -> list[dict]:
    zone = re.search(r"Z(\d{4})", os.path.basename(path)).group(1)
    out = []
    cur_addr = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.replace("\ufeff", "").rstrip("\n")
            field = line[:5].strip()
            if (ASM_ADDR_RE.fullmatch(field) and len(line) > 5
                    and line[5] in " :"):
                cur_addr = field
            fields = line.split("\t")
            if len(fields) < 3 or fields[-2].strip().lower() != "рег":
                continue
            operand = fields[-1].strip()
            mo = re.search(r"'([0-7]+)'", operand)
            mr = re.search(r"\(М(\d+)\)", operand)
            octal = mo.group(1) if mo else None
            value = int(octal, 8) if octal is not None else None
            cls, note = classify_operand(value)
            out.append(dict(source="asm", zone=zone, line=lineno, addr=cur_addr,
                            operand=octal, symbolic=None if octal else operand,
                            value=value, reg=mr.group(1) if mr else None,
                            classification=cls, note=note,
                            raw_line=line, file=os.path.relpath(path, root)))
    return out


def scan(root: str = ROOT) -> list[dict]:
    """Просканировать обе директории и связать .be-строки с адресами .asm."""
    occ = []
    for path in sorted(glob.glob(os.path.join(root, "bemsh", "*.be"))):
        occ.extend(parse_be(path, root))
    asm_occ = []
    for path in sorted(glob.glob(os.path.join(root, "dis-forced", "*.asm"))):
        asm_occ.extend(parse_asm(path, root))
    occ.extend(asm_occ)

    # Адрес для .be-вхождений: однозначное совпадение (зона, аргумент)
    # в .asm. При нескольких кандидатах сохраняем все.
    by_key = collections.defaultdict(list)
    for a in asm_occ:
        if a["value"] is not None and a["addr"] is not None:
            by_key[(a["zone"], a["value"])].append(a["addr"])
    for o in occ:
        if o["source"] != "be" or o["value"] is None:
            continue
        cands = []
        for addr in by_key.get((o["zone"], o["value"]), []):
            if o["reg"] is None or addr in cands:
                cands.append(addr)
        o["addr_candidates"] = cands
        o["addr"] = cands[0] if len(cands) == 1 else None
    for a in asm_occ:
        a["addr_candidates"] = [a["addr"]] if a["addr"] else []
    return occ


def group_by_value(occ: list[dict]) -> dict[int | None, list[dict]]:
    groups = collections.defaultdict(list)
    for o in occ:
        groups[o["value"]].append(o)
    return dict(groups)


def summarize(occ: list[dict]) -> dict:
    nums = [o["value"] for o in occ if o["value"] is not None]
    cls = collections.Counter(o["classification"] for o in occ)
    by_src = collections.Counter(o["source"] for o in occ)
    zones = collections.Counter(o["zone"] for o in occ)
    return dict(
        total=len(occ), by_source=dict(by_src), numeric=len(nums),
        nonnumeric=len(occ) - len(nums),
        min_value=min(nums) if nums else None, max_value=max(nums) if nums else None,
        by_class=dict(cls), by_zone=dict(sorted(zones.items())),
        distinct_values=len(set(nums)),
    )


def decode_word(gold: str, addr_oct: str) -> dict:
    """Побайтовое доказательство: 6 байт -> слово -> две половины."""
    index = int(addr_oct, 8)
    with open(gold, "rb") as fh:
        fh.seek(index * 6)
        raw = fh.read(6)
    if len(raw) != 6:
        return dict(addr=addr_oct, bytes_hex="", word=None, error="short read")
    word = int.from_bytes(raw, "big")
    left, right = word >> 24, word & 0xffffff
    printable = sum(1 for b in raw if 0x20 <= b <= 0x7E)
    return dict(
        addr=addr_oct,
        bytes_hex=" ".join("%02x" % b for b in raw),
        word_oct="%o" % word,
        ascii=raw.decode("ascii", "replace"),
        printable=printable,
        text_like=printable >= 5,
        left_oct="%06o" % left, left=decode_half(left),
        right_oct="%06o" % right, right=decode_half(right),
    )


def suspicious_details(occ: list[dict], root: str = ROOT) -> list[dict]:
    """Уникальные (зона, адрес, аргумент) для подозрительных слов."""
    seen = {}
    for o in occ:
        if o["classification"] != "SUSPICIOUS":
            continue
        for addr in (o["addr_candidates"] or [o["addr"]]):
            if not addr:
                continue
            key = (o["zone"], addr, o["value"])
            if key in seen:
                seen[key]["occurrences"].append(o)
                continue
            gp = gold_path(o["zone"], root)
            ev = decode_word(gp, addr) if gp else dict(error="нет gold-файла")
            seen[key] = dict(zone=o["zone"], addr=addr, value=o["value"],
                             evidence=ev, occurrences=[o])
    return sorted(seen.values(), key=lambda d: (d["zone"], int(d["addr"], 8)))


def fix_table(details: list[dict]) -> list[dict]:
    """Предложенные (НЕ применённые) правки для последующего агента."""
    rows = []
    for d in details:
        ev = d["evidence"]
        if not ev.get("word_oct"):
            continue
        o = d["occurrences"][0]
        word = ev["word_oct"]
        proof = "gold/%s-Z%s-L1.bin @0o%s: %s == 0o%s" % (
            _PREFIX_BY_ZONE.get(d["zone"], "?"), d["zone"], d["addr"],
            ev["bytes_hex"], word)
        sel = d["value"] & SELECTOR_MASK
        if ev.get("text_like"):
            new_line = "КОНД '%s'    , ТЕКСТ/ДАННЫЕ, не РЕГ: 6/6 печатных" % (
                ev["ascii"])
            role = "текстовая константа (ложное чтение opcode 002)"
        else:
            new_line = (
                "КОНД В'%s'    , ДАННЫЕ, не РЕГ: Aex=0o%s вне cmd_002"
                % (word, sel))
            role = "данные/константа (ложное чтение opcode 002)"
        proof += "; ASCII=%r" % ev.get("ascii", "")
        rows.append(dict(
            zone=d["zone"], line=o["line"], addr=d["addr"],
            old_line=o["raw_line"].strip(),
            proposed=new_line, role=role,
            byte_identity=proof,
        ))
    return rows


def render_text(occ: list[dict], summary: dict, groups: dict,
                details: list[dict], fixes: list[dict]) -> str:
    L = []
    add = L.append
    add("# АУДИТ АРГУМЕНТОВ РЕГ (автосгенерировано)")
    add("")
    add("Источники: bemsh/*.be, dis-forced/*.asm. Эталон: "
        "docs/REG-INSTRUCTION.md (simh cmd_002).")
    add("Валидные селекторы: 000-007, 020-033, 036-037, 0100-0137, "
        "0200-0207, 0237 (Aex & 0377).")
    add("")
    add("## Сводка")
    add("")
    add("всего вхождений: %d (be=%d, asm=%d)" % (
        summary["total"], summary["by_source"].get("be", 0),
        summary["by_source"].get("asm", 0)))
    add("числовых операндов: %d, без числа: %d, различных значений: %d" % (
        summary["numeric"], summary["nonnumeric"], summary["distinct_values"]))
    add("диапазон значений: 0o%o .. 0o%o" % (
        summary["min_value"] or 0, summary["max_value"] or 0))
    add("классы: VALID=%d SUSPICIOUS=%d HYPOTHETICAL=%d" % (
        summary["by_class"].get("VALID", 0),
        summary["by_class"].get("SUSPICIOUS", 0),
        summary["by_class"].get("HYPOTHETICAL", 0)))
    add("")
    add("## Группировка по значению (все значения)")
    add("")
    add("| значение (8) | dec | всего | VALID | SUSP | HYP | зоны |")
    add("|---|---|---|---|---|---|---|")
    for value in sorted(groups, key=lambda v: (v is None, v or 0)):
        items = groups[value]
        c = collections.Counter(o["classification"] for o in items)
        zones = ",".join(sorted({o["zone"] for o in items}))
        label = "—" if value is None else "0o%o" % value
        dec = "—" if value is None else str(value)
        add("| %s | %s | %d | %d | %d | %d | %s |" % (
            label, dec, len(items), c.get("VALID", 0),
            c.get("SUSPICIOUS", 0), c.get("HYPOTHETICAL", 0), zones))
    add("")
    add("## Подозрительные вхождения: побайтовые доказательства")
    add("")
    for d in details:
        ev = d["evidence"]
        o = d["occurrences"][0]
        add("### зона %s, слово 0o%s, аргумент 0o%o" % (
            d["zone"], d["addr"], d["value"]))
        add("источники: %s" % ", ".join(
            "%s:%d" % (x["file"], x["line"]) for x in d["occurrences"][:8]))
        add("класс: SUSPICIOUS — %s" % o["note"])
        if ev.get("error"):
            add("ОШИБКА: %s" % ev["error"])
        else:
            add("байты: %s" % ev["bytes_hex"])
            add("слово: 0o%s" % ev["word_oct"])
            add("ASCII: %r (печатных %d/6%s)" % (
                ev["ascii"], ev["printable"],
                " — ДАННЫЕ/ТЕКСТ" if ev["text_like"] else ""))
            for side in ("left", "right"):
                dec = ev[side]
                add("%s 0o%s: %s / %s, reg=М%d, arg1=0o%o, "
                    "Aex&0377=0o%o" % (
                        side.upper(), ev[side + "_oct"], dec["name"],
                        dec["kind"], dec["reg"], dec["arg1"],
                        dec["arg1"] & SELECTOR_MASK))
        add("")
    add("## Таблица предложенных правок (НЕ применены)")
    add("")
    add("| зона | line | addr | старая строка | предлагаемая строка/роль | "
        "доказательство байтовой идентичности |")
    add("|---|---|---|---|---|---|")
    for r in fixes:
        add("| %s | %d | 0o%s | `%s` | `%s` (%s) | %s |" % (
            r["zone"], r["line"], r["addr"], r["old_line"], r["proposed"],
            r["role"], r["byte_identity"]))
    add("")
    add("Правки НЕ применялись: AGENTS.md разрешает только комментарии "
        "после запятой. Перемаркировка — задача отдельного агента.")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT, help="корень репозитория")
    ap.add_argument("--out", help="писать отчёт в файл вместо stdout")
    ap.add_argument("--json", action="store_true", help="JSON вместо текста")
    args = ap.parse_args(argv)

    occ = scan(args.root)
    summary = summarize(occ)
    groups = group_by_value(occ)
    details = suspicious_details(occ, args.root)
    fixes = fix_table(details)

    if args.json:
        payload = dict(summary=summary, occurrences=occ,
                       groups={("null" if k is None else "%o" % k): v
                               for k, v in groups.items()},
                       suspicious=details, fix_table=fixes)
        text = json.dumps(payload, ensure_ascii=False, indent=1)
    else:
        text = render_text(occ, summary, groups, details, fixes)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
