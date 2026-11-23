#!/usr/bin/env python3
"""Streaming diff for two dispak -tt traces.

Finds the first differing text line, the first change in
the executed PC and mnemonic stream, and count deltas.
Files are read line by line and are never modified.

An instruction starts at column 0 with five octal digits
and a colon. Store and DD I/O lines are not PCs.
The --skip key drops the first N executed instructions
from both sequences and from the count histograms.

Usage:
    python3 tools/v78_token_diff.py A.trace.txt B.trace.txt
    python3 tools/v78_token_diff.py A B --format json
    python3 tools/v78_token_diff.py A B --check --skip 5

Exit codes: 0 ok, 1 check violation, 2 input or CLI error.
See analysis/V78-TOKEN-DIFF-TOOL.md.
"""
import argparse
from collections import Counter, deque
import json
from itertools import zip_longest
import re
import sys

PC_LIMIT = 0o200000          # valid PCs: 0..0177777
TOP_N = 20                   # rows in each top table
VIOLATION_N = 30             # bounded check output
EOF_MARK = '<EOF>'           # shorter trace at line level

RE_EXEC = re.compile(r'^([0-7]{5}):\s+(\S+)')
RE_STORE = re.compile(r'^\s*([0-7]{5,6}):\s+store\b', re.I)
RE_DD = re.compile(r'^\s*DD\b')
RE_DD_PC = re.compile(r'\bpc=([0-7]{1,6})L?(?![0-7])')
RE_PC_FIELD = re.compile(r'\bpc=(\S+)')
RE_MALFORMED = re.compile(r'^\s*[0-7]{4,6}:\s*$')


def octstr(value, digits=0):
    """Format an address as an octal string."""
    if digits:
        return ('%%0%do' % digits) % value
    return '%o' % value


def open_trace(path):
    """Open one trace for reading only."""
    return open(path, 'r', encoding='utf-8',
                errors='replace')


def normalize(line):
    """Drop the line ending and a leading BOM."""
    if line is None:
        return None
    return line.lstrip('\ufeff').rstrip('\r\n')


def sample(text, limit=48):
    """Shorten a line for a report row."""
    if text is None:
        return EOF_MARK
    text = text.strip()
    if len(text) > limit:
        return text[:limit] + '...'
    return text


def classify(text):
    """Return kind, address and mnemonic for one line."""
    if RE_DD.match(text):
        match = RE_DD_PC.search(text)
        pc = int(match.group(1), 8) if match else None
        return ('dd', pc, None)
    match = RE_EXEC.match(text)
    if match:
        word = match.group(2)
        if word.lower() == 'store':
            return ('store', int(match.group(1), 8), None)
        return ('exec', int(match.group(1), 8), word)
    match = RE_STORE.match(text)
    if match:
        return ('store', int(match.group(1), 8), None)
    return ('other', None, None)


class Violations:
    """Bounded list with an exact total."""

    def __init__(self):
        self.total = 0
        self.items = []

    def add(self, side, invariant, detail):
        self.total += 1
        if len(self.items) < VIOLATION_N:
            self.items.append({
                'side': side, 'invariant': invariant,
                'detail': detail})


class Accumulator:
    """Per-file counters. Only distinct PCs are retained."""

    def __init__(self, label):
        self.label = label
        self.lines = 0
        self.stores = 0
        self.dd = 0
        self.other = 0
        self.executed = 0
        self.pc_counts = Counter()
        self.skipped = 0

    def feed_exec(self, pc, lineno):
        self.executed += 1
        self.pc_counts[pc] += 1


class Side:
    """Classify lines of one trace and apply --skip."""

    def __init__(self, acc, skip, violations):
        self.acc = acc
        self.skip = skip
        self.violations = violations
        self.seen = 0

    def push(self, text, lineno):
        """Return an event, or None for other lines."""
        self.acc.lines += 1
        kind, pc, word = classify(text)
        if kind == 'exec':
            self.seen += 1
            if self.seen <= self.skip:
                self.acc.skipped += 1
                return None
            self.acc.feed_exec(pc, lineno)
            return (pc, word, lineno)
        if kind == 'store':
            self.acc.stores += 1
            self.check_pc(pc, lineno, 'store')
        elif kind == 'dd':
            self.acc.dd += 1
            if pc is None and RE_PC_FIELD.search(text):
                self.violations.add(
                    self.acc.label, 'malformed_dd_pc',
                    'line %d pc is not octal' % lineno)
            else:
                self.check_pc(pc, lineno, 'dd')
        else:
            self.acc.other += 1
            if RE_MALFORMED.match(text):
                self.violations.add(
                    self.acc.label, 'malformed_pc_line',
                    'line %d has no mnemonic' % lineno)
        return None

    def check_pc(self, pc, lineno, kind):
        if pc is not None and not 0 <= pc < PC_LIMIT:
            self.violations.add(
                self.acc.label, 'pc_range',
                'line %d %s pc=%s' % (
                    lineno, kind, octstr(pc)))


def event_row(event):
    """Turn an executed event into a report row."""
    pc, mnemonic, lineno = event
    return {'line': lineno, 'pc': octstr(pc, 5),
            'mnemonic': mnemonic}


def delta_rows(counts_a, counts_b):
    """All PCs sorted by descending absolute count delta."""
    rows = []
    for pc in set(counts_a) | set(counts_b):
        left = counts_a.get(pc, 0)
        right = counts_b.get(pc, 0)
        rows.append({'pc': octstr(pc, 5), 'a': left,
                     'b': right, 'delta': right - left})
    rows.sort(key=lambda row: (-abs(row['delta']),
                               row['pc']))
    return rows


def one_sided(counts, other):
    """PCs of counts absent from other, by count then PC."""
    rows = [{'pc': octstr(pc, 5), 'count': count}
            for pc, count in counts.items()
            if pc not in other]
    rows.sort(key=lambda row: (-row['count'], row['pc']))
    return rows


def analyze(path_a, path_b, skip=0):
    """Compare two traces in one streaming pass."""
    acc_a = Accumulator('A')
    acc_b = Accumulator('B')
    violations = Violations()
    side_a = Side(acc_a, skip, violations)
    side_b = Side(acc_b, skip, violations)
    first_line = None
    first_seq = None
    queue_a = deque()
    queue_b = deque()
    seq_index = 0
    with open_trace(path_a) as fa, open_trace(path_b) as fb:
        for lineno, pair in enumerate(
                zip_longest(fa, fb), 1):
            left, right = pair
            text_a = normalize(left)
            text_b = normalize(right)
            if first_line is None and text_a != text_b:
                first_line = {
                    'line': lineno, 'a': sample(text_a),
                    'b': sample(text_b)}
            if left is not None:
                event = side_a.push(text_a, lineno)
                if event is not None and first_seq is None:
                    queue_a.append(event)
            if right is not None:
                event = side_b.push(text_b, lineno)
                if event is not None and first_seq is None:
                    queue_b.append(event)
            while queue_a and queue_b:
                head_a = queue_a.popleft()
                head_b = queue_b.popleft()
                seq_index += 1
                if head_a[:2] != head_b[:2]:
                    first_seq = {
                        'index': seq_index,
                        'a': event_row(head_a),
                        'b': event_row(head_b)}
                    queue_a.clear()
                    queue_b.clear()
                    break
    if first_seq is None and (queue_a or queue_b):
        seq_index += 1
        first_seq = {
            'index': seq_index,
            'a': event_row(queue_a[0]) if queue_a else None,
            'b': event_row(queue_b[0]) if queue_b else None}

    counts_a = acc_a.pc_counts
    counts_b = acc_b.pc_counts
    deltas = delta_rows(counts_a, counts_b)
    summary = {
        'lines_a': acc_a.lines, 'lines_b': acc_b.lines,
        'exec_a': acc_a.executed, 'exec_b': acc_b.executed,
        'skipped_a': acc_a.skipped,
        'skipped_b': acc_b.skipped,
        'store_a': acc_a.stores, 'store_b': acc_b.stores,
        'dd_a': acc_a.dd, 'dd_b': acc_b.dd,
        'other_a': acc_a.other, 'other_b': acc_b.other,
        'distinct_pcs_a': len(counts_a),
        'distinct_pcs_b': len(counts_b),
        'common_pcs': len(set(counts_a) & set(counts_b)),
        'seq_compared': seq_index,
    }
    return {
        'sources': {'a': path_a, 'b': path_b},
        'skip': skip,
        'summary': summary,
        'first_line_diff': first_line,
        'pc_seq_diff': first_seq,
        'count_delta_top': deltas[:TOP_N],
        'only_a_top': one_sided(counts_a, counts_b)[:TOP_N],
        'only_b_top': one_sided(counts_b, counts_a)[:TOP_N],
        'parse': {
            'violations_total': violations.total,
            'violations': violations.items,
        },
    }


def walk_numbers(value, path=''):
    """Yield integer fields. Deltas may be negative."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'delta':
                continue
            yield from walk_numbers(
                item, path + '/' + key)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            yield from walk_numbers(
                item, '%s/%d' % (path, idx))
    elif isinstance(value, int) and not isinstance(
            value, bool):
        yield path, value


def check(report):
    """Validate parse violations, PC range and counts."""
    items = list(report['parse']['violations'])
    total = report['parse']['violations_total']
    numeric = list(walk_numbers(report))

    def add(invariant, detail):
        nonlocal total
        total += 1
        if len(items) < VIOLATION_N:
            items.append({'invariant': invariant,
                          'detail': detail})

    for path, value in numeric:
        if value < 0:
            add('no_negative_counts',
                '%s = %d' % (path, value))
    for side in ('a', 'b'):
        for label, key in (('exec', 'exec'),
                           ('store', 'store'),
                           ('dd', 'dd')):
            count = report['summary'][key + '_' + side]
            if count < 0:
                add('no_negative_counts',
                    '%s_%s = %d' % (label, side, count))
    return {
        'ok': total == 0,
        'checked': len(numeric) + len(report[
            'count_delta_top']),
        'violations_total': total,
        'truncated': max(0, total - len(items)),
        'violations': items,
    }


def format_text(report, checked=None):
    """Human-readable summary under 60 columns."""
    s = report['summary']
    out = ['V78 TOKEN DIFF']
    out.append('A: %s' % sample(
        report['sources']['a'], 52))
    out.append('B: %s' % sample(
        report['sources']['b'], 52))
    out.append('skip: %d' % report['skip'])
    out.append('строк     A/B: %d / %d' % (
        s['lines_a'], s['lines_b']))
    out.append('команд    A/B: %d / %d' % (
        s['exec_a'], s['exec_b']))
    out.append('пропущено A/B: %d / %d' % (
        s['skipped_a'], s['skipped_b']))
    out.append('store     A/B: %d / %d' % (
        s['store_a'], s['store_b']))
    out.append('DD        A/B: %d / %d' % (
        s['dd_a'], s['dd_b']))
    out.append('прочих    A/B: %d / %d' % (
        s['other_a'], s['other_b']))
    out.append('PC всего  A/B: %d / %d' % (
        s['distinct_pcs_a'], s['distinct_pcs_b']))
    out.append('сравнено команд: %d' % s['seq_compared'])

    line = report['first_line_diff']
    out.append('ПЕРВАЯ РАСХОДЯЩАЯСЯ СТРОКА')
    if line is None:
        out.append('  нет')
    else:
        out.append('  строка %d' % line['line'])
        out.append('  A: %s' % line['a'])
        out.append('  B: %s' % line['b'])

    seq = report['pc_seq_diff']
    out.append('ПЕРВОЕ РАСХОЖДЕНИЕ ПОСЛЕДОВАТЕЛЬНОСТИ')
    if seq is None:
        out.append('  нет')
    else:
        out.append('  индекс %d' % seq['index'])
        for side in ('a', 'b'):
            row = seq[side]
            if row is None:
                out.append('  %s: %s' % (
                    side.upper(), EOF_MARK))
            else:
                out.append('  %s: строка %d PC=%s %s' % (
                    side.upper(), row['line'],
                    row['pc'], row['mnemonic']))

    out.append('ДЕЛЬТА СЧЁТЧИКОВ PC')
    if report['count_delta_top']:
        out.append('    pc       A       B   delta')
        for row in report['count_delta_top']:
            out.append('  %5s %7d %7d %7d' % (
                row['pc'], row['a'], row['b'],
                row['delta']))
        out.append('  всего PC в выборке: %d' % (
            s['distinct_pcs_a'] + s['distinct_pcs_b']
            - s['common_pcs']))

    for key, title in (
            ('only_a_top', 'PC ТОЛЬКО В A'),
            ('only_b_top', 'PC ТОЛЬКО В B')):
        out.append(title)
        if report[key]:
            for row in report[key]:
                out.append('  %5s %10d' % (
                    row['pc'], row['count']))
        else:
            out.append('  нет')

    if checked is not None:
        out.append('ПРОВЕРКА: %s' % (
            'OK' if checked['ok'] else 'НАРУШЕНИЯ'))
        out.append('  проверено: %d' % checked['checked'])
        out.append('  нарушений: %d' % checked[
            'violations_total'])
        out.append('  урезано  : %d' % checked[
            'truncated'])
        for item in checked['violations']:
            out.append('  %s %s: %s' % (
                item['side'], item['invariant'],
                sample(item['detail'], 30)))
    return '\n'.join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Streaming diff of two dispak -tt traces; '
            'read-only.'))
    parser.add_argument(
        'trace_a', metavar='TRACE_A',
        help='first dispak -tt trace file')
    parser.add_argument(
        'trace_b', metavar='TRACE_B',
        help='second dispak -tt trace file')
    parser.add_argument(
        '--format', choices=('json', 'text'),
        default='text',
        help='output format (default: text)')
    parser.add_argument(
        '--check', action='store_true',
        help='validate invariants; exit 1 on violation')
    parser.add_argument(
        '--skip', type=int, default=0, metavar='N',
        help='ignore first N executed instructions')
    args = parser.parse_args(argv)
    if args.skip < 0:
        print('error: --skip must be >= 0',
              file=sys.stderr)
        return 2
    try:
        result = analyze(args.trace_a, args.trace_b,
                         args.skip)
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
