#!/usr/bin/env python3
"""Stream a dispak -tt trace and build a dynamic call graph.

Read the trace one line at a time.  Nothing is loaded
into memory as a whole.  The input is stderr of
"dispak -l -tt", for example
/tmp/.private/azizz/arap-dyn/B-explore.err.

Only EXECUTED instructions are counted.  cu.c prints
an instruction as "%05o: %-4s" with abpc (the PC).
A store line is indented and carries the WRITE
ADDRESS before the colon:

       165465: store 2031463100000000

Such a line is not an instruction and never enters
the PC stream.

Page = PC / 02000(8) = PC >> 10.  Page labels follow
analysis/PROC-LABEL-SCOPE-DYN.md, octal page numbers.
Zone candidates come from ZONE-BASE-MAP.md section 4.
A page may hold several zones at different times, so
a zone is never asserted from a PC alone.

No emulator, image or dispak run is needed.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict

# Instruction lines start at column 0.  Indented store
# lines do not match INSN_RE.
INSN_RE = re.compile(
    r'^([0-7]{5,6}):[ \t]+([^ \t]+)[ \t]*(.*)$')
STORE_RE = re.compile(r'^[ \t]+([0-7]+):[ \t]+store\b')
REGVAL_RE = re.compile(r'\br\[([0-7]+)\]=([0-7]+)')
OPERAND_RE = re.compile(r'(-?)([0-7]+)?(?:\(([0-7]+)\))?')

MASK = 0o77777
MAXTOP = 500
DEFAULT_TOP = 20

# Decimal page -> label and zone candidates (octal zones).
# Source: ZONE-BASE-MAP.md sections 3-5 and
# PROC-LABEL-SCOPE-DYN.md section 2.
PAGE_ZONES = {
    0: ('0147', '0147 @ 00000'),
    1: ('0154/0170/0172', 'overlay @ 02000'),
    2: ('0155/0171', 'overlay @ 04000'),
    3: ('0156', '0156 @ 06000'),
    6: ('0072', '0072 @ 014000'),
    7: ('0073', '0073 @ 016000'),
    10: ('0161', '0161 @ 24000'),
    11: ('0162', '0162 @ 26000'),
    24: ('monitor 64xxx', 'MON'),
    25: ('monitor 64xxx', 'MON'),
    26: ('monitor 64xxx', 'MON'),
    27: ('monitor 64xxx', 'MON'),
    28: ('0150', '0150 @ 070000'),
    30: ('0151/0153', 'ARAP overlay @ 074000'),
    31: ('0152/0157', 'ARAP overlay @ 076000'),
}

CALL_MNEMONICS = ('vjm', 'uj')


def operand_number(operand):
    """Leading octal literal, folded to a 15-bit address."""
    if not operand:
        return None
    m = OPERAND_RE.match(operand.strip())
    if not m or not m.group(2):
        return None
    value = int(m.group(2), 8)
    if m.group(1) == '-':
        # cu.c prints a negative as -(N).
        return (0o100000 - value) & MASK
    return value & MASK


def parse_line(line):
    """Return an instruction record, or None otherwise."""
    if not isinstance(line, str):
        return None
    text = line.rstrip('\n')
    m = INSN_RE.match(text)
    if not m:
        return None
    pc = int(m.group(1), 8)
    mnemonic = m.group(2)
    rest = m.group(3)
    field = rest.split(' (=', 1)[0]
    field = field.split(' acc=', 1)[0].strip()
    rm = re.search(r'\(([0-7]+)\)', field)
    reg = int(rm.group(1), 8) if rm else None
    reg_value = None
    if reg is not None:
        rv = re.search(r'\br\[%o\]=([0-7]+)' % reg, text)
        if rv:
            reg_value = int(rv.group(1), 8)
    else:
        rv = REGVAL_RE.search(text)
        if rv:
            reg_value = int(rv.group(2), 8)
    return {
        'pc': pc,
        'page': pc >> 10,
        'mnemonic': mnemonic,
        'operand': field,
        'number': operand_number(field),
        'reg': reg,
        'reg_value': reg_value,
        'raw': text,
    }


def call_target(rec):
    """Resolve a jump target, or None if unavailable."""
    # vjm: the register is a LINK, the literal is
    # the only target.
    if rec['mnemonic'] == 'vjm':
        return rec['number']
    # uj: EA = literal + r[idx], 15-bit wrap.
    if rec['mnemonic'] == 'uj':
        if (rec['number'] is None and
                rec['reg_value'] is None):
            return None
        value = (rec['number'] or 0)
        value += (rec['reg_value'] or 0)
        return value & MASK
    return None


def page_info(page):
    zones, note = PAGE_ZONES.get(page, (None, 'unmapped'))
    return {
        'page': page,
        'page_octal': '%02o' % page,
        'zones': zones,
        'note': note,
    }


class TraceStats(object):
    def __init__(self, samples=2):
        self.lines = 0
        self.instructions = 0
        self.store_lines = 0
        self.other_lines = 0
        self.insn_by_page = Counter()
        self.targets_by_page = defaultdict(set)
        self.callers_by_page = defaultdict(set)
        self.edges = Counter()
        self.calls_by_kind = Counter()
        self.calls_resolved = 0
        self.calls_unresolved = 0
        self.evidence = defaultdict(list)
        self.store_sample = None
        self.samples = samples

    def feed(self, line):
        self.lines += 1
        if STORE_RE.match(line):
            self.store_lines += 1
            if self.store_sample is None:
                self.store_sample = line.rstrip('\n')
            return
        rec = parse_line(line)
        if rec is None:
            self.other_lines += 1
            return
        self.instructions += 1
        page = rec['page']
        self.insn_by_page[page] += 1
        if len(self.evidence[page]) < self.samples:
            self.evidence[page].append(rec['raw'])
        if rec['mnemonic'] not in CALL_MNEMONICS:
            return
        self.calls_by_kind[rec['mnemonic']] += 1
        target = call_target(rec)
        if target is None:
            self.calls_unresolved += 1
            return
        self.calls_resolved += 1
        dst = target >> 10
        self.targets_by_page[page].add(target)
        self.callers_by_page[dst].add(page)
        self.edges[(page, dst)] += 1

    def result(self, top):
        pages = []
        items = self.insn_by_page.most_common(top)
        for page, count in items:
            info = page_info(page)
            targets = self.targets_by_page.get(page, ())
            callers = self.callers_by_page.get(page, ())
            info.update({
                'instructions': count,
                'distinct_targets': len(targets),
                'callers': sorted(callers),
                'callers_octal': [
                    '%02o' % p for p in callers],
                'evidence': self.evidence.get(page, []),
            })
            pages.append(info)
        edges = []
        items = self.edges.most_common(top)
        for (src, dst), count in items:
            edges.append({
                'src': '%02o' % src,
                'dst': '%02o' % dst,
                'calls': count,
                'src_zones': page_info(src)['zones'],
                'dst_zones': page_info(dst)['zones'],
            })
        return {
            'lines': self.lines,
            'instructions': self.instructions,
            'store_lines': self.store_lines,
            'other_lines': self.other_lines,
            'calls_vjm': self.calls_by_kind['vjm'],
            'calls_uj': self.calls_by_kind['uj'],
            'calls_resolved': self.calls_resolved,
            'calls_unresolved': self.calls_unresolved,
            'pages_total': len(self.insn_by_page),
            'edges_total': len(self.edges),
            'store_sample': self.store_sample,
            'top': top,
            'pages': pages,
            'edges': edges,
        }


def render_text(res, path):
    out = []
    out.append('MODULE CALL TRACE (dynamic, page level)')
    out.append('trace: %s' % path)
    out.append('lines %d | instructions %d | stores %d'
               ' | other %d'
               % (res['lines'], res['instructions'],
                  res['store_lines'], res['other_lines']))
    out.append('vjm %d | uj %d | resolved %d'
               ' | unresolved %d'
               % (res['calls_vjm'], res['calls_uj'],
                  res['calls_resolved'],
                  res['calls_unresolved']))
    out.append('pages with code %d | page edges %d'
               % (res['pages_total'], res['edges_total']))
    out.append('')
    out.append('TOP EXECUTED PAGES (limit %d)' % res['top'])
    out.append('page | zone       | cmd | goals | callers')
    for p in res['pages']:
        zones = p['zones'] or '?'
        out.append(' %-4s| %-11s | %8d | %7d | %s'
                   % (p['page_octal'], zones[:11],
                      p['instructions'],
                      p['distinct_targets'],
                      ','.join(p['callers_octal']) or '-'))
        for sample in p['evidence']:
            out.append('      e: %s' % sample[:55])
    out.append('')
    out.append('TOP PAGE EDGES (limit %d)' % res['top'])
    out.append('src -> dst | calls')
    for e in res['edges']:
        out.append(' %s -> %s | %d'
                   % (e['src'], e['dst'], e['calls']))
    if res['store_sample']:
        out.append('')
        out.append('store sample (address before colon):')
        out.append(' %s' % res['store_sample'][:55])
    return '\n'.join(out) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Build a dynamic page-level call graph'
                    ' from a dispak -tt trace in one pass.')
    ap.add_argument('trace',
                    help='trace file, or - for stdin')
    ap.add_argument('--top', type=int, default=DEFAULT_TOP,
                    help='max rows per table (default %d,'
                         ' max %d)' % (DEFAULT_TOP, MAXTOP))
    ap.add_argument('--format',
                    choices=('json', 'text'),
                    default='text',
                    help='output format (default text)')
    args = ap.parse_args(argv)
    if args.top < 1 or args.top > MAXTOP:
        ap.error('--top must be between 1 and %d' % MAXTOP)
    stats = TraceStats()
    try:
        handle = sys.stdin if args.trace == '-' else open(
            args.trace, 'r', encoding='utf-8',
            errors='replace')
    except OSError as exc:
        sys.stderr.write('cannot open trace: %s\n' % exc)
        return 2
    try:
        for line in handle:
            stats.feed(line)
    finally:
        if handle is not sys.stdin:
            handle.close()
    res = stats.result(args.top)
    if args.format == 'json':
        json.dump(res, sys.stdout, ensure_ascii=False,
                  indent=2)
        sys.stdout.write('\n')
    else:
        sys.stdout.write(render_text(res, args.trace))
    return 0


if __name__ == '__main__':
    sys.exit(main())
