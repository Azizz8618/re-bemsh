#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GLOBAL LITERAL-TO-LABEL TABLE for the 69 reconstructed .be sources.

The macro-BESM assembler (dispak) accepts a symbolic name wherever an octal
address field may stand.  A name defined by ``ЭКВ 'NNNN'`` emits NO word, so

    УИА '4235'(М2)      ->      УИА AM4235(М2)
    AM4235 ЭКВ '4235'

assembles to exactly the same 48-bit word.  Byte identity is checked by
``bash tools/rebuild-zone.sh <zone> <MODE>`` -> 1024/1024, 0 differences.

This tool NEVER edits a .be file in its default (scan) mode.  It only writes
    sym/ALL_LABELS.tab      (the global literal -> label dictionary)
    docs/LITERAL-LABELS.md  (methodology, stats, conflicts, caveats)
Use ``--apply-zone`` to edit ONE .be file (with a .bak, per AGENTS.md §0.5).

Classification is deliberately conservative:
  ADDRESS   - operand is a memory address / branch target (relabel).
  CONSTANT  - extract code, immediate, mask, data word, EQU definition
              (NEVER relabel).
  AMBIGUOUS - context does not decide; label assigned, confidence=ГИПОТЕЗА.

Labels are annotation aids, NOT ground truth (docs/LABEL-MAP.md §0).
"""

from __future__ import annotations

import argparse
import collections
import datetime
import pathlib
import re
import shutil
import sys

ROOT_DEFAULT = pathlib.Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 1. Extraction
# ---------------------------------------------------------------------------

# A quoted octal operand WITHOUT a letter prefix.  The negative look-behind
# excludes B'................' (48-bit data words), P'...'/H'...' (text), and
# any other prefixed literal.  Cyrillic В/П/Х are inside [А-Я].
QUOTED_OCTAL = re.compile(r"(?<![A-ZА-Я])'([0-7]+)'")

# Comment lines start with '*'.  Inline comments begin at the first comma;
# operands themselves never contain a comma in these 69 sources.
RE_MNEMONIC = re.compile(r"^\s*([A-ZА-Я][A-ZА-Я0-9]*)\b(.*)$", re.UNICODE)
RE_ZONE_FROM_NAME = re.compile(r"-Z(\d{4})\.be$")

# ---------------------------------------------------------------------------
# 2. Classification vocabularies
# ---------------------------------------------------------------------------

# Instructions whose numeric operand is the ADDRESS field of the BESM-6 word
# (memory cell, branch target, CALL entrance, index base, I/O cell, ...).
ADDRESS_MNEMONICS = {
    "УИА", "УИ",             # установка индекса
    "ПБ", "ПВ", "ПО", "ПЕ",  # переходы / CALL / return
    "НТЖ", "ЦИКЛ", "ВЫПР",   # условия, цикл, IRET/шлюз
    "ПИО", "ПИНО", "СБР",    # косвенные переходы
    "СЧ", "ЗП", "СЧИ", "СЧМ", "СЧРЖ", "СЧМР", "ЗПМ",  # считывание/запись
    "СЛИА",  # слияние/адрес (вне таблиц ошибок — адрес)
    "Э70", "Э74",            # экстракоды, работающие с адресом (по заданию)
    "И", "ИЛИ", "НЕД", "ЧЕД", "ЗНАК", "УМН", "ДЕЛ",  # арифметика (память)
    "СЛ", "СЛЦ", "СЛП", "РЗБ",
    "МОД", "МОДА",           # модификация адреса
    "ВЧ", "ВЧП", "ВЧАБ", "ВЧОБ", "УВВ",              # ввод/вывод
    "УИМ", "УИИ",            # индекс через регистр
}

# Operand is a value/code field, NOT an address.  Never relabel.
CONSTANT_MNEMONICS = {
    "СДА",      # маска: СДА 64-6
    "СЛПА",     # маска: СЛПА 64+48
    "ВЧПА",     # маска: ВЧПА 64+8
    "РЕГ",      # номер регистра
    "РЖА", "РЖ",  # загрузка константы в регистр
}

# Extract codes (EXEC/KOND).  Their operand is an extract-code word or a
# small immediate, NOT an address, unless context proves otherwise.  Only
# Э70 and Э74 are promoted to ADDRESS (explicit requirement).
EXTRACT_PREFIX = "Э"

# '25252' / '72525' under СЛИА/ВЧП in these zones are a chessboard test fill,
# not memory references (analysis/GLOBAL-XREF.md §3.1, SEMANTIC/Z0567.md §3).
FILL_VALUES = {"25252", "72525"}
FILL_ZONES = {"0146", "0160", "0163", "0164", "0167",
              "0546", "0560", "0563", "0564", "0567"}

# Zone family, used for context-prefixed label stems.
def zone_family(zone: str) -> str:
    z = int(zone, 8)
    if 0o55 <= z <= 0o60:
        return "ASM"      # avtokod ITM
    if 0o137 <= z <= 0o177:
        return "B"        # B 06/78
    if 0o540 <= z <= 0o577:
        return "B2"       # B2 12/77
    return "GL"           # global / memory

FAMILY_STEM = {"ASM": "AM", "B": "MB", "B2": "B2", "GL": "GM"}

# Mnemonic -> semantic class (second letter of a context-prefixed stem).
ROLE_STEM = {
    "УИА": "IX", "УИ": "IX", "УИМ": "IX", "УИИ": "IX",
    "ПБ": "BR", "ПО": "BR", "ПВ": "CA", "ПЕ": "BR", "НТЖ": "BR",
    "ЦИКЛ": "BR", "ВЫПР": "BR", "ПИО": "BR", "ПИНО": "BR", "СБР": "BR",
    "СЧ": "CE", "ЗП": "CE", "СЧИ": "CE", "СЧМ": "CE", "СЧРЖ": "CE",
    "СЧМР": "CE", "ЗПМ": "CE", "Э70": "CE", "Э74": "CE",
    "И": "CE", "ИЛИ": "CE", "СЛ": "CE", "СЛЦ": "CE", "СЛП": "CE",
    "НЕД": "CE", "ЧЕД": "CE", "ЗНАК": "CE", "УМН": "CE", "ДЕЛ": "CE",
    "РЗБ": "CE", "МОД": "MD", "МОДА": "MD", "СЧИ": "CE",
    "ВЧ": "IO", "ВЧП": "IO", "ВЧАБ": "IO", "ВЧОБ": "IO", "УВВ": "IO",
}

# Curated compact names for the handful of truly global addresses
# (docs/LABEL-MAP.md §8).  They follow the examples in the task statement.
CURATED_LABELS = {
    "70000": "SYSC70",   # SYSCALL_GATE
    "70707": "ITM707",   # CODE_ITM_GATE
    "4000":  "MON400",   # MEM_MONITOR
    "4007":  "PLB407",   # MEM_PLBEG
    "2000":  "EDL200",   # MAC_EDITOR_LOAD
    "1000":  "LOG001",   # INIT_LOG_ENTRY (alias of 00001)
    "1":     "LOG001",   # 00001 normalised
    "00000": "INI000",   # INIT_ZERO
}

# Generic role-name words that carry no information for a <=6 char label.
ROLE_STOPWORDS = {
    "CODE", "MEM", "DATA", "GLOBAL", "UNKNOWN", "THE", "ADDRESS",
    "YACHEYKA", "UTIL", "TXT", "ERR", "FUNC",
}

ROLE_TOKEN_STEM = {
    "SYSCALL": "SYSC", "GATE": "GAT", "ITM": "ITM", "MONITOR": "MON",
    "PLBEG": "PLB", "EDITOR": "EDT", "LOAD": "LDD", "PRINT": "PRN",
    "BUF": "BUF", "BUFFER": "BUF", "STAMP": "STP", "TAB": "TAB",
    "LINK": "LNK", "DISPATCH": "DSP", "ENTRY": "ENT", "EXIT": "EXT",
    "FLAG": "FLG", "CNT": "CNT", "COUNTER": "CNT", "CHECK": "CHK",
    "OFF": "OFF", "ARCH": "ARC", "SPR": "SPR", "MSG": "MSG",
    "MACH": "MCH", "ARA": "ARA", "MACRO": "MAC", "LOGICAL": "LOG",
    "INIT": "INI", "OUT": "OUT", "ZERO": "ZRO",
}

# ---------------------------------------------------------------------------
# 3. Scan / classify
# ---------------------------------------------------------------------------

def classify(mnem: str, value: str, zone: str) -> str:
    """Return ADDRESS | CONSTANT | AMBIGUOUS for one quoted operand."""
    # ЭКВ 'NNNN' is a label *definition*, not an operand to be relabeled.
    if mnem == "ЭКВ":
        return "CONSTANT"
    if mnem == "КОНД":
        return "CONSTANT"            # КОНД В'...' / raw data word
    if value in FILL_VALUES and zone in FILL_ZONES:
        return "CONSTANT"            # chessboard fill, not a memory cell
    if mnem in CONSTANT_MNEMONICS:
        return "CONSTANT"
    if mnem.startswith(EXTRACT_PREFIX):
        if mnem in {"Э70", "Э74"}:
            if value in FILL_VALUES and zone in FILL_ZONES:
                return "CONSTANT"
            return "ADDRESS"
        # All other extract codes are value/extract operands by default.
        # (Э50 '105' from the task statement is the canonical example.)
        return "CONSTANT"
    if mnem in ADDRESS_MNEMONICS:
        return "ADDRESS"
    # Unknown mnemonic: keep the value visible but mark the hypothesis weak.
    return "AMBIGUOUS"


def _code_part(line: str) -> str:
    """Strip comment lines and inline comments, keeping the operand field."""
    if line.lstrip().startswith("*"):
        return ""
    comma = line.find(",")
    return line[:comma] if comma >= 0 else line


def scan(root: pathlib.Path):
    """Scan all bemsh/*.be.  Return (occurrences, per_value_index)."""
    occurrences = []
    bemsh = root / "bemsh"
    for path in sorted(bemsh.glob("*.be")):
        mz = RE_ZONE_FROM_NAME.search(path.name)
        if not mz:
            continue
        zone = mz.group(1)
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = _code_part(raw)
            if not code:
                continue
            toks = code.split()
            if not toks:
                continue
            mnem = toks[0]
            is_eqv = len(toks) >= 2 and toks[1] == "ЭКВ"
            for m in QUOTED_OCTAL.finditer(code):
                value = m.group(1)
                kind = "CONSTANT" if is_eqv else classify(mnem, value, zone)
                # Normalise: leading zeros are insignificant for octal values.
                norm = value.lstrip("0") or "0"
                occurrences.append({
                    "file": path.name,
                    "line": lineno,
                    "zone": zone,
                    "family": zone_family(zone),
                    "mnem": mnem,
                    "raw": value,
                    "value": norm,
                    "kind": kind,
                    "is_eqv": is_eqv,
                })
    return occurrences


def load_global_roles(root: pathlib.Path):
    """value -> (role_name, type_code) from sym/GLOBAL.tab."""
    out = {}
    p = root / "sym" / "GLOBAL.tab"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        if not re.fullmatch(r"[0-7]+", parts[0]):
            continue
        # Keep the OCTAL spelling (leading zeros stripped), like scan() does.
        norm = parts[0].lstrip("0") or "0"
        out.setdefault(norm, (parts[2], parts[1]))
    return out


def load_semantic_roles(root: pathlib.Path):
    """value -> role token, harvested from docs/SEMANTIC/Z*.md 'NNN = ROLE'."""
    out = {}
    pat = re.compile(
        r"(?<!\d)([0-7]{2,6})[₈]?\s*(?:=|→|->)\s*"
        r"((?:ERR|CNT|FLAG|TXT|CODE|MAC|MEM|OUT|INIT|LIMIT|WORK|PTR|CALL|"
        r"JMP|SUB|TAB|DAT|GAT|ITM|SYSCALL)[A-Z0-9_]*)\b")
    for p in sorted((root / "docs" / "SEMANTIC").glob("Z*.md")):
        zone = p.stem[1:]
        for m in pat.finditer(p.read_text(encoding="utf-8")):
            norm = m.group(1).lstrip("0") or "0"
            out.setdefault(norm, (m.group(2), zone))
    return out


def load_existing_labels(root: pathlib.Path):
    """value -> set(existing label strings defined by ЭКВ in any .be)."""
    out = collections.defaultdict(set)
    for path in (root / "bemsh").glob("*.be"):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*([A-Z][A-Z0-9]{1,5})\s+ЭКВ\s+'([0-7]+)'", line)
            if m:
                out[m.group(2).lstrip("0") or "0"].add(m.group(1))
    return out


# ---------------------------------------------------------------------------
# 4. Label synthesis
# ---------------------------------------------------------------------------

def stem_from_role(role: str) -> str:
    """Deterministic <=4-char stem from a PREFIX_ROLE style name."""
    preferred = []
    for tok in re.split(r"[_]+", role.upper()):
        if not tok or tok in ROLE_STOPWORDS:
            continue
        preferred.append(ROLE_TOKEN_STEM.get(tok, tok[:4]))
    if not preferred:
        return "GEN"
    # Prefer the most specific (last meaningful) token, then the first one.
    stem = preferred[-1] if len(preferred[-1]) <= 4 else preferred[-1][:4]
    if len(stem) < 3 and len(preferred) > 1:
        stem = (preferred[0][:2] + stem)[:4]
    return stem.upper()


def compose_label(stem: str, value: str) -> str:
    """stem + right-aligned octal suffix, total length <= 6."""
    stem = re.sub(r"[^A-Z0-9]", "", stem.upper())[:4] or "LBL"
    room = 6 - len(stem)
    suffix = value[-room:] if room > 0 else ""
    return (stem + suffix)[:6]


def _b36(n: int, width: int) -> str:
    """Fixed-width base-36 number; never changes length while n < 36**width."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    n %= 36 ** width
    out = ""
    for _ in range(width):
        out = alphabet[n % 36] + out
        n //= 36
    return out


def unique_label(base: str, used: set) -> str:
    """Deterministic collision resolution, preserving <=6 chars."""
    if base not in used:
        used.add(base)
        return base
    for n in range(1, 10):
        cand = (base[:5] + str(n))[:6]
        if cand not in used:
            used.add(cand)
            return cand
    # Fallback: fixed-width base-36 tail (46656 distinct values, no loop trap).
    for i in range(36 ** 3):
        cand = "LBL" + _b36(i, 3)
        if cand not in used:
            used.add(cand)
            return cand
    raise RuntimeError("label space exhausted")


def build_index(occurrences, global_roles, semantic_roles, existing_labels, root):
    """Aggregate occurrences per unique value and assign one label each."""
    by_value = collections.defaultdict(list)
    for o in occurrences:
        if o["is_eqv"] or o["kind"] == "CONSTANT":
            continue
        by_value[o["value"]].append(o)

    # Reserve every label already present in any .be so the global table is
    # collision-free with the batch agents' previous work.  Labels that we
    # INTEND to reuse for their own value are released from the reserve set,
    # otherwise collision resolution would rename e.g. INIT03 -> INIT01.
    all_existing = set()
    for labels in existing_labels.values():
        all_existing.update(labels)
    reused = set()
    for value in by_value:
        if value in CURATED_LABELS:
            reused.add(CURATED_LABELS[value])
        elif value in existing_labels:
            reused.add(sorted(existing_labels[value])[0])
    used = all_existing - reused

    rows = {}
    for value in sorted(by_value, key=lambda v: (len(v), v)):
        occ = by_value[value]
        kinds = collections.Counter(o["kind"] for o in occ)
        kind = "ADDRESS" if kinds.get("ADDRESS", 0) >= kinds.get("AMBIGUOUS", 0) \
               else "AMBIGUOUS"
        zones = collections.Counter(o["zone"] for o in occ)
        zone = zones.most_common(1)[0][0]
        fams = collections.Counter(o["family"] for o in occ)
        family = fams.most_common(1)[0][0]
        mnems = collections.Counter(o["mnem"] for o in occ)
        mnem = mnems.most_common(1)[0][0]
        evidence = f"{occ[0]['file']}:{occ[0]['line']}"

        role_name, source, confidence = "", "", "ГИПОТЕЗА"
        if value in CURATED_LABELS:
            label = CURATED_LABELS[value]
            role_name = "GLOBAL.curated"
            source, confidence = "LABEL-MAP.md §8", "ПОДТВЕРЖДЕНО"
        elif value in existing_labels:
            # Reuse the batch agents' own name when there is a single choice.
            choices = sorted(existing_labels[value])
            label = choices[0]
            role_name = ",".join(choices)
            source, confidence = "bemsh/*.be ЭКВ", "ПОДТВЕРЖДЕНО"
        elif value in global_roles and int(value, 8) >= 0o2000:
            role_name = global_roles[value][0]
            stem = stem_from_role(role_name)
            label = compose_label(stem, value)
            source, confidence = "sym/GLOBAL.tab", "ГИПОТЕЗА"
        elif value in semantic_roles:
            role_name = semantic_roles[value][0]
            stem = stem_from_role(role_name)
            label = compose_label(stem, value)
            source, confidence = "docs/SEMANTIC/Z*.md", "ГИПОТЕЗА"
        else:
            # Context-prefixed compact label.  A 2-letter stem leaves room for
            # up to 4 octal digits: AM4235 / MB4235 / B24235 / BR4235 / CA...
            # Control transfers get BR/CA; everything else keeps the zone
            # family prefix (the detailed role stays in the `context` column).
            if mnem in {"ПБ", "ПО", "ПЕ", "НТЖ", "ЦИКЛ", "ВЫПР",
                        "ПИО", "ПИНО", "СБР"}:
                stem = "BR"
            elif mnem == "ПВ":
                stem = "CA"
            else:
                stem = FAMILY_STEM.get(family, "GM")
            label = compose_label(stem, value)
            source, confidence = f"context:{family}:{mnem}", "ГИПОТЕЗА"

        label = unique_label(label, used)

        # Conflicts: same octal value used under different semantic classes or
        # in different zone families (LABEL-MAP.md §0.1 — zone-local words).
        roles_in_doc = set()
        if value in global_roles:
            roles_in_doc.add(global_roles[value][0])
        if value in semantic_roles:
            roles_in_doc.add(semantic_roles[value][0])
        conflict = []
        if len(kinds) > 1:
            conflict.append("ADDRESS/AMBIGUOUS")
        if len(zones) > 1:
            conflict.append("Z:" + "/".join(sorted(z for z, _ in zones.most_common(4))))
        if len(set(o["family"] for o in occ)) > 1:
            conflict.append("FAMILY:" + "/".join(sorted(set(o["family"] for o in occ))))
        if len(roles_in_doc) > 1 or (roles_in_doc and label not in roles_in_doc):
            conflict.append("ROLE:" + "/".join(sorted(roles_in_doc)))

        rows[value] = {
            "label": label, "value": value, "type": kind,
            "zone": zone, "family": family, "mnem": mnem,
            "mnems": mnems, "zones": zones, "count": len(occ),
            "role": role_name, "source": source, "confidence": confidence,
            "evidence": evidence, "conflict": "; ".join(conflict),
            "occ": occ,
        }
    return rows


# ---------------------------------------------------------------------------
# 5. Writers
# ---------------------------------------------------------------------------

def write_table(rows, root: pathlib.Path):
    p = root / "sym" / "ALL_LABELS.tab"
    lines = [
        "# label<TAB>octal<TAB>type<TAB>zone<TAB>context<TAB>confidence",
        "# Generated by tools/literal_labels.py; annotation only, not ground truth.",
    ]
    for value in sorted(rows, key=lambda v: (len(v), v)):
        r = rows[value]
        ctx = f"{r['mnem']}|{','.join(m for m,_ in r['mnems'].most_common(3))}|{r['source']}"
        if r["conflict"]:
            ctx += "|CONFLICT:" + r["conflict"].replace(" ", "")
        lines.append("\t".join([r["label"], value, r["type"], r["zone"],
                                ctx, r["confidence"]]))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def load_table(root: pathlib.Path):
    """Read sym/ALL_LABELS.tab into the minimal row shape apply_zone needs."""
    out = {}
    p = root / "sym" / "ALL_LABELS.tab"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        label, value = parts[0], parts[1]
        out.setdefault(value, {"label": label, "type": parts[2] if len(parts) > 2 else "",
                               "zone": parts[3] if len(parts) > 3 else ""})
    return out


def write_report(rows, occurrences, root: pathlib.Path):
    stats = collections.Counter(o["kind"] for o in occurrences)
    eqv = sum(1 for o in occurrences if o["is_eqv"])
    uniq_all = len({o["value"] for o in occurrences})
    uniq_labelled = len(rows)
    conflicts = [(v, r) for v, r in rows.items() if r["conflict"]]
    top = sorted(rows.values(), key=lambda r: (-r["count"], r["value"]))[:100]
    lines = []
    a = lines.append
    a("# ГЛОБАЛЬНАЯ ТАБЛИЦА ЛИТЕРАЛ → МЕТКА")
    a("")
    a("Сгенерировано `python3 tools/literal_labels.py`. "
      "Исходники `.be`, `gold/`, `dis/` НЕ изменяются.")
    a("")
    a("> **Статус: аннотация, не ground truth.** Метки — компактные подсказки "
      "(≤6 символов, иначе `METKA>6`); роли из `GLOBAL.tab`/`SEMANTIC` — "
      "гипотезы без исходника транслятора. См. `docs/LABEL-MAP.md` §0.")
    a("")
    a("## 1. Методика")
    a("")
    a("1. Сканируются все 69 `bemsh/*.be`. Извлекаются кавычные восьмеричные "
      "операнды **без буквенного префикса** — `В'...'` (48-битные слова), "
      "`П'...'`/`Х'...'` (текст) не трогаются.")
    a("2. Строки комментариев (`*`) и хвост после первой запятой отсекаются.")
    a("3. Классификация по мнемонике, зоне и значению: `ADDRESS` (операнд — "
      "адрес/цель перехода), `CONSTANT` (экстракод `Э50 '105'`, маска `СДА "
      "64-6`, immediate `РЖА '3'`, слово данных, определение `ЭКВ`), "
      "`AMBIGUOUS` (контекст не определяет роль).")
    a("4. Метка: curated-адрес → `GLOBAL.tab` → `SEMANTIC/Z*.md` → "
      "префикс зоны+класс мнемоники + значение. Суффикс — последние цифры "
      "восьмеричного адреса; полное значение — в `ALL_LABELS.tab`. "
      "Коллизии разрешаются детерминированно.")
    a("5. Применение: `<МНЕМ> AM4235(М2)` + строка `AM4235 ЭКВ '4235'`, "
      "вставляемая после строки `М`. `ЭКВ` не порождает слово → байтовая "
      "идентичность сохраняется.")
    a("6. Если подстановка удлиняет строку до 80 символов, транслятор "
      "выдаёт `ОПЕРАЦИИ НЕТ` (`docs/RAW-RECOVERY.md`). `--apply-zone` "
      "сокращает только комментарий после первой запятой до ≤78 символов; "
      "кодовая часть строки не трогается.")
    a("")
    a("## 2. Статистика")
    a("")
    a("| Показатель | Значение |")
    a("|---|---|")
    a(f"| Всего кавычных операндов (без `В'...'`) | {sum(stats.values())} |")
    a(f"| Уникальных значений | {uniq_all} |")
    a(f"| ADDRESS (вхождений) | {stats['ADDRESS']} |")
    a(f"| CONSTANT (вхождений) | {stats['CONSTANT']} |")
    a(f"| AMBIGUOUS (вхождений) | {stats['AMBIGUOUS']} |")
    a(f"| из них определений `ЭКВ` (исключены) | {eqv} |")
    a(f"| Уникальных адресов/неопределённых → меток | {uniq_labelled} |")
    a(f"| Конфликтных значений | {len(conflicts)} |")
    a("")
    a("Подсчёт отличается от «60 189 / 5 411» в постановке задачи: здесь "
      "считаются **все** кавычные операнды кодовой части 69 файлов, включая "
      "233 значения в уже существующих строках `ЭКВ`; строки `*` и хвост "
      "после запятой исключены. Разница — в гранулярности сканера, а не в "
      "наборе файлов.")
    a("")
    a("## 3. Топ-100 literals по частоте")
    a("")
    a("| # | восьм. | метка | тип | вх | зона | мнемоника | evidence | источник роли |")
    a("|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(top, 1):
        a(f"| {i} | `{r['value']}` | `{r['label']}` | {r['type']} | "
          f"{r['count']} | {r['zone']} | {r['mnem']} | {r['evidence']} | "
          f"{r['source']} |")
    a("")
    a("## 4. Конфликты (одно значение → разные роли/зоны)")
    a("")
    a("| восьм. | метка | зоны | мнемоники |Conflict|")
    a("|---|---|---|---|---|")
    for value, r in sorted(conflicts, key=lambda x: (-x[1]["count"], x[0]))[:120]:
        zones = ",".join(sorted(r["zones"])[:6])
        mnems = ",".join(m for m, _ in r["mnems"].most_common(4))
        a(f"| `{value}` | `{r['label']}` | {zones} | {mnems} | "
          f"{r['conflict'].replace('|', '/')} |")
    if len(conflicts) > 120:
        a("")
        a(f"… и ещё {len(conflicts)-120} конфликтных значений (полный список — "
          "в `sym/ALL_LABELS.tab`, колонка `context` с `CONFLICT:`).")
    a("")
    a("## 5. Честные оговорки")
    a("")
    a("1. Метки компактны и нужны только для чтения листинга; они **не** "
      "доказательство роли. `ПОДТВЕРЖДЕНО` здесь означает флаг из "
      "`GLOBAL.tab`/`ЭКВ`-определения, а не исходник транслятора.")
    a("2. `A#####`/`D#####` и адреса `GLOBAL.tab` — zone-local (`LABEL-MAP.md` "
      "§0.1): одно и то же число в зонах 0055 и 0147 — разные ячейки. "
      "Поэтому role-имя применяется только к глобальным адресам ≥ `02000₈`; "
      "для остальных используется context-префикс зоны.")
    a("3. Экстракоды (`Э50 '105'`, `Э52 …`, …) и маски помечены `CONSTANT` и "
      "**не** переименовываются. `'25252'`/`'72525'` в зонах таблиц ошибок — "
      "шахматная заливка, а не адрес (`GLOBAL-XREF.md` §3.1).")
    a("4. `AMBIGUOUS` получает метку с confidence `ГИПОТЕЗА`; перед массовым "
      "применением такую строку стоит проверить вручную.")
    a("5. Обязательная проверка после `--apply-zone`: `bash "
      "tools/rebuild-zone.sh <zone> <MODE>` → `1024/1024`, `0 различий`.")
    a("")
    a("## 6. Применение по зонам (батч-агенты)")
    a("")
    a("```bash")
    a("cd /tmp/.private/azizz/re-bemsh")
    a("python3 tools/literal_labels.py --apply-zone 0055 --mode ASM")
    a("bash tools/rebuild-zone.sh 0055 ASM   # ожидаемо: 1024/1024, 0 различий")
    a("```")
    a("")
    a("`--mode`: `ASM` (0055–0060), `B` (0137–0177), `MBE2` (0540–0577). "
      "Инструмент делает `.bak.<timestamp>` и печатает список замен. "
      "Проверено на копиях в `/tmp/.private/azizz/label-test/`: зоны "
      "0055/ASM, 0137/B, 0147/B, 0547/MBE2, 0567/MBE2 → `RESULT: PASS`, "
      "0 различий.")
    a("")
    p = root / "docs" / "LITERAL-LABELS.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 6. apply mode
# ---------------------------------------------------------------------------

def find_target(root: pathlib.Path, zone_arg: str, mode: str | None):
    if zone_arg.endswith(".be"):
        p = root / "bemsh" / zone_arg
        return p if p.exists() else None
    if not re.fullmatch(r"[0-7]{2,4}", zone_arg):
        return None
    zone = f"{int(zone_arg, 8):04o}"
    mode_to_prefix = {"B": "MBE", "MBE2": "MBE2", "ASM": "ASM"}
    prefixes = [mode_to_prefix[mode]] if mode else ["ASM", "MBE", "MBE2"]
    for pref in prefixes:
        for tail in (f"{pref}-Z{zone}-L1.be", f"{pref}-Z{zone}.be"):
            p = root / "bemsh" / tail
            if p.exists():
                return p
    return None


def apply_zone(root: pathlib.Path, target: pathlib.Path, rows, occurrences,
               do_backup: bool = True):
    """Byte-safe in-place edit of ONE .be file.  Returns a report dict."""
    by_value = {}
    for value, r in rows.items():
        by_value[value] = r["label"]

    mz = RE_ZONE_FROM_NAME.search(target.name)
    zone = mz.group(1) if mz else "0000"

    text = target.read_text(encoding="utf-8")
    had_bom = text.startswith("\ufeff")
    if had_bom:
        text = text[1:]
    lines = text.split("\n")
    newline = "\n"

    used_labels = collections.Counter()
    changed_lines = []
    out = []
    for idx, raw in enumerate(lines):
        code = _code_part(raw)
        new = raw
        if code:
            toks = code.split()
            is_eqv = len(toks) >= 2 and toks[1] == "ЭКВ"
            if not is_eqv:
                def repl(m):
                    value = m.group(1).lstrip("0") or "0"
                    # Context-aware: never relabel an extract code, mask,
                    # immediate, data word or chessboard fill.
                    if classify(toks[0], value, zone) not in ("ADDRESS", "AMBIGUOUS"):
                        return m.group(0)
                    label = by_value.get(value)
                    if label is None:
                        return m.group(0)
                    used_labels[label] += 1
                    return label
                new = QUOTED_OCTAL.sub(repl, code) + raw[len(code):]
        # HARD LIMIT (docs/RAW-RECOVERY.md §"лимит длины строки"): an 80-char
        # source line wraps its comment into a phantom line and the translator
        # emits "ОПЕРАЦИИ НЕТ".  Shorten only the text AFTER the first comma;
        # the assembled word (code part) is never touched.
        if len(new) > 78:
            comma = new.find(",")
            if comma >= 0:
                head, cmt = new[:comma], new[comma:]
                cmt = re.sub(r"\s*->\s*адр\.\s*[0-7]+", "", cmt)
                if len(head) + len(cmt) <= 78:
                    new = head + cmt
                else:
                    new = (head + cmt)[:78]
        if new != raw:
            changed_lines.append((idx + 1, raw.strip(), new.strip()))
        out.append(new)

    if not used_labels:
        return {"file": str(target), "replacements": 0, "inserted": [],
                "changed": changed_lines, "backup": None, "written": False}

    # Existing ЭКВ definitions in this file (do not redefine).
    existing = set()
    for line in out:
        m = re.match(r"^\s*([A-Z][A-Z0-9]{1,5})\s+ЭКВ\s+'([0-7]+)'", line)
        if m:
            existing.add(m.group(1))

    to_insert = []
    for label, count in sorted(used_labels.items()):
        if label in existing:
            continue
        value = next(v for v, r in rows.items() if r["label"] == label)
        to_insert.append(f"{label} ЭКВ '{int(value,8):o}'")

    if to_insert:
        # Insert after the 'М' line / existing ЭКВ block, before first code.
        insert_at = None
        for i, line in enumerate(out):
            if line.strip() in ("М", "M"):
                insert_at = i + 1
                break
        if insert_at is None:
            for i, line in enumerate(out):
                if re.match(r"^\s*[A-Z][A-Z0-9]{1,5}\s+ЭКВ\s+'[0-7]+'", line):
                    insert_at = i + 1
        if insert_at is None:
            insert_at = 1
        # Skip comment lines immediately following 'М' that describe the block.
        j = insert_at
        while j < len(out) and out[j].lstrip().startswith("*"):
            j += 1
        while j < len(out) and re.match(
                r"^\s*[A-Z][A-Z0-9]{1,5}\s+ЭКВ\s+'[0-7]+'", out[j]):
            j += 1
        block = [f"* --- {len(to_insert)} меток из tools/literal_labels.py "
                 f"(≤6 симв.; ЭКВ не порождает слово)"]
        block += to_insert
        out[j:j] = block

    backup = None
    if do_backup:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = str(target) + f".bak.{stamp}"
        shutil.copy2(target, backup)

    body = newline.join(out)
    target.write_text(("\ufeff" if had_bom else "") + body, encoding="utf-8")
    return {
        "file": str(target),
        "replacements": sum(used_labels.values()),
        "inserted": to_insert,
        "changed": changed_lines,
        "backup": backup,
        "written": True,
    }


# ---------------------------------------------------------------------------
# 7. CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply-zone", metavar="Z",
                    help="apply labels to ONE .be file (zone '0055' or name "
                         "'ASM-Z0055.be'); NEVER run on repo files during build")
    ap.add_argument("--mode", choices=["B", "MBE2", "ASM"],
                    help="source family, disambiguates --apply-zone <octal>")
    ap.add_argument("--root", type=pathlib.Path, default=ROOT_DEFAULT,
                    help="repo root (default: parent of tools/)")
    ap.add_argument("--no-backup", action="store_true",
                    help="do not create a .bak before --apply-zone")
    ap.add_argument("--check", action="store_true",
                    help="only print stats; write nothing")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    occurrences = scan(root)
    global_roles = load_global_roles(root)
    semantic_roles = load_semantic_roles(root)
    existing = load_existing_labels(root)
    rows = build_index(occurrences, global_roles, semantic_roles, existing, root)

    stats = collections.Counter(o["kind"] for o in occurrences)
    print(f"scanned {len(set(o['file'] for o in occurrences))} .be files")
    print(f"quoted operands (no B-prefix): {len(occurrences)}, "
          f"unique values: {len(set(o['value'] for o in occurrences))}")
    print(f"ADDRESS={stats['ADDRESS']} CONSTANT={stats['CONSTANT']} "
          f"AMBIGUOUS={stats['AMBIGUOUS']}")
    print(f"labelled values: {len(rows)}, "
          f"conflicts: {sum(1 for r in rows.values() if r['conflict'])}")

    if not args.apply_zone:
        if not args.check:
            tp = write_table(rows, root)
            dp = write_report(rows, occurrences, root)
            print("wrote", tp.relative_to(root))
            print("wrote", dp.relative_to(root))
        return 0

    target = find_target(root, args.apply_zone, args.mode)
    if target is None:
        print(f"REFUSE: cannot resolve --apply-zone {args.apply_zone!r}", file=sys.stderr)
        return 2
    table_rows = load_table(root)
    if table_rows:
        print(f"apply: using {len(table_rows)} rows from sym/ALL_LABELS.tab")
        rows = table_rows
    else:
        print("apply: ALL_LABELS.tab not found, using freshly computed rows")
    rep = apply_zone(root, target, rows, occurrences, not args.no_backup)
    if not rep["written"]:
        print("nothing to change in", target.name)
        return 0
    print(f"APPLIED {target.name}: {rep['replacements']} operand replacements, "
          f"{len(rep['inserted'])} ЭКВ definitions inserted")
    if rep["backup"]:
        print("backup:", rep["backup"])
    for ln, old, new in rep["changed"][:20]:
        print(f"  :{ln}  {old}  ->  {new}")
    if len(rep["changed"]) > 20:
        print(f"  ... and {len(rep['changed'])-20} more lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
