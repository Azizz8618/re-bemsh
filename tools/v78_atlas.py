#!/usr/bin/env python3
"""Differential atlas for ВЕР.06/78 event fixtures.

Consumes the event JSONL schema of
tools/v78_runner.py:

    {"n": 12, "kind": "exec", "pc": "076505",
     "mn": "uza", "operand": "76230", "acc": "...",
     "phase": "RLE"}

Read-only and streaming: only counters, small queues and the
first divergent records are kept. See analysis/V78-ATLAS.md.

Exit codes: 0 no divergence, 1 divergence, 2 input error.
"""
import argparse
from collections import Counter, deque
from itertools import zip_longest
import json
import os
import re
import sys

TOP_N = 20
KINDS = ('exec', 'store', 'dd')
PHASES = ('BOOT', 'RLOAD', 'RLE', 'INPUT', 'EDITOR',
          'MACHINE', 'LISTING', 'UNKNOWN')
REQUIRED = ('n', 'kind', 'pc', 'mn', 'phase')
RE_OCTAL = re.compile(r'\A[0-7]{1,6}\Z')
RE_RANGE = re.compile(r'\A([0-7]+)\s*-\s*([0-7]+)\Z')
RE_CLUSTER = re.compile(
    r'\A\s*([0-7]{5,6})[-/]([0-7]{5,6})\s+(\d+)')
RE_PCMN = re.compile(
    r'\b([0-7]{5,6})\s+([a-z][a-z0-9]*)\b')
MNEMONICS = frozenset((
    'atx', 'uza', 'xta', 'utm', 'uj', 'aax', 'vlm',
    'utc', 'ati', 'aex', 'ita', 'vtm', 'anx', 'asn',
    'aox', 'apx', 'u1a'))
DEFAULT_REPORT = 'analysis/V78-FSM-VALIDATION.md'

# Built-in segments: docs/PLAN-TEST-CORPUS.md, §3.4.
# A PC may belong to more than one segment: 075353-075377
# lies inside both S-MARK and S-METKA.
SEGMENT_SPECS = (
    ('S-INPUT', ('076505-076642',)),
    ('S-DISPATCH', ('076031-076123',)),
    ('S-PACK', ('077421-077502',)),
    ('S-MARK', ('075344-075401',)),
    ('S-METKA', ('075353-075377',)),
    ('S-SLOT', ('04200-04207',)),
    ('S-DESCR', ('06061', '01534')),
)

# Candidate PCs read once from the report
# analysis/V78-FSM-VALIDATION.md, section ACTION 3.
# Fallback when that report is absent.
BUILTIN_CANDIDATES = (
    '03632', '03633', '04034', '04035', '04036', '04037',
    '04040', '04043', '04070', '04072', '04074', '04200',
    '04205', '04206', '04207', '06101', '06103', '06107',
    '06110', '06111', '06115', '06116', '06122', '06123',
    '26116', '26117', '26120', '26121', '40034', '42007',
    '75344', '75346', '75351', '75372', '75401', '76031',
    '76032', '76033', '76034', '76035', '76036', '76054',
    '76055', '76056', '76057', '76061', '76062', '76066',
    '76067', '76106', '76107', '76121', '76122', '76123',
    '77322', '77421', '77422', '77423', '77424', '77474',
    '77475', '77476', '77477', '77500', '77501', '77502',
)


class InputError(Exception):
    """Raised for malformed input or CLI data."""


def oct5(value):
    """Canonical five-digit octal address string."""
    return '%05o' % value


def parse_pc(text):
    """Integer address, or None when text is not octal."""
    if not isinstance(text, str):
        return None
    if not RE_OCTAL.match(text):
        return None
    return int(text, 8)


def parse_segment_part(part):
    """Turn 'lo-hi' or one PC into an inclusive pair."""
    match = RE_RANGE.match(part)
    if match:
        lo = int(match.group(1), 8)
        hi = int(match.group(2), 8)
        if lo <= hi:
            return (lo, hi)
        return None
    value = parse_pc(part)
    if value is None:
        return None
    return (value, value)


def read_segment_specs(path):
    """Read a JSON object or 'NAME lo-hi' text lines."""
    with open(path, 'r', encoding='utf-8') as handle:
        text = handle.read()
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict):
        return [(name, tuple(parts))
                for name, parts in data.items()]
    specs = []
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) < 2:
            raise InputError('bad segment line: ' + line)
        specs.append((fields[0], tuple(fields[1:])))
    return specs


def load_segments(path=None):
    """Return a list of (name, lo, hi) integer triples."""
    specs = SEGMENT_SPECS
    if path:
        specs = read_segment_specs(path)
    result = []
    for name, parts in specs:
        for part in parts:
            pair = parse_segment_part(part)
            if pair is None:
                raise InputError(
                    'bad segment range: ' + str(part))
            result.append((name, pair[0], pair[1]))
    return result


def segments_for(value, segments):
    """Segment names that contain one integer address."""
    return [name for name, lo, hi in segments
            if lo <= value <= hi]


def normalize_event(raw, path, lineno, strict, last_n):
    """Validate one record and return it with its n."""
    for key in REQUIRED:
        if key not in raw:
            raise InputError('%s:%d missing %s' % (
                path, lineno, key))
    n = raw['n']
    if not isinstance(n, int) or isinstance(n, bool):
        raise InputError('%s:%d n is not an integer' % (
            path, lineno))
    if strict and n <= last_n:
        raise InputError('%s:%d n not increasing' % (
            path, lineno))
    kind = raw['kind']
    if kind not in KINDS:
        if strict:
            raise InputError('%s:%d bad kind' % (
                path, lineno))
        kind = 'other'
    raw_pc = raw['pc']
    value = parse_pc(raw_pc)
    if value is None and raw_pc is not None and strict:
        raise InputError('%s:%d bad pc' % (path, lineno))
    mn = raw['mn']
    if mn is None:
        mn = ''                 # dd events have no mnemonic
    elif not isinstance(mn, str):
        raise InputError('%s:%d mn is not text' % (
            path, lineno))
    phase = raw['phase']
    if phase not in PHASES:
        if strict:
            raise InputError('%s:%d bad phase' % (
                path, lineno))
        phase = 'UNKNOWN'
    operand = raw.get('operand')
    acc = raw.get('acc')
    event = {
        'n': n, 'kind': kind,
        'pc': oct5(value) if value is not None
              else (raw_pc if isinstance(raw_pc, str)
                    else ''),
        'pc_value': value, 'mn': mn,
        'operand': operand if isinstance(operand, str)
                   else '',
        'acc': acc if isinstance(acc, str) else '',
        'phase': phase, '_line': lineno,
    }
    return event, n


def read_events(path, strict=False):
    """Yield normalized events, one JSONL line at a time."""
    last_n = 0
    with open(path, 'r', encoding='utf-8') as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except ValueError as exc:
                raise InputError('%s:%d JSON: %s' % (
                    path, lineno, exc))
            if not isinstance(raw, dict):
                raise InputError('%s:%d not an object' % (
                    path, lineno))
            event, last_n = normalize_event(
                raw, path, lineno, strict, last_n)
            yield event


def public_event(event):
    """Report form: shared schema fields only."""
    if event is None:
        return None
    return dict((key, event[key]) for key in (
        'n', 'kind', 'pc', 'mn', 'operand', 'acc', 'phase'))


def event_key(event):
    """Tuple used for whole-record equality."""
    return tuple(public_event(event).values())


class Accumulator:
    """Counters retained for one file or catalog."""

    def __init__(self, label):
        self.label = label
        self.events = 0
        self.kinds = Counter()
        self.phases = Counter()
        self.exec_counts = Counter()
        self.pc_hits = Counter()
        self.first_phase = None

    def feed(self, event):
        self.events += 1
        self.kinds[event['kind']] += 1
        self.phases[event['phase']] += 1
        if self.first_phase is None:
            self.first_phase = event['phase']
        value = event['pc_value']
        if value is not None:
            self.pc_hits[value] += 1
            if event['kind'] == 'exec':
                self.exec_counts[value] += 1


def delta_rows(counts_a, counts_b):
    """All PCs sorted by descending absolute delta."""
    rows = []
    for value in set(counts_a) | set(counts_b):
        left = counts_a.get(value, 0)
        right = counts_b.get(value, 0)
        rows.append({'pc': oct5(value), 'a': left,
                     'b': right, 'delta': right - left})
    rows.sort(key=lambda row: (-abs(row['delta']),
                               row['pc']))
    return rows


def one_sided(counts, other):
    """PCs present only in counts, by count then PC."""
    rows = [{'pc': oct5(value), 'count': count}
            for value, count in counts.items()
            if value not in other]
    rows.sort(key=lambda row: (-row['count'], row['pc']))
    return rows


def phase_rows(acc_a, acc_b):
    """Per-phase counts for phases seen in either side."""
    rows = []
    for phase in PHASES:
        left = acc_a.phases.get(phase, 0)
        right = acc_b.phases.get(phase, 0)
        if left or right:
            rows.append({'phase': phase, 'a': left,
                         'b': right})
    return rows


def coverage_rows(acc_a, acc_b, segments):
    """Per-segment PC and hit counts for both sides."""
    names = []
    for name, _, _ in segments:
        if name not in names:
            names.append(name)
    rows = []
    for name in names:
        picks = [(lo, hi) for nm, lo, hi in segments
                 if nm == name]
        sets = []
        totals = []
        for acc in (acc_a, acc_b):
            found = set()
            hits = 0
            for value, count in acc.pc_hits.items():
                if any(lo <= value <= hi
                       for lo, hi in picks):
                    found.add(value)
                    hits += count
            sets.append(found)
            totals.append(hits)
        rows.append({
            'segment': name,
            'a_pcs': len(sets[0]), 'b_pcs': len(sets[1]),
            'a_hits': totals[0], 'b_hits': totals[1],
            'a': sorted(oct5(v) for v in sets[0])[:TOP_N],
            'b': sorted(oct5(v) for v in sets[1])[:TOP_N],
        })
    all_pcs = set(acc_a.pc_hits) | set(acc_b.pc_hits)
    loose = sorted(oct5(v) for v in all_pcs
                   if not segments_for(v, segments))
    return {
        'segments': rows,
        'unmapped_count': len(loose),
        'unmapped_top': loose[:TOP_N],
    }


def compare(path_a, path_b, strict=False, segments=None):
    """Compare two event files in one streaming pass."""
    if segments is None:
        segments = load_segments()
    acc_a = Accumulator('A')
    acc_b = Accumulator('B')
    first_line = None
    first_seq = None
    seq_index = 0
    queue_a = deque()
    queue_b = deque()
    stream_a = read_events(path_a, strict)
    stream_b = read_events(path_b, strict)
    for event_a, event_b in zip_longest(stream_a, stream_b):
        if event_a is not None:
            acc_a.feed(event_a)
        if event_b is not None:
            acc_b.feed(event_b)
        if first_line is None and (
                event_a is None or event_b is None or
                event_key(event_a) != event_key(event_b)):
            line = (event_a['_line'] if event_a is not None
                    else event_b['_line'])
            first_line = {
                'line': line,
                'a': public_event(event_a),
                'b': public_event(event_b),
            }
        if first_seq is None:
            if (event_a is not None and
                    event_a['kind'] == 'exec'):
                queue_a.append(event_a)
            if (event_b is not None and
                    event_b['kind'] == 'exec'):
                queue_b.append(event_b)
            while queue_a and queue_b:
                head_a = queue_a.popleft()
                head_b = queue_b.popleft()
                seq_index += 1
                if head_a['pc'] != head_b['pc']:
                    first_seq = {
                        'index': seq_index,
                        'a': public_event(head_a),
                        'b': public_event(head_b),
                    }
                    break
            if first_seq is not None:
                queue_a.clear()
                queue_b.clear()
    if first_seq is None and (queue_a or queue_b):
        seq_index += 1
        first_seq = {
            'index': seq_index,
            'a': public_event(queue_a[0])
                if queue_a else None,
            'b': public_event(queue_b[0])
                if queue_b else None,
        }
    phase = None
    if first_line is not None:
        for side in ('a', 'b'):
            if first_line[side] is not None:
                phase = first_line[side]['phase']
                break
    distinct = len(set(acc_a.exec_counts) |
                   set(acc_b.exec_counts))
    return {
        'mode': 'pair',
        'sources': {'a': path_a, 'b': path_b},
        'summary': {
            'events_a': acc_a.events,
            'events_b': acc_b.events,
            'exec_a': sum(acc_a.exec_counts.values()),
            'exec_b': sum(acc_b.exec_counts.values()),
            'phases_a': len(acc_a.phases),
            'phases_b': len(acc_b.phases),
            'distinct_exec_pcs': distinct,
            'first_phase_a': acc_a.first_phase,
            'first_phase_b': acc_b.first_phase,
        },
        'first_line_diff': first_line,
        'pc_seq_diff': first_seq,
        'count_delta_top': delta_rows(
            acc_a.exec_counts, acc_b.exec_counts)[:TOP_N],
        'only_a_top': one_sided(
            acc_a.exec_counts, acc_b.exec_counts)[:TOP_N],
        'only_b_top': one_sided(
            acc_b.exec_counts, acc_a.exec_counts)[:TOP_N],
        'phase_counts': phase_rows(acc_a, acc_b),
        'first_divergence_phase': phase,
        'coverage': coverage_rows(
            acc_a, acc_b, segments),
    }


def parse_report_candidates(text):
    """Extract explicit PC mentions in section ACTION 3."""
    start = text.find('ACTION 3')
    end = text.find('ACTION 4', start + 1)
    if start < 0 or end < 0:
        raise InputError('report has no ACTION 3 section')
    section = text[start:end]
    values = set()
    clusters = []
    declared = 0
    for line in section.splitlines():
        match = RE_CLUSTER.match(line)
        if match:
            values.add(int(match.group(1), 8))
            values.add(int(match.group(2), 8))
            count = int(match.group(3))
            clusters.append({
                'from': match.group(1),
                'to': match.group(2),
                'count': count,
            })
            declared += count
        for item in RE_PCMN.finditer(line):
            if item.group(2) in MNEMONICS:
                values.add(int(item.group(1), 8))
    meta = {
        'declared_total': declared,
        'explicit_count': len(values),
        'clusters': clusters,
    }
    return sorted(values), meta


def load_candidates(path=None):
    """Return (sorted integer PCs, metadata dict)."""
    if path is not None:
        with open(path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        values = []
        for token in text.split():
            value = parse_pc(token.strip(','))
            if value is not None:
                values.append(value)
        if not values:
            raise InputError('no candidates in ' + path)
        return sorted(set(values)), {
            'source': path,
            'declared_total': len(set(values)),
            'explicit_count': len(set(values)),
            'clusters': [],
        }
    report = DEFAULT_REPORT
    if os.path.isfile(report):
        with open(report, 'r', encoding='utf-8') as handle:
            text = handle.read()
        values, meta = parse_report_candidates(text)
        meta['source'] = report
        return values, meta
    values = sorted(parse_pc(pc) for pc in
                    BUILTIN_CANDIDATES)
    return values, {
        'source': 'builtin',
        'declared_total': 84,
        'explicit_count': len(values),
        'clusters': [],
    }


def find_fixtures(directory):
    """Sorted list of *.jsonl files below one directory."""
    found = []
    for root, dirs, files in os.walk(directory):
        dirs.sort()
        for name in sorted(files):
            if name.endswith('.jsonl'):
                found.append(os.path.join(root, name))
    return sorted(found)


def catalog(directory, candidates_path=None, strict=False):
    """Aggregate exec PCs over fixtures in a directory."""
    if not os.path.isdir(directory):
        raise InputError('not a directory: ' + directory)
    fixtures = find_fixtures(directory)
    covered = Counter()
    rows = []
    total_events = 0
    total_exec = 0
    for path in fixtures:
        acc = Accumulator(path)
        for event in read_events(path, strict):
            acc.feed(event)
        covered.update(acc.exec_counts)
        total_events += acc.events
        total_exec += sum(acc.exec_counts.values())
        rows.append({
            'path': path, 'events': acc.events,
            'exec': sum(acc.exec_counts.values()),
        })
    values, meta = load_candidates(candidates_path)
    uncovered = [oct5(value) for value in values
                 if value not in covered]
    return {
        'mode': 'catalog',
        'catalog_dir': directory,
        'fixtures': rows,
        'fixture_count': len(rows),
        'events': total_events,
        'exec_events': total_exec,
        'covered_pcs': len(covered),
        'candidates': meta,
        'candidate_count': len(values),
        'uncovered': uncovered,
        'uncovered_count': len(uncovered),
    }


def has_divergence(report):
    """True when a pair or catalog has a divergence."""
    if report['mode'] == 'catalog':
        return report['uncovered_count'] > 0
    return any((
        report['first_line_diff'] is not None,
        report['pc_seq_diff'] is not None,
        any(row['delta'] != 0
            for row in report['count_delta_top']),
        bool(report['only_a_top']),
        bool(report['only_b_top']),
    ))


def sample(record, limit=44):
    """One-line view of an event record."""
    if record is None:
        return '<EOF>'
    text = 'n=%d %s %s %s [%s]' % (
        record['n'], record['kind'], record['pc'],
        record['mn'], record['phase'])
    if len(text) > limit:
        return text[:limit] + '...'
    return text


def format_pair_text(report):
    """Human-readable pair report under 60 columns."""
    out = ['V78 АТЛАС РАСХОЖДЕНИЙ']
    s = report['summary']
    out.append('A: %s' % report['sources']['a'][:52])
    out.append('B: %s' % report['sources']['b'][:52])
    out.append('событий  A/B: %d / %d' % (
        s['events_a'], s['events_b']))
    out.append('команд   A/B: %d / %d' % (
        s['exec_a'], s['exec_b']))
    out.append('фаз      A/B: %d / %d' % (
        s['phases_a'], s['phases_b']))
    line = report['first_line_diff']
    out.append('ПЕРВАЯ РАСХОДЯЩАЯСЯ СТРОКА')
    if line is None:
        out.append('  нет')
    else:
        out.append('  строка %d' % line['line'])
        out.append('  A: %s' % sample(line['a']))
        out.append('  B: %s' % sample(line['b']))
    seq = report['pc_seq_diff']
    out.append('ПЕРВОЕ PC-РАСХОЖДЕНИЕ (exec)')
    if seq is None:
        out.append('  нет')
    else:
        out.append('  индекс %d' % seq['index'])
        out.append('  A: %s' % sample(seq['a']))
        out.append('  B: %s' % sample(seq['b']))
    out.append('ДЕЛЬТА PC (top %d)' % TOP_N)
    if report['count_delta_top']:
        out.append('    pc       A       B   delta')
        for row in report['count_delta_top']:
            out.append('  %5s %7d %7d %7d' % (
                row['pc'], row['a'], row['b'],
                row['delta']))
    else:
        out.append('  нет')
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
    out.append('СОБЫТИЯ ПО ФАЗАМ')
    out.append('  фаза          A       B')
    for row in report['phase_counts']:
        out.append('  %-10s %7d %7d' % (
            row['phase'], row['a'], row['b']))
    out.append('первая фаза расхождения: %s' % (
        report['first_divergence_phase'] or 'нет'))
    cov = report['coverage']
    out.append('ПОКРЫТИЕ СЕГМЕНТОВ')
    out.append('  сегмент      PC A   PC B')
    for row in cov['segments']:
        out.append('  %-11s %5d %5d' % (
            row['segment'], row['a_pcs'], row['b_pcs']))
    out.append('PC вне сегментов: %d' %
               cov['unmapped_count'])
    return '\n'.join(out)


def format_catalog_text(report):
    """Human-readable catalog report under 60 columns."""
    out = ['V78 АТЛАС ПОКРЫТИЯ']
    out.append('каталог: %s' % report['catalog_dir'][:48])
    out.append('фикстур: %d' % report['fixture_count'])
    out.append('событий: %d' % report['events'])
    out.append('команд : %d' % report['exec_events'])
    out.append('покрыто PC: %d' % report['covered_pcs'])
    cand = report['candidates']
    out.append('кандидатов: %d' % report['candidate_count'])
    out.append('  источник: %s' % cand['source'][:46])
    out.append('  в отчёте: %s' % cand['declared_total'])
    out.append('  поименовано: %s' % cand['explicit_count'])
    out.append('НЕПОКРЫТЫЕ КАНДИДАТЫ')
    if report['uncovered']:
        for pc in report['uncovered']:
            out.append('  %s' % pc)
    else:
        out.append('  нет')
    return '\n'.join(out)


def build_parser():
    """CLI definition."""
    parser = argparse.ArgumentParser(
        description=(
            'Differential atlas for ВЕР.06/78 event '
            'fixtures; read-only, streaming.'))
    parser.add_argument(
        'events_a', metavar='EVENTS_A', nargs='?',
        help='first event JSONL fixture')
    parser.add_argument(
        'events_b', metavar='EVENTS_B', nargs='?',
        help='second event JSONL fixture')
    parser.add_argument(
        '--catalog', metavar='DIR',
        help='directory of fixtures to aggregate')
    parser.add_argument(
        '--candidates', metavar='FILE',
        help='plain list of candidate PCs, one per line')
    parser.add_argument(
        '--segments', metavar='FILE',
        help='custom segment table (JSON or text)')
    parser.add_argument(
        '--format', choices=('json', 'text'),
        default='text',
        help='output format (default: text)')
    parser.add_argument(
        '--check', action='store_true',
        help='strict schema check; exit 1 on any '
             'divergence or coverage gap')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.catalog:
        if args.events_a or args.events_b:
            print('error: positional fixtures are not '
                  'used with --catalog',
                  file=sys.stderr)
            return 2
        if args.candidates and not os.path.isfile(
                args.candidates):
            print('error: candidates file not found',
                  file=sys.stderr)
            return 2
    elif not args.events_a or not args.events_b:
        print('error: two event fixtures are required',
              file=sys.stderr)
        return 2
    try:
        segments = load_segments(args.segments)
        if args.catalog:
            report = catalog(args.catalog,
                             args.candidates,
                             args.check)
        else:
            report = compare(args.events_a,
                             args.events_b,
                             args.check,
                             segments)
    except (InputError, OSError, ValueError) as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2
    if args.format == 'json':
        print(json.dumps(report, ensure_ascii=False,
                         sort_keys=True, indent=2))
    elif report['mode'] == 'catalog':
        print(format_catalog_text(report))
    else:
        print(format_pair_text(report))
    return 1 if has_divergence(report) else 0


if __name__ == '__main__':
    sys.exit(main())
