#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""annotate_zone.py — аннотирование листинга disbesm6 комментариями после запятой.

Инвариант (см. AGENTS.md): аннотация меняет ТОЛЬко комментарии. Все числовые
поля, мнемоники, метки, BOM и переводы строк сохраняются побайтово. Комментарий
добавляется в конец строки как `` , COMMENT``; шапка — ведущие строки ``*``.

Формат карты комментариев (--comment-file): ``ADDRESS<TAB>COMMENT`` (адрес
восьмеричный, как в колонке адреса листинга). Длина комментария <= 55 символов,
длина строки шапки <= 59 колонок.

Коды возврата: 0 — успех, 1 — ошибка использования/Ввода-Вывода,
2 — ошибка проверки (слишком длинный комментарий/шапка, изменение содержимого,
расхождения в режиме --verify-only).
"""

import argparse
import os
import re
import sys

BOM = b'\xef\xbb\xbf'          # UTF-8 BOM в выводе disbesm6
SEP = ' , '                    # что добавляем к строке
SEP_STRIP = ' ,'               # что ищем при снятии комментария
MAX_COMMENT = 55               # предел длины комментария (AGENTS.md §0)
MAX_HEADER = 59                # предел ширины строки (<=60 колонок)

# Пять позиций — восьмеричный адрес (правый выравниватель), затем ':' или пробел.
ADDR_RE = re.compile(r'^([ 0-7]{5})([: ])')


class ToolError(Exception):
    """Ошибка использования или ввода/вывода (exit 1)."""


class ValidationError(Exception):
    """Нарушение формата или инварианта (exit 2)."""


class Parser(argparse.ArgumentParser):
    """argparse по умолчанию даёт exit 2 на usage-ошибку — нам нужен exit 1."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print('%s: error: %s' % (self.prog, message), file=sys.stderr)
        raise SystemExit(1)


def read_text(path):
    """Прочитать файл, вернув (был BOM, текст). Переводы строк не меняем."""
    try:
        with open(path, 'rb') as fh:
            data = fh.read()
    except OSError as exc:
        raise ToolError('не удалось прочитать %s: %s' % (path, exc))
    has_bom = data.startswith(BOM)
    if has_bom:
        data = data[len(BOM):]
    try:
        return has_bom, data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ToolError('%s не является UTF-8: %s' % (path, exc))


def write_text(path, has_bom, text):
    """Записать текст, восстановив BOM; LF сохраняются как есть."""
    data = text.encode('utf-8')
    if has_bom:
        data = BOM + data
    try:
        with open(path, 'wb') as fh:
            fh.write(data)
    except OSError as exc:
        raise ToolError('не удалось записать %s: %s' % (path, exc))


def parse_comment_file(path):
    """Прочитать карту ADDRESS<TAB>COMMENT в dict. Длина комментария <= 55."""
    cmap = {}
    try:
        fh = open(path, 'r', encoding='utf-8', errors='strict')
    except OSError as exc:
        raise ToolError('не удалось прочитать карту %s: %s' % (path, exc))
    with fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip('\r\n')
            if not line.strip() or line.lstrip().startswith(('#', ';')):
                continue
            if '\t' not in line:
                raise ValidationError('%s:%d: нет TAB между адресом и комментарием'
                                      % (path, lineno))
            addr, comment = line.split('\t', 1)
            addr = addr.strip()
            if not re.match(r'^[0-7]+$', addr):
                raise ValidationError('%s:%d: не восьмеричный адрес: %r'
                                      % (path, lineno, addr))
            if len(comment) > MAX_COMMENT:
                raise ValidationError('%s:%d: комментарий длиной %d > %d'
                                      % (path, lineno, len(comment), MAX_COMMENT))
            cmap[addr] = comment
    return cmap


def read_header(path):
    """Прочитать шапку: каждая непустая строка начинается с '*' и <= 59 колонок."""
    if not path:
        return []
    try:
        fh = open(path, 'r', encoding='utf-8', errors='strict')
    except OSError as exc:
        raise ToolError('не удалось прочитать шапку %s: %s' % (path, exc))
    out = []
    with fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip('\r\n')
            if not line:
                continue
            if not line.startswith('*'):
                raise ValidationError('%s:%d: строка шапки не начинается с "*"'
                                      % (path, lineno))
            if '\t' in line:
                raise ValidationError('%s:%d: TAB в строке шапки'
                                      % (path, lineno))
            if len(line) > MAX_HEADER:
                raise ValidationError('%s:%d: строка шапки длиной %d > %d'
                                      % (path, lineno, len(line), MAX_HEADER))
            out.append(line)
    return out


def line_address(line):
    """Вернуть восьмеричный адрес строки (или None, если адреса нет)."""
    m = ADDR_RE.match(line)
    if not m:
        return None
    addr = m.group(1).strip()
    return addr if addr else None


def annotate_lines(lines, header, cmap):
    """Добавить шапку и `` , COMMENT`` к строкам с адресом из карты."""
    out = list(header)
    for line in lines:
        addr = line_address(line)
        if addr is not None and addr in cmap:
            out.append(line + SEP + cmap[addr])
        else:
            out.append(line)
    return out


def strip_annotated_lines(lines):
    """Снять вставленную шапку и комментарии `` , …``.

    Шапка — это строки ``*`` ДО первой строки с TAB (первой инструкции
    disbesm6). Это покрывает оба варианта вставки: в самом начале файла
    и после метаданных ``File:/Type:/Code:/Address:``. Строки ``* next insn
    used as data`` идут ПОСЛЕ инструкций и поэтому сохраняются.
    """
    first_tab = next((i for i, line in enumerate(lines) if '\t' in line),
                     len(lines))
    out = []
    for i, line in enumerate(lines):
        if i < first_tab and line.startswith('*'):
            continue
        pos = line.find(SEP_STRIP)
        if pos >= 0:
            line = line[:pos]
        out.append(line)
    return out


def diff_lines(a, b):
    """Список расхождений: (номер строки, было, стало)."""
    out = []
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else '<нет строки>'
        y = b[i] if i < len(b) else '<нет строки>'
        if x != y:
            out.append((i + 1, x, y))
    return out


def build_parser():
    ap = Parser(description='Аннотирование листинга disbesm6 комментариями '
                            'после запятой (только комментарии!).')
    ap.add_argument('--input', required=True, help='исходный .asm листинг disbesm6')
    ap.add_argument('--output', required=True, help='выходной .asm')
    ap.add_argument('--header', default=None,
                    help='файл строк шапки (каждая начинается с "*")')
    ap.add_argument('--comment-file', default=None,
                    help='карта комментариев: ADDRESS<TAB>COMMENT')
    ap.add_argument('--force', action='store_true',
                    help='перезаписать существующий --output')
    ap.add_argument('--verify-only', action='store_true',
                    help='снять шапку и комментарии и сравнить с --input')
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)

    if os.path.abspath(args.input) == os.path.abspath(args.output):
        print('annotate: --input и --output указывают на один файл', file=sys.stderr)
        return 1

    try:
        has_bom, orig_text = read_text(args.input)
        original = orig_text.split('\n')

        if args.verify_only:
            if not os.path.isfile(args.output):
                raise ToolError('нет аннотированного файла: %s' % args.output)
            _, ann_text = read_text(args.output)
            restored = strip_annotated_lines(ann_text.split('\n'))
            diffs = diff_lines(original, restored)
            if not diffs:
                print('0 differences')
                return 0
            print('%d difference(s):' % len(diffs))
            for num, was, now in diffs:
                print('  line %d:' % num)
                print('    original:  %r' % was)
                print('    annotated: %r' % now)
            return 2

        # Режим аннотирования.
        if os.path.exists(args.output) and not args.force:
            raise ToolError('выходной файл уже существует: %s (нужен --force)'
                            % args.output)
        if not args.comment_file:
            raise ToolError('нужна карта комментариев: --comment-file FILE')
        cmap = parse_comment_file(args.comment_file)
        header = read_header(args.header)
        annotated = annotate_lines(original, header, cmap)

        # Самопроверка инварианта: снятие шапки/комментариев даёт оригинал.
        diffs = diff_lines(original, strip_annotated_lines(annotated))
        if diffs:
            raise ValidationError('аннотация изменила содержимое: %d расхождений'
                                  % len(diffs))

        write_text(args.output, has_bom, '\n'.join(annotated))
        ncom = sum(1 for line in annotated if SEP_STRIP in line)
        print('annotate: %s -> %s (шапка %d строк, комментариев %d)'
              % (args.input, args.output, len(header), ncom))
        return 0

    except ToolError as exc:
        print('annotate: %s' % exc, file=sys.stderr)
        return 1
    except ValidationError as exc:
        print('annotate: %s' % exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
