#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""global_xref.py — ГЛОБАЛЬНЫЙ кросс-референс листингов БЭСМ-6.

Сканирует ВСЕ .asm в dis/ и dis-forced/, извлекает каждый числовой/
восьмеричный операнд (литерал 'NNNN', голое число, A#####/D#####,
(Мn), ±N fuzz, сда 64-N) и строит «цель → список ссылок».

Источники ролей (только чтение):
  docs/LABELS-B.md, docs/LABELS-B2.md, docs/LABELS-BE.md  — role-таблицы;
  docs/SEMANTIC/Z*.md                                      — роли/штампы;
  docs/TEXT-CONSTANTS.md                                   — декод текста;
  analysis/procedures*.md                                  — имена процедур;
  analysis/VARIABLES.md, VARIABLES-VALIDATION.md           — символьные имена
  docs/COMMENTING-STANDARD.md                              — префиксы PREFIX_ROLE.

Ни один входной файл не модифицируется. Выход: TSV + Markdown-отчёт.

CLI:
  python3 tools/global_xref.py [--out analysis/global_xref.tsv]
                               [--md analysis/GLOBAL-XREF.md]
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# 1. Разбор строки disbesm6 (заимствовано у tools/xref.py, XREF-METHODOLOGY §3)
# ---------------------------------------------------------------------------

HEAD_RE = re.compile(r'^([ 0-7]{5})([: ])([0-7 ]*)\s*$')
ZONE_RE = re.compile(r'Z([0-7]{4})')
LABEL_DEF_RE = re.compile(r'^([AD])([0-7]{5})$')
LABEL_OP_RE = re.compile(r'^([AD])([0-7]{5})([+-][0-9]+)?$')
MOD_RE = re.compile(r'\(М([0-9]{1,2})\)')
QUOT_RE = re.compile(r"'([^']*)'")
BARE_RE = re.compile(r'^-?[0-9]+$')
BASEDELTA_RE = re.compile(r'^([0-9]+)-([0-9]+)$')

# Данные и псевдостроки — числовой операнд НЕ адрес (XREF-METHODOLOGY §3).
DATA_MNEM = {'конд', 'пам', 'nop', 'ноп', 'экв', 'конк',
             'старт', 'финиш'}
# IMMEX/REG/база-дельта — константа, не адрес (DISBESM6-GUIDE §5).
IMM_MNEM = {'рег', 'сда', 'счмр'}
# ADDREX — цель помечается W_DATA, но это адрес (DISBESM6-GUIDE §5).
ADDREX_MNEM = {'э64', 'э67', 'э70'}
EXTRACT_RE = re.compile(r'^э[0-7][0-7]$')

# Граница зоны: 1024 слова = 02000₈. Всё >= 02000₈ — память/глобальный адрес.
ZONE_WORDS = 0o2000

# Шахматный fill (docs/SEMANTIC/Z0567.md §3, Z0167.md): '25252'(М12)
# и '72525'(М5)/вчп. Это НЕ адреса, а повторяющийся тестовый узор.
CHECKERBOARD = {'25252', '72525', '2525252', '5252525',
                '2565352725653527', '5252525252525252',
                '2525252525252525'}


def norm_oct(text):
    """Нормализовать восьмеричный литерал: '00100'/'100' -> '100'."""
    try:
        return '%o' % int(text, 8)
    except ValueError:
        return text


def file_zone(path):
    m = ZONE_RE.search(os.path.basename(path))
    return m.group(1) if m else ''


class Ref(object):
    __slots__ = ('src', 'zone', 'addr', 'addr_text', 'mnem', 'operand',
                 'line', 'key', 'kind', 'raw', 'value', 'as_data', 'mod')

    def __init__(self, src, zone, addr, addr_text, mnem, operand, line,
                 key, kind, raw, value, as_data, mod):
        self.src = src
        self.zone = zone
        self.addr = addr
        self.addr_text = addr_text
        self.mnem = mnem
        self.operand = operand
        self.line = line
        self.key = key
        self.kind = kind          # LBL / OCT / NUM / EXPR / MOD
        self.raw = raw
        self.value = value
        self.as_data = as_data
        self.mod = mod


def parse_line_operand(mnem, operand, as_data):
    """Извлечь ВСЕ числовые токены операнда.

    Возвращает список (kind, key, raw, value).  (Мn) возвращается отдельно
    как MOD; числовой адрес — как LBL/OCT/NUM/EXPR.  Текстовые константы
    ('F00900') и данные помечаются TXT и отфильтровываются позже.
    """
    out = []
    low = mnem.lower()
    mods = MOD_RE.findall(operand)
    for mn in mods:
        out.append(('MOD', 'MOD:M%s' % int(mn, 10), '(М%s)' % mn,
                    int(mn, 10)))
    raw = MOD_RE.sub('', operand)
    if ',' in raw:                       # 'PRINT8, М15' -> PRINT8
        raw = raw.split(',', 1)[0]
    raw = raw.strip()
    if not raw:
        return out
    if low in DATA_MNEM:                 # конд/пам/nop — данные, не адрес
        out.append(('DATA', '', raw, None))
        return out

    lm = LABEL_OP_RE.match(raw)
    if lm:
        label = lm.group(1) + lm.group(2)
        if lm.group(3):                  # fuzz=64: A00003+34 — псевдо-ссылка
            out.append(('FUZZ', 'FUZZ:' + label + lm.group(3), raw, None))
        else:
            out.append(('LBL', label, raw, int(lm.group(2), 8)))
        return out

    if raw.startswith("'") and raw.endswith("'"):
        inner = raw[1:-1]
        if re.fullmatch(r'[0-7]+', inner):
            out.append(('OCT', 'OCT:' + norm_oct(inner), raw,
                        int(inner, 8)))
        else:
            # п'F00900'/п'000400' — GOST-текст/число, не адрес
            out.append(('TXT', 'TXT:' + inner, raw, None))
        return out

    bd = BASEDELTA_RE.match(raw)
    if bd:
        out.append(('EXPR', 'EXPR:' + raw, raw, None))
        return out

    if BARE_RE.match(raw):
        try:
            val = int(raw, 10)
        except ValueError:
            val = None
        # disbesm6 печатает адреса как 'NNNN'; голое число — десятичный
        # immediate/смещение (praddr: < 0100 => decimal). Всегда IMM.
        kind = 'IMM'
        out.append((kind, 'IMM:' + raw, raw, val))
        return out

    # `'...'` без кавычек-восьмёрки, START/PRINT8/символы — не число.
    out.append(('SYM', '', raw, None))
    return out


def scan_asm_files(dirs):
    """Пробежаться по всем .asm; вернуть (refs, definitions, stats)."""
    refs = []
    definitions = []                     # (zone, 'A'/'D', addr, src, line)
    stats = Counter()
    files = []
    for d in dirs:
        if os.path.isdir(d):
            files += [os.path.join(d, f) for f in sorted(os.listdir(d))
                      if f.endswith('.asm')]
    files.sort()
    for path in files:
        zone = file_zone(path)
        src = os.path.basename(path)
        cur = None
        cur_text = ''
        pending_data = False
        with open(path, 'r', encoding='utf-8-sig', errors='replace') as fh:
            for lineno, rawline in enumerate(fh, 1):
                line = rawline.rstrip('\n')
                if line.startswith('*'):
                    if 'used as data' in line:
                        pending_data = True
                    continue
                parts = line.split('\t')
                if len(parts) < 4:
                    continue
                m = HEAD_RE.match(parts[0])
                if not m:
                    continue
                addr_field, mark, _ = m.groups()
                has_addr = bool(addr_field.strip())
                if has_addr:
                    try:
                        cur = int(addr_field.strip(), 8)
                    except ValueError:
                        cur = None
                    cur_text = addr_field.strip()
                label = parts[1].strip()
                mnem = parts[2].strip()
                operand = parts[3].strip()
                if not (label or mnem or operand):
                    continue
                as_data = pending_data and has_addr
                if has_addr:
                    pending_data = False

                ld = LABEL_DEF_RE.match(label)
                if ld and has_addr:
                    definitions.append((zone, ld.group(1),
                                        int(ld.group(2), 8), src, lineno))

                for kind, key, rraw, value in parse_line_operand(mnem,
                                                                  operand,
                                                                  as_data):
                    if kind in ('', 'DATA', 'SYM'):
                        stats['skip_' + (kind or 'empty')] += 1
                        continue
                    refs.append(Ref(src, zone, cur, cur_text, mnem, operand,
                                    lineno, key, kind, rraw, value,
                                    as_data, ','.join(MOD_RE.findall(operand))))
    return refs, definitions, stats, files


# ---------------------------------------------------------------------------
# 2. Источники ролей (PREFIX_ROLE), COMMENTING-STANDARD §2.2
# ---------------------------------------------------------------------------

ROLE_RE = re.compile(r'^[A-Z][A-Z0-9_]{2,}$')
STATUS_CONF = 'ПОДТВЕРЖДЕНО'
STATUS_HYP = 'ГИПОТЕЗА'


def _read(path):
    if not os.path.isfile(path):
        return []
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read().splitlines()


def load_roles(root):
    """Загрузить все доступные role-таблицы.

    Возвращает dict:
      'pair'   : (zone, 'A#####'/'D#####') -> (role, status, evidence)
      'any'    : 'A#####'/'D#####'         -> (role, status, evidence)
      'mod'    : 'M15'                     -> (role, status)
      'mem'    : octal-value (int)         -> (name, status)
      'text'   : (zone, word)              -> (phrase, hint)
      'proc'   : (zone, start)             -> (role-class, evidence)
    """
    d = {'pair': {}, 'any': {}, 'mod': {}, 'mem': {}, 'text': {}, 'proc': {}}

    # --- role-таблицы LABELS-B/B2/BE ---------------------------------------
    for fname in ('docs/LABELS-B.md', 'docs/LABELS-B2.md',
                  'docs/LABELS-BE.md'):
        for line in _read(os.path.join(root, fname)):
            if not line.lstrip().startswith('|'):
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            cleaned = [c.strip('`* ') for c in cells]
            status = STATUS_HYP
            for c in cells:
                if STATUS_CONF in c:
                    status = STATUS_CONF
            # ищем ячейку A#####/D##### и СЛЕДУЮЩУЮ role-ячейку
            for i, c in enumerate(cleaned[:-1]):
                m = re.fullmatch(r'([AD])([0-7]{5})', c)
                if not m:
                    continue
                nxt = cleaned[i + 1]
                # BE-таблица:Was | Became | Role | ... ;'B2': Was | Became | Role
                if ROLE_RE.match(nxt):
                    key = m.group(0)
                    # зону можно вывести из файла .be в первой ячейке
                    z = ''
                    zm = ZONE_RE.search(cells[0])
                    if zm:
                        z = zm.group(1)
                    val = (nxt, status, fname)
                    if z:
                        d['pair'][(z, key)] = val
                    d['any'].setdefault(key, val)
                    break
            # регистры (Мn) -> роль; ячейка может быть `(М5) / (М12)`
            for i, c in enumerate(cleaned[:-1]):
                mms = re.findall(r'\(М([0-9]{1,2})\)', c)
                if mms:
                    nxt = cleaned[i + 1]
                    if ROLE_RE.match(nxt):
                        for mn in mms:
                            d['mod']['M%s' % int(mn, 10)] = (nxt, status)
                    break

    # --- символьные имена памяти (VARIABLES / VALIDATION) ------------------
    name_re = re.compile(r'\b([0-7]{4,6})\s+[12]\s+([A-Z][A-Z0-9_]{2,})\b')
    for fname in ('analysis/VARIABLES.md',
                  'analysis/VARIABLES-VALIDATION.md'):
        for line in _read(os.path.join(root, fname)):
            for m in name_re.finditer(line):
                val = int(m.group(1), 8)
                d['mem'].setdefault(val, (m.group(2), STATUS_HYP))

    # глобальные константы с доказанной ролью (SEMANTIC/ASM-CODE-RECOVERY и др.)
    known_mem = {
        0o70707: ('GATE', STATUS_CONF),     # шлюз ИТМ [Z0060.md:125]
        0o70000: ('SYSCALL', STATUS_HYP),   # резидентный вход [Z0151.md:124]
        0o14000: ('TAB5', STATUS_HYP),      # база TAB5 [Z0147.md:175]
        0o12000: ('TAB4', STATUS_HYP),
        0o10000: ('TAB3', STATUS_HYP),
        0o06000: ('TAB2', STATUS_HYP),
        0o04000: ('TAB1', STATUS_HYP),
        0o02000: ('PAGE', STATUS_HYP),      # MEMORY-MAP.md §3
        0o066666: ('RET_M15', STATUS_HYP),
        0o076027: ('ERR_EXIT', STATUS_HYP),
    }
    for val, (role, st) in known_mem.items():
        d['mem'][val] = (role, st)

    # --- роли из SEMANTIC/Z*.md --------------------------------------------
    sem_re = re.compile(r'\b([AD][0-7]{5})\s+([A-Z][A-Z0-9_]{2,})\b')
    rev_re = re.compile(r'\b([A-Z][A-Z0-9_]{2,})\s+([AD][0-7]{5})\b')
    for fname in os.listdir(os.path.join(root, 'docs', 'SEMANTIC')):
        zm = re.fullmatch(r'Z([0-7]{4})\.md', fname)
        if not zm:
            continue
        zone = zm.group(1)
        text = '\n'.join(_read(os.path.join(root, 'docs', 'SEMANTIC', fname)))
        conf = STATUS_CONF if STATUS_CONF in text else STATUS_HYP
        for m in sem_re.finditer(text):
            d['pair'].setdefault((zone, m.group(1)),
                                 (m.group(2), conf, 'SEMANTIC/' + fname))
            d['any'].setdefault(m.group(1),
                                (m.group(2), conf, 'SEMANTIC/' + fname))
        for m in rev_re.finditer(text):
            d['pair'].setdefault((zone, m.group(2)),
                                 (m.group(1), conf, 'SEMANTIC/' + fname))
            d['any'].setdefault(m.group(2),
                                (m.group(1), conf, 'SEMANTIC/' + fname))

    # --- декодированный текст (TEXT-CONSTANTS.md §4-6) ---------------------
    tc_re = re.compile(r'^([0-7]{4})\.([0-7]{4})\s+[0-9a-f]{6,16}\s+(.+)$')
    for line in _read(os.path.join(root, 'docs/TEXT-CONSTANTS.md')):
        m = tc_re.match(line)
        if not m:
            continue
        zone, word = m.group(1), m.group(2)
        tail = m.group(3).strip()
        phrase = tail.split()[0] if tail else ''
        # Только кириллица — иначе это число ('F00900' из TC §2), не текст.
        if not any('\u0400' <= c <= '\u04ff' for c in phrase):
            continue
        hint = 'TXT_MSG'
        if any(w in tail for w in ('штамп', 'red.', 'B2', 'B ')):
            hint = 'TXT_STAMP'
        elif any(w in tail for w in ('ошибк', 'спр', 'ерр')):
            hint = 'TXT_ERR'
        d['text'][(zone, int(word, 8))] = (phrase, hint)

    # --- имена процедур (procedures.md / procedures-RESOLVED.md) -----------
    proc_re = re.compile(r'^\s*([0-7]{4})\s+([0-7]{3,4})-([0-7]{3,4})')
    for fname in ('analysis/procedures.md',
                  'analysis/procedures-RESOLVED.md'):
        for line in _read(os.path.join(root, fname)):
            m = proc_re.match(line)
            if not m:
                continue
            tail = line[m.end():]
            if 'вывод' in tail:
                role = 'OUT_PRINT'
            elif 'диспетчер' in tail:
                role = 'CODE_DISPATCH'
            elif 'таблица' in tail:
                role = 'ERR_TAB'
            else:
                role = 'CODE_UTIL'
            d['proc'][(m.group(1), int(m.group(2), 8))] = (
                role, 'procedures:' + fname)
    return d


# Permission to use bare role names as labels: normalize to PREFIX_ROLE when
# the source gives a bare ordinal (CNT0, FLAG2, ...).
BARE_PREFIX = {
    'CNT': 'CODE_CNT', 'FLAG': 'MAC_FLAG', 'ERRCELL': 'ERR_CELL',
    'ERRPTR': 'ERR_PTR', 'ERRJMP': 'ERR_JMP', 'ERRVEC': 'ERR_VEC',
    'ERRTBL': 'ERR_TAB', 'ERRSUB': 'ERR_SUB', 'SUB': 'CODE_SUB',
    'WORK': 'CODE_WORK', 'LIMIT': 'CODE_LIMIT',
    'OUTBUF': 'OUT_BUF', 'RETM15': 'CODE_RET', 'MODEL': 'CODE_CHECK',
}
# Уже осмысленные имена — не трогаем (особенно для MEM_*).
APPROVED = {'GATE', 'SYSCALL', 'TAB1', 'TAB2', 'TAB3', 'TAB4', 'TAB5',
            'PAGE', 'RET_M15', 'ERR_EXIT', 'OUTBUF', 'ERRCELL1',
            'ERRCELL2', 'ERRCELL3', 'ERRCELL4', 'ERRCELL5', 'ERRJMP',
            'ERRVEC', 'ERRTBL1', 'ERRSUB', 'SYSCALL'}

# Первое слово GOST-строки -> ASCII-код для PREFIX_ROLE (TEXT-CONSTANTS §4-6).
TEXT_CODE = {
    'ИПМ': 'STAMP', 'АРАП': 'ARAP', 'МАКРОР': 'STAMP_ED',
    'МАКРОМ': 'STAMP_MACH', 'ОШ.СПР': 'ERR_TAB', 'ОШИБКИ': 'ERR_MSG',
    'Г-БЕМШ': 'STAMP_B1', 'БЕМШ2': 'STAMP_B2', 'ЗАПИСЬ': 'WRITE',
    'НЕТ': 'NO_ENTRY', 'НЕВЕ': 'BAD', 'МЕТКА': 'LABEL',
}


def normalize_role(name):
    if name in APPROVED:
        return name
    if name.startswith(tuple('INIT MAC ARA MNEM ERR TXT OUT CODE LOAD '
                             .split())):
        return name
    for stem, prefix in BARE_PREFIX.items():
        if name.startswith(stem) and len(name) > len(stem):
            return prefix + '_' + name[len(stem):]
    return 'CODE_' + name


def suggest(target, zones, kind, value, roles):
    """Вернуть (label, status, evidence) для цели."""
    # (Мn) — роль регистра из LABELS-B §3
    if kind == 'MOD':
        role = roles['mod'].get(target[4:])
        if role:
            return role[0], role[1], 'LABELS-B §3'
        return target[4:] + '_REG', STATUS_HYP, '(Мn)'

    # Память/глобаль (>= 02000₈) — symtab/штампы
    if value is not None and value >= ZONE_WORDS:
        mem = roles['mem'].get(value)
        if mem:
            return ('MEM_%o_%s' % (value, normalize_role(mem[0])),
                    mem[1], 'VARIABLES/SEMANTIC')
        return 'MEM_%o_UNKNOWN' % value, STATUS_HYP, 'external'

    # A#####/D##### и локальные литералы
    labels = []
    if target[:1] in ('A', 'D'):
        labels.append(target)
    if value is not None:
        labels.append('A%05o' % value)
        labels.append('D%05o' % value)
    for z in zones or []:
        for lab in labels:
            r = roles['pair'].get((z, lab))
            if r:
                return normalize_role(r[0]), r[1], r[2]
    for lab in labels:
        r = roles['any'].get(lab)
        if r:
            return normalize_role(r[0]), r[1], r[2]
    # процедура по началу (только для A-меток)
    for z in zones or []:
        for lab in labels:
            if lab.startswith('A'):
                p = roles['proc'].get((z, int(lab[1:], 8)))
                if p:
                    return p[0], STATUS_HYP, p[1]
    # текст по (зона, слово) — только для `'NNNN'`; A/D-метки описаны
    # role-таблицами (TEXT-CONSTANTS §4-6)
    if kind == 'OCT' and value is not None:
        for z in zones or []:
            t = roles['text'].get((z, value))
            if t:
                code = TEXT_CODE.get(t[0], '')
                return (t[1] + ('_' + code if code else ''),
                        STATUS_CONF, 'TEXT-CONSTANTS')
    # эвристика по префиксу метки
    if target.startswith('A'):
        return 'CODE_ENTRY', STATUS_HYP, 'A-label (no role table)'
    if target.startswith('D'):
        return 'CODE_DATA', STATUS_HYP, 'D-label (no role table)'
    if kind == 'IMM':
        return 'IMM_' + target.split(':', 1)[-1], STATUS_HYP, 'immediate'
    if kind == 'EXPR':
        return 'LOAD_BASE_DELTA', STATUS_HYP, 'сда 64-N'
    if kind == 'NUM':
        return 'LITERAL_' + target.split(':', 1)[-1], STATUS_HYP, 'bare number'
    if kind == 'OCT' and value is not None:
        return 'LOCAL_%o' % value, STATUS_HYP, "'NNNN' (no role table)"
    return 'UNKNOWN', STATUS_HYP, '-'


# ---------------------------------------------------------------------------
# 3. Фильтры ложных срабатываний
# ---------------------------------------------------------------------------

def apply_filters(refs, stats):
    """Отсеять псевдо-ссылки. Возвращает (чистые refs, настроенный порог fill)."""
    # 3.1 fuzz=64
    clean = [r for r in refs if r.kind != 'FUZZ']
    stats['filter_fuzz64'] = sum(1 for r in refs if r.kind == 'FUZZ')

    # 3.2 текстовые константы, похожие на числа ('F00900', GOST)
    stats['filter_text_const'] = sum(1 for r in refs if r.kind == 'TXT')
    clean = [r for r in clean if r.kind != 'TXT']

    # 3.3 explicit checkerboard fill
    def is_checker(r):
        return (r.raw in CHECKERBOARD or
                r.key.split(':')[-1] in CHECKERBOARD)
    chk = [r for r in clean if is_checker(r)]
    stats['filter_checkerboard'] = len(chk)
    clean = [r for r in clean if not is_checker(r)]

    # 3.3b generic repetitive-fill: один и тот же (mnem,key,mod) >= 100 раз
    counts = Counter((r.mnem, r.key, r.mod) for r in clean
                     if r.kind in ('OCT', 'NUM', 'LBL'))
    fill_keys = {k for k, n in counts.items() if n >= 100}
    gen = [r for r in clean if (r.mnem, r.key, r.mod) in fill_keys]
    stats['filter_fill_generic'] = len(gen)
    clean = [r for r in clean if (r.mnem, r.key, r.mod) not in fill_keys]

    # 3.4 dual cell: адресное слово/метка, помеченное "used as data",
    #     ссылающееся само на себя (START зп START, D00003 зп D00003).
    def is_dual(r):
        if not r.as_data or r.value is None or r.addr is None:
            return False
        return r.value == r.addr
    dual = [r for r in clean if is_dual(r)]
    stats['filter_dual_cell'] = len(dual)
    clean = [r for r in clean if not is_dual(r)]

    # 3.5 точные дубли (половины одного 48-битного слова)
    seen = set()
    uniq = []
    dup = 0
    for r in clean:
        sig = (r.src, r.addr, r.mnem, r.key, r.raw)
        if sig in seen:
            dup += 1
            continue
        seen.add(sig)
        uniq.append(r)
    stats['filter_dup_lines'] = dup
    return uniq


# ---------------------------------------------------------------------------
# 4. Вывод
# ---------------------------------------------------------------------------

def clip(text, n):
    text = str(text)
    return text if len(text) <= n else text[:n - 2] + '..'


def build(refs, definitions, roles):
    """target -> dict(zones, refs, def_zones, value, kinds)."""
    defzones = defaultdict(set)
    for z, letter, addr, src, line in definitions:
        defzones['%s%05o' % (letter, addr)].add(z)
        defzones['A%05o' % addr].add(z)
        defzones['D%05o' % addr].add(z)

    grouped = defaultdict(list)
    for r in refs:
        grouped[r.key].append(r)

    rows = []
    for key, rs in grouped.items():
        zones = sorted({r.zone for r in rs if r.zone})
        for r in rs:
            zones += list(defzones.get(r.key, ()))
        zones = sorted(set(zones))
        value = next((r.value for r in rs if r.value is not None), None)
        kind = rs[0].kind
        if kind == 'LBL':
            zones = sorted(set(zones + list(defzones.get(key, ()))))
        label, status, evidence = suggest(key, zones, kind, value, roles)
        srcs = ['%s:%s:%s' % (r.src, r.addr_text or '-', r.mnem) for r in rs]
        # Память/глобальный адрес (>= 02000₈) НЕ является словом зоны.
        if value is not None and value >= ZONE_WORDS:
            zone_col = 'GLOBAL'
        elif zones:
            zone_col = ','.join(zones)
        else:
            zone_col = kind.upper()
        rows.append({
            'target': key,
            'zones': zones,
            'zone_col': zone_col,
            'label': '%s[%s]' % (label, status),
            'label_raw': label,
            'status': status,
            'evidence': evidence,
            'count': len(rs),
            'sources': '; '.join(srcs),
            'kind': kind,
            'value': value,
        })
    rows.sort(key=lambda x: (-x['count'], x['target']))
    return rows


def write_tsv(path, rows):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('# target\tzone_of_definition\tlabel\tref_count\tsources\n')
        for r in rows:
            fh.write('%s\t%s\t%s\t%d\t%s\n' % (
                r['target'], r['zone_col'], r['label'], r['count'],
                r['sources']))


def write_md(path, rows, stats, files, root, args):
    nfiles = len(files)
    ntargets = len(rows)
    nrefs = sum(r['count'] for r in rows)
    local = [r for r in rows if r['zone_col'] != 'GLOBAL'
             and r['zone_col'] not in ('MOD', 'IMM', 'EXPR', 'NUM', 'LITERAL')]
    glob = [r for r in rows if r['zone_col'] == 'GLOBAL']
    addr_rows = [r for r in rows if r['kind'] in ('LBL', 'OCT')]
    conf = sum(1 for r in rows if r['status'] == STATUS_CONF)
    hyp = ntargets - conf

    out = []
    out.append('# ГЛОБАЛЬНЫЙ КРОСС-РЕФЕРЕНС ЛИСТИНГОВ БЭСМ-6')
    out.append('')
    out.append('Автоматически построен `tools/global_xref.py`. '
               'Исходные `.asm`, `.be`, `gold/`, `docs/` НЕ изменялись.')
    out.append('')
    out.append('## 1. Что сканировалось')
    out.append('')
    out.append('| Каталог | Файлов .asm |')
    out.append('|---|---|')
    for d in ('dis', 'dis-forced'):
        n = sum(1 for f in files if os.path.dirname(f).endswith(d))
        out.append('| `%s/` | %d |' % (d, n))
    out.append('| **ИТОГО** | **%d** |' % nfiles)
    out.append('')
    out.append('Каждая строка disbesm6 — половина 48-битного слова; '
               'адрес наследуется второй строкой. Разбор по '
               '`docs/XREF-METHODOLOGY.md` §3 и `docs/DISBESM6-GUIDE.md` §2.')
    out.append('')
    out.append('## 2. Точные команды')
    out.append('')
    out.append('```bash')
    out.append('cd %s' % root)
    out.append('python3 tools/global_xref.py \\')
    out.append('  --out analysis/global_xref.tsv \\')
    out.append('  --md analysis/GLOBAL-XREF.md')
    out.append('```')
    out.append('')
    out.append('Проверка числа файлов: '
               '`find dis dis-forced -name "*.asm" | wc -l` → %d.' % nfiles)
    out.append('')
    out.append('## 3. Статистика')
    out.append('')
    out.append('| Показатель | Значение |')
    out.append('|---|---|')
    out.append('| Всего файлов .asm | %d |' % nfiles)
    out.append('| Всего целей (target) | %d |' % ntargets)
    out.append('| Всего ссылок (refs) | %d |' % nrefs)
    out.append("| Адресных целей (`A/D#####` / `'NNNN'`) | %d |"
               % len(addr_rows))
    out.append('| ЗОНА-LOCAL целей | %d |' % len(local))
    out.append('| MEMORY/GLOBAL целей (>= 02000₈) | %d |' % len(glob))
    out.append('| `%s` | %d |' % (STATUS_CONF, conf))
    out.append('| `%s` | %d |' % (STATUS_HYP, hyp))
    out.append('')
    out.append('Граница LOCAL/GLOBAL — `%04o`₈ = 1024 слова одной зоны '
               '(AGENTS.md §1, MEMORY-MAP.md §3). '
               'A#####/D##### — зона-локальные слова `-a0`; '
               "`'70707'`, `'14000'`, `'70000'` — память вне зоны." %
               ZONE_WORDS)
    out.append('')
    out.append('### 3.1 Правила фильтрации (ложные срабатывания)')
    out.append('')
    out.append('| Правило | Отсеяно | Обоснование |')
    out.append('|---|---|---|')
    frules = [
        ('fuzz=64 `A#####±N`',
         stats['filter_fuzz64'],
         'praddr() печатает имя±дец в окне ±64; не адрес '
         '(XREF-METHODOLOGY §5.1)'),
        ('текст, похожий на число',
         stats['filter_text_const'],
         "`конд п'F00900'` и GOST-строки — не операнды-адреса "
         '(TEXT-CONSTANTS §2)'),
        ('шахматный fill',
         stats['filter_checkerboard'],
         "'25252'(М12)/'72525'(М5) — тестовый узор, не адрес "
         '(SEMANTIC/Z0567.md §3)'),
        ('generic repetitive fill',
         stats['filter_fill_generic'],
         'одинаковый (mnem, операнд, Мn) >= 100 раз — забел, не код'),
        ('двойная ячейка used-as-data',
         stats['filter_dual_cell'],
         'адресное слово ссылается само на себя; метка+код — одна ячейка '
         '(CROSSREF §5.2)'),
        ('дубль половин слова',
         stats['filter_dup_lines'],
         'идентичные (файл, адрес, мнем, операнд) — одна строка'),
        ('данные/символы (не числа)',
         stats['skip_DATA'] + stats['skip_SYM'] + stats['skip_empty'],
         'конд/пам/nop/START/PRINT8 — не числовые адреса'),
    ]
    for a, b, c in frules:
        out.append('| %s | %d | %s |' % (a, b, c))
    out.append('')
    out.append('## 4. Топ-50 адресных целей по числу ссылок')
    out.append('')
    out.append('| # | Цель | Зона | Роль | Статус | ВХ | Пример источника |')
    out.append('|---|---|---|---|---|---|---|')
    for i, r in enumerate(addr_rows[:50], 1):
        src = r['sources'].split(';')[0].strip()
        out.append('| %d | `%s` | `%s` | `%s` | %s | %d | `%s` |' % (
            i, r['target'], clip(r['zone_col'], 24), r['label_raw'],
            r['status'], r['count'], clip(src, 34)))
    out.append('')
    out.append('## 5. Топ-15 MEMORY/GLOBAL целей')
    out.append('')
    out.append('| Цель | Роль | ВХ | Комментарий |')
    out.append('|---|---|---|---|')
    for r in glob[:15]:
        out.append('| `%s` | `%s` | %d | %s |' % (
            r['target'], r['label_raw'], r['count'], r['evidence']))
    out.append('')
    out.append('## 6. Методика присвоения роли')
    out.append('')
    out.append('Источники в порядке приоритета:')
    out.append('')
    out.append('1. `docs/LABELS-B.md`, `LABELS-B2.md`, `LABELS-BE.md` — '
               'Explicit `A#####/D##### → PREFIX_ROLE` и `(Мn) → роль`.')
    out.append('2. `docs/SEMANTIC/Z*.md` — роли зон и штампы; '
               'пары `D00717 CNT6`, `A00477 OUT_PRINT`.')
    out.append('3. `analysis/procedures.md`, `procedures-RESOLVED.md` — '
               'начала процедур → `CODE_UTIL`/`OUT_PRINT`/`CODE_DISPATCH`.')
    out.append('4. `docs/TEXT-CONSTANTS.md` — декод GOST-текста по '
               '`зона.слово` → `TXT_*`/`ERR_*`.')
    out.append('5. `analysis/VARIABLES.md`, `VARIABLES-VALIDATION.md` — '
               'символьные имена памяти (`MEM_70707_GATE`, `MEM_04000_TAB1`).')
    out.append('')
    out.append('Формат имени — `ПРЕФИКС_РОЛЬ` по '
               '`docs/COMMENTING-STANDARD.md` §2.2–2.3. '
               '`[ПОДТВЕРЖДЕНО]` — есть штамп/пара вызов→возврат/'
               'role-таблица с этим статусом; `[ГИПОТЕЗА]` — роль '
               'выведена из шаблона, исходника транслятора на диске нет.')
    out.append('')
    out.append('## 7. Честные оговорки')
    out.append('')
    out.append('1. **Статический анализ.** `(Мn)` — индекс/счётчик; '
               'disbesm6 не отслеживает содержимое регистров '
               '(DISBESM6-GUIDE §3). Косвенные переходы `пб (М3)`, '
               '`по (М13)` НЕ разрешаются статически.')
    out.append("2. **Внешние адреса.** `'70000'`, `'14000'`, `'70707'`, "
               "`'02000'`/`'04000'` — память/ОС/target другой программы; "
               'в зонах 0137–0177/0540–0577 этих слов нет '
               '(XREF-METHODOLOGY §5.2).')
    out.append('3. **Одинаковые A/D-метки в B и B2 — разные физические '
               'ячейки** (база `-a0`); в колонке «Зона» перечислены все '
               'зоны-определения.')
    out.append('4. **Данные vs код.** Многие D-цели — таблицы/счётчики, '
               'а не процедуры; роль «утилита/вывод/диспетчер» — гипотеза.')
    out.append('5. **Дублирование зон.** `dis/` содержит 75 `.asm` '
               '(71 канонический `-L1` + 4 `ASM-Z*-full`), `dis-forced/` — '
               '49 форсированных копий. Одна и та же ячейка попадает '
               'в несколько файлов — счётчики ссылок отражают число '
               'листингов, не число машинных обращений.')
    out.append("6. Числовой операнд `'N'` и метка `D00NNN` не объединялись: "
               'разные Representation в листинге, возможна разная'
               ' привязка.')
    out.append('')
    out.append('---')
    out.append('')
    out.append('Файл данных: `analysis/global_xref.tsv` '
              '(`target<TAB>zone_of_definition<TAB>label<TAB>ref_count<TAB>sources`).')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out) + '\n')


def main():
    ap = argparse.ArgumentParser(
        description='Глобальный кросс-референс всех листингов БЭСМ-6.')
    ap.add_argument('--out', default=os.path.join('analysis',
                                                  'global_xref.tsv'))
    ap.add_argument('--md', default=os.path.join('analysis',
                                                 'GLOBAL-XREF.md'))
    ap.add_argument('--root', default='.',
                    help='корень репозитория (по умолчанию .)')
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    dirs = [os.path.join(root, 'dis'), os.path.join(root, 'dis-forced')]
    refs, defs, stats, files = scan_asm_files(dirs)
    if not files:
        print('global_xref: нет .asm в dis/ и dis-forced/', file=sys.stderr)
        return 1
    clean = apply_filters(refs, stats)
    roles = load_roles(root)
    rows = build(clean, defs, roles)

    out = args.out if os.path.isabs(args.out) else os.path.join(root, args.out)
    md = args.md if os.path.isabs(args.md) else os.path.join(root, args.md)
    for p in (out, md):
        od = os.path.dirname(os.path.abspath(p))
        if od and not os.path.isdir(od):
            os.makedirs(od, exist_ok=True)
    write_tsv(out, rows)
    write_md(md, rows, stats, files, root, args)

    nrefs = sum(r['count'] for r in rows)
    print('global_xref: файлов=%d  целей=%d  ссылок=%d  '
          'GLOBAL=%d  LOCAL=%d  фильтров=%d' % (
              len(files), len(rows), nrefs,
              sum(1 for r in rows if r['zone_col'] == 'GLOBAL'),
              sum(1 for r in rows if r['zone_col'] not in
                  ('GLOBAL', 'MOD', 'IMM', 'EXPR', 'NUM', 'LITERAL')),
              sum(v for k, v in stats.items() if k.startswith('filter_'))))
    print('  TSV: %s\n  MD : %s' % (out, md))
    return 0


if __name__ == '__main__':
    sys.exit(main())
