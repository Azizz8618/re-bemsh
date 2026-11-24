#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V78 OFFSET RESOLVER: выражения -> метки и область.

Read-only CLI. Извлекает адресные выражения из поля операнда
всех исходников БЕМШ (MBE-Z*, MBE2-Z*, ASM-Z*.be),
вычисляет восьмеричный адрес и сопоставляет его с индексом
меток. Область: local / interzone / external.

ПРАВИЛА РАДИКСА (проверены, analysis/OPERAND-CATALOG.md §4):
  - голое число в .be-выражении ДЕСЯТИЧНОЕ;
  - кавычное значение ЭКВ ВОСЬМЕРИЧНОЕ;
  - D00100+40 = 0100(8) + 40(10) = 0150(8);
  - "-З" вычитает базу наложения без численной оценки;
  - внешний адрес = страница * 02000(8) + смещение.

Операторская дефиниция «смещения» включает литералы,
указывающие на ПРОЦЕДУРНЫЕ МЕТКИ того же или внешнего
модуля, а не только числовые смещения.

Выход: детерминированный JSON или текст. Вход не меняется.

Использование:
    python3 tools/v78_offset_resolve.py --help
    python3 tools/v78_offset_resolve.py --summary
    python3 tools/v78_offset_resolve.py --labels idx.json \
        --format json --check > /var/tmp/v78-offsets/r.json
    python3 tools/v78_offset_resolve.py FILE.be \
        --scope local --format text

Коды выхода: 0 = успех, 1 = --check, 2 = ошибка ввода.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import re
import sys

DATE = '24.11.2026'
MAX_ADDR = 0o1777777          # 15-битное поле адреса БЭСМ-6
ZONE_WINDOW = 0o2000          # 1024 слова на зону/страницу
MIN_RESOLVED = 1000  # порог --check на корпусе

# Мнемоники .be (кириллица и гомоглифы).
OPCODES = frozenset((
    'ЗП', 'СЧ', 'СЛ', 'ВЧ', 'ВЧОБ', 'ВЧАБ', 'НТЖ', 'СЛЦ',
    'ЗНАК', 'ИЛИ', 'ДЕЛ', 'УМН', 'СЧМ', 'СЛП', 'СДА', 'РЖА',
    'УИ', 'УИМ', 'СЧИ', 'СЧИМ', 'УИИ', 'СЛИ', 'И',
    'МОДА', 'МОД', 'УИА', 'СЛИА', 'ПО', 'ПЕ', 'ПБ', 'ПВ',
    'ЦИКЛ', 'ПИО', 'ПИНО', 'ВЫПР', 'УВВ', 'СЧРЖ', 'СЧМР',
    'Э50', 'Э52', 'Э66', 'Э67', 'Э73', 'Э77', 'СТОП',
    'ЭКВ', 'СТАРТ', 'РЕГ', 'КОНД', 'КОНК',
    'ВНЕШН', 'ВНЕШ', 'ВХОДН', 'ВХОД', 'ВХОДС', 'ВХОДБ',
    'ВНЕШБ', 'ВНЕШС', 'ЕВНЕШ', 'МАСRО', 'МЕND', 'АIF',
    'SЕТА', 'SЕТВ', 'GВLА', 'GВLВ', 'LСLА', 'ЭКВИВ',
    'ОПРЕ', 'ДК', 'СПO', 'ТЕКСТ', 'ПРЕ', 'ВО', 'ФИНИШ',
    'Е', 'М', 'АНОП', 'НОП', 'РЗБ', 'ТЕРМ', 'КО',
))

# Внешние связи: операнд - имя owner.symbol.
EXTERNAL_OPS = frozenset((
    'ВНЕШН', 'ВНЕШ', 'ВХОДН', 'ВХОД', 'ВХОДС', 'ВХОДБ',
    'ВНЕШБ', 'ВНЕШС', 'ЕВНЕШ',
))

# Мнемоники принудительных листингов dis-forced/Z*.asm.
ASM_OPS = frozenset((
    'зп', 'сч', 'сда', 'сбр', 'рзб', 'нтж', 'или', 'и',
    'мод',
    'мода', 'пб', 'пв', 'по', 'пе', 'цикл', 'пио', 'пино',
    'выпр', 'вчаб', 'вчоб', 'вч', 'сл', 'умн',
    'дел', 'знак',
    'уи', 'уим', 'уия', 'уиа', 'сли', 'слиа', 'счм', 'счмр',
    'счи', 'уив', 'счрж', 'нтр', 'uj', 'vjm', 'xta', 'atx',
))

RE_ZONE = re.compile(r'Z(\d{4})')
RE_BASE_ROW = re.compile(
    r'^\s*(\d{4}),\s*([^,]+),\s*(.+?)\s*$')
RE_REG = re.compile(
    r'\(\s*(?:[МM]?\d+)\s*(?:,\s*\d+)?\s*\)\s*$')
RE_CELL = re.compile(
    r'(?P<sym>[DAGI][0-7]{3,6})'
    r'(?P<overlay>-З|-3)?'
    r'(?P<off>[+-]\d+)?')
RE_XLABEL = re.compile(
    r'X(?P<digits>[0-7]{3,6})(?P<suffix>[A-Z]?)')
RE_QUOTED = re.compile(r"'(?P<digits>[0-7]+)'")
RE_PAGE = re.compile(
    r'(?P<page>[0-7]+)\s*(?:\*|×)\s*02000'
    r'(?P<off>[+-]\d+)?')
RE_NAME = re.compile(
    r'(?<![A-ZА-Я0-9_])'
    r'[A-ZА-Я][A-ZА-Я0-9_]*\.[A-ZА-Я0-9_]+')
RE_DEC_ARITH = re.compile(
    r'(?<![\w\'])([+-]?\d+(?:[+-]\d+)+)(?![\w\'])')
RE_BARE = re.compile(r'(?<![\w\'])[+-]?\d+(?![\w\'])')
RE_OPAQUE = re.compile(
    r"'[^']*'|\([^)]*\)|[A-ZА-Я][A-ZА-Я0-9_]*\."
    r"[A-ZА-Я0-9_]+|[A-ZА-Я][A-ZА-Я0-9_]*")

STATUS_CODE = {
    'ФАКТ': 'Ф', 'Ф': 'Ф', 'ПОДТВЕРЖДЕНО': 'Ф',
    'ГИПОТЕЗА': 'Г', 'Г': 'Г',
    'НЕ ИЗВЕСТНО': 'Н', 'Н': 'Н',
}


def zone_of_path(path):
    """Зона из имени файла или пустая строка."""
    match = RE_ZONE.search(os.path.basename(path))
    return match.group(1) if match else ''


def strip_bom(text):
    """Убрать один BOM в начале текста."""
    return text[1:] if text.startswith('\ufeff') else text


def strip_comment(text):
    """Отсечь комментарий после запятой.

    Запятая внутри скобок (М1,1) или списка макроса не
    является началом комментария.
    """
    depth = 0
    for pos, char in enumerate(text):
        if char == '(':
            depth += 1
        elif char == ')':
            depth = max(0, depth - 1)
        elif char == ',' and depth == 0:
            tail = text[pos + 1:]
            if not tail or tail[0].isspace():
                return text[:pos]
            if (tail[0] != '∧' and (' ' in tail
                                   or ';' in tail
                                   or ':' in tail)):
                return text[:pos]
    return text


def split_fields(text):
    """Вернуть (мнemonika, операнд) для строки .be."""
    code = strip_comment(text).strip()
    if not code or code.startswith('*'):
        return None
    tokens = code.split()
    if tokens[0] in OPCODES:
        idx = 0
    elif (len(tokens) >= 2 and tokens[1] in OPCODES
          and re.match(r'^[A-ZА-Я0-9_.-]+$', tokens[0])):
        idx = 1
    else:
        return None
    return tokens[idx], ' '.join(tokens[idx + 1:])


def split_asm_fields(text):
    """Вернуть (мн, операнд) строки dis-forced."""
    code = text.rstrip()
    if not code.strip() or code.lstrip().startswith('*'):
        return None
    tokens = code.split()
    for idx, token in enumerate(tokens):
        if token in ASM_OPS:
            return token, ' '.join(tokens[idx + 1:])
    return None


def parse_base_map(path):
    """Прочитать Приложение A ZONE-BASE-MAP.md.

    Возвращает {зона: (база_int|None, код_статуса)}.
    """
    bases = {}
    if not path or not os.path.isfile(path):
        return bases
    with open(path, encoding='utf-8',
            errors='replace') as fh:
        for line in fh:
            match = RE_BASE_ROW.match(line)
            if not match:
                continue
            zone, base_txt, status_txt = match.groups()
            base_txt = base_txt.strip()
            if base_txt in ('-', ''):
                base = None
            else:
                base = int(base_txt.rstrip('?'), 8)
            status = 'Н'
            for key, code in STATUS_CODE.items():
                if status_txt.startswith(key):
                    status = code
                    break
            bases[zone] = (base, status)
    return bases


def normalize_zone(value):
    """Зона к 4 цифрам или пустая строка."""
    if value is None:
        return ''
    match = re.search(r'(\d{3,4})', str(value).strip())
    return match.group(1).zfill(4) if match else ''


def normalize_number(value):
    """Преобразовать число индекса в int.

    Префикс 0o - восьмеричное, d: - десятичное, простая
    строка цифр по умолчанию восьмеричная (адреса БЭСМ-6).
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.startswith('0o'):
        return int(text[2:], 8)
    if text.startswith('d:'):
        return int(text[2:])
    if text.isdigit():
        try:
            return int(text, 8)
        except ValueError:
            return int(text)
    try:
        return int(text, 8)
    except ValueError:
        return None


def load_label_index(path, bases=None):
    """Загрузить индекс меток из JSON.

    Принимает список словарей, {"labels": [...]} и словарь
    вида {зона: [записи]}. Ключи записей: name/label/symbol,
    zone, absolute/address/addr/offset, status. Если bases
    задан, адрес восстанавливается из базы зоны и смещения.
    """
    bases = bases or {}
    index = {
        'by_absolute': {}, 'by_name': {},
        'by_zone_addr': {}, 'entries': [],
    }
    if not path:
        return index
    with open(path, encoding='utf-8',
            errors='replace') as fh:
        data = json.load(fh)
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ('labels', 'records',
                    'entries', 'items'):
            if isinstance(data.get(key), list):
                items = data[key]
                break
        else:
            for zone, entries in data.items():
                if isinstance(entries, dict):
                    entries = [entries]
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if isinstance(entry, dict):
                        row = dict(entry)
                        row.setdefault('zone', zone)
                        items.append(row)
    for raw in items:
        if not isinstance(raw, dict):
            continue
        name = (raw.get('name') or raw.get('label')
                or raw.get('symbol') or raw.get('id'))
        zone = normalize_zone(
            raw.get('zone') or raw.get('z'))
        absolute = normalize_number(
            raw.get('absolute')
            if raw.get('absolute') is not None
            else raw.get('addr_absolute'))
        offset = normalize_number(
            raw.get('address')
            if raw.get('address') is not None
            else raw.get('addr')
            if raw.get('addr') is not None
            else raw.get('offset'))
        if absolute is None and zone and offset is not None:
            base, _code = bases.get(zone, (None, 'Н'))
            if base is not None:
                absolute = base + offset
        status = str(raw.get('status')
                     or raw.get('confidence')
                     or 'Н')
        entry = {
            'name': str(name) if name is not None else '',
            'zone': zone,
            'absolute': absolute,
            'offset': offset,
            'status': status,
        }
        index['entries'].append(entry)
        if entry['name']:
            index['by_name'].setdefault(
                entry['name'], []).append(entry)
        if absolute is not None:
            index['by_absolute'].setdefault(
                absolute, []).append(entry)
        if zone and offset is not None:
            index['by_zone_addr'].setdefault(
                (zone, offset), []).append(entry)
    for bucket in (index['by_absolute'], index['by_name'],
                   index['by_zone_addr']):
        for key in bucket:
            bucket[key].sort(key=entry_sort_key)
    return index


def entry_sort_key(entry):
    """Детерминированный порядок записей индекса."""
    return (entry['name'], entry['zone'],
            entry['absolute']
            if entry['absolute'] is not None
            else -1)


def short_status(text):
    """Свести статус индекса/карты к Ф, Г или Н."""
    for key, code in STATUS_CODE.items():
        if str(text).startswith(key):
            return code
    upper = str(text).upper()
    if 'Ф' in upper:
        return 'Ф'
    if 'Г' in upper:
        return 'Г'
    return 'Н'


def zone_for_absolute(absolute, bases):
    """Зона окна адреса или пустая строка."""
    if absolute is None:
        return ''
    hits = []
    for zone, (base, _status) in bases.items():
        if base is not None and (
                base <= absolute <= base + ZONE_WINDOW - 1):
            hits.append((base, zone))
    if not hits:
        return ''
    hits.sort(key=lambda item: (-item[0], item[1]))
    return hits[0][1]


def pick_label(index, absolute=None, name=None,
               file_zone=None):
    """Индекс: адрес, имя или зона+смещение.

    Когда база зоны неизмерена, индекс может хранить только
    локальное смещение. Тогда адрес выражения сравнивается
    со смещением метки той же зоны.
    """
    found = []
    if absolute is not None:
        found.extend(index['by_absolute'].get(absolute, ()))
    if name:
        for entry in index['by_name'].get(name, ()):
            if entry not in found:
                found.append(entry)
    if not found and absolute is not None and file_zone:
        found.extend(index['by_zone_addr'].get(
            (file_zone, absolute), ()))
    if not found:
        return None
    # При коллизии адресов (общая база 10000) метка своей
    # зоны приоритетнее любой метки другой зоны.
    found.sort(key=lambda e: (
        0 if e['zone'] and e['zone'] == file_zone else 1,
        e['name'], e['zone'],
        e['absolute'] if e['absolute'] is not None else -1))
    return found[0]


def make_record(source, line_no, mnemonic, operand,
                base_symbol,
                offset_value, offset_radix, absolute,
                file_zone,
                bases, index, is_external=False):
    """Собрать одну запись с областью и статусом."""
    label = pick_label(index, absolute, base_symbol,
                       file_zone)
    if (label and absolute is None
            and label['absolute'] is not None):
        absolute = clip_absolute(label['absolute'])
        label = pick_label(index, absolute, base_symbol,
                           file_zone)
    target_label = (label['name'] if label and label['name']
                    and absolute is not None else None)
    target_zone = (label['zone']
                   if label and label['zone'] else '')
    if not target_zone:
        target_zone = zone_for_absolute(absolute, bases)

    if not target_zone:
        scope = 'external'
    elif file_zone and target_zone == file_zone:
        scope = 'local'
    else:
        scope = 'interzone'

    if label and label['status']:
        status = short_status(label['status'])
    elif target_zone and target_zone in bases:
        status = bases[target_zone][1]
    else:
        status = 'Н'
    if is_external and scope == 'external':
        if status == 'Ф':
            status = 'Г'

    return {
        'file': source,
        'line': line_no,
        'mnemonic': mnemonic,
        'operand_raw': operand,
        'base_symbol': base_symbol,
        'offset_value': offset_value,
        'offset_radix': offset_radix,
        'absolute': absolute,
        'target_label': target_label,
        'scope': scope,
        'target_zone': target_zone or None,
        'status': status,
    }


def eval_decimal_arithmetic(text):
    """Вычислить выражение из десятичных чисел и +/-."""
    if not re.fullmatch(r'[+-]?\d+(?:[+-]\d+)*', text):
        return None
    parts = re.findall(r'[+-]?\d+', text)
    return sum(int(tok) for tok in parts)


def clip_absolute(value):
    """Оставить только 15-битный адрес; иначе None.

    Длинные кавычные литералы суть 48-битные слова, а
    отрицательные смещения не являются адресами. Такие
    выражения остаются в отчёте без абсолютного адреса.
    """
    if value is None or not (0 <= value <= MAX_ADDR):
        return None
    return value


def extract_expressions(operand):
    """Список (позиция, symbol, off, radix, absolute).

    Порядок: составные формы, затем голые числа. Регистры
    снимаются заранее. Позиция нужна для стабильного вывода.
    """
    text = RE_REG.sub('', operand).strip()
    result = []
    consumed = []

    def mark(span):
        consumed.append(span)

    def overlaps(span):
        return any(span[0] < end and start < span[1]
                   for start, end in consumed)

    # Страница * 02000 + смещение.
    for match in RE_PAGE.finditer(text):
        page = int(match.group('page'), 8)
        off = int(match.group('off') or 0)
        absolute = page * ZONE_WINDOW + off
        result.append((match.start(),
                       'page%s' % match.group('page'),
                       off, 'decimal', absolute))
        mark(match.span())

    # Ячейка Dnnnnn/Annnn/Innnn/Gnnnnn с -З и сдвигом.
    for match in RE_CELL.finditer(text):
        if overlaps(match.span()):
            continue
        base = int(match.group('sym')[1:], 8)
        off = int(match.group('off') or 0)
        symbol = match.group('sym')
        if match.group('overlay'):
            symbol += '-З'
        result.append((match.start(), symbol,
                       off, 'decimal', base + off))
        mark(match.span())

    # Внешняя метка Xnnnnn.
    for match in RE_XLABEL.finditer(text):
        if overlaps(match.span()):
            continue
        result.append((
            match.start(), match.group(0), 0, 'octal',
            int(match.group('digits'), 8)))
        mark(match.span())

    # Глобальное имя owner.symbol (адрес только по индексу).
    for match in RE_NAME.finditer(text):
        if overlaps(match.span()):
            continue
        result.append((match.start(), match.group(0),
                       None, 'none', None))
        mark(match.span())

    # Кавычные восьмеричные значения и выражения с ними.
    for match in RE_QUOTED.finditer(text):
        if overlaps(match.span()):
            continue
        digits = match.group('digits')
        quoted = "'%s'" % digits
        base = int(digits, 8)
        tail = text[match.end():]
        sign_off = re.match(r'\s*([+-])(\d+)', tail)
        if sign_off:
            off = int(sign_off.group(2))
            if sign_off.group(1) == '-':
                off = -off
            result.append((match.start(), quoted,
                           off, 'decimal', base + off))
        else:
            result.append((match.start(), quoted,
                           base, 'octal', base))
        mark(match.span())

    # Десятичная арифметика 64-6, 64+16.
    spans = [m.span() for m in RE_OPAQUE.finditer(text)]
    for match in RE_DEC_ARITH.finditer(text):
        if overlaps(match.span()):
            continue
        if any(a <= match.start() and match.end() <= b
               for a, b in spans):
            continue
        token = match.group(1)
        value = eval_decimal_arithmetic(token)
        result.append((match.start(), token,
                       value, 'decimal', value))
        mark(match.span())

    # Одиночные голые числа.
    for match in RE_BARE.finditer(text):
        if overlaps(match.span()):
            continue
        if any(a <= match.start() and match.end() <= b
               for a, b in spans):
            continue
        token = match.group(0)
        value = int(token)
        result.append((match.start(), token,
                       value, 'decimal', value))
        mark(match.span())

    result.sort(key=lambda row: row[0])
    return [(pos, sym, off, radix, clip_absolute(absolute))
            for pos, sym, off, radix, absolute in result]


def scan_text(text, source, file_zone, bases, index):
    """Сканировать текст и вернуть записи."""
    lines = strip_bom(text).splitlines()
    records = []
    for number, raw in enumerate(lines, 1):
        fields = split_fields(raw)
        is_asm = False
        if fields is None:
            fields = split_asm_fields(raw)
            is_asm = True
        if fields is None:
            continue
        mnemonic, operand = fields
        if is_asm:
            operand = strip_comment(operand)
        is_external = mnemonic in EXTERNAL_OPS
        for _pos, base, off, radix, absolute in (
                extract_expressions(operand)):
            records.append(make_record(
                source, number, mnemonic, operand.strip(),
                base, off, radix, absolute, file_zone,
                bases, index, is_external))
    return records


def default_inputs(root):
    """Список исходников по умолчанию, отсортированный."""
    bemsh = os.path.join(root, 'bemsh')
    names = []
    if os.path.isdir(bemsh):
        for name in os.listdir(bemsh):
            if not name.endswith('.be') or '.bak' in name:
                continue
            if re.match(r'^(MBE2?|ASM)-Z\d{4}\.be$', name):
                names.append(os.path.join(bemsh, name))
    return sorted(names)


def probe(paths, bases, index, scope_filter=None):
    """Собрать детерминированный результат."""
    records = []
    sources = []
    for path in paths:
        with open(path, encoding='utf-8',
                  errors='replace') as handle:
            text = handle.read()
        rel = os.path.relpath(path, os.getcwd())
        sources.append(rel)
        records.extend(scan_text(
            text, rel, zone_of_path(path), bases, index))
    records.sort(key=lambda rec: (
        rec['file'], rec['line'], rec['mnemonic'],
        rec['operand_raw'], rec['base_symbol'] or ''))
    if scope_filter is not None:
        records = [rec for rec in records
                   if rec['scope'] == scope_filter]
    scopes = Counter(rec['scope'] for rec in records)
    statuses = Counter(rec['status'] for rec in records)
    resolved = sum(1 for rec in records
                   if rec['absolute'] is not None)
    return {
        'date': DATE,
        'sources': sources,
        'scope_filter': scope_filter,
        'records_total': len(records),
        'resolved': resolved,
        'scope_counts': dict(sorted(scopes.items())),
        'status_counts': dict(sorted(statuses.items())),
        'records': records,
    }


def check(result):
    """Проверить радикс, диапазон, метки и порог --check."""
    items = []
    checked = 0

    def add(invariant, rec, detail):
        if len(items) < 30:
            items.append({
                'invariant': invariant,
                'file': rec['file'],
                'line': rec['line'],
                'detail': detail,
            })

    for rec in result['records']:
        sym = rec['base_symbol'] or ''
        radix = rec['offset_radix']
        absolute = rec['absolute']
        checked += 1

        if radix == 'octal' and not (
                sym.startswith('X') or sym.startswith("'")):
            add('radix_octal_form', rec, sym)
        if (sym.startswith("'") and radix == 'octal'
                and absolute is not None
                and absolute != rec['offset_value']):
            add('radix_quoted_octal', rec, sym)
        if (sym.startswith("'") and radix == 'octal'
                and rec['offset_value'] is not None
                and rec['offset_value'] > MAX_ADDR
                and absolute is not None):
            add('quoted_word_not_address', rec, sym)
        if absolute is not None and not (
                0 <= absolute <= MAX_ADDR):
            add('absolute_range', rec, str(absolute))
        if rec['target_label'] and absolute is None:
            add('label_without_absolute', rec,
                rec['target_label'])

    if result['resolved'] < MIN_RESOLVED:
        items.append({
            'invariant': 'min_resolved',
            'file': '-', 'line': 0,
            'detail': '%d < %d' % (
                result['resolved'], MIN_RESOLVED),
        })

    return {
        'ok': not items,
        'checked': checked,
        'min_resolved': MIN_RESOLVED,
        'violations_total': len(items),
        'violations': items,
    }


def format_text(result, checked=None):
    """Текстовый вывод, строки не длиннее 60 колонок."""
    out = ['V78 OFFSET RESOLVER', 'дата: %s' % DATE]
    out.append('файлов : %d' % len(result['sources']))
    out.append('записей: %d' % result['records_total'])
    out.append('разреш.: %d' % result['resolved'])
    if result['scope_filter']:
        out.append('фильтр : %s' % result['scope_filter'])
    rows = result['records'][:20]
    out.append('ЗАПИСИ file line mn sym off abs sc st')
    for rec in rows:
        out.append('  %-14s %5d %-4s' % (
            os.path.basename(rec['file'])[:14],
            rec['line'], rec['mnemonic'][:4]))
        out.append('    sym=%s off=%s rad=%s abs=%s' % (
            str(rec['base_symbol'])[:12],
            rec['offset_value'], rec['offset_radix'],
            format(rec['absolute'], 'o')
            if rec['absolute'] is not None else '-'))
        out.append('    lbl=%s sc=%s z=%s st=%s' % (
            str(rec['target_label'])[:14],
            rec['scope'], rec['target_zone'] or '-',
            rec['status']))
    extra = result['records_total'] - len(rows)
    if extra:
        out.append('  ... ещё %d' % extra)
    if checked is not None:
        out.append('CHECK %s' % ('OK' if checked['ok']
                                else 'FAIL'))
        out.append('  проверено: %d' % checked['checked'])
        out.append('  нарушений: %d' %
                   checked['violations_total'])
        for item in checked['violations'][:10]:
            out.append('  %s %s:%d %s' % (
                item['invariant'], item['file'],
                item['line'], item['detail']))
    return '\n'.join(out)


def format_summary(result):
    """Сводка по областям и статусам."""
    out = ['СВОДКА ПО ОБЛАСТИ']
    for name in ('local', 'interzone', 'external'):
        out.append('  %-10s %5d' % (
            name, result['scope_counts'].get(name, 0)))
    out.append('СВОДКА ПО СТАТУСУ')
    for name, count in sorted(
            result['status_counts'].items()):
        out.append('  %-4s %5d' % (name, count))
    return '\n'.join(out)


def build_parser():
    """Собрать аргументы CLI."""
    parser = argparse.ArgumentParser(
        description=(
            'Read-only resolver of BEMSH address '
            'expressions to labels and scope.'))
    parser.add_argument(
        'inputs', nargs='*', metavar='FILE',
        help='source files (default: all bemsh/*.be)')
    parser.add_argument(
        '--root', metavar='DIR', default=None,
        help='repository root (default: parent of tools/)')
    parser.add_argument(
        '--labels', metavar='JSON', default=None,
        help='label index JSON from the parallel tool')
    parser.add_argument(
        '--base-map', metavar='MD', default=None,
        help='ZONE-BASE-MAP.md path')
    parser.add_argument(
        '--asm', nargs='*', default=None, metavar='ASM',
        help='additional dis-forced/Z*.asm files')
    parser.add_argument(
        '--scope',
        choices=('local', 'interzone', 'external'),
        default=None, help='keep one scope only')
    parser.add_argument(
        '--format', choices=('json', 'text'),
        default='text', help='output format')
    parser.add_argument(
        '--check', action='store_true',
        help='validate invariants; exit 1 on violation')
    parser.add_argument(
        '--summary', action='store_true',
        help='print counts by scope and status')
    return parser


def main(argv=None):
    """Точка входа CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.root or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    base_map = args.base_map or os.path.join(
        root, 'analysis', 'ZONE-BASE-MAP.md')
    try:
        bases = parse_base_map(base_map)
        index = load_label_index(args.labels, bases)
        paths = list(args.inputs) or default_inputs(root)
        paths.extend(args.asm or [])
        if not paths:
            raise ValueError('no input files found')
        for path in paths:
            if not os.path.isfile(path):
                raise ValueError('missing file: %s' % path)
        result = probe(paths, bases, index, args.scope)
    except (OSError, ValueError,
            json.JSONDecodeError) as exc:
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
        if args.summary:
            print(format_summary(result))
    if checked is not None and not checked['ok']:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
