#!/usr/bin/env python3
"""Streaming analyzer for dispak -tt traces and RVS.

Reads trace files line by line and never writes to them.
Executed instructions are lines that start with five octal
digits, a colon and a mnemonic. Store lines are memory
writes, DD lines are I/O events. Neither is an executed PC.

A catalog field stream (decoded z0001.txt) is split on the
U+203E separator. Each МДЛ record carries a name, a tape
zone code, an octal НАЗ load address and a ЗОНГП zone with
a length in 1024-word pages. A module range is
    [НАЗ, НАЗ + length * 0o1000).
Overlapping ranges are resolved by the narrowest range and
then by catalog order. Such overlaps are reported by --check
because they make attribution ambiguous.

Usage:
    python3 tools/rvs_trace.py TRACE [TRACE...]
    python3 tools/rvs_trace.py TRACE --catalog z0001.txt
    python3 tools/rvs_trace.py TRACE --format json --check

Exit codes: 0 ok, 1 check failed, 2 input or CLI error.
See analysis/RVS-TRACE-TOOL.md.
"""
import argparse
from array import array
from collections import Counter
import json
import os
import re
import sys

PC_LIMIT = 0o200000          # addresses 0..0177777
PAGE_SHIFT = 9               # page = PC >> 9
PAGE_SIZE = 1 << PAGE_SHIFT  # 0o1000 words
TOP_N = 20                   # rows in text tables
SAMPLE_N = 5                 # bounded malformed samples
VIOLATION_N = 30             # bounded check output
FIELD_SEP = '\u203e'         # decoded catalog separator
OCT = frozenset('01234567')

RE_PC = re.compile(r'^([0-7]{5}):\s+([A-Za-z0-9*+\-]+)')
RE_STORE = re.compile(r'^\s*([0-7]{5,6}):\s+store\b', re.I)
RE_DD_PC = re.compile(r'\bpc=([0-7]{1,6})L?(?![0-7])')
RE_DD_U = re.compile(r'\bu=([0-7]+)\b')
RE_DD_Z = re.compile(r'\bz=([0-7]+)\b')
RE_MDL = re.compile(r'^МДЛ\s+(.+)$', re.I)
RE_NAZ = re.compile(r'^НАЗ\s+(\S+)', re.I)
RE_ZONGP = re.compile(r'^ЗОНГП\s+(\S+)\s+(\S+)', re.I)
RE_MDL_TAIL = re.compile(r'^(.*?)([0-7]{6})$')
RE_OCTAL = re.compile(r'^[0-7]{1,6}$')


def octstr(value, digits=0):
    """Format an address as an octal string."""
    if digits:
        return ('%%0%do' % digits) % value
    return '%o' % value


def split_mdl(payload):
    """Split a МДЛ payload into name and tape zone."""
    text = ' '.join(payload.split())
    match = RE_MDL_TAIL.match(text)
    if match:
        return match.group(1).strip(), match.group(2)
    return text, None


def parse_catalog(text, source='catalog'):
    """Parse decoded catalog text into module records."""
    fields = []
    for row in text.replace('\r', '\n').split('\n'):
        fields.extend(row.split(FIELD_SEP))
    raw = []
    current = None
    for field in fields:
        item = field.strip().lstrip('\ufeff')
        if not item:
            continue
        match = RE_MDL.match(item)
        if match:
            if current is not None:
                raw.append(current)
            name, code = split_mdl(match.group(1))
            current = {'name': name, 'code': code}
            continue
        if current is None:
            continue
        match = RE_NAZ.match(item)
        if match:
            current['naz_raw'] = match.group(1)
            continue
        match = RE_ZONGP.match(item)
        if match:
            current['zone'] = match.group(1)
            current['zones_raw'] = match.group(2)
    if current is not None:
        raw.append(current)
    return [finish_module(item, source) for item in raw]


def finish_module(item, source):
    """Validate one catalog record and compute its range."""
    naz = item.get('naz_raw', '')
    valid = bool(RE_OCTAL.match(naz))
    start = int(naz, 8) if valid else None
    zones_raw = item.get('zones_raw', '1')
    zones = 1
    if RE_OCTAL.match(zones_raw):
        zones = int(zones_raw, 8)
    end = None
    if valid:
        end = min(start + zones * PAGE_SIZE, PC_LIMIT)
    return {
        'source': source,
        'name': item['name'],
        'code': item.get('code'),
        'naz': naz or None,
        'zone': item.get('zone'),
        'zones': zones,
        'start': octstr(start, 6) if valid else None,
        'end': octstr(end, 6) if valid else None,
        'valid': valid and end > start,
        '_start': start,
        '_end': end,
    }


def build_index(modules):
    """Return an address -> module index lookup array."""
    index = array('i', [-1]) * PC_LIMIT
    order = sorted(
        (idx for idx, mod in enumerate(modules)
         if mod['valid']),
        key=lambda idx: (
            modules[idx]['_end'] - modules[idx]['_start'],
            idx))
    for idx in order:
        mod = modules[idx]
        for addr in range(mod['_start'], mod['_end']):
            if index[addr] < 0:
                index[addr] = idx
    return index


def fmt_pc(value):
    """Format an optional PC value as five octal digits."""
    return octstr(value, 5) if value is not None else None


def mnemonic_of(counter):
    """Most frequent mnemonic, with a stable tie break."""
    if not counter:
        return None
    ranked = sorted(counter.items(),
                    key=lambda pair: (-pair[1], pair[0]))
    return ranked[0][0]


class Accumulator:
    """Bounded accumulators for one streaming pass."""

    def __init__(self, modules, index):
        self.modules = modules
        self.index = index
        self.lines = 0
        self.instructions = 0
        self.stores = 0
        self.dd_events = 0
        self.unparsed = 0
        self.pc_counts = Counter()
        self.pc_mnemonics = {}
        self.page_counts = Counter()
        self.store_counts = Counter()
        self.dd_u = Counter()
        self.dd_z = Counter()
        self.dd_pair = Counter()
        self.module_hits = [0] * len(modules)
        self.module_first = [None] * len(modules)
        self.module_last = [None] * len(modules)
        self.pc_min = None
        self.pc_max = None
        self.dd_pc_min = None
        self.dd_pc_max = None
        self.pc_out_of_range = 0
        self.samples = []

    def note_sample(self, line, source, lineno):
        """Keep a few malformed line samples."""
        if len(self.samples) < SAMPLE_N:
            self.samples.append({
                'source': source, 'line': lineno,
                'text': line.strip()[:40]})

    def feed(self, line, source, lineno):
        """Classify and accumulate one trace line."""
        self.lines += 1
        text = line.lstrip('\ufeff')
        if text.startswith('DD '):
            self.feed_dd(text, source, lineno)
            return
        if (len(text) >= 7 and text[0] in OCT and
                text[5] == ':'):
            match = RE_PC.match(text)
            if match:
                token = match.group(2)
                if token.lower() == 'store':
                    self.feed_store(match.group(1))
                else:
                    self.feed_pc(match.group(1), token,
                                 source, lineno)
                return
        match = RE_STORE.match(text)
        if match:
            self.feed_store(match.group(1))
            return
        if text.strip():
            self.unparsed += 1
            self.note_sample(text, source, lineno)

    def feed_pc(self, oct_pc, mnemonic, source, lineno):
        """Accumulate one executed instruction."""
        pc = int(oct_pc, 8)
        self.instructions += 1
        self.pc_counts[pc] += 1
        counts = self.pc_mnemonics.setdefault(pc, Counter())
        counts[mnemonic] += 1
        self.page_counts[pc >> PAGE_SHIFT] += 1
        if self.pc_min is None or pc < self.pc_min:
            self.pc_min = pc
        if self.pc_max is None or pc > self.pc_max:
            self.pc_max = pc
        if pc >= PC_LIMIT:
            self.pc_out_of_range += 1
        if self.index is not None and pc < PC_LIMIT:
            idx = self.index[pc]
            if idx >= 0:
                self.module_hits[idx] += 1
                if self.module_first[idx] is None:
                    self.module_first[idx] = lineno
                self.module_last[idx] = lineno

    def feed_store(self, oct_addr):
        """Accumulate one memory write, never a PC."""
        self.stores += 1
        self.store_counts[int(oct_addr, 8)] += 1

    def feed_dd(self, text, source, lineno):
        """Accumulate one DD I/O event, never a PC."""
        self.dd_events += 1
        match = RE_DD_PC.search(text)
        if match:
            pc = int(match.group(1), 8)
            if (self.dd_pc_min is None or
                    pc < self.dd_pc_min):
                self.dd_pc_min = pc
            if (self.dd_pc_max is None or
                    pc > self.dd_pc_max):
                self.dd_pc_max = pc
            if pc >= PC_LIMIT:
                self.pc_out_of_range += 1
        match_u = RE_DD_U.search(text)
        match_z = RE_DD_Z.search(text)
        u = '-'
        z = '-'
        if match_u:
            u = octstr(int(match_u.group(1), 8), 3)
        if match_z:
            z = octstr(int(match_z.group(1), 8), 4)
        self.dd_u[u] += 1
        self.dd_z[z] += 1
        self.dd_pair[u + '/' + z] += 1

    def result(self, sources, catalog):
        """Build the stable report dict."""
        pages = [
            {'page': octstr(page, 3), 'count': count}
            for page, count in sorted(
                self.page_counts.items(),
                key=lambda pair: (-pair[1], pair[0]))]
        top_pcs = [
            {'pc': octstr(pc, 5),
             'mnemonic': mnemonic_of(self.pc_mnemonics[pc]),
             'count': count}
            for pc, count in sorted(
                self.pc_counts.items(),
                key=lambda pair: (-pair[1],
                                  pair[0]))[:TOP_N]]
        modules = []
        for idx, mod in enumerate(self.modules):
            row = {key: value for key, value in mod.items()
                   if not key.startswith('_')}
            row['count'] = self.module_hits[idx]
            row['first_line'] = self.module_first[idx]
            row['last_line'] = self.module_last[idx]
            modules.append(row)
        modules.sort(
            key=lambda row: (-row['count'], row['name']))
        store_top = sorted(
            self.store_counts.items(),
            key=lambda pair: (-pair[1], pair[0]))[:TOP_N]
        return {
            'sources': list(sources),
            'catalog': catalog,
            'page_shift': PAGE_SHIFT,
            'lines_total': self.lines,
            'counts': {
                'instructions': self.instructions,
                'stores': self.stores,
                'dd_events': self.dd_events,
                'unparsed': self.unparsed,
                'distinct_pcs': len(self.pc_counts),
                'distinct_pages': len(self.page_counts),
                'distinct_store_addrs':
                    len(self.store_counts),
                'modules': len(modules),
                'pc_out_of_range': self.pc_out_of_range,
            },
            'pc_min': fmt_pc(self.pc_min),
            'pc_max': fmt_pc(self.pc_max),
            'pages': pages,
            'top_pcs': top_pcs,
            'modules': modules,
            'dd': {
                'total': self.dd_events,
                'by_u': dict(sorted(self.dd_u.items())),
                'by_z': dict(sorted(self.dd_z.items())),
                'by_pair': dict(
                    sorted(self.dd_pair.items())),
                'pc_min': fmt_pc(self.dd_pc_min),
                'pc_max': fmt_pc(self.dd_pc_max),
            },
            'stores': {
                'total': self.stores,
                'distinct_addrs': len(self.store_counts),
                'top': [
                    {'addr': octstr(addr, 6),
                     'count': count}
                    for addr, count in store_top],
            },
            'unparsed_samples': self.samples,
        }


def analyze(paths, catalog=None):
    """Stream traces and a catalog, return a report."""
    modules = []
    if catalog:
        with open(catalog, encoding='utf-8',
                  errors='replace') as handle:
            modules = parse_catalog(handle.read(), catalog)
    index = build_index(modules) if modules else None
    acc = Accumulator(modules, index)
    for path in paths:
        if path == '-':
            for lineno, line in enumerate(sys.stdin, 1):
                acc.feed(line.rstrip('\r\n'), '-', lineno)
            continue
        with open(path, encoding='utf-8',
                  errors='replace') as handle:
            for lineno, line in enumerate(handle, 1):
                acc.feed(line.rstrip('\r\n'), path, lineno)
    return acc.result(paths, catalog)


def walk_numbers(value, path=''):
    """Yield (path, int) for every integer in a report."""
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            child = path + '/' + str(key)
            yield from walk_numbers(item, child)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            child = path + '/%d' % idx
            yield from walk_numbers(item, child)


def check(report):
    """Validate counts, PC bounds and overlaps."""
    violations = []
    numeric = list(walk_numbers(report))
    for path, value in numeric:
        if value < 0:
            violations.append({
                'invariant': 'no_negative_counts',
                'detail': '%s = %d' % (path, value)})
    total = report['counts']['instructions']
    for key in ('pc_min', 'pc_max'):
        text = report.get(key)
        if text and not 0 <= int(text, 8) < PC_LIMIT:
            violations.append({
                'invariant': 'pc_range',
                'detail': '%s = %s' % (key, text)})
    for key in ('pc_min', 'pc_max'):
        text = report['dd'].get(key)
        if text and not 0 <= int(text, 8) < PC_LIMIT:
            violations.append({
                'invariant': 'pc_range',
                'detail': 'dd_%s = %s' % (key, text)})
    ranges = sorted(
        (mod for mod in report['modules'] if mod['valid']),
        key=lambda mod: int(mod['start'], 8))
    for left, right in zip(ranges, ranges[1:]):
        lo = int(right['start'], 8)
        hi = int(left['end'], 8)
        if lo < hi:
            violations.append({
                'invariant': 'module_no_overlap',
                'detail': '%s [%s..%s) / %s [%s..%s)' % (
                    left['name'], left['start'],
                    left['end'], right['name'],
                    right['start'], right['end'])})
    truncated = max(0, len(violations) - VIOLATION_N)
    return {
        'ok': not violations,
        'checked': total + len(numeric) + len(ranges),
        'violations_total': len(violations),
        'truncated': truncated,
        'violations': violations[:VIOLATION_N],
    }


def format_text(report, checked=None):
    """Human-readable summary under 60 columns."""
    counts = report['counts']
    out = ['RVS TRACE ANALYZER']
    out.append('источников: %d' % len(report['sources']))
    out.append('строк      : %d' % report['lines_total'])
    out.append('команд     : %d' % counts['instructions'])
    out.append('store      : %d' % counts['stores'])
    out.append('DD событий : %d' % counts['dd_events'])
    out.append('прочих     : %d' % counts['unparsed'])
    out.append('PC         : %s..%s' % (
        report['pc_min'] or '-', report['pc_max'] or '-'))
    if report['pages']:
        out.append('СТРАНИЦЫ PC (всего %d)' %
                   counts['distinct_pages'])
        for row in report['pages'][:12]:
            out.append('  %3s %10d' %
                       (row['page'], row['count']))
    if report['top_pcs']:
        out.append('ВЕРХ PC (всего %d)' %
                   counts['distinct_pcs'])
        for row in report['top_pcs'][:12]:
            out.append('  %5s %-6s %10d' % (
                row['pc'], row['mnemonic'], row['count']))
    if report['modules']:
        out.append('МОДУЛИ (всего %d)' % counts['modules'])
        for row in report['modules'][:12]:
            first = row['first_line'] or '-'
            last = row['last_line'] or '-'
            out.append('  %-10s %6s %8d %7s %7s' % (
                row['name'][:10], row['naz'] or '-',
                row['count'], first, last))
    if report['dd']['total']:
        out.append('DD ПО u')
        for key, value in list(
                report['dd']['by_u'].items())[:12]:
            out.append('  %3s %10d' % (key, value))
        out.append('DD ПО z')
        for key, value in list(
                report['dd']['by_z'].items())[:12]:
            out.append('  %4s %10d' % (key, value))
    if checked is not None:
        status = 'OK' if checked['ok'] else 'FAIL'
        out.append('ПРОВЕРКА %s (%d)' % (
            status, checked['checked']))
        out.append('нарушений: %d' %
                   checked['violations_total'])
        for item in checked['violations'][:10]:
            out.append('  %s %s' % (
                item['invariant'], item['detail'][:38]))
        if checked['truncated']:
            out.append('  ... ещё %d' %
                       checked['truncated'])
    return '\n'.join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='RVS trace analyzer (read-only).')
    parser.add_argument(
        'traces', nargs='+',
        help='dispak -tt trace file(s), "-" for stdin')
    parser.add_argument(
        '--catalog', metavar='FILE',
        help='decoded catalog text (z0001.txt)')
    parser.add_argument(
        '--format', choices=('json', 'text'),
        default='text',
        help='output format (default: text)')
    parser.add_argument(
        '--check', action='store_true',
        help='validate invariants; exit 1 on violation')
    args = parser.parse_args(argv)
    try:
        result = analyze(args.traces, args.catalog)
    except (OSError, ValueError) as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2
    checked = check(result) if args.check else None
    if args.format == 'json':
        payload = dict(result)
        if checked is not None:
            payload['check'] = checked
        print(json.dumps(payload, ensure_ascii=False,
                         sort_keys=True, indent=2))
    else:
        print(format_text(result, checked))
    if checked is not None and not checked['ok']:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
