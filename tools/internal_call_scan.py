#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""internal_call_scan.py -- внутренние смещения 0000-1777к8 в ПРОГРАММЕ 2.

Объект: ПРОГРАММА 2 (БЕМШ 06/78, зоны 0137-0177к8).
Сканируются только листинги:
  dis-forced/Z<зона>.asm    (принудительный разбор, полнее)
  dis/MBE-Z<зона>-L1.asm    (канонический -a0 -e0)
Одна и та же ячейка может попасть в оба листинга; дедупликация
по (зона, адрес, мнемоника, значение, (Мn), вид).

Набор мнемоник сужен указанием оператора: только ПБ, ПВ, ПИО,
ПИНО (включая ПИО36) -- переходы с возвратом.  ПО/ПЕ/ЦИКЛ/ВЫПР
в определении процедур не участвуют.  Числовые операнды 0000-1777к8
делятся на абсолютные (кавычки, '605') и индексные смещения
(5(М7), 32(М14)); в таблицу целей идут только абсолютные.

Ни один входной файл (gold/, dis/, dis-forced/, bemsh/, docs/,
analysis/, sym/) не меняется.

CLI:
  python3 tools/internal_call_scan.py
  python3 tools/internal_call_scan.py --out docs/INTERNAL-CALL-OFFSETS.md
  python3 tools/internal_call_scan.py --json > /tmp/internal.json
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

# Разбор строк заимствован из tools/global_xref.py и
# tools/call_xref_scan.py (проверенный парсер листингов).
from global_xref import HEAD_RE, MOD_RE, QUOT_RE  # noqa: E402
from call_xref_scan import ZONES, iter_listings  # noqa: E402

# Только четыре перехода с возвратом (указание оператора).
TRANSFER_MNEMONICS = frozenset(('пв', 'пб', 'пио', 'пино', 'пио36'))
RET_MNEMONICS = frozenset(('пб',))
STOP_MNEMONICS = frozenset(('стоп', 'э74'))
DATA_MNEMONICS = frozenset(('конд', 'пам'))
ZONE_LOCAL_MAX = 0o1777
RET_WINDOW = 16

DATA_FILL = frozenset(('25252', '72525', '66666'))
LABEL_RE = re.compile(r'^[A-ZА-ЯЁ][A-ZА-ЯЁ0-9_]*$')
MNEM_RE = re.compile(r'^[а-яёa-z]{2,6}\d*$')
PROC_RE = re.compile(
    r'^\s*(\d{4}):(\d{4})-(\d{4})\s+size=\d+\s+\S+\s+(\S+)'
)
EQU_RE = re.compile(r"^\s*(P[A-ZА-ЯЁ0-9_]+)\s+ЭКВ\s+'([0-7]+)'")

VERDICT_FALSE = 'FALSE_TARGET'
VERDICT_PROC = 'PROCEDURE_ENTRY'
VERDICT_NAMED = 'ALREADY_NAMED'
VERDICT_LABEL = 'LABELED_TARGET'
VERDICT_SINGLE = 'SINGLE_REF'


def _read_lines(path):
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as fh:
        return fh.read().splitlines()


def parse_line(line):
    """Вернуть (есть_адрес, адрес, метка, мнемоника, операнд).

    Мнемоника -- первая нижнерегистровая ячейка строки; метка --
    предшествующая ячейка верхнего регистра (START, D00001, P605).
    """
    parts = line.split('\t')
    head = HEAD_RE.match(parts[0]) if parts else None
    has_addr = bool(head and head.group(1).strip())
    addr = int(head.group(1).strip(), 8) if has_addr else None
    mi = None
    for i, p in enumerate(parts):
        if MNEM_RE.fullmatch(p.strip()):
            mi = i
            break
    if mi is None:
        return has_addr, addr, '', '', ''
    mnem = parts[mi].strip()
    operand = parts[mi + 1].strip() if mi + 1 < len(parts) else ''
    label = ''
    if mi > 0 and LABEL_RE.fullmatch(parts[mi - 1].strip()):
        label = parts[mi - 1].strip()
    return has_addr, addr, label, mnem, operand


def extract_numeric(operand):
    """Вернуть (значение, вид) для числа 0000-1777к8 или (None, '').

    Кавычка -- абсолютный адрес; голое число с (Мn) или арифметикой --
    индексное смещение.  D00571+12 и -1(М17) не являются числами.
    """
    q = QUOT_RE.search(operand)
    if q:
        if not re.fullmatch(r'[0-7]{1,4}', q.group(1)):
            return None, ''
        value = int(q.group(1), 8)
        return (value, 'absolute') if 0 <= value <= ZONE_LOCAL_MAX \
            else (None, '')
    bare = operand.split('(')[0].strip()
    if not re.fullmatch(r'[0-7]{1,4}', bare):
        return None, ''
    value = int(bare, 8)
    if not 0 <= value <= ZONE_LOCAL_MAX:
        return None, ''
    indexed = '(' in operand or '+' in operand or '-' in operand
    return value, ('displacement' if indexed else 'absolute')


def scan_listings(root):
    """Собрать (абсолютные_ссылки, смещения, метаданные листингов)."""
    refs, disps, meta = [], [], []
    for path, zone, rel in iter_listings(root):
        lines = _read_lines(path)
        meta.append({'file': rel, 'zone': zone, 'lines': len(lines)})
        cur = None
        for lineno, line in enumerate(lines, 1):
            if line.startswith('*'):
                continue
            has_addr, addr, _label, mnem, operand = parse_line(line)
            if has_addr:
                cur = addr
            if mnem not in TRANSFER_MNEMONICS:
                continue
            value, kind = extract_numeric(operand)
            if value is None:
                continue
            mod = MOD_RE.search(operand)
            rec = {
                'zone': zone, 'addr': cur, 'mnem': mnem,
                'value': format(value, '04o'), 'value_int': value,
                'operand': operand, 'kind': kind,
                'mod': 'М' + mod.group(1) if mod else '-',
                'file': os.path.basename(path), 'line': lineno,
            }
            (refs if kind == 'absolute' else disps).append(rec)
    return dedup(refs), dedup(disps), meta


def dedup(refs):
    """Схлопнуть перекрытие листингов; первым остаётся первый файл."""
    seen, out = {}, []
    for r in refs:
        key = (r['zone'], r['addr'], r['mnem'], r['value_int'],
               r['mod'], r['kind'])
        if key in seen:
            seen[key]['raw_count'] += 1
            continue
        r['raw_count'] = 1
        seen[key] = r
        out.append(r)
    return out


def load_proc_catalog(root):
    """(зона, адрес) -> статусы ОСН/ВЛОЖ/ДАН из PROCEDURES-B.md."""
    out = defaultdict(set)
    path = os.path.join(root, 'docs/PROCEDURES-B.md')
    if not os.path.isfile(path):
        return {}
    for line in _read_lines(path):
        m = PROC_RE.match(line)
        if m:
            out[(m.group(1), int(m.group(2), 8))].add(m.group(4))
    return {k: tuple(sorted(v)) for k, v in out.items()}


def load_p_labels(root):
    """(зона, значение) -> список P-меток из bemsh/MBE-Z*.be."""
    out = defaultdict(set)
    for zone in ZONES:
        path = os.path.join(root, 'bemsh/MBE-Z%s.be' % zone)
        if not os.path.isfile(path):
            continue
        for line in _read_lines(path):
            m = EQU_RE.match(line)
            if m:
                out[(zone, int(m.group(2), 8))].add(m.group(1))
    return {k: tuple(sorted(v)) for k, v in out.items()}


def index_listing(path):
    """адрес -> (мнсм, операнд, метка) для одного листинга."""
    out = {}
    cur = None
    for line in _read_lines(path):
        has_addr, addr, label, mnem, operand = parse_line(line)
        if has_addr:
            cur = addr
        if cur is not None:
            out[cur] = (mnem, operand, label)
    return out


def code_context(fi, bi, target):
    """Доказательства по коду в точке цели: RET, метка, данные в базе."""
    mnem, operand, label = fi.get(target, ('', '', ''))
    base_mnem, base_operand, _ = bi.get(target, ('', '', ''))
    has_ret = False
    for addr in range(target, min(target + RET_WINDOW + 1, 0o1777 + 1)):
        m, o, _ = fi.get(addr, ('', '', ''))
        if m in RET_MNEMONICS or m in STOP_MNEMONICS:
            has_ret = True
            break
        if "в'" in o and ('стоп' in o or 'э74' in o):
            has_ret = True
            break
    base_is_data = (base_mnem in DATA_MNEMONICS or
                    base_operand.startswith("в'"))
    return {
        'target_mnem': mnem, 'target_operand': operand, 'label': label,
        'has_ret': has_ret, 'base_is_data': base_is_data,
    }


def classify(row):
    """Единственный вердикт по строке цели (приоритет -- сверху вниз)."""
    if row['false_reason']:
        return VERDICT_FALSE
    if row['p_labels']:
        return VERDICT_NAMED
    if row['refs'] >= row['min_refs'] and row['has_ret'] and \
            any(s in ('ОСН', 'ВЛОЖ') for s in row['proc_status']):
        return VERDICT_PROC
    if row['refs'] >= row['min_refs'] and row['has_ret']:
        return VERDICT_LABEL
    return VERDICT_SINGLE


def build(root, min_refs=2):
    """Главная точка: собрать все данные для отчёта."""
    refs, disps, meta = scan_listings(root)
    proc = load_proc_catalog(root)
    plabels = load_p_labels(root)
    groups = defaultdict(list)
    for r in refs:
        groups[(r['zone'], r['value_int'])].append(r)

    forced = {}
    base = {}
    for zone in ZONES:
        fp = os.path.join(root, 'dis-forced/Z%s.asm' % zone)
        bp = os.path.join(root, 'dis/MBE-Z%s-L1.asm' % zone)
        if os.path.isfile(fp):
            forced[zone] = index_listing(fp)
        if os.path.isfile(bp):
            base[zone] = index_listing(bp)

    rows = []
    for (zone, target), members in groups.items():
        members.sort(key=lambda r: (r['addr'] if r['addr'] is not None
                                    else -1, r['file']))
        ctx = code_context(forced.get(zone, {}), base.get(zone, {}), target)
        status = proc.get((zone, target), ())
        labels = plabels.get((zone, target), ())
        false_reason = ''
        if any(s == 'ДАН' for s in status):
            false_reason = 'каталог: ДАН'
        elif members[0]['value'] in DATA_FILL:
            false_reason = 'константа забела'
        row = {
            'zone': zone, 'target': format(target, '04o'),
            'target_int': target, 'refs': len(members), 'min_refs': min_refs,
            'sources': ['%s@%s' % (m['mnem'],
                        format(m['addr'], '04o') if m['addr'] is not None
                        else '????') for m in members],
            'mnems': sorted(set(m['mnem'] for m in members)),
            'proc_status': status, 'p_labels': labels,
            'false_reason': false_reason,
            'has_ret': ctx['has_ret'], 'base_is_data': ctx['base_is_data'],
            'target_mnem': ctx['target_mnem'],
            'target_operand': ctx['target_operand'],
            'label': ctx['label'],
            'evidence': '%s:%d' % (members[0]['file'], members[0]['line']),
        }
        row['verdict'] = classify(row)
        rows.append(row)
    rows.sort(key=lambda r: (r['zone'], r['target_int']))

    top = sorted(rows, key=lambda r: (-r['refs'], r['zone'], r['target_int']))
    for i, r in enumerate(top, 1):
        r['rank'] = i

    named = [r for r in rows if r['p_labels']]
    confirmed = [r for r in rows if r['verdict'] == VERDICT_PROC]
    stats = {
        'listings': len(meta),
        'zones_in_listings': len(set(m['zone'] for m in meta)),
        'raw_absolute_refs': sum(r['raw_count'] for r in refs),
        'dedup_absolute_refs': len(refs),
        'displacement_refs': len(disps),
        'targets': len(rows),
        'multi_ref_targets': sum(1 for r in rows
                                 if r['refs'] >= min_refs),
        'procedures_confirmed': len(confirmed),
        'targets_with_p_label': len(named),
        'targets_without_p_label': len(rows) - len(named),
        'confirmed_without_p_label': sum(1 for r in confirmed
                                         if not r['p_labels']),
        'catalog_entries': len(proc),
        'p_label_entries': len(plabels),
        'zones_with_targets': len(set(r['zone'] for r in rows)),
        'by_mnem_absolute': dict(Counter(r['mnem'] for r in refs)),
        'by_mnem_displacement': dict(Counter(r['mnem'] for r in disps)),
        'by_zone_absolute': dict(Counter(r['zone'] for r in refs)),
        'by_verdict': dict(Counter(r['verdict'] for r in rows)),
    }
    return {'stats': stats, 'rows': rows, 'displacements': disps,
            'meta': meta, 'min_refs': min_refs}


TABLE_HEADER = ('| зона | цель | ссылок | CALL-источники | RET? | '
                'каталог | P-метка в .be | вердикт |')


def render_table(result, limit=None):
    out = [TABLE_HEADER,
           '|---|---|---:|---|---|---|---|---|']
    rows = result['rows'] if limit is None else result['rows'][:limit]
    for r in rows:
        out.append('| {zone} | {target} | {refs} | {src} | {ret} | '
                   '{proc} | {plab} | {verdict} |'.format(
                       zone=r['zone'], target=r['target'], refs=r['refs'],
                       src=','.join(r['sources']),
                       ret='да' if r['has_ret'] else 'нет',
                       proc=','.join(r['proc_status']) or '-',
                       plab=','.join(r['p_labels']) or '-',
                       verdict=r['verdict']))
    return '\n'.join(out)


def render_report(result):
    s = result['stats']
    out = [
        'ВНУТРЕННИЕ СМЕЩЕНИЯ 0000-1777к8, ПРОГРАММА 2',
        '=' * 50,
        'Мнемоники: ПВ, ПБ, ПИО, ПИНО (ПИО36); ПО/ПЕ исключены.',
        'листингов: %d; зон с целями: %d' % (
            s['listings'], s['zones_with_targets']),
        'абсолютных ссылок: сырых %d, после дедупликации %d' % (
            s['raw_absolute_refs'], s['dedup_absolute_refs']),
        'индексных смещений (исключены): %d' % s['displacement_refs'],
        'целей: %d; с >=%d ссылок: %d; подтверждено процедур: %d' % (
            s['targets'], result['min_refs'], s['multi_ref_targets'],
            s['procedures_confirmed']),
        'целей с P-меткой: %d; без P-метки: %d; из подтверждённых '
        'без метки: %d' % (s['targets_with_p_label'],
                          s['targets_without_p_label'],
                          s['confirmed_without_p_label']),
        'по мнемоникам (абсолют): %s' % s['by_mnem_absolute'],
        'по зонам (абсолют): %s' % s['by_zone_absolute'],
        'по вердиктам: %s' % s['by_verdict'],
        '',
        'ПОЛНАЯ ТАБЛИЦА (%d целей)' % s['targets'],
        render_table(result),
        '',
        'ТОП-30 ПО ЧИСЛУ ССЫЛОК',
    ]
    top = sorted(result['rows'],
                 key=lambda r: (-r['refs'], r['zone'], r['target_int']))
    for r in top[:30]:
        out.append('%2d. Z%s %s: %d ссылок, каталог=%s, P=%s, %s' % (
            r['rank'], r['zone'], r['target'], r['refs'],
            ','.join(r['proc_status']) or '-',
            ','.join(r['p_labels']) or '-', r['verdict']))
    return '\n'.join(out)


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default=root,
                    help='корень репозитория (по умолчанию родитель tools/)')
    ap.add_argument('--out', default=None,
                    help='записать отчёт в файл')
    ap.add_argument('--json', action='store_true',
                    help='выдать структурированный JSON на stdout')
    ap.add_argument('--min-refs', type=int, default=2,
                    help='порог числа ссылок для процедурной записи')
    args = ap.parse_args(argv)

    result = build(args.root, args.min_refs)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    elif args.out:
        with open(args.out, 'w', encoding='utf-8') as fh:
            fh.write(render_report(result) + '\n')
        print('wrote %s' % args.out)
    else:
        print(render_report(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
