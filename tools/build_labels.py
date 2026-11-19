#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_labels.py — глобальный словарь ролевых имён (@GLOBAL LABEL DICTIONARY).

Собирает осмысленные имена из уже существующих documents-таблиц и строит
два выходных файла (больше файлы не трогаются):

  sym/GLOBAL.tab   — аннотационная таблица символов формата "%o %d %63s";
  docs/LABEL-MAP.md — полный отчёт: адрес | имя | роль | evidence | confidence.

ВХОД (только чтение):
  docs/COMMENTING-STANDARD.md   — префиксы/суффиксы, запрещённые авто-имена;
  docs/LABELS-B.md, -B2.md, -BE.md — таблицы «было → стало»;
  analysis/VARIABLES.md, VARIABLES-VALIDATION.md — 76/73 унаследованных имени;
  docs/SEMANTIC/Z*.md, ASM-CODE-RECOVERY.md — новые роли и штампы;
  docs/TEXT-CONSTANTS.md, docs/ANCHORS.md,
  analysis/MEMORY-MAP.md, docs/PLAN-NEXT.md, docs/PLAN.md — глобальные адреса.

ВАЖНО: это АННОТАЦИЯ, а не ground truth. Роль без исходника транслятора
остаётся ГИПОТЕЗОЙ (COMMENTING-STANDARD.md §2.4, AGENTS.md §0.1–2).
Ни один .be/.asm/gold-файл не модифицируется.

CLI:
  python3 tools/build_labels.py            # записать оба файла + отчёт в stdout
  python3 tools/build_labels.py --check    # только проверить счётчики/конфликты
  python3 tools/build_labels.py --no-map   # не перезаписывать docs/LABEL-MAP.md

Воспроизводимость: дата фиксирована, Sorting детерминирован, выход стабилен.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATE = "20.11.2026"  # дата верификации; фиксирована ради воспроизводимости

# ---------------------------------------------------------------------------
# 1. Правила именования (docs/COMMENTING-STANDARD.md §2.2–2.4)
# ---------------------------------------------------------------------------

PREFIXES = ("INIT", "MAC", "ARA", "MNEM", "ERR", "TXT", "OUT", "CODE",
            "LOAD", "SYSCALL", "MEM")
SUFFIXES = ("LOOP", "EXIT", "RET", "NEXT", "CHECK", "DATA", "LINK", "GATE")
NAME_RE = re.compile(r"^(?:%s)_[A-Z0-9]+(?:_[A-Z0-9]+)*$"
                     % "|".join(PREFIXES))
FORBIDDEN_RE = re.compile(
    r"^(?:[ADG]\d{5}|[AD]\d{5}[+-]\d+|SUB\d{3,}|CNT\d|FLAG\d|MBEENTRY"
    r"|TAB\d|ZEROBUF|OUTBUF|ERRCELL\d|ERRPTR\d|ERRJMP|ERRVEC|ERRSUB"
    r"|RETM15|WORK\w*|LIMIT\w*|PTR\d+)")
MAXLEN = 20

CONF = "ПОДТВЕРЖДЕНО"
HYP = "ГИПОТЕЗА"

# Приоритет источника при выборе канонического имени (меньше = сильнее).
PRIO = {"CURATED": 0, "SEMANTIC": 1, "BE": 2, "LABELS-B": 3,
        "B2": 4, "VARIABLES": 5, "VALIDATED": 6, "EQU": 7}

GROUPS = ("Загрузчик и инициализация", "Макроредактор (0154/0554)",
          "Макромашина (0170/0570)", "АРАП (0152/0552)",
          "Таблицы ошибок и справок", "ASM ИТМ (0055–0060)",
          "Ядро исполняемого кода (0147/0547)",
          "Глобальная память и системные адреса")

# ---------------------------------------------------------------------------
# 2. Утилиты разбора
# ---------------------------------------------------------------------------


def lines_of(rel):
    p = ROOT / rel
    if not p.is_file():
        return []
    return p.read_text(encoding="utf-8").splitlines()


def find_line(rel, pattern):
    """Номер первой строки файла, совпадающей с regex (1-based), или 0."""
    rx = re.compile(pattern)
    for n, ln in enumerate(lines_of(rel), 1):
        if rx.search(ln):
            return n
    return 0


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def unq(s):
    return s.strip().strip("`").strip()


# Номер слова может содержать 8/9 (например, 0154:9), поэтому [0-9], не [0-7].
ZONE_WORD_RE = re.compile(r"\b([0-7]{4})\.([0-9]{1,4})\b")
ZONE_COLON_RE = re.compile(r"\b([0-7]{4}):([0-9]{1,4})\b")
LABEL_RE = re.compile(r"\b([ADG])([0-7]{5})\b")
OCT_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([0-7]{4,6})(?![A-Za-z0-9_])")


def extract_addr(text):
    """Вернуть (число, тип) для поля «было». Тип 2=A/G-метка кода, 1=данные.

    Форматы: A#####/D##### (zone-local), зона.слово, зона:слово, голое
    восьмеричное. Номер зоны сам по себе `(0147)` адресом не является.
    """
    t = unq(text)
    m = ZONE_WORD_RE.search(t)
    if m:
        return int(m.group(2), 8), 1
    m = ZONE_COLON_RE.search(t)
    if m:
        # 0154:9 — это dis/MBE-Z0154-L1.asm:9, т.е. НОМЕР СТРОКИ (дес.),
        # а не восьмеричный адрес слова (в номере может быть цифра 8/9).
        return int(m.group(2), 10), 2  # команда (пв/пб/ржа) — код
    m = LABEL_RE.search(t)
    if m:
        return int(m.group(2), 8), (2 if m.group(1) in ("A", "G") else 1)
    if "MBEENTRY" in t:
        return 0, 1
    # Голое восьмеричное число; `(NNNN)` — номер зоны, не адрес.
    t = re.sub(r"\([0-7]{4}\)", " ", t)
    for tok in OCT_TOKEN_RE.findall(t):
        if tok in ("2757", "2214", "2207", "4012"):
            continue  # прямые адреса возврата из пб — не ячейки таблицы
        return int(tok, 8), 1
    return None, None


def expand_evidence(ev):
    """Короткие ссылки таблиц → file:line, где это возможно."""
    s = unq(ev)

    def zone_ref(m):
        z, n = m.group(1), m.group(2)
        kind = "MBE2" if z.startswith("05") else "MBE"
        return "dis/%s-Z%s-L1.asm:%s" % (kind, z, n)

    s = re.sub(r"\b(\d{4}):(\d+)\b", zone_ref, s)
    s = re.sub(r"\bVAL:(\d+)\b", r"analysis/VARIABLES-VALIDATION.md:\1", s)
    s = re.sub(r"\bVAR\s*§", "analysis/VARIABLES.md §", s)
    s = re.sub(r"\bPROC:(\d+)\b", r"analysis/procedures.md:\1", s)
    s = re.sub(r"\bPR:(\d+)\b", r"analysis/procedures-RESOLVED.md:\1", s)
    s = re.sub(r"\bXREF:(\d+)\b", r"analysis/CROSSREF.md:\1", s)
    s = re.sub(r"\bTC:(\d+)\b", r"docs/TEXT-CONSTANTS.md:\1", s)
    s = re.sub(r"\bLB:(\d+)\b", r"docs/LABELS-BE.md:\1", s)
    s = re.sub(r"\bREG:§(\d+)M(\d+)", r"docs/REGISTERS.md §\1 M\2", s)
    s = re.sub(r"\bANNOT-MACRO\s*§", "docs/ANNOT-MACRO.md §", s)
    return s.replace("|", "/")


def compliant(name):
    return bool(NAME_RE.match(name)) and len(name) <= MAXLEN \
        and not FORBIDDEN_RE.match(name)


def status_of(text):
    return CONF if CONF in text else HYP


def classify(name, ev, source):
    s = (name + " " + ev + " " + source).lower()
    if "asm-code-recovery" in s or "z0055" in s or "z0056" in s \
            or "z0057" in s or "z0060" in s or "itm" in s \
            or name == "CODE_ITM_GATE":
        return GROUPS[5]
    if "z0154" in s or "z0554" in s or "mbe-z0154" in s \
            or "mbe2-z0554" in s or name.startswith("MAC_") \
            or "stamp_ed" in s:
        return GROUPS[1]
    if "z0170" in s or "z0570" in s or "stamp_mach" in s \
            or "stamp_mach_b2" in s:
        return GROUPS[2]
    if "z0152" in s or "z0552" in s or "ara" in s or "arch_err" in s \
            or "stamp_ara" in s:
        return GROUPS[3]
    if name == "SYSCALL_GATE":
        return GROUPS[7]
    if name.startswith("ERR_") or "error" in s or "z0144" in s \
            or "z0173" in s or "z0573" in s or "spr" in s \
            or "z0150" in s or "z0550" in s:
        return GROUPS[4]
    if name.startswith(("INIT_", "LOAD_", "MNEM_")) or "z0137" in s \
            or "z0140" in s or "z0141" in s or "z0142" in s \
            or "z0143" in s or "z0540" in s:
        return GROUPS[0]
    return GROUPS[6]


# ---------------------------------------------------------------------------
# 3. Набор записей
# ---------------------------------------------------------------------------

records = []  # каждый: dict(addr, name, role, ev, conf, src, group, typ,
              #         priority, legacy, rejected)


def add(addr, name, role, ev, conf, src, group, typ, priority,
        legacy=False, rejected=None):
    if addr is None:
        return
    records.append(dict(addr=int(addr), name=name, role=role, ev=ev,
                        conf=conf, src=src, group=group, typ=typ,
                        priority=priority, legacy=legacy,
                        rejected=rejected))


# --- 3.1 LABELS-B (75 пар) -------------------------------------------------
n_b = 0
for n, ln in enumerate(lines_of("docs/LABELS-B.md"), 1):
    c = cells(ln)
    if len(c) < 5:
        continue
    old, new = unq(c[0]), unq(c[1])
    addr, typ = extract_addr(old)
    if not re.match(r"^[A-Z][A-Z0-9_–-]+$", new):
        continue  # макрокоманды/заголовки — не роли
    n_b += 1
    reason = None
    if not compliant(new):
        reason = "неrole-имя или >20 символов"
    ev = expand_evidence(c[3]) + "; [docs/LABELS-B.md:%d]" % n
    if addr is None:
        # Регистры (Мn) — роль есть, адреса нет: в симтабу не идёт.
        records.append(dict(addr=None, name=new, role=c[2], ev=ev,
                            conf=status_of(c[4]),
                            src="docs/LABELS-B.md:%d" % n, group="",
                            typ=0, priority=PRIO["LABELS-B"],
                            legacy=False, rejected=reason))
        continue
    add(addr, new, c[2], ev, status_of(c[4]),
        "docs/LABELS-B.md:%d" % n, "", typ, PRIO["LABELS-B"],
        rejected=reason)

# --- 3.2 LABELS-B2 (43 пары) ----------------------------------------------
n_b2 = 0
for n, ln in enumerate(lines_of("docs/LABELS-B2.md"), 1):
    c = cells(ln)
    if len(c) < 5:
        continue
    old, new = unq(c[0]), unq(c[1])
    addr, typ = extract_addr(old)
    if addr is None or not re.match(r"^[A-Z][A-Z0-9_]+$", new):
        continue
    n_b2 += 1
    reason = None if compliant(new) else "неrole-имя или >20 символов"
    add(addr, new, c[2], expand_evidence(c[3]) + "; [docs/LABELS-B2.md:%d]" % n,
        status_of(c[4]), "docs/LABELS-B2.md:%d" % n, "", typ,
        PRIO["B2"], rejected=reason)

# --- 3.3 LABELS-BE (88 соответствий) --------------------------------------
n_be = 0
for n, ln in enumerate(lines_of("docs/LABELS-BE.md"), 1):
    c = cells(ln)
    if len(c) < 6:
        continue
    old, new = unq(c[1]), unq(c[2])
    addr, typ = extract_addr(old)
    if not re.match(r"^[A-Z][A-Z0-9_–-]+$", new):
        continue
    n_be += 1
    reason = None if compliant(new) else "неrole-имя (en-dash) или >20"
    ev = expand_evidence(c[4]) + "; [docs/LABELS-BE.md:%d]" % n
    if addr is None:
        records.append(dict(addr=None, name=new, role=c[3], ev=ev,
                            conf=status_of(c[5]),
                            src="docs/LABELS-BE.md:%d" % n, group="",
                            typ=0, priority=PRIO["BE"],
                            legacy=False, rejected=reason))
        continue
    add(addr, new, c[3], ev, status_of(c[5]),
        "docs/LABELS-BE.md:%d" % n, "", typ, PRIO["BE"],
        rejected=reason)

# --- 3.4 VARIABLES.md (76 имён, все типа 1) --------------------------------
n_var = 0
for n, ln in enumerate(lines_of("analysis/VARIABLES.md"), 1):
    c = cells(ln)
    if len(c) != 4 or not re.match(r"^\d+$", c[0]):
        continue
    addr_s, typ_s, name = unq(c[1]), unq(c[2]), unq(c[3])
    if not re.match(r"^[0-7]{4,6}$", addr_s) or not re.match(r"^[A-Z]", name):
        continue
    n_var += 1
    add(int(addr_s, 8), name, "унаследованное имя из sym/MBE.named.tab",
        "analysis/VARIABLES.md:%d (№ %s); STRONG по "
        "analysis/VARIABLES-VALIDATION.md" % (n, c[0]), HYP,
        "analysis/VARIABLES.md:%d" % n, "", 1, PRIO["VARIABLES"],
        legacy=True, rejected="авто-имя/шаблон (§2.4)" if not compliant(name) else None)

# --- 3.5 VARIABLES-VALIDATION.md (73 проверенных имени) --------------------
n_val = 0
val_state = "search"  # search → before → inside → done
for n, ln in enumerate(lines_of("analysis/VARIABLES-VALIDATION.md"), 1):
    if val_state == "search":
        if "Очищенная таблица" in ln:
            val_state = "before"
        continue
    if ln.startswith("```"):
        if val_state == "before":
            val_state = "inside"
        elif val_state == "inside":
            val_state = "done"
        continue
    if val_state != "inside":
        continue
    for addr_s, typ_s, name in re.findall(
            r"\b([0-7]{5,6})\s+(1)\s+([A-Z][A-Z0-9]*)", ln):
        n_val += 1
        add(int(addr_s, 8), name, "проверенная подстановка (STRONG)",
            "analysis/VARIABLES-VALIDATION.md:%d; STRONG" % n, HYP,
            "analysis/VARIABLES-VALIDATION.md:%d" % n, "", 1,
            PRIO["VALIDATED"], legacy=True,
            rejected="авто-имя/шаблон (§2.4)" if not compliant(name) else None)

# --- 3.6 Новые роли в SEMANTIC Z*.md --------------------------------------
# (адрес, имя, роль, файл, regex для строки-доказательства, тип)
SEMANTIC = (
    (0o275, "ERR_ADDR", "сообщение «НЕВЕРНЫЙ АДРЕС…» (зона 0144)",
     "docs/SEMANTIC/Z0144.md", r"ERR_ADDR", 1),
    (0o314, "ERR_BUF", "сообщение «ПРОГРАММА НЕ…» (зона 0144)",
     "docs/SEMANTIC/Z0144.md", r"ERR_BUF", 1),
    (0o543, "ERR_OVF", "«ПРПЛН ТАБЛ МЕТОК» — переполнение (зона 0144)",
     "docs/SEMANTIC/Z0144.md", r"ERR_OVF", 1),
    (0o1516, "FORMAT_ERR", "тексты ошибок формата (зона 0150)",
     "docs/SEMANTIC/Z0150.md", r"FORMAT_ERR", 1),
    (0o340, "ARCH_ERR", "тексты ошибок АРАП (зона 0151)",
     "docs/SEMANTIC/Z0151.md", r"ARCH_ERR", 1),
    (None, "OPCODE_IRET", "выпр '70707'(М17) — IRET, opcode (НЕ адрес)",
     "docs/SEMANTIC/ASM-CODE-RECOVERY.md", r"OPCODE_IRET", 0),
)
n_sem = 0
for addr, name, role, rel, rx, typ in SEMANTIC:
    ln = find_line(rel, rx)
    n_sem += 1
    if addr is None:
        # Опкод не имеет адреса: остаётся в отчёте, но не в симтабе.
        records.append(dict(addr=None, name=name, role=role,
                            ev="%s:%d (опкод, адреса нет)" % (rel, ln),
                            conf=CONF, src="%s:%d" % (rel, ln),
                            group=GROUPS[5], typ=0, priority=PRIO["SEMANTIC"],
                            legacy=False, rejected=None))
        continue
    add(addr, name, role, "%s:%d" % (rel, ln), HYP,
        "%s:%d" % (rel, ln), "", typ, PRIO["SEMANTIC"])

# --- 3.7 Ключевые глобальные адреса (curated, regex-проверка в docs) -------
# (addr, name, role, typ, group, confidence, [(file, regex), ...])
GLOBAL_RULES = (
    (0o70707, "CODE_ITM_GATE",
     "шлюз передачи управления ИТМ: выпр '70707'(М17)", 2, GROUPS[5],
     CONF + " (дизассембль; логический адрес)", (
         ("docs/SEMANTIC/Z0055.md", r"выпр '70707'"),
         ("docs/SEMANTIC/ASM-CODE-RECOVERY.md", r"70707.*IRET"),
     )),
    (0o2000, "MAC_EDITOR_LOAD",
     "загрузка зоны 0154 (макроредактор) в ОП; breakpoint →xta 6065", 2,
     GROUPS[7], CONF + " (1024/1024 слово, breakpoint)", (
         ("analysis/MEMORY-MAP.md", r"0154.*02000.*1024"),
         ("analysis/MEMORY-MAP.md", r"breakpoint.*02000"),
     )),
    (0o4000, "MEM_MONITOR",
     "MON*ITOR — монитор (адрес из *EXECUTE листинга)", 0, GROUPS[7],
     HYP + " (логический/памятный адрес)", (
         ("docs/ANCHORS.md", r"04000.*MON\*ITOR"),
         ("analysis/MEMORY-MAP.md", r"MON\*ITOR 04000"),
     )),
    (0o4007, "MEM_PLBEG",
     "PLBEG — выделение страницы/буфера (*EXECUTE)", 0, GROUPS[7],
     HYP + " (логический адрес; исходник не найден)", (
         ("analysis/MEMORY-MAP.md", r"PLBEG E 04007"),
         ("docs/PLAN-NEXT.md", r"PLBEG E 04007"),
     )),
    (0o1, "INIT_LOG_ENTRY",
     "вход МВЕ60 = 00001 (тестовая программа ДКС, не транслятор)", 0,
     GROUPS[7], CONF + " (logical)", (
         ("docs/ANCHORS.md", r"МВЕ60 = 00001"),
         ("docs/PLAN.md", r"ВХОД МВЕ60 = 01000"),
     )),
    (0o1000, "INIT_LOG_ENTRY",
     "память 01000₈ = логический вход 00001 + 0777₈ (алиас)", 0,
     GROUPS[7], CONF + " (logical)", (
         ("docs/ANCHORS.md", r"01000.*вход"),
         ("docs/PLAN.md", r"ВХОД МВЕ60 = 01000"),
     )),
    (0o70000, "SYSCALL_GATE",
     "системный вызов/ячейка приёма '70000' (0137.0, 9 зон)", 0,
     GROUPS[7], HYP + " (логический адрес ОП)", (
         ("analysis/VARIABLES.md", r"070000.*SYSCALL"),
         ("docs/PLAN.md", r"MON\*ITOR 04000"),
     )),
    (0o1315, "TXT_STAMP_B",
     "штамп «ИПМ МАКРО-БЕМШ ВЕР.06/78» (0147.1315)", 1, GROUPS[4],
     CONF + " (GOST 6 бит, besmtool search)", (
         ("docs/TEXT-CONSTANTS.md", r"0147\.1315.*ВЕР\.06"),
         ("docs/ANCHORS.md", r"0147\.1315.*ИПМ МАКРО"),
     )),
    (0o1164, "TXT_STAMP_ARA",
     "штамп «АРАП ВАР.04/78» (0152.1164)", 1, GROUPS[3],
     CONF + " (GOST 6 бит)", (
         ("docs/TEXT-CONSTANTS.md", r"0152\.1164.*АРАП"),
     )),
    (0o751, "TXT_STAMP_ED",
     "штамп «МАКРОРЕДАКТОР ОТ 20.06.78» (0154.0751)", 1, GROUPS[1],
     CONF + " (GOST 6 бит)", (
         ("docs/TEXT-CONSTANTS.md", r"0154\.0751.*МАКРОРЕДАКТОР"),
     )),
    (0o216, "TXT_STAMP_MACH",
     "штамп «МАКРОМАШИНА ОТ 1.11.78» (0170.0216)", 1, GROUPS[2],
     CONF + " (GOST 6 бит)", (
         ("docs/TEXT-CONSTANTS.md", r"0170\.0216.*МАКРОМАШИНА"),
     )),
    (0o1050, "ERR_MSG",
     "сообщение «НЕВЕРНЫЙ 1-Й КОМПИЛИР» (0154.1050)", 1, GROUPS[4],
     CONF + " (GOST 6 бит)", (
         ("docs/TEXT-CONSTANTS.md", r"0154\.1050.*НЕВЕРНЫЙ"),
     )),
    (0o1450, "ERR_CNT",
     "«-КОЛИЧ ЯЧ ГС» — счётчик ГС (0154.1450)", 1, GROUPS[4],
     CONF + " (GOST 6 бит)", (
         ("docs/TEXT-CONSTANTS.md", r"0154\.1450.*КОЛИЧ"),
     )),
    (0o655, "TXT_SPR_B1",
     "«ОШ.СПР.НА БЕМШ1» — справка (0173.0655)", 1, GROUPS[4],
     CONF + " (GOST 6 бит)", (
         ("docs/TEXT-CONSTANTS.md", r"0173\.0655.*ОШ\.СПР"),
     )),
    (0o1315, "TXT_STAMP_B2",
     "штамп «ИПМ МАКРО-БЕМШ ВАР.12/77» (0547.1315) — B2", 1, GROUPS[4],
     CONF + " (GOST 6 бит; конфликт с B)", (
         ("docs/TEXT-CONSTANTS.md", r"0547\.1315.*ВАР\.12"),
     )),
    (0o1154, "TXT_STAMP_ARA_B2",
     "штамп «АРАП ВАР.10/75» (0552.1154) — B2", 1, GROUPS[3],
     CONF + " (GOST 6 бит)", (
         ("docs/TEXT-CONSTANTS.md", r"0552\.1154.*АРАП"),
     )),
    (0o751, "TXT_STAMP_ED_B2",
     "штамп «МАКРОРЕДАКТОР ОТ 10.04.76» (0554.0751) — B2", 1, GROUPS[1],
     CONF + " (GOST 6 бит; конфликт с B)", (
         ("docs/TEXT-CONSTANTS.md", r"0554\.0751.*10\.04\.76"),
     )),
    (0o274, "TXT_STAMP_MACH_B2",
     "штамп «МАКРОМАШИНА ОТ 15.12.76» (0570.0274) — B2", 1, GROUPS[2],
     CONF + " (GOST 6 бит)", (
         ("docs/TEXT-CONSTANTS.md", r"0570\.0274.*15\.12\.76"),
     )),
)
missing_evidence = []
n_cur = 0
for addr, name, role, typ, group, conf, checks in GLOBAL_RULES:
    ev_parts = []
    for rel, rx in checks:
        ln = find_line(rel, rx)
        if not ln:
            missing_evidence.append("%s :: %s" % (rel, rx))
        tag = "%s:%d" % (rel, ln) if ln else "%s:? [НЕ НАЙДЕНО]" % rel
        if tag not in ev_parts:
            ev_parts.append(tag)
    n_cur += 1
    add(addr, name, role, "; ".join(ev_parts), conf,
        "; ".join(p[0] for p in checks), group, typ, PRIO["CURATED"])

# --- 3.8 EQU-константы из LABELS-BE §2 (тип 0, в отчёт) --------------------
n_equ = 0
inside_equ = False
for n, ln in enumerate(lines_of("docs/LABELS-BE.md"), 1):
    if ln.startswith("## 2."):
        inside_equ = True
        continue
    if inside_equ and ln.startswith("## "):
        inside_equ = False
    if not inside_equ:
        continue
    c = cells(ln)
    if len(c) != 3 or ",EQU," not in c[1]:
        continue
    name = unq(c[0])
    val = re.search(r",EQU,([0-7]+)", c[1])
    if not name or not val:
        continue
    n_equ += 1
    records.append(dict(addr=int(val.group(1), 8), name=name,
                        role="EQU-константа: " + c[2],
                        ev="docs/LABELS-BE.md:%d (,EQU,)" % n,
                        conf=HYP, src="docs/LABELS-BE.md:%d" % n,
                        group=GROUPS[7], typ=0, priority=PRIO["EQU"],
                        legacy=False, rejected=None))

# ---------------------------------------------------------------------------
# 4. Дедупликация, конфликты, выбор канонического имени
# ---------------------------------------------------------------------------

by_addr = defaultdict(list)
for r in records:
    if r["addr"] is not None:
        by_addr[r["addr"]].append(r)

rejected = [r for r in records if r["rejected"]]
legacy_only = [r for r in records if r["rejected"] and r["legacy"]]


def rank(r):
    """Каноническое имя: role-совместимое, сильный источник, подтверждённое."""
    return (0 if compliant(r["name"]) else 1, r["priority"],
            0 if CONF in r["conf"] else 1, r["name"])


chosen = {}
conflicts = {}
for addr, rs in by_addr.items():
    names = sorted({r["name"] for r in rs})
    if len(names) > 1:
        conflicts[addr] = rs
    ok = [r for r in rs if compliant(r["name"])]
    if ok:
        chosen[addr] = sorted(ok, key=rank)[0]

top = sorted(chosen.items())
top10 = top[:10]


# ---------------------------------------------------------------------------
# 5. Выход: sym/GLOBAL.tab
# ---------------------------------------------------------------------------


def write_tab():
    # ВАЖНО: disbesm6.readsymtab() (disbesm6.c:862-881) читает строго
    # fscanf("%o %d %63s") и НЕ пропускает строки-комментарии: '#' в
    # симтабе вызвало бы "dis: error reading symbol table". Поэтому файл
    # состоит только из данных; provenance описана в LABEL-MAP.md §0.
    out = []
    for addr, r in top:
        out.append("%05o %d %63s" % (addr, r["typ"], r["name"]))
    path = ROOT / "sym/GLOBAL.tab"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 6. Выход: docs/LABEL-MAP.md
# ---------------------------------------------------------------------------


def short(s, limit=110):
    s = str(s).replace("|", "/").replace("\n", " ")
    return s if len(s) <= limit else s[:limit - 1] + "…"


def md_row(addr, r):
    a = ("%05o" % addr) if addr is not None else "—"
    star = "" if compliant(r["name"]) else " ⚠"
    return "| `%s` | `%s`%s | %s | %s | %s |" % (
        a, r["name"], star, short(r["role"]), short(r["ev"], 130),
        short(r["conf"], 60))


def write_map():
    o = []
    ap = o.append
    ap("# GLOBAL LABEL DICTIONARY — глобальный словарь ролевых имён")
    ap("")
    ap("Дата: %s. Построено `tools/build_labels.py` "
       "(regex-извлечение из документов; воспроизводимо)." % DATE)
    ap("")
    ap("> **Статус: аннотация, а не ground truth.** Ни один адрес не "
       "подтверждён исходником транслятора — его на диске нет. "
       "`ПОДТВЕРЖДЕНО` означает штамп/пару вызов→возврат/breakpoint, "
       "`ГИПОТЕЗА` — шаблон использования. См. `COMMENTING-STANDARD.md` "
       "§2.4, `AGENTS.md` §0.1–2.")
    ap("")
    ap("## 0. Как пользоваться таблицей")
    ap("")
    ap("```bash")
    ap("cd /tmp/.private/azizz/re-bemsh")
    ap("disbesm6 -a0 -e0 -nsym/GLOBAL.tab \\")
    ap("  gold/MBE-Z0147-L1.bin > /tmp/.private/azizz/global-0147.asm")
    ap("```")
    ap("")
    ap("`sym/GLOBAL.tab` — формат `%o %d %63s` (адрес печатается `%05o`, "
       "читается как `%o`); тип `1`=W_DATA (ячейка/таблица), `2`=W_CODE "
       "(точка входа), `0`=эквивалентность/EQU. Адреса уникальны и "
       "отсортированы; имя ≤20 символов, латиница, `PREFIX_ROLE` "
       "(`COMMENTING-STANDARD.md` §2.2–2.4).")
    ap("")
    ap("Оговорки:")
    ap("1. Имена `A#####`/`D#####` и штампы `зона.слово` — **zone-local**: "
       "число — 0-based смещение внутри зоны при `-a0`; в другой зоне то же "
       "число означает другую ячейку. См. `VARIABLES.md` §6.6.")
    ap("2. `70707`, `04000`, `04007`, `00001`, `01000` — **логические** "
       "адреса листинга/ОП, физический якорь тома для них не доказан "
       "(`ANCHORS.md` §1, §3; `MEMORY-MAP.md` §3). Не подставлять их как "
       "физические без доказательства (`AGENTS.md` §3).")
    ap("3. `00001` и `01000` — один и тот же вход в двух системах "
       "координат (`ANCHORS.md`:66); это алиас, не конфликт.")
    ap("4. Имена `SUB*`, `CNT*`, `FLAG*`, `MBEENTRY`, `TAB*` и т.п. из "
       "`VARIABLES.md` — авто-имена/шаблоны; они **не** вошли в "
       "`GLOBAL.tab` как роли, но сохранены в §10 как исторические.")

    # Таблицы по подсистемам
    for gi, group in enumerate(GROUPS, 1):
        ap("")
        ap("## %d. %s" % (gi, group))
        ap("")
        ap("| адрес | роль-имя | роль | evidence (file:line) | confidence |")
        ap("|---|---|---|---|---|")
        rows = []
        for addr, r in top:
            g = r["group"] or classify(r["name"], r["ev"], r["src"])
            if g == group:
                rows.append((addr, r))
        for addr, r in rows:
            ap(md_row(addr, r))
        if not rows:
            ap("| — | — | — | — | — |")

    ap("")
    ap("## 9. Конфликты (одно число → разные имена)")
    ap("")
    ap("Всего конфликтных адресов: **%d**." % len(conflicts))
    ap("")
    ap("| адрес | имя A → источник | имя B → источник | verdict |")
    ap("|---|---|---|---|")
    for addr in sorted(conflicts):
        rs = conflicts[addr]
        byname = defaultdict(list)
        for r in rs:
            byname[r["name"]].append(r)
        items = sorted(byname.items())
        a = items[0][0] + " → " + items[0][1][0]["src"]
        b = " ; ".join("%s → %s" % (k, v[0]["src"]) for k, v in items[1:])
        can = chosen.get(addr)
        if can:
            verdict = "каноническое: `%s` (%s)" % (can["name"], can["src"])
        else:
            verdict = "только авто-имена — в GLOBAL.tab не включено"
        ap("| `%05o` | %s | %s | %s |" % (addr, short(a, 70),
                                          short(b, 70), short(verdict, 70)))

    ap("")
    ap("### 9.1 Отвергнутые не-role имена")
    ap("")
    ap("Имена, не прошедшие фильтр `PREFIX_ROLE`/≤20/запрет авто-имён "
       "(`%d` записей): %s." % (
           len(rejected),
           ", ".join("`%s`" % r["name"] for r in rejected[:40])
           + (" …" if len(rejected) > 40 else "")))

    ap("")
    ap("## 10. Унаследованные имена `VARIABLES.md` (%d записей)" % n_val)
    ap("")
    ap("Все 73 имени из `sym/MBE.named.validated.tab` собраны здесь для "
       "полноты. Это шаблонные имена; как роли они запрещены "
       "§2.4 и в `GLOBAL.tab` не используются (если для адреса нет "
       "role-имя из §1–8). Ниже — весь список.")
    ap("")
    ap("| адрес | унаследованное имя | evidence | примечание |")
    ap("|---|---|---|---|")
    seen_legacy = set()
    for r in sorted((x for x in records if x["legacy"] and x["addr"] is not None),
                    key=lambda x: (x["addr"], x["name"])):
        key = (r["addr"], r["name"])
        if key in seen_legacy:
            continue
        seen_legacy.add(key)
        alt = chosen.get(r["addr"])
        note = ("есть role-имя: `%s`" % alt["name"]) if alt else \
               "авто-имя, роли нет"
        ap("| `%05o` | `%s` | %s | %s |" % (
            r["addr"], r["name"], short(r["ev"], 95), note))

    ap("")
    ap("## 11. Счётчики и воспроизводимость")
    ap("")
    ap("| Источник | собрано |")
    ap("|---|---|")
    for label, val in (("LABELS-B.md", n_b), ("LABELS-B2.md", n_b2),
                       ("LABELS-BE.md", n_be),
                       ("VARIABLES.md (всего)", n_var),
                       ("VARIABLES-VALIDATION.md (проверено)", n_val),
                       ("SEMANTIC Z*.md (новые роли)", n_sem),
                       ("глобальные адреса (curated)", n_cur),
                       ("EQU-константы LABELS-BE §2", n_equ)):
        ap("| `%s` | %d |" % (label, val))
    ap("")
    ap("• Уникальных адресов: **%d**. role-имён в `GLOBAL.tab`: **%d**. "
       "Конфликтов: **%d**. Отвергнутых имён: **%d**." % (
           len(by_addr), len(top), len(conflicts), len(rejected)))
    ap("• Провалы поиска evidence: %d%s." % (
           len(missing_evidence),
           (" — " + "; ".join(missing_evidence)) if missing_evidence else ""))
    ap("")
    ap("```bash")
    ap("python3 tools/build_labels.py --check")
    ap("```")
    ap("")
    ap("Перезапуск генератора даёт байт-в-байт тот же `GLOBAL.tab` и этот "
       "отчёт. Эталонные образы, `.be`, `dis/`, `analysis/` и "
       "`docs/SEMANTIC/*` не изменяются.")

    path = ROOT / "docs/LABEL-MAP.md"
    path.write_text("\n".join(o) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 7. CLI / отчёт
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="только проверить счётчики/конфликты, не писать файлы")
    ap.add_argument("--no-map", action="store_true",
                    help="не перезаписывать docs/LABEL-MAP.md")
    args = ap.parse_args()

    print("== GLOBAL LABEL DICTIONARY ==")
    for label, val, need in (
            ("LABELS-B", n_b, 75), ("LABELS-B2", n_b2, 43),
            ("LABELS-BE", n_be, 88), ("VARIABLES", n_var, 76),
            ("VALIDATED", n_val, 73), ("SEMANTIC", n_sem, 5),
            ("CURATED", n_cur, len(GLOBAL_RULES)), ("EQU", n_equ, 1)):
        flag = "OK" if val >= need else "LOW!"
        print("  %-12s %3d / >=%d  [%s]" % (label, val, need, flag))
    print("  unique addresses : %d" % len(by_addr))
    print("  role names in tab: %d" % len(top))
    print("  conflicts        : %d" % len(conflicts))
    print("  rejected names   : %d" % len(rejected))
    print("  missing evidence : %d" % len(missing_evidence))
    print("  top-10:")
    for addr, r in top10:
        print("    %05o %-20s %s" % (addr, r["name"], r["src"]))

    if missing_evidence:
        print("ERROR: evidence not found:", file=sys.stderr)
        for m in missing_evidence:
            print("  " + m, file=sys.stderr)
        return 2
    if n_b < 75 or n_b2 < 43 or n_be < 88 or n_val < 73:
        print("ERROR: source counts below required thresholds",
              file=sys.stderr)
        return 1
    if args.check:
        print("--check: OK (файлы не изменены)")
        return 0

    tab = write_tab()
    print("written: %s (%d entries)" % (tab.relative_to(ROOT), len(top)))
    if not args.no_map:
        mp = write_map()
        print("written: %s" % mp.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
