#!/usr/bin/env python3
"""Детерминированный генератор колод ВЕР.06/78.

Читает tests/decks/manifest.json. По умолчанию печатает план.
Выписывает колоды в tests/decks/generated/ только по --emit.
Эталонные образы только на чтение. См. analysis/V78-DECKGEN.md.
"""
import argparse
from collections import Counter
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'tests' / 'decks' / 'manifest.json'
OUT_DIR = ROOT / 'tests' / 'decks' / 'generated'
REF_DIR = '/usr/local/share/besm6'
REF_MD5 = {
    '2048': '4b94cc188969c110dcc78d1958b80fe0',
    '2053': '4c6abfc5068a94f8766fc38e360acabd',
    '2099': '90971c339b8744a545c8719a5d134650',
    '2248': 'c11067b35e2b85a51433e7d7b5efdd19',
}
PROTECTED = ('/usr/local/share/besm6',)
BASE_NAME = 'P1a.job.b6'

# Канонические значения 11 измерений плана. Класс знака
# пишется как "class@field", поле нужно для мутации.
DIMS = {
    'leading_space': ('off', 'on'),
    'label_separator': ('space', 'colon'),
    'comment_separator': ('semi', 'comma'),
    'token_column': ('1', '3', '8', '15', '30'),
    'character_class': (
        'digit', 'letter', 'colon', 'semi', 'comma',
        'star', 'space', 'arrow'),
    'label_length': ('1', '6', '7'),
    'macro_params': ('0', '1', '2', '4'),
    'macro_body': ('1', '3', '6'),
    'nesting': ('0', '1', '2'),
    'line_kind': ('МАСRО', 'ЭКВ', 'ВНЕШН', 'ВХОДН',
                  'КОНД', 'ordinary'),
    'directive': ('СТАРТ', 'ФИНИШ', 'ПАМ', 'КОНД'),
}
KINDS = tuple(DIMS) + ('custom',)
FIELDS = ('METKA', 'OP', 'OPR', 'CMT')
FIELD_TOKEN = {
    'METKA': 'ZLBL1', 'OP': 'ZOPC1',
    'OPR': 'ZOPR1', 'CMT': 'ZCMT1',
}
CHAR_MAP = {
    'digit': '7', 'letter': 'Q', 'colon': ':',
    'semi': ';', 'comma': ',', 'star': '*',
    'space': ' ', 'arrow': '^',
}
PARAMS = {
    '0': '', '1': ' ∧ZP', '2': ' ∧ZP ∧ZQ',
    '4': ' ∧ZP ∧ZQ ∧ZR ∧ZS',
}
KIND_LINE = {
    'МАСRО': 'МАСRО /^',
    'ЭКВ': 'ЭКВ ZEQV01=17^',
    'ВНЕШН': 'ВНЕШН ZEXT01^',
    'ВХОДН': 'ВХОДН ZENT01^',
    'КОНД': 'КОНД ZCND01^',
    'ordinary': 'ZLBL2 ZOPC2 ZOPR2 ; ZCMT2^',
}

# Реконструкция рабочей колоды P1a по docs/V78-SYNTAX-PLAN.md
# и analysis/V78-TOKEN-DECKS.md. Оригинальный скретч-файл
# /var/tmp/v78-syntax/token-exp/P1a.job.b6 отсутствует.
BASE_LINES = (
    'шифр 419999^',
    'трак 64^',
    'лент 30(2048-6200)^',
    'лент 42(2099)^',
    'лент 43(2248-ЗП)^',
    'ацп 40^',
    'росп 0^',
    'врем 240^',
    'лист 0-37^',
    'вход 4000^',
    'е',
    'в 4000',
    'к 00 010 4003',
    'к 15 24 04000',
    'к 00 066 0001 00 000 0100',
    'с 3000 67',
    'в 14000',
    'а1',
    'ВВД$$$^',
    'МАСRО /^',
    '∧М ZMAC01 ∧ZP ∧ZQ^',
    ' ZLBL1 ZOPC1 ZOPR1 ; ZCMT1^',
    'ZLBL2 ZOPC2 ZOPR2 ; ZCMT2^',
    'МЕND /^',
    'ФИНИШ^',
    'КВЧ$$$^',
    'ТРН$$$^',
    'ЧТКОМП420070^',
    '0-0^',
    'ЗОНМОД433900  0001^',
    'КНЦ$$$^',
    '_$ЕКОНЕЦ',
)
BASE_DECK = ('\n'.join(BASE_LINES) + '\n').encode('utf-8')
BASE_DECKS = {BASE_NAME: BASE_DECK}

CUSTOM = {
    'BASE1967': lambda lines: lines,
    'COLBASE': lambda lines: _set_target(lines, '^'),
    'R1a': lambda lines: _set_target(
        lines, ':ZLBL1 ZOPC1 ZOPR1 ; ZCMT1^'),
    'R1b': lambda lines: _set_target(
        lines, ':ZOPC1 ZOPR1 ; ZCMT1^'),
    'R2a': lambda lines: _set_second(
        lines, 'ZLBL2:ZOPC2,ZOPR2;ZCMT2^'),
    'R2b': lambda lines: _set_target(
        lines, 'ZLBL1:ZOPC1 ZOPR1 ; ZCMT1^'),
    'R3a': lambda lines: _set_target(
        lines, 'ZL    BL1 ZOPC1 ZOPR1 ; ZCMT1^'),
    'R3b': lambda lines: _set_target(
        lines, 'ZLBL1 ZO PC1 ZO PR1 ; ZCMT1^'),
    'R4a': lambda lines: _set_target(
        lines, _long_line(58, False)),
    'R4b': lambda lines: _set_target(
        lines, _long_line(59, False)),
    'R4c': lambda lines: _set_target(
        lines, _long_line(58, True)),
    'R4d': lambda lines: _set_target(
        lines, _long_line(59, True)),
}


class DeckError(Exception):
    """Общий класс ошибок входа, манифеста и мутаций."""


class GuardError(DeckError):
    """Попытка записи в защищённый каталог."""


def _long_line(total, trailing):
    """Строка 58 или 59 знаков без терминатора."""
    head = 'ZLBL1:ZOPC1,'
    tail = ';ZCMT1'
    body = 'Z' * (total - len(head) - len(tail))
    if trailing:
        return (head + 'ZOPR1' + tail
                + ' ' * (total - len(head) - len(tail) - 5)) + '^'
    return head + body + tail + '^'


def _find(lines, needle):
    """Индекс первой строки с подстрокой."""
    for i, line in enumerate(lines):
        if needle in line:
            return i
    raise DeckError('нет строки с ' + needle)


def _set(lines, index, value):
    """Заменить одну строку, сохранив остальные."""
    out = list(lines)
    out[index] = value
    return out


def _set_target(lines, value):
    return _set(lines, _find(lines, 'ZLBL1'), value)


def _set_second(lines, value):
    return _set(lines, _find(lines, 'ZLBL2'), value)


def guard_path(path):
    """Отказать для эталонного каталога и его подкаталогов."""
    text = os.path.expanduser(str(path))
    resolved = str(Path(text).resolve())
    for bad in PROTECTED:
        if resolved == bad or resolved.startswith(bad + os.sep):
            raise GuardError('запись в ' + bad + ' forbidden')
    return resolved


def load_manifest(path=MANIFEST):
    """Прочитать и проверить манифест колод."""
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise DeckError('manifest must be a list')
    seen = set()
    for case in data:
        if not isinstance(case, dict):
            raise DeckError('case must be an object')
        for key in ('id', 'group', 'base_deck', 'mutation', 'expect'):
            if key not in case:
                raise DeckError('нет ключа ' + key)
        cid = case['id']
        if not isinstance(cid, str) or not cid:
            raise DeckError('bad id')
        if cid in seen:
            raise DeckError('дубль id ' + cid)
        seen.add(cid)
        if case['base_deck'] not in BASE_DECKS:
            raise DeckError('неизвестная база ' +
                            str(case['base_deck']))
        mutation = case['mutation']
        expect = case['expect']
        if not isinstance(mutation, dict):
            raise DeckError('mutation must be an object')
        if not isinstance(expect, dict):
            raise DeckError('expect must be an object')
        for key in ('kind', 'value'):
            if key not in mutation:
                raise DeckError('нет mutation.' + key)
        for key in ('feature', 'note'):
            if key not in expect:
                raise DeckError('нет expect.' + key)
        kind = mutation['kind']
        if kind not in KINDS:
            raise DeckError('неизвестный kind ' + str(kind))
        _check_value(case)
        dims = case.get('dims')
        if dims is not None:
            if not isinstance(dims, dict):
                raise DeckError('dims must be an object')
            for key, value in dims.items():
                if key not in DIMS or value not in DIMS[key]:
                    raise DeckError('плохой dims.' + str(key))
    return data


def _check_value(case):
    """Проверить значение мутации по домену измерения."""
    kind = case['mutation']['kind']
    value = case['mutation']['value']
    if not isinstance(value, str):
        raise DeckError('mutation.value must be a string')
    if kind == 'custom':
        if value not in CUSTOM:
            raise DeckError('неизвестный custom ' + value)
        return
    if kind == 'character_class':
        parts = value.split('@')
        if len(parts) != 2 or parts[0] not in DIMS[kind] \
                or parts[1] not in FIELDS:
            raise DeckError('плохой character_class ' + value)
        return
    if value in DIMS[kind]:
        return
    # Колонки 5, 10, 20 из старой матрицы не входят в 11
    # канонических измерений, но сохраняются как именные случаи.
    if kind == 'token_column' and value in ('5', '10', '20') \
            and str(case['group']).startswith('prior-'):
        return
    raise DeckError('недопустимое значение ' + value)


def normalize(case):
    """Каноническое значение измерения для случая."""
    kind = case['mutation']['kind']
    value = case['mutation']['value']
    if kind not in DIMS:
        return None
    if kind == 'character_class':
        value = value.split('@')[0]
    if value not in DIMS[kind]:
        return None
    return (kind, value)


def dimension_row(case):
    """Вектор измерений: аннотация dims плюс сама мутация."""
    row = {}
    dims = case.get('dims')
    if isinstance(dims, dict):
        for key, value in dims.items():
            if key not in DIMS or value not in DIMS[key]:
                continue
            row[key] = value
    item = normalize(case)
    if item is not None:
        row[item[0]] = item[1]
    return row


def pairs_missing(cases):
    """Список непокрытых пар значений попарного покрытия."""
    covered = set()
    present = {}
    rows = []
    for case in cases:
        row = dimension_row(case)
        rows.append(row)
        for kind, value in row.items():
            present.setdefault(kind, set()).add(value)
    dims = [d for d in DIMS if len(present.get(d, ())) > 1]
    for row in rows:
        for a, b in itertools.combinations(dims, 2):
            if a in row and b in row:
                covered.add(((a, row[a]), (b, row[b])))
    missing = []
    for a, b in itertools.combinations(dims, 2):
        for va in present[a]:
            for vb in present[b]:
                pair = ((a, va), (b, vb))
                if pair not in covered:
                    missing.append(pair)
    return missing


def apply_mutation(base, case):
    """Применить одно изменение к базовой колоде."""
    if isinstance(base, str):
        base = base.encode('utf-8')
    text = base.decode('utf-8')
    lines = text.split('\n')
    kind = case['mutation']['kind']
    value = case['mutation']['value']
    if kind == 'custom':
        return ('\n'.join(CUSTOM[value](lines))).encode('utf-8')
    if kind == 'leading_space':
        idx = _find(lines, 'ZLBL1')
        line = lines[idx]
        if value == 'on' and not line.startswith(' '):
            lines = _set(lines, idx, ' ' + line)
        elif value == 'off' and line.startswith(' '):
            lines = _set(lines, idx, line[1:])
    elif kind == 'label_separator':
        idx = _find(lines, 'ZLBL1')
        line = lines[idx]
        pos = line.index('ZLBL1') + len('ZLBL1')
        char = ':' if value == 'colon' else ' '
        lines = _set(lines, idx, line[:pos] + char +
                     line[pos + 1:])
    elif kind == 'comment_separator':
        idx = _find(lines, 'ZLBL1')
        line = lines[idx]
        pos = min(p for p in (line.find(';'), line.find(','))
                  if p >= 0)
        char = ';' if value == 'semi' else ','
        lines = _set(lines, idx, line[:pos] + char +
                     line[pos + 1:])
    elif kind == 'token_column':
        col = int(value)
        if col < 1 or col > 37:
            raise DeckError('вне диапазона колонок: ' + value)
        row = [' '] * 40
        row[col - 1:col + 3] = list('QQQQ')
        lines = _set_target(lines, ''.join(row) + '^')
    elif kind == 'character_class':
        char_key, field = value.split('@')
        token = FIELD_TOKEN[field]
        idx = _find(lines, 'ZLBL1')
        line = lines[idx]
        pos = line.index(token)
        lines = _set(lines, idx, line[:pos] + CHAR_MAP[char_key]
                     + line[pos + 1:])
    elif kind == 'label_length':
        labels = {'1': 'Z', '6': 'ZLBL16', '7': 'ZLBL167'}
        idx = _find(lines, 'ZLBL1')
        lines = _set(lines, idx, lines[idx].replace(
            'ZLBL1', labels[value], 1))
    elif kind == 'macro_params':
        idx = _find(lines, '∧М ZMAC01')
        lines = _set(lines, idx, '∧М ZMAC01' +
                     PARAMS[value] + '^')
    elif kind == 'macro_body':
        n = int(value)
        body = []
        for k in range(1, n + 1):
            if k == 1:
                body.append(' ZLBL1 ZOPC1 ZOPR1 ; ZCMT1^')
            else:
                body.append('ZLBL%d ZOPC%d ZOPR%d ; ZCMT%d^'
                            % (k, k, k, k))
        idx = _find(lines, 'ZLBL1')
        lines[idx:idx + 1] = body
    elif kind == 'nesting':
        if value == '0':
            for needle in ('МАСRО /', '∧М ZMAC01', 'МЕND /'):
                idx = _find(lines, needle)
                del lines[idx]
        elif value == '2':
            h = _find(lines, 'МАСRО /')
            f = _find(lines, 'МЕND /')
            lines[f + 1:f + 1] = ['МЕND /^']
            lines[h:h] = ['МАСRО /^', '∧М ZOUT01^']
    elif kind == 'line_kind':
        lines = _set_second(lines, KIND_LINE[value])
    elif kind == 'directive':
        idx = _find(lines, 'ФИНИШ')
        lines = _set(lines, idx, value + '^')
    else:
        raise DeckError('не поддержан kind ' + kind)
    return '\n'.join(lines).encode('utf-8')


def deck_bytes(case):
    """Собрать байты колоды для случая."""
    base = BASE_DECKS[case['base_deck']]
    return apply_mutation(base, case)


def plan(cases):
    """Детерминированный план без записи файлов."""
    rows = []
    for case in sorted(cases, key=lambda c: c['id']):
        data = deck_bytes(case)
        rows.append({
            'id': case['id'],
            'group': case['group'],
            'base_deck': case['base_deck'],
            'mutation': case['mutation'],
            'expect': case['expect'],
            'size': len(data),
            'md5': hashlib.md5(data).hexdigest(),
        })
    return rows


def check_reference():
    """Проверка guard и md5 эталонных образов."""
    images = {}
    guard_ok = False
    try:
        guard_path(REF_DIR)
    except GuardError:
        guard_ok = True
    for name, expected in REF_MD5.items():
        path = os.path.join(REF_DIR, name)
        if not os.path.isfile(path):
            images[name] = 'missing'
            continue
        digest = hashlib.md5()
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(1 << 16), b''):
                digest.update(chunk)
        images[name] = 'ok' if digest.hexdigest() == expected \
            else 'mismatch'
    return {'guard_refuses_reference': guard_ok,
            'images': images}


def check_all(cases):
    """Сводная проверка манифеста, guard и эталонов."""
    violations = []
    groups = Counter(c['group'] for c in cases)
    kinds = Counter(c['mutation']['kind'] for c in cases)
    missing = pairs_missing(cases)
    if missing:
        violations.append('нет попарного покрытия: ' +
                          str(len(missing)))
    ref = check_reference()
    if not ref['guard_refuses_reference']:
        violations.append('guard не отказал ' + REF_DIR)
    for name, state in ref['images'].items():
        if state == 'mismatch':
            violations.append('md5 не совпал: ' + name)
    return {
        'cases': len(cases),
        'groups': dict(sorted(groups.items())),
        'kinds': dict(sorted(kinds.items())),
        'pairs_missing': len(missing),
        'reference': ref,
        'base_md5': hashlib.md5(BASE_DECK).hexdigest(),
        'base_size': len(BASE_DECK),
        'violations': violations,
    }


def emit(cases, out_dir=OUT_DIR):
    """Записать колоды только в защищённый scratch-каталог."""
    target = Path(guard_path(out_dir))
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for case in sorted(cases, key=lambda c: c['id']):
        name = case['id'] + '.job.b6'
        path = target / name
        guard_path(path)
        path.write_bytes(deck_bytes(case))
        written.append(name)
    return written


def _print_text(rows):
    """Печать плана, не более 60 колонок."""
    for row in rows:
        mut = row['mutation']
        line = '%-13s %-14s %s=%s' % (
            row['id'], row['group'], mut['kind'],
            mut['value'])
        line = line[:52].ljust(52) + '%4d B' % row['size']
        print(line)


def main(argv=None):
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(
        description='Генератор колод ВЕР.06/78 (только чтение)')
    parser.add_argument('--format', choices=('json', 'text'),
                        default='text', help='формат вывода')
    parser.add_argument('--check', action='store_true',
                        help='проверить guard, md5 и покрытие')
    parser.add_argument('--emit', action='store_true',
                        help='записать колоды в scratch-каталог')
    parser.add_argument('--out', default=str(OUT_DIR),
                        help='каталог вывода для --emit')
    parser.add_argument('--manifest', default=str(MANIFEST),
                        help='путь к манифесту')
    args = parser.parse_args(argv)
    try:
        cases = load_manifest(args.manifest)
        if args.check:
            report = check_all(cases)
            if args.format == 'json':
                print(json.dumps(report, ensure_ascii=False,
                                 indent=2))
            else:
                print('cases:', report['cases'])
                print('pairs missing:', report['pairs_missing'])
                print('guard:', report['reference'][
                    'guard_refuses_reference'])
                for name, state in report['reference'][
                        'images'].items():
                    print('md5', name, state)
                for text in report['violations']:
                    print('VIOLATION:', text)
            return 1 if report['violations'] else 0
        if args.emit:
            names = emit(cases, args.out)
            print('emitted', len(names), 'to', args.out)
            return 0
        rows = plan(cases)
        if args.format == 'json':
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            _print_text(rows)
        return 0
    except GuardError as exc:
        print('REFUSE:', exc, file=sys.stderr)
        return 3
    except (DeckError, OSError, ValueError, json.JSONDecodeError) \
            as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
