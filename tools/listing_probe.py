#!/usr/bin/env python3
"""Read-only probe for BEMSH (МАКРО-БЕМШ) listing files.

Extracts the fixed column layout, counts object words, detects the
translator error summary and the banner/shamp lines. No emulator and no
image access, the input is plain listing text.

Usage:
    python3 tools/listing_probe.py LISTING.out [--format json|text]
"""
import argparse
import json
import re
import sys

# Latin glyphs rendered by the 7-bit/GOST printer in place of Cyrillic.
# Translation is one-to-one, so character positions are preserved.
OMO = str.maketrans({
    'A': 'А', 'B': 'В', 'E': 'Е', 'H': 'Н', 'K': 'К', 'M': 'М',
    'N': 'Н', 'O': 'О', 'P': 'Р', 'C': 'С', 'T': 'Т', 'X': 'Х',
    'Y': 'У', 'a': 'а', 'e': 'е', 'o': 'о', 'p': 'р', 'c': 'с',
    'x': 'х', 'y': 'у', '3': 'З',
})

# 0-based start columns, from re-dispak/AGENTS.md section 9 and the real
# 0137 listing. Python slice [25:30] is the АДРЕС field.
DEFAULT_COLUMNS = {
    'ОШИБКИ': 0, 'НПК': 9, 'СВОБ': 14, 'ПЕРЕМ': 19,
    'АДРЕС': 25, 'КОМАНДА': 31, 'А ИСП': 42, 'Н ГЕН': 48,
    'Н ИСХ': 54, 'МЕТКА': 60, 'ОПЕРАЦИЯ': 67,
    'ОПЕРАНД': 76, 'КОММЕНТАРИЙ': 86,
}

HEADER_TOKENS = tuple(DEFAULT_COLUMNS)

BANNERS = (
    'ИПМ МАКРО-БЕМШ ВЕР.06/78',   # B stamp, 0147.1315-1320
    'АРАП ВАР.04/78',              # ARAP B, 0152.1164-1166
    'МАКРОРЕДАКТОР ОТ 20.06.78',   # 0154.0751-0755
    'МАКРОМАШИНА ОТ 1.11.78',      # 0170.0216-0221
    'ИПМ МАГ-БЕМШ ВАР.А(12/71',    # old stamp, 0176.1732-1735
    'ИМ ПРГ СТР',                  # old header, 0176.1737-1740
    'ИПМ МАКРО-БЕМШ ВАР.12/77',    # B2 stamp
    'АРАП ВАР.10/75',              # ARAP B2
    'ОШ. СПРАВКИ БЕМШ2',           # B2 reference
)

RE_WORD = re.compile(r'^([0-7]{16})\b')
RE_CMD = re.compile(r'^([0-7]{2})\s+([0-7]{2,3})\s+([0-7]{4,5})\b')
RE_ADDRESS = re.compile(r'[0-7]{5}')


def strip_bom(text):
    """Remove a single UTF-8 BOM at the very start."""
    return text[1:] if text.startswith('\ufeff') else text


def omo(text):
    """Map printer omoglyphs to Cyrillic without changing length."""
    return text.translate(OMO)


def squash(text):
    """Normalized text with whitespace collapsed, for phrase matching."""
    return ' '.join(omo(text).split())


def find_header(lines):
    """Return (1-based line, {column: start}) or (None, {})."""
    for i, line in enumerate(lines):
        n = omo(line)
        if 'АДРЕС' in n and 'КОМАНДА' in n and 'МЕТКА' in n:
            cols = {}
            for name in HEADER_TOKENS:
                pos = n.find(name)
                if pos >= 0:
                    cols[name] = pos
            return i + 1, cols
    return None, {}


def find_banners(lines):
    """Return recognized shamp/banner phrases in order of appearance."""
    found = []
    for line in lines:
        s = squash(line)
        for phrase in BANNERS:
            if phrase in s and phrase not in found:
                found.append(phrase)
    return found


def find_footer(lines):
    """Parse 'ЧИСЛО ОШИБОК=NNNN. МАКС СЕРЬЕЗН=N.' if present."""
    for i, line in enumerate(lines):
        s = squash(line)
        m = re.search(r'ЧИСЛО ОШИБОК\s*=\s*(\d+)', s)
        if not m:
            continue
        m2 = re.search(r'МАКС СЕРЬЕЗН\s*=\s*(\d+)', s)
        return {
            'errors': int(m.group(1)),
            'serious': int(m2.group(1)) if m2 else None,
            'line': i + 1,
        }
    return None


def parse_address(line, start=25, stop=30):
    """[start:stop] is the fixed АДРЕС field: int, None or 'bad'."""
    field = line[start:stop]
    if RE_ADDRESS.fullmatch(field):
        return int(field, 8)
    if not field.strip():
        return None
    return 'bad'


def parse_words(lines, start=25, stop=30, cmd_col=31):
    """Mirror tools/rebuild-zone.sh listing parsing.

    A КОНД line carries a 16-octal-digit word. A command is printed as two
    24-bit halves: the first at the address, the second on the next line
    with an empty АДРЕС field.
    """
    whole = pairs = other = 0
    pending = None
    values = {}
    for line in lines:
        addr = parse_address(line, start, stop)
        if addr == 'bad':
            other += 1
            continue
        rest = line[cmd_col:].lstrip()
        m = RE_WORD.match(rest)
        if m:
            if addr is not None:
                values[addr] = int(m.group(1), 8)
                whole += 1
                pending = None
            continue
        m = RE_CMD.match(rest)
        if m:
            reg, op, af = (int(m.group(1), 8), int(m.group(2), 8),
                           int(m.group(3), 8))
            shift = 15 if len(m.group(3)) == 5 else 12
            half = (reg << 20) | (op << shift) | af
            if addr is not None:
                pending = addr
                values[addr] = half << 24
            elif pending is not None:
                values[pending] |= half
                pairs += 1
                pending = None
    return {
        'whole_words': whole,
        'half_pairs': pairs,
        'words_total': len(values),
        'non_address_lines': other,
        'addresses': sorted(values),
        'values': values,
    }


def probe(text):
    """Probe listing text and return a deterministic result dict."""
    lines = strip_bom(text).splitlines()
    header_line, cols = find_header(lines)
    columns = dict(DEFAULT_COLUMNS)
    columns.update(cols)
    return {
        'lines': len(lines),
        'header_line': header_line,
        'columns_from_header': bool(cols),
        'columns': columns,
        'banners': find_banners(lines),
        'footer': find_footer(lines),
        'parse': parse_words(lines),
    }


def format_text(r):
    """Compact human-readable summary, lines within 60 columns."""
    out = ['LISTING PROBE']
    out.append('lines       : %d' % r['lines'])
    out.append('header line : %s' % (r['header_line'] or 'NOT FOUND'))
    out.append('banners (%d):' % len(r['banners']))
    out.extend('  ' + b for b in r['banners'])
    f = r['footer']
    if f:
        out.append('errors      : %d (serious %s), line %d'
                   % (f['errors'], f['serious'], f['line']))
    else:
        out.append('errors      : NOT FOUND')
    p = r['parse']
    out.append('whole words : %d' % p['whole_words'])
    out.append('half pairs  : %d' % p['half_pairs'])
    out.append('words total : %d' % p['words_total'])
    out.append('other field : %d' % p['non_address_lines'])
    out.append('columns (%s):'
               % ('header' if r['columns_from_header'] else 'defaults'))
    for name, pos in r['columns'].items():
        out.append('  %-12s %d' % (name, pos))
    return '\n'.join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Probe a BEMSH listing.')
    ap.add_argument('listing', help='path to LISTING.out (read-only)')
    ap.add_argument('--format', choices=('json', 'text'), default='text',
                    help='output format (default: text)')
    args = ap.parse_args(argv)
    try:
        with open(args.listing, encoding='utf-8') as fh:
            text = fh.read()
    except OSError as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2
    result = probe(text)
    if args.format == 'json':
        print(json.dumps(result, ensure_ascii=False, sort_keys=True,
                         indent=2))
    else:
        print(format_text(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
