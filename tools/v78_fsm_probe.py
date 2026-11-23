#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only probe for the reconstructed 06/78 line FSM.

Counts executions of the named state PCs in one dispak -tt
trace, optionally compares a second trace and reads mask
words from a zone 0152 image. The trace is streamed line by
line and is never modified.

Line parsing is reused from tools/v78_token_diff.py: an
executed instruction starts at column 0 with five octal
digits and a colon; store and DD lines are not PCs.

A state is recognised by its PC and by the first mnemonic
at that PC. Several PCs are shared by unrelated code, for
example 06061 is both "atx 72000(16)" and "vjm 6015(4)",
so the mnemonic is required to separate the two paths.

Usage:
    python3 tools/v78_fsm_probe.py P2a.trace
    python3 tools/v78_fsm_probe.py P2a.trace \
        --compare P2b.trace
    python3 tools/v78_fsm_probe.py P2a.trace --check
    python3 tools/v78_fsm_probe.py P2a.trace \
        --masks-from gold/MBE-Z0152-L1.bin

Exit codes: 0 ok, 1 check violation, 2 input or CLI error.
See analysis/V78-FSM-PROBE.md.
"""
import argparse
from collections import Counter, namedtuple
import json
import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import v78_token_diff as td  # noqa: E402

open_trace = td.open_trace
normalize = td.normalize
classify = td.classify
octstr = td.octstr

PC_LIMIT = 0o200000          # valid PCs: 0..0177777
VIOLATION_N = 30             # bound on stored violations
DESC_WRITE_MAX = 1000        # generous bound per trace
WORD_BYTES = 6               # BESM-6 word in bytes
ZONE_BASE = 0o76000          # zone 0152 starts here

State = namedtuple('State', 'key label pc mnemonic ref')

# Exact PCs from the phase 3 reconstruction. The mnemonic is
# the first word of each two-word instruction and separates
# paths that share one PC (06061, 075377).
STATES = (
    State('RLE_NORMALIZE', 'RLE нормализация',
          0o76604, 'apx', '076604'),
    State('RLE_MASK40', 'RLE маска 0x40',
          0o76611, 'aex', '076611'),
    State('RLE_SPACE', 'RLE пробел, ветка 76612',
          0o76612, 'xta', '076612'),
    State('RLE_NONSPACE', 'RLE не пробел, ветка 76615',
          0o76615, 'vlm', '076615'),
    State('RLE_END', 'RLE рзб',
          0o76621, 'aux', '076621'),
    State('CONSUME_XT', 'Потребитель xta (5)',
          0o01412, 'xta', '001412'),
    State('CONSUME_AT', 'Потребитель atx (11)',
          0o01413, 'atx', '001413'),
    State('CLS_A', 'Классификатор, маска A',
          0o75353, 'aex', '075353'),
    State('CLS_B', 'Классификатор, маска B',
          0o75356, 'aex', '075356'),
    State('METKA_READ', 'Чтение METKA utm 1(6)',
          0o75377, 'utm', '075377'),
    State('LINE_COPY', 'Копия строки xta 6405(1)',
          0o77320, 'xta', '077320'),
    State('DESC_WRITE', 'Дескриптор atx 72000(16)',
          0o06061, 'atx', '06061'),
    State('DESC_READ', 'Дескриптор xta (6)',
          0o01534, 'xta', '01534'),
)

COUNTER_MAP = (
    ('rle_normalize', 'RLE_NORMALIZE'),
    ('rle_mask40', 'RLE_MASK40'),
    ('rle_space_branch', 'RLE_SPACE'),
    ('rle_nonspace_branch', 'RLE_NONSPACE'),
    ('rle_end', 'RLE_END'),
    ('consume_xt', 'CONSUME_XT'),
    ('consume_at', 'CONSUME_AT'),
    ('classifier_mask_a', 'CLS_A'),
    ('classifier_mask_b', 'CLS_B'),
    ('metka_read', 'METKA_READ'),
    ('line_copy_read', 'LINE_COPY'),
    ('descriptor_write', 'DESC_WRITE'),
    ('descriptor_read', 'DESC_READ'),
)

# Mask words read from gold/MBE-Z0152-L1.bin. The binary is
# authoritative: 076315 = be, 076316 = bf, 076317 = 40.
MASK_SPECS = (
    (0o76315, 0xbe, '076315'),
    (0o76316, 0xbf, '076316'),
    (0o76317, 0x40, '076317'),
)
MASK_REFS = {
    'CLS_A': '076316',
    'CLS_B': '076315',
    'RLE_MASK40': '076317',
}


def match_state(pc, word, tolerance=0):
    """Return the state owning one executed instruction."""
    if word is None:
        return None
    word = word.lower()
    best = None
    best_dist = tolerance + 1
    for state in STATES:
        dist = abs(pc - state.pc)
        if dist > tolerance:
            continue
        if state.mnemonic != word:
            continue
        if dist < best_dist:
            best = state
            best_dist = dist
    return best


class Accumulator:
    """One-pass counters for one trace."""

    def __init__(self, label, tolerance):
        self.label = label
        self.tolerance = tolerance
        self.lines = 0
        self.executed = 0
        self.stores = 0
        self.dd = 0
        self.other = 0
        self.hits = Counter()
        self.visits = Counter()
        self.at_pc = Counter()
        self.prev = None
        self.violations = td.Violations()

    def push(self, text, lineno):
        """Classify one line and update counters."""
        self.lines += 1
        kind, pc, word = classify(text)
        if kind in ('exec', 'store', 'dd'):
            self.check_pc(pc, lineno)
        if kind == 'store':
            self.stores += 1
            return
        if kind == 'dd':
            self.dd += 1
            return
        if kind == 'other':
            self.other += 1
            if td.RE_MALFORMED.match(text):
                self.violations.add(
                    self.label, 'malformed_pc_line',
                    'line %d has no mnemonic' % lineno)
            return
        self.executed += 1
        for state in STATES:
            if abs(pc - state.pc) <= self.tolerance:
                self.at_pc[state.key] += 1
        state = match_state(pc, word, self.tolerance)
        if state is None:
            self.prev = None
            return
        key = state.key
        self.hits[key] += 1
        if self.prev != key:
            self.visits[key] += 1
        self.prev = key

    def check_pc(self, pc, lineno):
        """Record an out-of-range PC once."""
        if pc is not None and not 0 <= pc < PC_LIMIT:
            self.violations.add(
                self.label, 'pc_range',
                'line %d pc=%s' % (lineno, octstr(pc)))


def scan(path, tolerance=0, label='a'):
    """Stream one trace without loading it whole."""
    acc = Accumulator(label, tolerance)
    with open_trace(path) as handle:
        for lineno, raw in enumerate(handle, 1):
            acc.push(normalize(raw), lineno)
    return acc


def counters_of(acc):
    """Named counters from one accumulator."""
    return dict((name, acc.hits[key])
                for name, key in COUNTER_MAP)


def states_of(acc_a, acc_b=None):
    """State rows for one or two traces."""
    rows = []
    for state in STATES:
        row = {
            'key': state.key,
            'label': state.label,
            'pc': state.ref,
            'mnemonic': state.mnemonic,
            'hits': acc_a.hits[state.key],
            'visits': acc_a.visits[state.key],
            'lines': acc_a.at_pc[state.key],
        }
        if acc_b is not None:
            row['b_hits'] = acc_b.hits[state.key]
            row['b_visits'] = acc_b.visits[state.key]
            row['delta'] = (acc_b.hits[state.key]
                            - acc_a.hits[state.key])
        rows.append(row)
    return rows


def summary_of(acc):
    """Coarse parse summary for one trace."""
    return {
        'lines': acc.lines,
        'executed': acc.executed,
        'stores': acc.stores,
        'dd': acc.dd,
        'other': acc.other,
        'assigned': sum(acc.hits.values()),
        'parse_violations_total': acc.violations.total,
    }


def read_masks(path):
    """Read mask words 076315/076316/076317."""
    with open(path, 'rb') as handle:
        data = handle.read()
    need = (0o76317 - ZONE_BASE + 1) * WORD_BYTES
    words = []
    for addr, expected, ref in MASK_SPECS:
        off = (addr - ZONE_BASE) * WORD_BYTES
        byte = data[off] if off < len(data) else None
        words.append({
            'addr': ref,
            'expected': '%02x' % expected,
            'actual': None if byte is None
                      else '%02x' % byte,
            'ok': byte == expected,
        })
    return {
        'file': path,
        'base': '076000',
        'refs': dict(MASK_REFS),
        'size': len(data),
        'need_bytes': need,
        'size_ok': len(data) >= need,
        'words': words,
        'ok': (len(data) >= need and
               all(word['ok'] for word in words)),
    }


def analyze(path_a, path_b=None, tolerance=0,
            masks_path=None):
    """Probe one trace and optionally a second one."""
    acc_a = scan(path_a, tolerance, 'a')
    acc_b = None
    if path_b is not None:
        acc_b = scan(path_b, tolerance, 'b')
    violations = list(acc_a.violations.items)
    if acc_b is not None:
        violations.extend(acc_b.violations.items)
    report = {
        'sources': {'a': path_a, 'b': path_b},
        'tolerance': tolerance,
        'states': states_of(acc_a, acc_b),
        'counters': counters_of(acc_a),
        'summary': summary_of(acc_a),
        'parse': {
            'violations_total': (
                acc_a.violations.total +
                (acc_b.violations.total
                 if acc_b is not None else 0)),
            'violations': violations,
        },
        'masks': (read_masks(masks_path)
                  if masks_path else None),
        'compare': None,
    }
    if acc_b is not None:
        counters_b = counters_of(acc_b)
        rows = []
        for name, _ in COUNTER_MAP:
            left = report['counters'][name]
            right = counters_b[name]
            rows.append({
                'key': name, 'a': left, 'b': right,
                'delta': right - left,
            })
        report['compare'] = {
            'counters': counters_b,
            'summary': summary_of(acc_b),
            'counter_delta': rows,
        }
    return report


def check(report):
    """Validate the documented invariants."""
    items = []
    total = 0

    def add(invariant, detail, side='-'):
        nonlocal total
        total += 1
        if len(items) < VIOLATION_N:
            items.append({
                'side': side, 'invariant': invariant,
                'detail': detail,
            })

    numeric = list(td.walk_numbers(report))
    for path, value in numeric:
        if value < 0:
            add('no_negative_counts',
                '%s = %d' % (path, value))

    sides = [('a', report['counters'])]
    if report['compare'] is not None:
        sides.append(('b', report['compare']['counters']))
    for side, counters in sides:
        writes = counters['descriptor_write']
        if writes > DESC_WRITE_MAX:
            add('descriptor_write_bound',
                '%d > %d' % (writes, DESC_WRITE_MAX),
                side)
        hits = (counters['classifier_mask_a'] +
                counters['classifier_mask_b'])
        if hits < 1:
            add('classifier_present',
                'no classifier hit', side)

    # The parse list is already bounded, but its total is
    # exact. Restore the exact total before rendering rows.
    total += report['parse']['violations_total']
    for item in report['parse']['violations']:
        if len(items) < VIOLATION_N:
            items.append({
                'side': item['side'],
                'invariant': item['invariant'],
                'detail': item['detail'],
            })

    masks = report['masks']
    if masks is not None and not masks['ok']:
        add('mask_words', 'mismatch or short image')

    return {
        'ok': total == 0,
        'checked': len(numeric) + len(sides),
        'violations_total': total,
        'truncated': max(0, total - len(items)),
        'violations': items,
    }


def format_text(report, checked=None):
    """Human-readable summary, lines within 60 columns."""
    out = ['V78 FSM PROBE']
    out.append('A: %s' % report['sources']['a'])
    out.append('B: %s' % (report['sources']['b'] or '-'))
    out.append('tolerance: %d' % report['tolerance'])
    s = report['summary']
    out.append('строк A: %d' % s['lines'])
    out.append('команд A: %d' % s['executed'])
    out.append('ошибок разбора: %d' %
               report['parse']['violations_total'])

    if report['compare'] is None:
        rows = [{
            'key': name,
            'a': report['counters'][name],
            'b': 0, 'delta': 0,
        } for name, _ in COUNTER_MAP]
    else:
        rows = report['compare']['counter_delta']
    out.append('СЧЁТЧИКИ (A / B / DELTA)')
    out.append('  %-22s %5s %5s %5s' % (
        'key', 'A', 'B', 'D'))
    for row in rows:
        out.append('  %-22s %5d %5d %+5d' % (
            row['key'], row['a'], row['b'],
            row['delta']))

    paired = report['compare'] is not None
    out.append('СОСТОЯНИЯ (PC / OP / KEY / A / B)')
    out.append('  %6s %-5s %-18s %5s %5s' % (
        'pc', 'op', 'key', 'A', 'B'))
    for row in report['states']:
        right = ('%5d' % row['b_hits']) if paired \
                else '    -'
        out.append('  %6s %-5s %-18s %5d %s' % (
            row['pc'], row['mnemonic'], row['key'],
            row['hits'], right))

    masks = report['masks']
    if masks is not None:
        out.append('МАСКИ %s, %s' % (
            masks['base'], 'OK' if masks['ok']
            else 'FAIL'))
        for word in masks['words']:
            out.append('  %s %s == %s %s' % (
                word['addr'],
                word['actual'] or '--',
                word['expected'],
                'OK' if word['ok'] else 'FAIL'))

    if checked is not None:
        out.append('ПРОВЕРКА: %s' % (
            'OK' if checked['ok'] else 'НАРУШЕНИЯ'))
        out.append('  проверено: %d' % checked['checked'])
        out.append('  нарушений: %d' % checked[
            'violations_total'])
        out.append('  урезано  : %d' % checked[
            'truncated'])
        for item in checked['violations'][:10]:
            out.append('  %s %s: %s' % (
                item['side'], item['invariant'],
                item['detail'][:30]))
    return '\n'.join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Read-only FSM counter for a dispak -tt '
            'trace.'))
    parser.add_argument(
        'trace', metavar='TRACE',
        help='first dispak -tt trace file')
    parser.add_argument(
        '--compare', metavar='TRACE2', default=None,
        help='second trace, report count deltas')
    parser.add_argument(
        '--masks-from', metavar='GOLD', default=None,
        help='zone 0152 image with the mask words')
    parser.add_argument(
        '--tolerance', type=int, default=0,
        metavar='N',
        help='accept PCs within +/-N of each state')
    parser.add_argument(
        '--format', choices=('json', 'text'),
        default='text',
        help='output format (default: text)')
    parser.add_argument(
        '--check', action='store_true',
        help='validate invariants; exit 1 on violation')
    args = parser.parse_args(argv)
    if args.tolerance < 0:
        print('error: --tolerance must be >= 0',
              file=sys.stderr)
        return 2
    try:
        result = analyze(
            args.trace, args.compare,
            args.tolerance, args.masks_from)
    except (OSError, ValueError) as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2
    checked = check(result) if args.check else None
    if args.format == 'json':
        if checked is not None:
            result['check'] = checked
        print(json.dumps(result, ensure_ascii=False,
                         sort_keys=True, indent=2))
    else:
        print(format_text(result, checked))
    if checked is not None and not checked['ok']:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
