#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only probe for operand syntax forms in .be sources.

Classifies every operand line as one form and validates the
operand to PC catalog facts kept in the report
analysis/OPERAND-PROBE.md. Input is plain text:
no emulator, no image access, no writes.

Usage:
    python3 tools/v78_operand_probe.py FILE...
    python3 tools/v78_operand_probe.py --catalog macros.be
    python3 tools/v78_operand_probe.py FILE --check
    python3 tools/v78_operand_probe.py FILE \
        --format json --summary --form cell_ref

Exit codes: 0 ok, 1 check violation, 2 input or CLI error.
"""
import argparse
from collections import Counter
import json
import os
import re
import sys

FORMS = (
    'none', 'bare_number', 'quoted_number', 'cell_ref',
    'register', 'register_pair', 'string_constant',
    'equiv_expr', 'macro_param', 'label', 'external',
    'mnemonic_operand', 'unknown',
)

# Mnemonics seen in bemsh/*.be and in re-dispak/macros.be.
# Cyrillic and Latin homoglyphs are both kept as spelled.
OPCODES = frozenset((
    'ЗП', 'СЧ', 'СЛ', 'ВЧ', 'ВЧОБ', 'ВЧАБ', 'НТЖ', 'СЛЦ',
    'ЗНАК', 'ИЛИ', 'ДЕЛ', 'УМН', 'СЧМ', 'СЛП', 'СДА', 'РЖА',
    'УИ', 'УИМ', 'СЧИ', 'СЧИМ', 'УИИ', 'СЛИ', 'И',
    'МОДА', 'МОД',
    'УИА', 'СЛИА', 'ПО', 'ПЕ', 'ПБ', 'ПВ', 'ЦИКЛ', 'ПИО',
    'ПИНО', 'СБР', 'ВЫПР', 'УВВ', 'СЧРЖ', 'СЧМР',
    'Э50', 'Э52', 'Э66', 'Э67', 'Э73', 'Э77',
    'ЭКВ', 'СТАРТ', 'РЕГ', 'КОНД', 'КОНК',
    'ВНЕШН', 'ВНЕШ', 'ВХОДН', 'ВХОД', 'ВХОДС', 'ВХОДБ',
    'ВНЕШБ', 'ВНЕШС', 'КОНДБ', 'КОНДС', 'ЕВНЕШ',
    'МАСRО', 'МЕND', 'АIF', 'АNОР', 'АНОР', 'SЕТА', 'SЕТВ',
    'GВLА', 'GВLВ', 'LСLА', 'ЭКВИВ', 'ОПРЕ', 'ЕЕ', 'Б',
    'ДК', 'СПО', 'ТЕКСТ', 'ПРЕ', 'ВО', 'ФИНИШ', 'Е', 'М',
    'АНОП', 'НОП', 'ВТБРЗ', 'ШИАР', 'ШИФАР', 'МNОТЕ',
    'РЗБ', 'КОТПВВ', 'ДАЙКОТ', 'ТЕРМ', 'КО', 'ВТ∧SNDХ',
))

EXTERNAL = frozenset((
    'ВНЕШН', 'ВНЕШ', 'ВХОДН', 'ВХОД', 'ВХОДС', 'ВХОДБ',
    'ВНЕШБ', 'ВНЕШС', 'ЕВНЕШ',
))

NO_WORD = frozenset((
    'ЭКВ', 'СТАРТ', 'РЕГ', 'ЭКВИВ', 'ОПРЕ',
)) | EXTERNAL

MACRO_TIME = frozenset((
    'МАСRО', 'МЕND', 'АIF', 'АNОР', 'АНОР', 'SЕТА', 'SЕТВ',
    'GВLА', 'GВLВ', 'LСLА', 'ЕЕ', 'Б', 'ДК', 'СПО',
    'ПРЕ', 'ВО', 'ФИНИШ', 'Е', 'М',
    'АНОП', 'НОП', 'ВТБРЗ', 'ШИАР', 'ШИФАР', 'МNОТЕ',
    'ВТ∧SNDХ',
))

DATA_WORD = frozenset(('КОНД', 'КОНК', 'ТЕКСТ'))

STRING_PREFIXES = ('П', 'В', 'К', 'Х')
QUOTES = "'’"
PARAM_MARK = '∧↑'

RE_REG = re.compile(r'(?P<reg>\((?:[МM]\d+|\d+)\))\s*$')
RE_REG_PAIR = re.compile(
    r'^\((?:[МM]\d+|\d+),\d+\)'
    r'(?:,\((?:[МM]\d+|\d+),\d+\))*$')
RE_CELL = re.compile(
    r'(?P<sym>[DAG](?P<addr>[0-7]{5}))'
    r'(?P<minus>-З)?(?P<off>[+-]\d+)?$')
RE_QUOTED = re.compile(r"^['’]([0-7]+)['’]$")
RE_QUOTED_INNER = re.compile(r"['’]([0-7]+)['’]")
RE_STRING = re.compile(r"^([ПВКХ])['’](.*)['’]$")
RE_BARE = re.compile(r'^[+-]?\d+$')
RE_LABEL = re.compile(r'^[A-Za-zА-Яа-яЁё][\w.]*$')
RE_LABELISH = re.compile(
    r'^[A-Za-zА-Яа-яЁё][\w.]*\d[\w.]*$')
RE_PARAM = re.compile('[' + PARAM_MARK + r']')
RE_ARITH = re.compile(r'[+-]')
RE_SIGNED_NUM = re.compile(r'([+-])\s*(\d+)')
RE_MINUS_PARAM = re.compile(r'-\s*([∧↑]\w+)')

CHECK_SAMPLE = 200
VIOLATION_N = 30
SHOW_ROWS = 20


def strip_bom(text):
    """Remove a single UTF-8 BOM at the very start."""
    return text[1:] if text.startswith('\ufeff') else text


def short(path):
    """Basename shortened for the fixed-width table."""
    return os.path.basename(path)[:8]


def strip_comment(text):
    """Cut a trailing comment after a comma.

    A comma starts a comment when the next char is a space,
    or when the rest reads like prose. A comma inside
    ∧А,∧Б or (М1,1) is kept as part of the operand.
    """
    for pos, char in enumerate(text):
        if char != ',':
            continue
        tail = text[pos + 1:]
        if not tail:
            return text[:pos]
        if tail[0].isspace():
            return text[:pos]
        if tail[0] != '∧' and (
                ' ' in tail or ';' in tail
                or ':' in tail):
            return text[:pos]
    return text


def is_labelish(token):
    """Does this token look like a label, not an opcode?"""
    if token.startswith(('∧', '↑', '.')):
        return True
    return bool(RE_LABELISH.match(token))


def strip_inline_note(code):
    """Drop a prose tail written into the operand field.

    Catalog lines such as SЕТА 0 ДЛЯ ТРУБКА carry notes.
    A leading * is also a note inside the code field.
    """
    cut = len(code)
    for marker in (' ДЛЯ ', ' ВМЕСТО ', ' * '):
        pos = code.find(marker)
        if pos >= 0:
            cut = min(cut, pos)
    return code[:cut].strip()


def split_fields(text):
    """Return (mnemonic, operand) for one code line.

    Comments are cut by strip_comment(). Commas inside
    a macro list (∧А,∧Б) stay part of the operand.
    """
    code = strip_comment(text).strip()
    if not code or code.startswith('*'):
        return None
    code = strip_inline_note(code)
    if not code:
        return None
    tokens = code.split()
    if tokens[0] in OPCODES:
        idx = 0
    elif len(tokens) >= 2 and (
            tokens[1] in OPCODES or is_labelish(tokens[0])):
        idx = 1
    else:
        idx = 0
    return tokens[idx], ' '.join(tokens[idx + 1:])


def split_register(operand):
    """Peel a trailing register suffix off one operand."""
    text = operand.strip()
    match = RE_REG.search(text)
    if match is None:
        return None, text
    raw = match.group('reg')
    reg = raw[1:-1].replace('M', 'М')
    return reg, text[:match.start()].strip()


def classify(core, register, mnemonic):
    """Return the form of one operand core."""
    if not core:
        return 'register' if register else 'none'
    if mnemonic in EXTERNAL:
        return 'external'
    if RE_STRING.match(core):
        return 'string_constant'
    if RE_REG_PAIR.match(core):
        return 'register_pair'
    if RE_CELL.match(core):
        return 'cell_ref'
    if RE_QUOTED.match(core):
        return 'quoted_number'
    if RE_BARE.match(core):
        return 'bare_number'
    if RE_ARITH.search(core) and (
            RE_PARAM.search(core)
            or RE_SIGNED_NUM.search(core)
            or RE_QUOTED_INNER.search(core)):
        return 'equiv_expr'
    if RE_PARAM.search(core):
        return 'macro_param'
    if core in OPCODES or any(
            token in OPCODES for token in core.split()):
        return 'mnemonic_operand'
    if RE_LABEL.match(core):
        return 'label'
    return 'unknown'


def octal_of(number):
    """Octal text for a signed integer, no 0o prefix."""
    if number < 0:
        return '-' + '%o' % -number
    return '%o' % number


def value_of(form, core):
    """Build the value field with its radix noted."""
    empty = {'radix': 'none', 'raw': core, 'decimal': None,
             'octal': None, 'detail': ''}
    if form in ('label', 'external', 'register',
                'register_pair', 'macro_param',
                'mnemonic_operand', 'none', 'unknown'):
        if form == 'macro_param':
            empty['radix'] = 'symbolic'
        return empty

    if form == 'bare_number':
        number = int(core)
        return {
            'radix': 'decimal', 'raw': core,
            'decimal': number, 'octal': octal_of(number),
            'detail': 'bare число десятичное',
        }

    if form == 'quoted_number':
        digits = core[1:-1]
        return {
            'radix': 'octal', 'raw': core,
            'decimal': int(digits, 8), 'octal': digits,
            'detail': 'кавычки дают восьмеричное',
        }

    if form == 'string_constant':
        match = RE_STRING.match(core)
        prefix, body = match.group(1), match.group(2)
        if body and all(ch in '01234567' for ch in body):
            return {
                'radix': 'octal', 'raw': core,
                'decimal': int(body, 8), 'octal': body,
                'detail': 'префикс %s, восьмеричные цифры'
                          % prefix,
            }
        return {
            'radix': 'text', 'raw': core,
            'decimal': None, 'octal': None,
            'text': body,
            'detail': 'префикс %s, текст' % prefix,
        }

    if form == 'cell_ref':
        match = RE_CELL.match(core)
        addr = int(match.group('addr'), 8)
        off = int(match.group('off')) if match.group(
            'off') else 0
        total = addr + off
        return {
            'radix': 'octal', 'raw': core,
            'decimal': total,
            'octal': '%05o' % total if total >= 0
                     else octal_of(total),
            'base_octal': match.group('addr'),
            'base_decimal': addr,
            'offset_decimal': off,
            'minus_overlay_base': (
                bool(match.group('minus'))),
            'detail': 'база %s(8) + %d(10)%s' % (
                match.group('addr'), off,
                ', минус база наложения'
                if match.group('minus') else ''),
        }

    if form == 'equiv_expr':
        quoted = RE_QUOTED_INNER.search(core)
        const = int(quoted.group(1), 8) if quoted else 0
        radix = 'octal' if quoted else 'decimal'
        rest = RE_QUOTED_INNER.sub(' ', core).strip()
        if rest and rest[0].isdigit():
            rest = '+' + rest
        for sign, digits in RE_SIGNED_NUM.findall(rest):
            step = int(digits)
            const += step if sign == '+' else -step
        symbols = RE_MINUS_PARAM.findall(rest)
        detail = 'постоянная часть'
        if symbols:
            detail += ', минус ' + ' '.join(symbols)
        return {
            'radix': radix, 'raw': core,
            'decimal': const, 'octal': octal_of(const),
            'symbols': symbols, 'detail': detail,
        }

    return empty


def symbol_of(form, core):
    """Referenced symbol, if the operand has one."""
    if form == 'cell_ref':
        match = RE_CELL.match(core)
        return match.group('sym') if match else None
    if form in ('label', 'external', 'macro_param'):
        return core
    return None


def output_class(mnemonic):
    """Expected output class for the owning line."""
    if mnemonic in DATA_WORD:
        return 'data_word'
    if mnemonic in NO_WORD:
        return 'directive_no_word'
    if mnemonic in MACRO_TIME:
        return 'macro_time'
    if mnemonic in OPCODES:
        return 'code_word'
    return 'unknown'


def scan_text(text, source):
    """Scan one text and return its operand records."""
    lines = strip_bom(text).splitlines()
    records = []
    for number, raw in enumerate(lines, 1):
        fields = split_fields(raw)
        if fields is None:
            continue
        mnem, operand = fields
        register, core = split_register(operand)
        form = classify(core, register, mnem)
        records.append({
            'file': source,
            'line': number,
            'mnemonic': mnem,
            'operand': operand,
            'form': form,
            'value': value_of(form, core),
            'symbol': symbol_of(form, core),
            'register': register,
            'output_class': output_class(mnem),
        })
    return records, len(lines)


def probe(paths, catalog=None, form_filter=None):
    """Probe files in order, return a stable dict."""
    sources = list(paths)
    if catalog is not None:
        sources.append(catalog)
    if not sources:
        raise ValueError('no input: FILE or --catalog')
    all_records = []
    lines_total = 0
    for path in sources:
        with open(path, encoding='utf-8',
                  errors='replace') as handle:
            text = handle.read()
        part, count = scan_text(text, path)
        all_records.extend(part)
        lines_total += count
    if form_filter is not None:
        all_records = [rec for rec in all_records
                       if rec['form'] == form_filter]
    forms = Counter(rec['form'] for rec in all_records)
    classes = Counter(rec['output_class']
                      for rec in all_records)
    unclassified = sum(1 for rec in all_records
                       if rec['form'] == 'unknown'
                       or rec['output_class'] == 'unknown')
    return {
        'sources': sources,
        'catalog': catalog,
        'filter': form_filter,
        'lines_total': lines_total,
        'records': all_records,
        'form_counts': dict(
            (name, forms[name]) for name in FORMS
            if forms[name]),
        'class_counts': dict(sorted(classes.items())),
        'unclassified': unclassified,
    }


def check(result):
    """Validate the documented operand invariants."""
    items = []
    checked = 0
    total = 0

    def add(invariant, rec, detail):
        nonlocal total
        total += 1
        if len(items) < VIOLATION_N:
            items.append({
                'invariant': invariant,
                'file': rec['file'],
                'line': rec['line'],
                'detail': detail,
            })

    sampled = 0
    for rec in result['records']:
        form = rec['form']
        value = rec['value']
        raw = rec['operand']
        if raw.strip():
            sampled += 1
            if sampled <= CHECK_SAMPLE and (
                    form == 'unknown'
                    or rec['output_class'] == 'unknown'):
                add('no_unclassified', rec, form)
        if form not in FORMS:
            add('form_known', rec, form)

        if form == 'bare_number':
            checked += 1
            if value['radix'] != 'decimal' or (
                    value['decimal'] !=
                    int(value['raw'])):
                add('radix_bare_decimal', rec, raw)

        if form == 'quoted_number':
            checked += 1
            digits = value['raw'][1:-1]
            if value['radix'] != 'octal' or (
                    value['decimal'] != int(digits, 8)):
                add('radix_quoted_octal', rec, raw)

        if form == 'string_constant':
            checked += 1
            core = value['raw']
            if (not core
                    or core[0] not in STRING_PREFIXES
                    or len(core) < 2
                    or core[1] not in QUOTES):
                add('string_prefix', rec, raw)
            if value['radix'] == 'octal' and (
                    value['decimal'] !=
                    int(value['octal'], 8)):
                add('radix_quoted_octal', rec, raw)

        if form == 'cell_ref':
            checked += 1
            base = value['base_decimal']
            off = value['offset_decimal']
            if value['decimal'] != base + off:
                add('cell_offset_arithmetic', rec, raw)
            if value['octal'] != '%05o' % (base + off) and (
                    base + off >= 0):
                add('cell_offset_arithmetic', rec, raw)

        if rec['register'] is not None:
            checked += 1
            suffix = RE_REG.search(raw)
            if suffix is None or (
                    '(' + rec['register'] + ')' not in raw
                    and not re.search(
                        r'\(\d+\)', raw)):
                add('register_notation', rec, raw)

    return {
        'ok': total == 0,
        'checked': checked,
        'sample': min(sampled, CHECK_SAMPLE),
        'violations_total': total,
        'truncated': max(0, total - len(items)),
        'violations': items,
    }


def format_text(result, checked=None):
    """Human-readable summary, lines within 60 columns."""
    out = ['V78 OPERAND PROBE']
    out.append('sources : %d' % len(result['sources']))
    out.append('lines   : %d' % result['lines_total'])
    out.append('operands: %d' % len(result['records']))
    out.append('uncateg.: %d' % result['unclassified'])
    if result['filter'] is not None:
        out.append('form    : %s' % result['filter'])
    rows = result['records'][:SHOW_ROWS]
    out.append('OPERND (file line mn form val sym reg cls)')
    for rec in rows:
        value = rec['value']
        shown = (value['octal'] or value['detail']
                 or '-')[:8]
        out.append('  %-8s %4d %-4s %-10s %-8s' % (
            short(rec['file']), rec['line'],
            rec['mnemonic'][:4], rec['form'][:10], shown))
        out.append('      sym=%s reg=%s cls=%s' % (
            rec['symbol'] or '-', rec['register'] or '-',
            rec['output_class']))
    extra = len(result['records']) - len(rows)
    if extra:
        out.append('  ... %d more' % extra)
    if checked is not None:
        out.append('CHECK %s' % (
            'OK' if checked['ok'] else 'FAIL'))
        out.append('  проверено: %d' % checked['checked'])
        out.append('  выборка  : %d' % checked['sample'])
        out.append('  нарушений: %d' %
                   checked['violations_total'])
        out.append('  урезано  : %d' % checked['truncated'])
        for item in checked['violations'][:10]:
            out.append('  %s %s:%d' % (
                item['invariant'], short(item['file']),
                item['line']))
    return '\n'.join(out)


def format_summary(result):
    """Counts by form and by output class."""
    out = ['СВОДКА ПО ФОРМАМ']
    for name in FORMS:
        count = result['form_counts'].get(name, 0)
        if count:
            out.append('  %-16s %5d' % (name, count))
    out.append('СВОДКА ПО КЛАССУ ВЫВОДА')
    for name, count in sorted(
            result['class_counts'].items()):
        out.append('  %-16s %5d' % (name, count))
    return '\n'.join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Read-only operand form probe for .be '
            'sources.'))
    parser.add_argument(
        'inputs', nargs='*', metavar='FILE',
        help='one or more .be source files')
    parser.add_argument(
        '--catalog', metavar='MACROS_BE', default=None,
        help='operand to PC catalog, for example macros.be')
    parser.add_argument(
        '--format', choices=('json', 'text'),
        default='text',
        help='output format (default: text)')
    parser.add_argument(
        '--check', action='store_true',
        help='validate invariants; exit 1 on violation')
    parser.add_argument(
        '--summary', action='store_true',
        help='print counts by form and output class')
    parser.add_argument(
        '--form', metavar='FORM', default=None,
        help='keep only records of this form')
    args = parser.parse_args(argv)
    try:
        result = probe(args.inputs, args.catalog,
                       args.form)
    except (OSError, ValueError) as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2
    checked = check(result) if args.check else None
    if args.format == 'json':
        if checked is not None:
            result['check'] = checked
        if args.summary:
            result['summary'] = result['form_counts']
        print(json.dumps(result, ensure_ascii=False,
                         sort_keys=True, indent=2))
    else:
        print(format_text(result, checked))
        if args.summary:
            print(format_summary(result))
    if checked is not None and not checked['ok']:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
