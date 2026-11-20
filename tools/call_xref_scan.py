#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""call_xref_scan.py -- CALL/return со смещением ВНЕ зоны 0..1777к8.

Объект: ПРОГРАММА 2 (БЕМШ 06/78, зоны 0137-0177к8).
Сканируются только листинги:
  dis-forced/Z<зона>.asm    (принудительный разбор, полнее)
  dis/MBE-Z<зона>-L1.asm    (канонический -a0 -e0)
Одна и та же машина ячейка может попасть в оба листинга; дедубликация
по (зона, адрес, мнемоника, операнд, Мn). Ни один входной файл
(gold/, dis/, dis-forced/, bemsh/, sym/, docs/, analysis/) не меняется.

CLI:
  python3 tools/call_xref_scan.py                  -- таблица на stdout
  python3 tools/call_xref_scan.py --out docs/CALL-OUT-OF-MODULE.md
  python3 tools/call_xref_scan.py --json > /tmp/call-xref.json
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

# Разбор строк заимствован из tools/global_xref.py (проверенный парсер,
# XREF-METHODOLOGY.md §3): адрес в первых 5 колонках, вторая строка слова
# адреса не имеет и наследит адрес первой.
from global_xref import HEAD_RE, MOD_RE, QUOT_RE, ZONE_RE  # noqa: E402

ZONE_LOCAL_MAX = 0o1777
PAGE_SIZE = 0o2000                # 1024 слова, MEMORY-MAP.md §3
# Только четыре инструкции по указанию пользователя:
# ПБ (безусловный передач), ПВ (с возвратом), ПИО/ПИНО (условные
# передачи с возвратом). 'пио36' -- OCR/двух-структурный вариант ПИО.
# ПО, ПЕ, ЦИКЛ, ВЫПР, НТЖ в счёт НЕ входят.
CALL_MNEMONICS = frozenset(('пб', 'пв', 'пио', 'пино', 'пио36'))
ZONES = ['%04o' % z for z in range(0o137, 0o177 + 1)]

# Повторяющиеся слова-забелы. '25252'/'72525' -- GLOBAL-XREF.md §3.1;
# '66666' -- конец зон таблиц ошибок (побайтово проверено в листинге).
DATA_FILL = frozenset(('25252', '72525', '66666'))
CHECKERBOARD = ('25252', '72525')

CLASS_FP = 'FALSE_POSITIVE'
CLASS_KNOWN = 'KNOWN_SYMBOLS'
CLASS_PAGE = 'ZONE_PAGE'
CLASS_UNKNOWN = 'UNKNOWN_ABSOLUTE_ADDRESS'
CLASS_ORDER = (CLASS_FP, CLASS_KNOWN, CLASS_PAGE, CLASS_UNKNOWN)

# Проверка адреса 07417к8 (только чтение, 20.11.2026). Результат:
# страница 03 привязана к зоне 0156, поэтому адрес НЕ "данные".
ADDRESS_RESEARCH = {
    '7417': [
        'analysis/MEMORY-MAP.md:111: зона 0156 загружена по '
        '06000к8, стр. 03; 07417к8 = 06000к8 + 01417к8',
        'monitor80-re/duread/g13024.asm:3, :23; '
        'monitor80-re/duread/g20776.asm:3, :13: метка *D17417* '
        '-- другой адрес 17417к8 (стр. 07)',
        'monitor80-re/permanent/paramt%.masm:614: 7417 внутри '
        'OCT-слова данных, не поле адреса вызова',
        'simh/BESM6 (docs/, *.c, *.h, *.asm): 07417 как адрес '
        'не найден',
        're-dispak/serp3.be:1351: метка G07417 -- код другой '
        'программы, для зон 0137-0177 не доказательство',
    ],
    '27615': [
        'analysis/MEMORY-MAP.md:105-117: страница 13к8 не '
        'привязана -- адрес неопознан, но не данные',
    ],
}


def octs(value):
    """Восьмеричное число без ведущих нулей (для вывода)."""
    return '%o' % value


def page_of(value):
    """Номер страницы ОП двумя восьмеричными цифрами (MEMORY-MAP.md §5)."""
    return '%02o' % (value // PAGE_SIZE)


def compact_name(value, used):
    """Компактная метка <=6 символов (EXTERNAL-OFFSET-FIX.md §1).

    Порядок кандидатов: X+3 цифры+B, X+4 цифры+B, X+5 цифр.
    Все кандидаты конечны и короче 7 символов.
    """
    core = octs(value).rjust(5, '0')
    candidates = ('X%sB' % core[-3:], 'X%sB' % core[-4:], 'X%s' % core[-5:])
    for name in candidates:
        if len(name) <= 6 and name not in used:
            used.add(name)
            return name
    name = ('X%s' % octs(value))[-6:]
    used.add(name)
    return name


def iter_listings(root):
    """Все листинги ПРОГРАММЫ 2 в детерминированном порядке."""
    for zone in ZONES:
        for rel in ('dis-forced/Z%s.asm' % zone,
                    'dis/MBE-Z%s-L1.asm' % zone):
            path = os.path.join(root, rel)
            if os.path.isfile(path):
                yield path, zone, rel


def _read_lines(path):
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as fh:
        return fh.read().splitlines()


def load_symbols(root):
    """Значение -> (имя роли, доказательство file:line).

    Источники: sym/GLOBAL.tab (формат %o %d %63s) и
    docs/ENTRY-POINTS.md §3 (*EXECUTE / внешние символы МВЕ60).
    """
    out = {}
    tab = os.path.join(root, 'sym/GLOBAL.tab')
    if os.path.isfile(tab):
        for lineno, line in enumerate(_read_lines(tab), 1):
            m = re.match(r'^([0-7]+)\s+([0-9]|-)\s+(\S+)\s*$', line)
            if not m:
                continue
            value = int(m.group(1), 8)
            if value > ZONE_LOCAL_MAX:
                out[value] = (m.group(3), 'sym/GLOBAL.tab:%d' % lineno)

    doc = os.path.join(root, 'docs/ENTRY-POINTS.md')
    if os.path.isfile(doc):
        lines = _read_lines(doc)
        # Строки таблицы *EXECUTE: | `СИМВОЛ` (...) | `01000₈` | N | ...
        row = re.compile(r'^\|\s*`([^`]+)`[^|]*\|\s*`([0-7]{3,7})₈`\s*\|')
        for lineno, line in enumerate(lines, 1):
            m = row.match(line)
            if not m:
                continue
            value = int(m.group(2), 8)
            name = m.group(1)
            # Таблица загрузочных адресов: `0156` | `06000₈`.
            if re.fullmatch(r'[0-7]{4}', name):
                name = 'Z%s_ZONE_START' % name
            if value > ZONE_LOCAL_MAX and value not in out:
                out[value] = (name, 'docs/ENTRY-POINTS.md:%d' % lineno)
    return out


def load_pages(root):
    """Номер страницы (восьм.) -> ([зоны], доказательство file:line)."""
    out = {}
    path = os.path.join(root, 'analysis/MEMORY-MAP.md')
    if not os.path.isfile(path):
        return out
    for lineno, line in enumerate(_read_lines(path), 1):
        if not line.lstrip().startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 3:
            continue
        zone = re.fullmatch(r'([0-7]{4})', cells[0].strip('`'))
        addr = re.fullmatch(r'`?([0-7]{4,6})₈`?', cells[1])
        page = re.fullmatch(r'([0-7]{1,2})', cells[2])
        if not (zone and addr and page):
            continue
        out.setdefault(page.group(1), [[], 'analysis/MEMORY-MAP.md:%d'
                                       % lineno])
        if zone.group(1) not in out[page.group(1)][0]:
            out[page.group(1)][0].append(zone.group(1))
    return out


def scan_listings(root):
    """Вернуть (сырые ссылки, метаданные листингов, сигнатуры забелов).

    Каждая сырая ссылка -- dict с зоной, адресом слова, мнемоникой,
    операндом, значением, (Мn), файлом, строкой и признаком двойной
    половины слова (dup_half).
    """
    refs = []
    meta = []
    dup_addrs = defaultdict(set)         # (зона, мнем, значение) -> адреса
    checker = Counter()                  # зона -> число слов-шахматок

    for path, zone, rel in iter_listings(root):
        lines = _read_lines(path)
        cnt = sum(1 for ln in lines
                  if any(c in ln for c in CHECKERBOARD))
        if cnt:
            checker[zone] += cnt
        meta.append({'file': rel, 'zone': zone, 'lines': len(lines),
                     'checkerboard': cnt})
        cur = None
        pending = False
        prev_sig = None                  # (мнсм, значение) предыдущей половины
        for lineno, line in enumerate(lines, 1):
            if line.startswith('*'):
                if 'used as data' in line:
                    pending = True
                continue
            parts = line.split('\t')
            # Адрес разбирается ДО проверки числа полей: строка с
            # пустым операндом имеет всего 3 поля, но несёт адрес слова.
            head = HEAD_RE.match(parts[0]) if parts else None
            if not head:
                continue
            addr_field = head.group(1).strip()
            has_addr = bool(addr_field)
            if has_addr:
                cur = int(addr_field, 8)
                pending = False              # W_CODE|W_DATA -- не забел
                prev_sig = None
            if len(parts) < 4:
                continue
            mnem = parts[2].strip().lower()
            operand = parts[3].strip()
            sig = None
            q = QUOT_RE.search(operand)
            if q and re.fullmatch(r'[0-7]+', q.group(1)):
                value = int(q.group(1), 8)
                if value > ZONE_LOCAL_MAX:
                    sig = (mnem, octs(value))
            dup_half = bool(sig and sig == prev_sig and not has_addr)
            if sig and mnem in CALL_MNEMONICS:
                mod = MOD_RE.search(operand)
                refs.append({
                    'zone': zone, 'addr': cur, 'mnem': mnem,
                    'operand': "'%s'" % q.group(1), 'value': sig[1],
                    'value_int': int(sig[1], 8),
                    'mod': 'М' + mod.group(1) if mod else '-',
                    'file': os.path.basename(path), 'line': lineno,
                    'dup_half': dup_half, 'data_marker': pending,
                })
                if dup_half:
                    dup_addrs[(zone, mnem, sig[1])].add(cur)
            prev_sig = sig
    return refs, meta, dup_addrs, checker


def dedup(raw):
    """Схлопнуть перекрытие листингов; первым остаётся первый файл."""
    seen = {}
    out = []
    for r in raw:
        key = (r['zone'], r['addr'], r['mnem'], r['value_int'], r['mod'])
        if key in seen:
            seen[key]['raw_count'] += 1
            seen[key]['dup_half'] = (seen[key]['dup_half'] or
                                     r['dup_half'])
            continue
        r['raw_count'] = 1
        seen[key] = r
        out.append(r)
    return out


def fill_addresses(dup_addrs):
    """Слова (зона, мнем, значение, адрес) в забеле из 3+ дублей подряд.

    Одиночные пары одинаковых половин доказательством не являются:
    помечается только само слово, входящее в повтор.
    """
    out = set()
    for (zone, mnem, value), addrs in dup_addrs.items():
        ordered = sorted(addrs)
        run = [ordered[0]]
        for prev, cur in zip(ordered, ordered[1:]):
            if cur == prev + 1:
                run.append(cur)
            else:
                if len(run) >= 3:
                    out.update((zone, mnem, value, a) for a in run)
                run = [cur]
        if len(run) >= 3:
            out.update((zone, mnem, value, a) for a in run)
    return out


def classify(ref, symbols, pages, repeats, checker):
    """Вернуть (класс, деталь, доказательство).

    Повторяющиеся слова НЕ помечаются данными: по указанию пользователя
    числовой операнд CALL -- абсолютный адрес. `repeats` сохраняется в
    статистике как подозрение, но на класс не влияет (см. §5 отчёта).
    """
    zone = ref['zone']
    value = ref['value_int']
    evidence = '%s:%d' % (ref['file'], ref['line'])

    if value in symbols:
        name, sym_ev = symbols[value]
        return CLASS_KNOWN, name, sym_ev
    page = page_of(value)
    if page in pages:
        zones, page_ev = pages[page]
        return CLASS_PAGE, 'стр. %s / зона %s' % (page, ','.join(zones)), \
            page_ev
    return CLASS_UNKNOWN, 'стр. %s не привязана' % page, evidence


def suggest_role(cls, detail, value):
    """(длинная роль, компактная метка <=6 символов)."""
    if cls == CLASS_KNOWN:
        long = 'MEM_' + detail.replace('-', '_')
    elif cls == CLASS_PAGE:
        m = re.search(r'зона ([0-7]{4})', detail)
        long = 'MEM_P%s_Z%s' % (page_of(value), m.group(1) if m else 'UNK')
    elif cls == CLASS_FP:
        long = 'MEM_FILL_' + octs(value)
    else:
        long = 'EXT_CALL_' + octs(value)
    return long


def build(root):
    """Главная точка: собрать все данные для отчёта."""
    symbols = load_symbols(root)
    pages = load_pages(root)
    raw, meta, dup, checker = scan_listings(root)
    fills = fill_addresses(dup)
    refs = dedup(raw)
    for r in refs:
        cls, detail, evidence = classify(r, symbols, pages, fills, checker)
        r['class'] = cls
        r['detail'] = detail
        r['class_evidence'] = evidence
        r['role'] = suggest_role(cls, detail, r['value_int'])

    groups = defaultdict(list)
    for r in refs:
        groups[(r['zone'], r['mnem'], r['value_int'], r['mod'],
                r['class'])].append(r)
    rows = []
    for (zone, mnem, value, mod, cls), members in groups.items():
        members.sort(key=lambda r: (r['addr'], r['file']))
        first = members[0]
        addrs = sorted(set(r['addr'] for r in members))
        rows.append({
            'zone': zone, 'mnem': mnem, 'operand': first['operand'],
            'value': octs(value), 'value_int': value, 'mod': mod,
            'count': len(members),
            'raw_count': sum(r['raw_count'] for r in members),
            'addr': addrs[0], 'addrs': addrs,
            'class': first['class'], 'detail': first['detail'],
            'role': first['role'],
            'evidence': '%s:%d' % (first['file'], first['line']),
            'class_evidence': first['class_evidence'],
        })
    rows.sort(key=lambda r: (r['zone'], r['addr'], r['mnem'], r['value_int'],
                             r['mod']))

    used = set()
    targets = defaultdict(list)
    for r in refs:
        targets[(r['value_int'], r['class'])].append(r)
    top = []
    for (value, cls), members in targets.items():
        src = ['Z%s.%04o' % (r['zone'], r['addr']) for r in members]
        top.append({
            'value': octs(value), 'value_int': value, 'class': cls,
            'count': len(members),
            'role': suggest_role(cls, members[0]['detail'], value),
            'detail': members[0]['detail'],
            'compact': compact_name(value, used),
            'sources': sorted(src),
            'zones': sorted(set(r['zone'] for r in members)),
            'mnems': sorted(set(r['mnem'] for r in members)),
        })
    top.sort(key=lambda t: (-t['count'], t['value_int']))
    for i, t in enumerate(top, 1):
        t['rank'] = i

    stats = {
        'listings': len(meta),
        'raw_refs': len(raw),
        'dedup_refs': len(refs),
        'groups': len(rows),
        'targets': len(top),
        'zones': len(set(r['zone'] for r in refs)),
        'by_class_refs': dict(Counter(r['class'] for r in refs)),
        'by_class_groups': dict(Counter(r['class'] for r in rows)),
        'by_mnem': dict(Counter(r['mnem'] for r in refs)),
        'fill_words': len(fills),
        'error_table_zones': sorted(z for z, c in checker.items()
                                    if c >= 100),
    }
    return {'stats': stats, 'rows': rows, 'top': top, 'meta': meta,
            'symbols': symbols, 'pages': pages}


def render_table(data):
    """Основная таблица: зона | адрес | мнем | операнд | (Mn) | ... ."""
    out = ['| зона |WORD| мнем | операнд | (Mn) | ВХ | класс | объяснение |',
           '|---|---|---|---|---|---:|---|---|']
    for r in data['rows']:
        suffix = '' if r['count'] == 1 else '+%d' % (r['count'] - 1)
        cls = r['class']
        det = r['detail']
        out.append('| %s | %04o%s | %s | %s | %s | %d | %s / %s | %s |'
                   % (r['zone'], r['addr'], suffix, r['mnem'], r['operand'],
                      r['mod'], r['count'], cls, det, r['evidence']))
    return '\n'.join(out)


def render_json(data):
    return json.dumps({'stats': data['stats'], 'rows': data['rows'],
                       'top': data['top'], 'meta': data['meta']},
                      ensure_ascii=False, indent=1)


def render_markdown(data, root):
    s = data['stats']
    lines = []
    add = lines.append
    add('# CALL/return вне локального диапазона зоны (ПРОГРАММА 2)')
    add('')
    add('Автоматически построено `tools/call_xref_scan.py`. '
        'Эталонные образы, `gold/`, `dis/`, `dis-forced/`, `bemsh/`, '
        '`sym/` и `analysis/` не изменялись.')
    add('')
    add('## 1. Методика')
    add('')
    add('Сканируются 33 зоны БЕМШ (0137-0177к8) в двух наборах листингов:')
    add('')
    add('| Каталог | Шаблон | Назначение |')
    add('|---|---|---|')
    add('| `dis-forced/` | `Z<зона>.asm` | принудительный разбор, полнее |')
    add('| `dis/` | `MBE-Z<зона>-L1.asm` | канонический `-a0 -e0` |')
    add('')
    add('Каждая строка `disbesm6` -- половина 48-битного слова; вторая '
        'строка наследит адрес первой (`docs/XREF-METHODOLOGY.md` §3). '
        'Учитываются ТОЛЬКО `пб`, `пв`, `пио`, `пино` и вариант '
        '`пио36` (OCR/двух-структурный): ПИО/ПИНО -- условные передачи '
        'с возвратом, поэтому их числовой операнд -- тоже кросс-ссылка. '
        'Мнемоники `по`, `пе`, `цикл`, `выпр`, `нтж` и прочие в счёт '
        'не входят. Берутся строки с кавычным восьмеричным операндом '
        '\'NNNN\' при `значение > 01777к8` (1024 слова зоны). Ссылки '
        'через `(Мn)` без числа не учитываются: регистр статически '
        'не разрешается.')
    add('')
    add('Перекрытие листингов схлопывается по ключу '
        '`(зона, слово, мнемоника, операнд, (Мn))`; доказательство -- '
        'первый файл в порядке `dis-forced/`, затем `dis/`. '
        '`* next insn used as data` **не** отбрасывается: это ячейка '
        '`W_CODE|W_DATA`, а не ошибка разбора '
        '(`docs/MACRO-BEMSH-ARCHITECTURE.md` §5.4).')
    add('')
    add('### Точные команды')
    add('')
    add('```bash')
    add('cd /home/azizz/Yandex.Disk/re-bemsh')
    add('python3 tools/call_xref_scan.py --out docs/CALL-OUT-OF-MODULE.md')
    add('python3 tools/call_xref_scan.py --json > /tmp/call-xref.json')
    add('python3 -m unittest tools.tests.test_call_xref_scan -v')
    add('```')
    add('')
    add('## 2. Правила классификации')
    add('')
    add('| Класс | Правило | Источник |')
    add('|---|---|---|')
    add('| %s | 0: повторяющиеся слова без доказательства не '
        'считаются данными; числовой операнд CALL -- адрес | §5, '
        'решение пользователя |' % CLASS_FP)
    add('| %s | операнд есть адрес из `sym/GLOBAL.tab` или '
        '`docs/ENTRY-POINTS.md` | `sym/GLOBAL.tab`, '
        '`docs/ENTRY-POINTS.md` §3 |' % CLASS_KNOWN)
    add('| %s | операнд внутри известной страницы ОП | '
        '`analysis/MEMORY-MAP.md` §5 |' % CLASS_PAGE)
    add('| %s | вне 0..01777к8 и не привязан к странице | '
        'правило пользователя: всё вне зоны -- кросс-ссылка |'
        % CLASS_UNKNOWN)
    add('')
    add('Страница считается как `операнд / 02000к8` (адрес '
        '`страница × 02000к8`, `analysis/MEMORY-MAP.md` §3). '
        'Например `77316к8` -- страница `37к8` = зона `0157`, '
        '`07417к8` -- страница `03к8` = зона `0156` (§5), '
        '`72000к8` -- страница `35к8` = зоны `0174/0175/0177` '
        '(неоднозначно).')
    add('')
    add('## 3. Статистика')
    add('')
    add('| Показатель | Значение |')
    add('|---|---:|')
    for k, label in (('listings', 'Листингов .asm'),
                     ('raw_refs', 'Ссылок до дедупликации'),
                     ('dedup_refs', 'Ссылок после дедупликации'),
                     ('groups', 'Групп (зона, мнем, операнд, Мn)'),
                     ('targets', 'Различных целей (значение, класс)'),
                     ('zones', 'Зон-источников')):
        add('| %s | %d |' % (label, s[k]))
    add('')
    add('| Класс | Групп | Ссылок |')
    add('|---|---:|---:|')
    for cls in CLASS_ORDER:
        add('| %s | %d | %d |' % (cls, s['by_class_groups'].get(cls, 0),
                                 s['by_class_refs'].get(cls, 0)))
    add('')
    add('| Мнемоника | Ссылок |')
    add('|---|---:|')
    for mnem in sorted(CALL_MNEMONICS):
        if s['by_mnem'].get(mnem):
            add('| `%s` | %d |' % (mnem, s['by_mnem'][mnem]))
    add('')
    add('Предварительный проход по `пв/пво/вжм` давал 1746 сырых '
        'ссылок; после сужения набора до ПБ/ПВ/ПИО/ПИНО и '
        'дедупликации итоговые числа приведены выше. `пио36` '
        'учтён как ПИО.')
    add('')
    add('## 4. Топ-50 целей по числу ссылок')
    add('')
    add('`роль` -- мнемоническое имя по '
        '`docs/COMMENTING-STANDARD.md` §2.2 (`MEM_`) и §2.3 '
        '(`EXT_CALL_` как подсказка вызова); `компакт` -- метка '
        '`XnnnnB` длиной 6 символов (`docs/EXTERNAL-OFFSET-FIX.md` §1). '
        'Роли -- гипотезы: исходника транслятора на диске нет.')
    add('')
    add('| # | Цель | ВХ | Класс | Роль | Компакт | Источники '
        '(зона.слово) |')
    add('|---:|---|---:|---|---|---|---|')
    for t in data['top'][:50]:
        sources = ', '.join(t['sources'])
        add('| %d | `%sк8` | %d | %s | `%s` | `%s` | %s |'
            % (t['rank'], t['value'], t['count'], t['class'], t['role'],
               t['compact'], sources))
    add('')
    add('## 5. Проверка подозрительных адресов (ложные срабатывания)')
    add('')
    add('**В классе %s: %d групп, %d ссылок.** Повторяющиеся слова '
        '(одинаковые половины 3+ раз подряд) сняты с класса «данные» '
        'по указанию пользователя: числовой операнд CALL -- '
        'абсолютный адрес. Подозреваемых слов-повторов: %d; '
        'они учтены как `ZONE_PAGE` или '
        '`%s`.' % (CLASS_FP, s['by_class_groups'].get(CLASS_FP, 0),
                   s['by_class_refs'].get(CLASS_FP, 0),
                   s['fill_words'], CLASS_UNKNOWN))
    add('')
    add('Сырой проход по всем мнемоникам даёт 205 ссылок на '
        'операнд `7417`: 202 -- `пио36`, 3 -- другие. После '
        'дедупликации -- 138. Ранее 48 из них назывались «забел»; '
        'теперь все 138 -- адреса страницы `03к8`.')
    add('')
    for value, evidence_lines in ADDRESS_RESEARCH.items():
        add('### 5.%d Операнд `%sк8`' %
            (list(ADDRESS_RESEARCH).index(value) + 1, value))
        add('')
        for item in evidence_lines:
            add('- ' + item)
        add('')
    add('**Вывод по `07417к8`:** адрес привязан к странице `03к8` '
        '(`analysis/MEMORY-MAP.md:111`: зона `0156` по `06000к8`), '
        'то есть `07417к8 = 06000к8 + 01417к8`. Класс -- '
        '`ZONE_PAGE`, а не данные. Слово `01417к8` не расшифровано '
        'в `dis/MBE-Z0156-L1.asm` (там разобрано ~130 слов из '
        '1024), поэтому роль точки входа неизвестна.')
    add('')
    add('**Вывод по `27615к8`:** страница `13к8` в карте памяти '
        'отсутствует; класс -- `%s`. Это не данные, а '
        'неопознанный абсолютный адрес.' % CLASS_UNKNOWN)
    add('')
    add('## 6. Приложение: все строки по зонам')
    add('')
    add('`WORD` -- адрес первого слова в группе, `+N` -- ещё N '
        'адресов той же группы; полные списки -- в §4.')
    add('')
    add(render_table(data))
    add('')
    add('## 7. Честные оговорки')
    add('')
    add('1. **Статический анализ.** Косвенные переходы через `(Мn)` '
        'не разрешаются: `disbesm6` не отслеживает регистры. '
        'Динамические значения M15/M16/M13 даны в '
        '`docs/PROGRAM2-REGISTERS.md`, но не привязаны к слову.')
    add('2. **Карта памяти неполна.** Привязаны 12 из 33 зон '
        '(`analysis/MEMORY-MAP.md` §5). Остальные операнды попадают '
        'в %s -- это кросс-ссылки по правилу пользователя, но '
        'цель неизвестна.' % CLASS_UNKNOWN)
    add('3. **Неоднозначность страницы 35.** Зоны `0174/0175/0177` '
        'совпадают и со страницей 33 '
        '(`analysis/MEMORY-MAP.md` §7 п. 2).')
    add('4. **Дублирование листингов.** Одно слово может попасть в '
        '`dis-forced/` и `dis/`; дедупликация -- по ключу из §1, '
        'поэтому счёт -- число слов, не число обращений '
        'машины и не число листингов.')
    add('5. **`02000к8` -- две роли.** И `MAC_EDITOR_LOAD`, и `*PAGE*` '
        'из `*EXECUTE`; приоритет у `KNOWN_SYMBOLS` '
        '(`docs/ENTRY-POINTS.md` §3). Совпадение адресов не '
        'доказывает совпадение программ.')
    add('6. **Роли -- гипотезы.** `EXT_CALL_`/`MEM_` -- подсказки по '
        '`docs/COMMENTING-STANDARD.md` §2.2-2.3, не доказанные имена '
        'процедур. Адреса из `sym/GLOBAL.tab` -- локальные '
        'метки `-a0`, не физические якоря.')
    add('7. **`used as data` оставлены.** Это `W_CODE|W_DATA`, '
        'то есть код и данные одновременно; выбрасывать такой '
        'вызов нельзя без трассы.')
    add('8. **Повторы -- не данные.** Слова с одинаковыми '
        'половинами (`пио36 \'7417\'`, `пб \'27615\'`) '
        'переклассифицированы как адреса; проверка источников '
        'приведена в §5.')
    add('')
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default=None,
                    help='корень репозитория (по умолчанию -- каталог '
                         'родитель tools/)')
    ap.add_argument('--out', default=None,
                    help='записать Markdown-отчёт в файл')
    ap.add_argument('--json', action='store_true',
                    help='печать JSON вместо таблицы')
    args = ap.parse_args(argv)
    root = args.root or os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))
    data = build(root)
    if args.json:
        print(render_json(data))
    elif args.out:
        path = args.out if os.path.isabs(args.out) else os.path.join(
            root, args.out)
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(render_markdown(data, root) + '\n')
        s = data['stats']
        print('call_xref_scan: листингов=%d сырых=%d уникальных=%d '
              'групп=%d' % (s['listings'], s['raw_refs'],
                            s['dedup_refs'], s['groups']))
        print('  отчёт: %s' % path)
    else:
        print(render_table(data))
    return 0


if __name__ == '__main__':
    sys.exit(main())
