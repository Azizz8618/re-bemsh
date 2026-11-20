#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Каталог текстов PROGRAM 2 (0137-0177) со ссылками из global_xref.tsv.

Вход (только чтение):
  docs/TEXT-CONSTANTS-ALL.md   -- декодированные фразы B-зон
  docs/SEMANTIC/B-TEXT-ENRICHMENT.md -- топ-30 сообщений (дополнение)
  docs/SEMANTIC/Z<зона>.md     -- роль/эвиденс текста
  analysis/global_xref.tsv     -- ссылки из листингов
  analysis/MEMORY-MAP.md       -- база загрузки зоны (для абс. адресов)

Выход: таблица
  текст | кодировка | текст | смысл | число ссылок | источники | уверенность
"""

import argparse
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

P2_MIN = 0o137
P2_MAX = 0o177

# Базовые адреса ОП из analysis/MEMORY-MAP.md §5 (12 привязанных зон).
# Ключ -- восьмеричный номер зоны, значение -- восьмеричная база.
MEM_BASE = {
    '0147': '00000', '0150': '70000', '0153': '74000',
    '0154': '02000', '0155': '04000', '0156': '06000',
    '0157': '76000', '0161': '24000', '0162': '26000',
    '0174': '72000', '0175': '72000', '0177': '72000',
}

ROLE_WORDS = (
    'штамп', 'диагн.', 'шапка', 'маркеры', 'запрос', 'сообщ.',
    'заголов.', 'вывод', 'текст', 'таблица',
)

ADDR_RE = re.compile(
    r'^(\d{4})\.(\d{3,4})(?:\D+(\d{4})\.(\d{3,4}))?$')
ENRICH_RE = re.compile(
    r'^\s*\d{2}\s+(\d{4})\.(\d{3,4})-(\d{2,4})\s+(.+?)\s{2,}(\S.*?)\s*$')
ZONE_FILE_RE = re.compile(r'(?:^|[-Z])(\d{4})')


def _zok(zone):
    """Истина, если зона относится к PROGRAM 2."""
    try:
        return P2_MIN <= int(zone, 8) <= P2_MAX
    except (TypeError, ValueError):
        return False


def load_catalog(path=None):
    """Прочитать фразы B-зон из TEXT-CONSTANTS-ALL.md.

    Возвращает список словарей: zone, first, last, enc, text, meaning,
    evidence, conf, section, source.
    """
    path = path or os.path.join(REPO, 'docs', 'TEXT-CONSTANTS-ALL.md')
    out = []
    section = ''
    with open(path, encoding='utf-8') as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip('\n')
            if line.startswith('### '):
                section = line[4:].strip()
            if not line.startswith('|'):
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if len(cells) < 11:
                continue
            m = ADDR_RE.match(cells[0])
            if not m:
                continue
            zone = m.group(1)
            if not _zok(zone):
                continue
            first = int(m.group(2), 8)
            last = int(m.group(4), 8) if m.group(4) else first
            out.append({
                'zone': zone,
                'first': first,
                'last': last,
                'addr': cells[0],
                'enc': cells[6],
                'text': cells[7],
                'meaning': cells[8],
                'evidence': cells[9],
                'conf': cells[10],
                'section': section,
                'src': 'TA:%d' % lineno,
            })
    return out


def load_enrichment(path=None):
    """Добавить сообщения из топ-30 B-TEXT-ENRICHMENT.md.

    Фразы, уже присутствующие в каталоге (по зоне и первому слову),
    не дублируются.
    """
    path = path or os.path.join(
        REPO, 'docs', 'SEMANTIC', 'B-TEXT-ENRICHMENT.md')
    out = []
    with open(path, encoding='utf-8') as fh:
        for lineno, raw in enumerate(fh, 1):
            m = ENRICH_RE.match(raw.rstrip('\n'))
            if not m:
                continue
            zone, a, b_short, text, kind = m.groups()
            if not _zok(zone):
                continue
            # В топ-30 конец пишется сокращённо: 1732-36 = 1732-1736.
            b = b_short if len(b_short) == len(a) else \
                a[:len(a) - len(b_short)] + b_short
            out.append({
                'zone': zone,
                'first': int(a, 8),
                'last': int(b, 8),
                'addr': '%s.%s-%s' % (zone, a, b_short),
                'enc': 'GOST',
                'text': text.strip(),
                'meaning': kind.strip(),
                'evidence': 'BTE:%d' % lineno,
                'conf': '',
                'section': 'сообщения (топ-30)',
                'src': 'BTE:%d' % lineno,
            })
    return out


def catalog(path=None, enrich_path=None):
    """Объединить каталог и топ-30, убрав дубли по (зона, слово)."""
    rows = load_catalog(path)
    seen = {(r['zone'], r['first']) for r in rows}
    for r in load_enrichment(enrich_path):
        if (r['zone'], r['first']) not in seen:
            seen.add((r['zone'], r['first']))
            rows.append(r)
    rows.sort(key=lambda r: (int(r['zone'], 8), r['first']))
    return rows


def load_zone_roles(root=None):
    """Роль зоны из docs/SEMANTIC/Z<зона>.md (первая строка 'Роль:')."""
    root = root or os.path.join(REPO, 'docs', 'SEMANTIC')
    roles = {}
    if not os.path.isdir(root):
        return roles
    for name in os.listdir(root):
        m = re.fullmatch(r'Z(\d{4})\.md', name)
        if not m or not _zok(m.group(1)):
            continue
        with open(os.path.join(root, name), encoding='utf-8') as fh:
            text = fh.read()
        rm = re.search(r'^\s*Роль:\s*(.+)$', text, re.M)
        if rm:
            roles[m.group(1)] = rm.group(1).strip()
        else:
            hm = re.search(r'^#\s+(.+)$', text, re.M)
            roles[m.group(1)] = hm.group(1).strip() if hm else ''
    return roles


def load_xref(path=None):
    """Прочитать analysis/global_xref.tsv.

    Возвращает dict: target -> список dict(zones, label, count, sources).
    """
    path = path or os.path.join(REPO, 'analysis', 'global_xref.tsv')
    idx = defaultdict(list)
    with open(path, encoding='utf-8') as fh:
        fh.readline()
        for line in fh:
            p = line.rstrip('\n').split('\t')
            if len(p) < 5:
                continue
            idx[p[0]].append({
                'zones': set(p[1].split(',')),
                'label': p[2],
                'count': int(p[3]) if p[3].isdigit() else 0,
                'sources': p[4],
            })
    return idx


def file_zone(name):
    """Восьмеричный номер зоны из имени файла листинга.

    Источники бывают из ASM (0055-0060), B (0137-0177) и B2
    (0540-0577); все три набора допустимы как источники ссылок.
    """
    m = ZONE_FILE_RE.search(name)
    if not m:
        return ''
    z = m.group(1)
    try:
        return z if 0o40 <= int(z, 8) <= 0o577 else ''
    except ValueError:
        return ''


def parse_sources(field):
    """Разобрать 'Z0144.asm:197:сч; ...' в список (зона, линия, мнем)."""
    out = []
    for chunk in field.split(';'):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r'^([^:]+):(\d+):(\S+)$', chunk)
        if not m:
            continue
        out.append((file_zone(m.group(1)), m.group(2), m.group(3)))
    return out


def _oct5(value):
    return format(value, '05o')


def candidate_targets(row):
    """Возможные представления адреса текста в global_xref.tsv.

    Возвращает список (target, kind). kind: 'label' или 'absolute'.
    """
    zone = row['zone']
    words = list(range(row['first'], min(row['last'], row['first'] + 7) + 1))
    out = []
    for w in words:
        out.append(('A' + _oct5(w), 'label'))
        out.append(('D' + _oct5(w), 'label'))
    if zone in MEM_BASE:
        base = int(MEM_BASE[zone], 8)
        for w in words:
            absv = base + w
            o = format(absv, 'o')
            out.append(('OCT:' + o, 'absolute'))
            out.append(('A' + _oct5(absv), 'absolute'))
            out.append(('D' + _oct5(absv), 'absolute'))
    return out


def find_refs(row, xref):
    """Найти ссылки на текст в global_xref.tsv.

    Возвращает (refs, label). refs -- список dict:
      zone, addr, mnem, target, label, kind, confidence.
    """
    refs = []
    seen = set()
    for target, kind in candidate_targets(row):
        for entry in xref.get(target, ()):
            if kind == 'label' and row['zone'] not in entry['zones']:
                continue
            for z, addr, mnem in parse_sources(entry['sources']):
                if kind == 'label' and z != row['zone']:
                    continue
                key = (z, addr, mnem, target)
                if key in seen:
                    continue
                seen.add(key)
                refs.append({
                    'zone': z,
                    'addr': addr,
                    'mnem': mnem,
                    'target': target,
                    'label': entry['label'],
                    'kind': kind,
                    'confidence': 'средний' if kind == 'label' else 'низкий',
                })
    # Абсолютные совпадения с ролью MEM_* -- только кандидаты.
    refs.sort(key=lambda r: (r['kind'] != 'label', r['zone'],
                             int(r['addr']) if r['addr'].isdigit() else 0,
                             r['mnem']))
    return refs


def zone_role(zone, roles, row=None):
    """Роль текста: из Z<зона>.md, иначе из смысла каталога."""
    r = roles.get(zone, '')
    if r:
        return r
    if row:
        return row.get('meaning', '')
    return ''


def build(path=None, enrich_path=None, xref_path=None, root=None):
    """Собрать итоговые строки: текст + роль + ссылки."""
    rows = catalog(path, enrich_path)
    xref = load_xref(xref_path)
    roles = load_zone_roles(root)
    out = []
    for row in rows:
        refs = find_refs(row, xref)
        out.append({
            'addr': row['addr'],
            'zone': row['zone'],
            'enc': row['enc'],
            'text': row['text'],
            'meaning': row['meaning'],
            'role': zone_role(row['zone'], roles, row),
            'catalog_conf': row['conf'],
            'section': row['section'],
            'src': row['src'],
            'refs': refs,
            'ref_count': len(refs),
        })
    return out


def _clip(s, n):
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + '?'


def format_table(rows):
    """Одномерная таблица с семью колонками по заданию."""
    head = ('адрес текста', 'кодировка', 'расшифровка', 'смысл',
            'ссылок', 'источники (зона:адр мнем)', 'уверенность')
    lines = [' | '.join(head), ' | '.join(['---'] * len(head))]
    for r in rows:
        srcs = '; '.join(
            '%s:%s %s' % (x['zone'] or '??', x['addr'], x['mnem'])
            for x in r['refs'][:6])
        if not srcs:
            srcs = '-'
        conf = r['catalog_conf'] or 'высокий'
        lines.append(' | '.join([
            r['addr'], r['enc'], _clip(r['text'], 44),
            _clip(r['meaning'] or r['role'], 30),
            str(r['ref_count']), _clip(srcs, 54), conf,
        ]))
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', help='записать таблицу в файл')
    ap.add_argument('--min-refs', type=int, default=0,
                    help='показывать только строки с числом ссылок >= N')
    args = ap.parse_args(argv)
    rows = build()
    if args.min_refs:
        rows = [r for r in rows if r['ref_count'] >= args.min_refs]
    table = format_table(rows)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as fh:
            fh.write(table + '\n')
        print('записано строк: %d -> %s' % (len(rows), args.out))
    else:
        print(table)
    return 0


if __name__ == '__main__':
    sys.exit(main())
