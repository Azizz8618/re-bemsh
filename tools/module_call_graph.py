#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""module_call_graph.py — статический граф вызовов 69 зон БЕМШ.

Источники (только чтение):
  dis/ASM-Z*-L1.asm, dis/MBE-Z*-L1.asm, dis/MBE2-Z*-L1.asm
  dis-forced/Z*.asm            — косвенная сверка (принудительный разбор)
  analysis/ZONE-BASE-MAP.md    — базы загрузки (Приложение A)
  analysis/xref.txt            — устаревший кросс-референс (meta only)

Разбор строк заимствован из проверенных tools/xref.py и
tools/internal_call_scan.py (HEAD_RE + parse_line). Ни один
входной файл не модифицируется, кэш не используется.

CLI:
  python3 tools/module_call_graph.py --format json
  python3 tools/module_call_graph.py --format text --zone 0147
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

from internal_call_scan import parse_line  # noqa: E402

EXTRACT_MNEM_RE = re.compile(r'^[Ээ][0-7]{2}$')
EXTRACT_LABEL_RE = re.compile(r'^[A-Z][0-9]{5}$')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIS = os.path.join(ROOT, 'dis')
FORCED = os.path.join(ROOT, 'dis-forced')
BASE_MAP_FILE = os.path.join(ROOT, 'analysis', 'ZONE-BASE-MAP.md')
XREF_FILE = os.path.join(ROOT, 'analysis', 'xref.txt')

CALL_MNEM = frozenset(('пв', 'вжм', 'э70'))
LINK_MNEM = frozenset(('пб', 'по'))
MOD_RE = re.compile(r'\(М(\d{1,2})\)')
LABEL_RE = re.compile(r'^([ADG])(\d{5})(?:\+\d+)?$')
QUOT_RE = re.compile(r"^'([0-7]+)'$")
BARE_RE = re.compile(r'^[0-7]{1,6}$')
ZONE_WORDS = 0o2000
ZONE_LOCAL_MAX = 0o1777

STATUS_FACT = 'ФАКТ'
STATUS_HYP = 'ГИПОТЕЗА'
STATUS_UNKNOWN = 'НЕ ИЗВЕСТНО'
BASE_STATUSES = (STATUS_FACT, STATUS_HYP, STATUS_UNKNOWN)


def parse_line_mcg(line):
    """Обёртка над проверенным parse_line: добавляет ЭNN.

    parse_line из internal_call_scan ищет мнемонику по шаблону
    «2-6 букв + цифры», поэтому однобуквенные экстракоды Э70
    не распознаются. Остальные строки разбираются тем же кодом.
    """
    has_addr, addr, label, mnem, operand = parse_line(line)
    if mnem:
        return has_addr, addr, label, mnem, operand
    parts = line.split('\t')
    for i, cell in enumerate(parts):
        token = cell.strip()
        if EXTRACT_MNEM_RE.match(token):
            nxt = parts[i + 1].strip() if i + 1 < len(parts) else ''
            prev = parts[i - 1].strip() if i > 0 else ''
            lab = prev if EXTRACT_LABEL_RE.match(prev) else ''
            return has_addr, addr, lab, token.lower(), nxt
    return has_addr, addr, label, mnem, operand


def oseq(first, last):
    """Восьмеричный диапазон зон включительно."""
    return ['%04o' % v for v in range(int(first, 8), int(last, 8) + 1)]


def zone_catalog():
    """69 канонических зон в порядке: АСМ, B, B2."""
    asm = [(z, 'ASM', 'ASM-Z%s-L1.asm' % z)
           for z in oseq('0055', '0060')]
    b = [(z, 'B', 'MBE-Z%s-L1.asm' % z)
         for z in oseq('0137', '0177')]
    b2 = [(z, 'B2', 'MBE2-Z%s-L1.asm' % z)
          for z in oseq('0540', '0577')]
    return asm + b + b2


def read_base_map(path=BASE_MAP_FILE):
    """Приложение A ZONE-BASE-MAP.md: зона -> база, статус."""
    out = {}
    if not os.path.isfile(path):
        return out
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            parts = line.strip().split(',')
            if len(parts) != 3:
                continue
            zone, field, status = parts
            if not re.fullmatch(r'\d{4}', zone) or status not in BASE_STATUSES:
                continue
            if field == '-':
                base, candidate = None, False
            elif field.endswith('?') and re.fullmatch(r'[0-7]+\?', field):
                base, candidate = int(field[:-1], 8), True
            elif re.fullmatch(r'[0-7]+', field):
                base, candidate = int(field, 8), False
            else:
                continue
            out[zone] = {'base': base, 'candidate': candidate,
                         'status': status}
    return out


def zones_for_addr(addr, base_map):
    """Все зоны, чьё окно [база, база+01777] содержит адрес."""
    hits = []
    for zone, info in sorted(base_map.items()):
        base = info['base']
        if base is not None and base <= addr <= base + ZONE_LOCAL_MAX:
            hits.append(zone)
    return hits


def classify(mnem, operand, caller_zone, base_map):
    """Классифицировать одну передачу управления.

    Возвращает dict: kind, target, target_zone, addr, note.
   """
    low = mnem.lower()
    mod = MOD_RE.search(operand)
    core = MOD_RE.sub('', operand).strip()
    if ',' in core:
        core = core.split(',', 1)[0].strip()

    lab = LABEL_RE.match(core)
    if lab:
        return {
            'kind': 'internal', 'target': lab.group(0),
            'target_zone': caller_zone,
            'addr': int(lab.group(2), 8), 'note': 'LABEL_LOCAL',
        }

    value = None
    q = QUOT_RE.match(core)
    if q:
        value = int(q.group(1), 8)
    elif BARE_RE.match(core):
        value = int(core, 8)

    if value is not None:
        base = base_map.get(caller_zone, {}).get('base')
        if base is None and value < ZONE_WORDS:
            return {
                'kind': 'unknown', 'target': core,
                'target_zone': None, 'addr': value,
                'note': 'SMALL_LITERAL_BASE_UNKNOWN',
            }
        phys = base + value if base is not None and value < ZONE_WORDS \
            else value
        hits = zones_for_addr(phys, base_map)
        if caller_zone in hits:
            kind, zone = 'internal', caller_zone
        elif hits:
            kind, zone = 'external', '/'.join(hits)
        else:
            kind, zone = 'unknown', None
        return {
            'kind': kind, 'target': core, 'target_zone': zone,
            'addr': phys,
            'note': 'ADDR_NO_ZONE' if kind == 'unknown' else 'BASE_WINDOW',
        }

    if mod and core in ('', '-'):
        return {
            'kind': 'indirect', 'target': '(М%s)' % mod.group(1),
            'target_zone': None, 'addr': None,
            'note': 'LINK_' + ('CALL' if low in CALL_MNEM else 'BRANCH'),
        }

    return {
        'kind': 'unknown', 'target': core or operand,
        'target_zone': None, 'addr': None, 'note': 'UNPARSED_OPERAND',
    }


def parse_listing(text, zone, source, base_map):
    """Разобрать текст листинга в список записей о передачах."""
    recs = []
    for lineno, line in enumerate(text.splitlines(), 1):
        has_addr, addr, label, mnem, operand = parse_line_mcg(line)
        if not mnem:
            continue
        low = mnem.lower()
        if low in CALL_MNEM:
            info = classify(mnem, operand, zone, base_map)
            info.update(zone=zone, mnem=low, addr_src=addr, label=label,
                        evidence='%s:%d' % (source, lineno))
            recs.append(info)
        elif low in LINK_MNEM:
            mod = MOD_RE.search(operand)
            core = MOD_RE.sub('', operand).strip()
            if mod and core in ('', '-'):
                info = classify(mnem, operand, zone, base_map)
                info.update(mnem=low, addr_src=addr, label=label,
                            evidence='%s:%d' % (source, lineno))
                recs.append(info)
            else:
                recs.append({
                    'kind': 'branch', 'zone': zone, 'mnem': low,
                    'target': core or operand,
                    'target_zone': None, 'addr_src': addr, 'label': label,
                    'note': 'DIRECT_BRANCH',
                    'evidence': '%s:%d' % (source, lineno),
                })
    return recs


def scan_file(path, zone, rel, base_map):
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as fh:
        return parse_listing(fh.read(), zone, rel, base_map)


def read_xref_meta(path=XREF_FILE):
    """Только шапка устаревшего xref.txt; логика графа её не использует."""
    meta = {'files': None, 'calls': None, 'branches': None}
    if not os.path.isfile(path):
        return meta
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = re.search(r'# файлов \.asm:\s*(\d+)', line)
            if m:
                meta['files'] = int(m.group(1))
            m = re.search(r'переходы BR=(\d+)\s+вызовы CALL=(\d+)', line)
            if m:
                meta['branches'] = int(m.group(1))
                meta['calls'] = int(m.group(2))
    return meta


def count_all_asm_calls(folder):
    """Число CALL-строк во всех .asm каталога (для честной сверки).

    Повторяем правило tools/xref.py: строка, помеченная
    '* next insn used as data', в счёт CALL не идёт.
    """
    total, raw, files = 0, 0, 0
    if not os.path.isdir(folder):
        return files, total, raw
    for name in sorted(os.listdir(folder)):
        if not name.endswith('.asm'):
            continue
        files += 1
        pending_data = False
        with open(os.path.join(folder, name), 'r',
                  encoding='utf-8-sig', errors='replace') as fh:
            for line in fh:
                if line.startswith('*') and 'used as data' in line:
                    pending_data = True
                    continue
                has_addr, _addr, _lab, mnem, _op = parse_line_mcg(line)
                as_data = pending_data and has_addr
                if has_addr:
                    pending_data = False
                if not mnem or mnem.lower() not in CALL_MNEM:
                    continue
                raw += 1
                if not as_data:
                    total += 1
    return files, total, raw


def build(root=ROOT):
    """Собрать полный граф. Чистая функция от содержимого файлов."""
    base_map = read_base_map(os.path.join(root, 'analysis',
                                          'ZONE-BASE-MAP.md'))
    dis_dir = os.path.join(root, 'dis')
    forced_dir = os.path.join(root, 'dis-forced')
    xref_path = os.path.join(root, 'analysis', 'xref.txt')

    zones = {}
    all_records = []
    for zone, group, fname in zone_catalog():
        path = os.path.join(dis_dir, fname)
        if not os.path.isfile(path):
            continue
        recs = scan_file(path, zone, 'dis/' + fname, base_map)
        all_records.extend(recs)
        counts = Counter(r['kind'] for r in recs)
        targets = defaultdict(lambda: {'count': 0, 'evidence': [],
                                       'kind': '', 'target_zone': None})
        for r in recs:
            if r['kind'] in ('internal', 'external'):
                t = targets[r['target']]
                t['count'] += 1
                t['kind'] = r['kind']
                t['target_zone'] = r['target_zone']
                t['evidence'].append(r['evidence'])
        info = base_map.get(zone, {})
        zones[zone] = {
            'group': group,
            'file': 'dis/' + fname,
            'base': info.get('base'),
            'base_status': info.get('status', STATUS_UNKNOWN),
            'candidate': info.get('candidate', False),
            'counts': {
                'internal': counts['internal'],
                'external': counts['external'],
                'indirect': counts['indirect'],
                'unknown': counts['unknown'],
                'branch': counts['branch'],
            },
            'targets': [
                {'target': t, 'zone': v['target_zone'],
                 'kind': v['kind'], 'count': v['count'],
                 'evidence': v['evidence']}
                for t, v in sorted(targets.items())
            ],
            'branches': [
                {'mnem': r['mnem'], 'target': r['target'],
                 'evidence': r['evidence']}
                for r in recs if r['kind'] == 'branch'
            ],
        }

    # Рёбра собираются напрямую по паре (зона-источник, зона-цель).
    edge_map = defaultdict(lambda: {'count': 0, 'evidence': []})
    for r in all_records:
        if r['kind'] in ('internal', 'external') and r['target_zone']:
            key = (r['zone'], r['target_zone'], r['kind'])
            edge_map[key]['count'] += 1
            edge_map[key]['evidence'].append(r['evidence'])
    edges = [
        {'caller': z, 'target': tz, 'kind': kind,
         'count': v['count'], 'evidence': v['evidence'][:12]}
        for (z, tz, kind), v in sorted(edge_map.items())
    ]

    procs = defaultdict(lambda: {'count': 0, 'evidence': [], 'kind': '',
                                 'zone': None})
    for r in all_records:
        if r['kind'] in ('internal', 'external'):
            key = (r['zone'], r['target'])
            p = procs[key]
            p['count'] += 1
            p['kind'] = r['kind']
            p['zone'] = r['target_zone']
            p['evidence'].append(r['evidence'])
    top = [
        {'caller': z, 'target': t, 'target_zone': v['zone'],
         'kind': v['kind'], 'count': v['count'],
         'evidence': v['evidence'][:8]}
        for (z, t), v in sorted(procs.items(),
                                key=lambda kv: -kv[1]['count'])[:10]
    ]

    cf, cc, cr = count_all_asm_calls(dis_dir)
    ff, fc, fr = count_all_asm_calls(forced_dir)
    meta = {
        'zones_total': len(zones),
        'canonical_files': len(zones),
        'asm_files_all': cf,
        'call_lines_all_asm': cc,
        'call_lines_raw': cr,
        'forced_files': ff,
        'call_lines_forced': fc,
        'call_lines_forced_raw': fr,
        'xref_stale': read_xref_meta(xref_path),
        'base_map_status': {
            STATUS_FACT: sum(1 for v in base_map.values()
                             if v['status'] == STATUS_FACT),
            STATUS_HYP: sum(1 for v in base_map.values()
                            if v['status'] == STATUS_HYP),
            STATUS_UNKNOWN: sum(1 for v in base_map.values()
                                if v['status'] == STATUS_UNKNOWN),
        },
    }
    return {'meta': meta, 'zones': zones, 'adjacency': edges,
            'top_procedures': top}


def render_text(graph, zone=None):
    """Текстовый вид, ширина строки <=60."""
    out = []
    m = graph['meta']
    out.append('СТАТИЧЕСКИЙ ГРАФ ВЫЗОВОВ 69 ЗОН')
    out.append('файлов зон: %d, .asm всего: %d' %
               (m['zones_total'], m['asm_files_all']))
    xs = m['xref_stale']
    out.append('xref.txt (устарел): файлов %s, CALL %s' %
               (xs['files'], xs['calls']))
    out.append('сейчас: CALL в dis/ %d (сырых %d)' %
               (m['call_lines_all_asm'], m['call_lines_raw']))
    out.append('сейчас: CALL в dis-forced/ %d' % m['call_lines_forced'])
    out.append('')

    zones = graph['zones']
    if zone:
        zones = {zone: zones[zone]} if zone in zones else {}

    out.append('ЗОНА  ГРУППА БАЗА   СТАТУС        ВН  ВНЕШ КОСВ НЕИЗВ')
    out.append('----- ------ ----- ------------ -- ---- ---- -----')
    for z, d in zones.items():
        c = d['counts']
        base = '%05o' % d['base'] if d['base'] is not None else '-'
        st = d['base_status']
        if d['candidate']:
            st += '?'
        out.append('%-5s %-6s %-5s %-12s %2d %4d %4d %5d' %
                   (z, d['group'], base, st, c['internal'],
                    c['external'], c['indirect'], c['unknown']))
    out.append('')

    adj = graph['adjacency']
    if zone:
        adj = [e for e in adj if e['caller'] == zone]
    loops = [e for e in adj if e['caller'] == e['target']]
    out.append('ПЕТЛИ (внутренние): %d пар' % len(loops))
    for e in loops[:8]:
        out.append('%s -> %s  %3d  %s' %
                   (e['caller'], e['target'], e['count'],
                    e['evidence'][0] if e['evidence'] else '-'))
    out.append('')

    out.append('РЁБРА (внешние, caller -> target)')
    ext = [e for e in adj if e['caller'] != e['target']]
    for e in ext[:40]:
        out.append('%s -> %-11s %3d  %s' %
                   (e['caller'], e['target'], e['count'],
                    e['evidence'][0] if e['evidence'] else '-'))
    if not ext:
        out.append('(внешних рёбер нет)')
    out.append('')

    out.append('ТОП-10 ПРОЦЕДУР')
    top = graph['top_procedures']
    if zone:
        top = [p for p in top if p['caller'] == zone]
    for p in top:
        out.append('%s:%s  %3d  %-10s %s' %
                   (p['caller'], p['target'], p['count'],
                    p['kind'], p['evidence'][0] if p['evidence'] else '-'))
    return '\n'.join(out) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--format', choices=('json', 'text'), default='text')
    ap.add_argument('--zone', help='только одна зона, например 0147')
    args = ap.parse_args(argv)

    graph = build()
    if args.zone:
        z = args.zone
        if z not in graph['zones']:
            print('нет зоны %s' % z, file=sys.stderr)
            return 2
        graph['zones'] = {z: graph['zones'][z]}
        graph['adjacency'] = [e for e in graph['adjacency']
                              if e['caller'] == z]
        graph['top_procedures'] = [p for p in graph['top_procedures']
                                   if p['caller'] == z]

    if args.format == 'json':
        print(json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_text(graph, args.zone))
    return 0


if __name__ == '__main__':
    sys.exit(main())
