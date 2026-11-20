#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""asm_zone_links.py - cross-zone address links in ASM ITM full listings.

Scans dis/ASM-Z*-full.asm (forced W_CODE listings) and reports, for
each address value, which zones 0055/0056/0057/0060 reference it, in
which instruction, and whether the code stored at that same offset is
identical or different across zones (normalized instruction lines).

Operand parsing REUSES the proven code tools/global_xref.py:
HEAD_RE, file_zone and parse_line_operand (XREF-METHODOLOGY section 3).
That parser is already validated on all dis/*.asm listings. No input
file (gold/, dis/, bemsh/) is modified.

Usage:
  python3 tools/asm_zone_links.py
  python3 tools/asm_zone_links.py --value 3604
  python3 tools/asm_zone_links.py --dir dis --min-zones 2
  python3 tools/asm_zone_links.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

import global_xref as G  # noqa: E402

# Proven constants and parser from tools/global_xref.py.
HEAD_RE = G.HEAD_RE
file_zone = G.file_zone
parse_line_operand = G.parse_line_operand

LABEL_ONLY_RE = re.compile(r'^(?:[AD][0-7]{5}|START)$')

# Data / pseudo mnemonics: never a real instruction for cell comparison.
DATA_MNEM = set(G.DATA_MNEM) | {'nop', 'ноп'}

# Control-transfer mnemonics (PROCEDURES-ASM.md section 1.4).
CALL_MNEMONICS = frozenset({'пв'})
BRANCH_MNEMONICS = frozenset({'пб', 'по', 'пе', 'цикл', 'пио',
                              'пино', 'выпр'})
TRANSFER_MNEMONICS = CALL_MNEMONICS | BRANCH_MNEMONICS

# Zone-internal offsets are below 02000 (one zone = 1024 words).
ZONE_WORDS = G.ZONE_WORDS


@dataclass
class Ref:
    """One numeric address reference found in a disbesm6 instruction."""

    zone: str
    addr: object          # octal offset of the containing word, or None
    line: int             # 1-based line number in the .asm file
    mnem: str
    operand: str
    raw: str              # operand token as extracted by parse_line_operand
    kind: str             # OCT / LBL / NUM
    value: int            # octal integer value
    transfer: bool        # CALL or branch instruction


@dataclass
class ZoneData:
    """Parsed content of one ASM-Z*-full.asm listing."""

    zone: str
    src: str
    cells: dict = field(default_factory=dict)   # addr -> ((mnem, op), ...)
    refs: list = field(default_factory=list)


def split_line(line):
    """Split one disbesm6 line into (addr, has_addr, label, mnem, op).

    Handles both the normal 'addr:fields <tab> label <tab> mnem <tab> op'
    layout and the label-only 'START <tab> mnem <tab> op' layout that
    disbesm6 prints for the decoded word 0.
    """
    parts = line.rstrip('\n').split('\t')
    addr = None
    has_addr = False
    toks = []
    for part in parts:
        if not part.strip():
            continue
        m = HEAD_RE.match(part)
        if m:
            addr_field = m.group(1).strip()
            if addr_field:
                try:
                    addr = int(addr_field, 8)
                except ValueError:
                    addr = None
                has_addr = True
            continue
        toks.append(part.strip())
    if not toks:
        return None
    label = ''
    if len(toks) >= 2 and LABEL_ONLY_RE.match(toks[0]):
        label = toks[0]
        toks = toks[1:]
    if not toks:
        return None
    mnem = toks[0]
    operand = toks[1] if len(toks) > 1 else ''
    return addr, has_addr, label, mnem, operand


def parse_zone(path):
    """Parse one full listing into a ZoneData object."""
    zone = file_zone(path)
    data = ZoneData(zone, os.path.basename(path))
    cur = None
    pending_data = False
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip('\n')
            if line.startswith('*'):
                if 'used as data' in line:
                    pending_data = True
                continue
            parsed = split_line(line)
            if parsed is None:
                continue
            addr, has_addr, label, mnem, operand = parsed
            if has_addr:
                cur = addr
                pending_data = False
            as_data = pending_data and has_addr
            low = mnem.lower()
            if cur is not None and low not in DATA_MNEM:
                data.cells.setdefault(cur, []).append((low, operand))
            for kind, key, rraw, value in parse_line_operand(mnem, operand,
                                                             as_data):
                if kind not in ('OCT', 'LBL', 'IMM'):
                    continue
                if kind == 'IMM':
                    # Only a numeric CALL operand is an address here.
                    # disbesm6 prints it as the decimal form of the
                    # octal address (AGENTS section 2): 16 -> 020.
                    if low not in CALL_MNEMONICS:
                        continue
                    octal = int(str(value), 10) if value is not None else None
                    kind = 'NUM'
                else:
                    octal = value
                if octal is None or octal < 0:
                    continue
                data.refs.append(Ref(zone, cur, lineno, low, operand, rraw,
                                     kind, octal,
                                     low in TRANSFER_MNEMONICS))
    return data


def scan(directory):
    """Scan all dis/ASM-Z*-full.asm in *directory* (default: repo dis/)."""
    if not os.path.isabs(directory):
        directory = os.path.join(ROOT, directory)
    names = sorted(n for n in os.listdir(directory)
                   if n.startswith('ASM-Z') and n.endswith('-full.asm'))
    return [parse_zone(os.path.join(directory, n)) for n in names]


def oct_key(value):
    """Canonical octal string for an integer address value."""
    return '%o' % value


def group_by_value(datas):
    """Map an octal address string to all references to it."""
    by = defaultdict(list)
    for data in datas:
        for ref in data.refs:
            by[oct_key(ref.value)].append(ref)
    return by


def cell_pairs(datas, value):
    """Compare normalized code at one offset across zones.

    Returns a list of (zone_a, zone_b, identical) triples.
    """
    try:
        v = int(value, 8)
    except (TypeError, ValueError):
        return []
    have = [(d.zone, tuple(d.cells[v]))
            for d in datas if v in d.cells]
    pairs = []
    for i in range(len(have)):
        for j in range(i + 1, len(have)):
            pairs.append((have[i][0], have[j][0],
                          have[i][1] == have[j][1]))
    return pairs


def cell_summary(datas, value):
    """Short cell-status label for an address value."""
    try:
        v = int(value, 8)
    except (TypeError, ValueError):
        return '?'
    if v >= ZONE_WORDS:
        return 'вне зоны'
    pairs = cell_pairs(datas, value)
    if not pairs:
        return 'н/д'
    return 'ДА' if all(same for _, _, same in pairs) else 'НЕТ'


def cross_zone(datas, min_zones=2, all_kinds=False):
    """Rows for address values referenced in at least *min_zones* zones.

    By default a row needs either an absolute quoted address (OCT) or
    a control-transfer reference (CALL/branch). With *all_kinds* every
    numeric operand, including working-cell references, is kept.
    """
    by = group_by_value(datas)
    rows = []
    for value in by:
        refs = by[value]
        zones = sorted({r.zone for r in refs})
        if len(zones) < min_zones:
            continue
        if not all_kinds and not any(r.kind == 'OCT' or r.transfer
                                     for r in refs):
            continue
        rows.append({'value': value, 'zones': zones, 'refs': refs,
                     'nrefs': len(refs),
                     'transfers': sum(1 for r in refs if r.transfer),
                     'cells': cell_summary(datas, value),
                     'pairs': cell_pairs(datas, value)})
    rows.sort(key=lambda r: (-len(r['zones']), int(r['value'], 8)))
    return rows


def format_report(datas, rows, value=None):
    """Human-readable report, every line at most 60 columns."""
    out = ['ASM ITM: %d zones, %d cross-zone values'
           % (len(datas), len(rows)), '']
    if value is not None:
        selected = [r for r in rows if r['value'] == value]
        if not selected:
            by = group_by_value(datas)
            refs = by.get(value, [])
            selected = [{'value': value,
                         'zones': sorted({r.zone for r in refs}),
                         'refs': refs, 'nrefs': len(refs),
                         'transfers': sum(1 for r in refs if r.transfer),
                         'cells': cell_summary(datas, value),
                         'pairs': cell_pairs(datas, value)}]
        for row in selected:
            out.append('value=%s zones=%s refs=%d cell=%s'
                       % (row['value'], ' '.join(row['zones']),
                          row['nrefs'], row['cells']))
            out.append('')
            for r in row['refs']:
                w = oct_key(r.addr) if r.addr is not None else '-'
                out.append('%s %s:%s L%d %s %s'
                           % (r.zone, w, r.kind, r.line,
                              r.mnem, r.operand))
            out.append('')
            for a, b, same in row['pairs']:
                out.append('%s %s %s' % (a, '=' if same else '!=', b))
        return '\n'.join(out)
    out.append('value  zones                     refs  cells')
    for row in rows:
        zs = ' '.join(row['zones'])
        out.append('%-6s %-26s %4d  %s'
                   % (row['value'], zs, row['nrefs'], row['cells']))
    return '\n'.join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--dir', default='dis', help='directory with listings')
    ap.add_argument('--value', default=None,
                    help='show detail for one octal address value')
    ap.add_argument('--min-zones', type=int, default=2,
                    help='minimum zones for a cross-zone row (default 2)')
    ap.add_argument('--all-kinds', action='store_true',
                    help='include plain working-cell data references')
    ap.add_argument('--limit', type=int, default=0,
                    help='max text rows (0 = all)')
    ap.add_argument('--json', action='store_true',
                    help='emit JSON instead of text')
    args = ap.parse_args(argv)

    datas = scan(args.dir)
    rows = cross_zone(datas, args.min_zones, args.all_kinds)
    if not args.json and args.limit > 0:
        rows = rows[:args.limit]
    if args.json:
        payload = []
        for row in rows:
            payload.append({
                'value': row['value'], 'zones': row['zones'],
                'refs': [{'zone': r.zone, 'addr': r.addr, 'line': r.line,
                          'mnem': r.mnem, 'operand': r.operand,
                          'kind': r.kind, 'value': oct_key(r.value),
                          'transfer': r.transfer} for r in row['refs']],
                'cells': row['cells'],
                'pairs': [{'a': a, 'b': b, 'identical': s}
                          for a, b, s in row['pairs']],
            })
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    else:
        print(format_report(datas, rows, args.value))
    return 0


if __name__ == '__main__':
    sys.exit(main())
