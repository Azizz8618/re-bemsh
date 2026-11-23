#!/usr/bin/env python3
"""Read-only probe for text-pool descriptors.

Extracts references to the pool symbols 072000, 06402
and 06445, and decodes 48-bit octal descriptor words
of the form

    [ 2010 | N | 0005 | 200K ](8)

found in a .be source or in a dispak trace/listing.
Each 12-bit field is reported separately. No emulator,
no image access and no writes: input is plain text.

Usage:
    python3 tools/text_pool_probe.py FILE...
    python3 tools/text_pool_probe.py FILE... --check

The --check mode validates four invariants and exits
1 when any fails: flag 2010, constant 0005, K in 2..5
and a nondecreasing ordinal N. See the report
analysis/POOL-DESCRIPTOR-FIELDS.md.
"""
import argparse
import json
import os
import re
import sys

# Fixed fields, from POOL-DESCRIPTOR-FIELDS.md section 1.
FLAG_2010 = 0o2010      # 2000 OR 0010, set by aox 6126
FLAG_2000 = 0o2000      # seen after MEND in memory dumps
TAG_0005 = 0o0005       # constant from cell 01762
BASE_2000 = 0o2000      # base of the low 12-bit field
MASK_01762 = 0o00052000  # (0005 << 12) | 2000
MASK_OCT = '%016o' % MASK_01762
K_MIN = 2
K_MAX = 5
SYMBOL_NAMES = ('72000', '6402', '6445')

# A symbol digit run must not start inside a longer
# octal number. A leading letter (C6402) or a leading
# zero (06402) is fine.
RE_SYMBOL = re.compile(
    r'(?<![0-7])0*(72000|6402|6445)(?![0-7])')
RE_WORD16 = re.compile(
    r'(?<![0-7])([0-7]{16})(?![0-7])')
RE_FIELDS4 = re.compile(
    r'(?<![0-7])(2010|2000)[ \t]+([0-7]{4})[ \t]+'
    r'([0-7]{4})[ \t]+([0-7]{4})(?![0-7])')

DEFINE_MARKERS = ('ЭКВ', 'EQU')
WRITE_MARKERS = ('atx', 'ЗП', 'store')
READ_MARKERS = ('СЧ', 'xta', 'arx', 'read')


def strip_bom(text):
    """Remove a single UTF-8 BOM at the very start."""
    return text[1:] if text.startswith('\ufeff') else text


def short(path):
    """Basename shortened for the fixed-width table."""
    return os.path.basename(path)[:12]


def decode_word(word):
    """Split one 48-bit octal word into four fields."""
    flag = (word >> 36) & 0o7777
    line_no = (word >> 24) & 0o7777
    tag = (word >> 12) & 0o7777
    words_field = word & 0o7777
    if words_field >= BASE_2000:
        k = words_field - BASE_2000
    else:
        k = None
    return {
        'word': '%016o' % word,
        'flag': '%04o' % flag,
        'N': '%04o' % line_no,
        'tag': '%04o' % tag,
        'words_field': '%04o' % words_field,
        'K': k,
        'k_ok': k is not None and K_MIN <= k <= K_MAX,
    }


def decode_fields(flag, line_no, tag, words_field):
    """Build a word from four fields, then decode it."""
    word = ((flag << 36) | (line_no << 24) |
            (tag << 12) | words_field)
    return decode_word(word)


def role_of(line):
    """Role of a symbol line: define/write/read/mention."""
    if any(marker in line for marker in DEFINE_MARKERS):
        return 'define'
    if any(marker in line for marker in WRITE_MARKERS):
        return 'write'
    if any(marker in line for marker in READ_MARKERS):
        return 'read'
    return 'mention'


def scan_text(text, source='-'):
    """Scan one text and return symbol and word records."""
    lines = strip_bom(text).splitlines()
    symbols = []
    descriptors = []
    prefix_2000 = []
    for i, line in enumerate(lines, 1):
        for name in sorted(set(RE_SYMBOL.findall(line))):
            symbols.append({
                'source': source,
                'line': i,
                'symbol': name,
                'role': role_of(line),
                'text': line.strip()[:56],
            })
        for match in RE_WORD16.finditer(line):
            word = int(match.group(1), 8)
            flag = (word >> 36) & 0o7777
            if flag not in (FLAG_2010, FLAG_2000):
                continue
            record = decode_word(word)
            record['source'] = source
            record['line'] = i
            if flag == FLAG_2010:
                descriptors.append(record)
            else:
                prefix_2000.append(record)
        for match in RE_FIELDS4.finditer(line):
            flag = int(match.group(1), 8)
            record = decode_fields(
                flag, int(match.group(2), 8),
                int(match.group(3), 8),
                int(match.group(4), 8))
            record['source'] = source
            record['line'] = i
            if flag == FLAG_2010:
                descriptors.append(record)
            else:
                prefix_2000.append(record)
    return {
        'symbols': symbols,
        'descriptors': descriptors,
        'prefix_2000': prefix_2000,
        'lines': len(lines),
    }


def probe(paths):
    """Probe input files in order, return a stable dict."""
    result = {
        'sources': list(paths),
        'lines_total': 0,
        'symbols': [],
        'descriptors': [],
        'prefix_2000': [],
    }
    for path in paths:
        with open(path, encoding='utf-8',
                  errors='replace') as handle:
            text = handle.read()
        part = scan_text(text, path)
        result['lines_total'] += part['lines']
        result['symbols'].extend(part['symbols'])
        result['descriptors'].extend(part['descriptors'])
        result['prefix_2000'].extend(part['prefix_2000'])
    counts = {name: 0 for name in SYMBOL_NAMES}
    for entry in result['symbols']:
        counts[entry['symbol']] += 1
    result['counts'] = {
        'symbols': counts,
        'symbol_lines': len(result['symbols']),
        'descriptors': len(result['descriptors']),
        'prefix_2000': len(result['prefix_2000']),
    }
    return result


def check(result):
    """Validate the four documented invariants."""
    records = result['descriptors']
    if not records:
        return {
            'ok': False,
            'checked': 0,
            'violations': [{
                'invariant': 'descriptor_present',
                'source': '-',
                'line': 0,
                'detail': 'no prefix-2010 word found',
            }],
        }
    violations = []
    # N is an ordinal inside one pool stream, so compare
    # only records that came from the same source file.
    previous = {}
    for record in records:
        where = (record['source'], record['line'])
        if record['flag'] != '%04o' % FLAG_2010:
            violations.append({
                'invariant': 'flag_2010',
                'source': where[0],
                'line': where[1],
                'detail': record['flag'],
            })
        if record['tag'] != '%04o' % TAG_0005:
            violations.append({
                'invariant': 'tag_0005',
                'source': where[0],
                'line': where[1],
                'detail': record['tag'],
            })
        if not record['k_ok']:
            violations.append({
                'invariant': 'K_2_5',
                'source': where[0],
                'line': where[1],
                'detail': record['words_field'],
            })
        ordinal = int(record['N'], 8)
        last = previous.get(where[0])
        if last is not None and ordinal < last:
            violations.append({
                'invariant': 'N_monotonic',
                'source': where[0],
                'line': where[1],
                'detail': record['N'],
            })
        previous[where[0]] = ordinal
    return {
        'ok': not violations,
        'checked': len(records),
        'violations': violations,
    }


def format_text(result, checked=None):
    """Human-readable summary, lines within 60 columns."""
    counts = result['counts']
    out = ['TEXT POOL PROBE']
    out.append('sources   : %d' % len(result['sources']))
    out.append('lines     : %d' % result['lines_total'])
    out.append('sym lines : %d' % counts['symbol_lines'])
    for name in SYMBOL_NAMES:
        out.append('  %-6s %d' %
                   (name, counts['symbols'][name]))
    out.append('descriptor: %d' % counts['descriptors'])
    out.append('prefix2000: %d' % counts['prefix_2000'])
    out.append('mask 01762: %s' % MASK_OCT)
    if result['descriptors']:
        out.append('DESCRIPTORS (flag N tag 200K K)')
        shown = result['descriptors'][:20]
        for record in shown:
            out.append('  %-12s %4d %s %s %s %s %s' % (
                short(record['source']), record['line'],
                record['flag'], record['N'], record['tag'],
                record['words_field'],
                '-' if record['K'] is None
                else record['K']))
        extra = len(result['descriptors']) - len(shown)
        if extra:
            out.append('  ... %d more' % extra)
    if checked is not None:
        status = 'OK' if checked['ok'] else 'FAIL'
        out.append('CHECK %s (%d checked)' %
                   (status, checked['checked']))
        for item in checked['violations'][:10]:
            out.append('  %s %s:%d %s' % (
                item['invariant'], short(item['source']),
                item['line'], item['detail']))
    return '\n'.join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Probe text-pool words (read-only).')
    parser.add_argument(
        'inputs', nargs='+',
        help='.be source and/or dispak listing')
    parser.add_argument(
        '--format', choices=('json', 'text'),
        default='text',
        help='output format (default: text)')
    parser.add_argument(
        '--check', action='store_true',
        help='validate invariants; exit 1 on violation')
    args = parser.parse_args(argv)
    try:
        result = probe(args.inputs)
    except OSError as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2
    checked = check(result) if args.check else None
    if args.format == 'json':
        payload = dict(result)
        if checked is not None:
            payload['check'] = checked
        print(json.dumps(
            payload, ensure_ascii=False,
            sort_keys=True, indent=2))
    else:
        print(format_text(result, checked))
    if checked is not None and not checked['ok']:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
