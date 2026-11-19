#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xref.py — граф переходов/вызовов по листингам disbesm6 (Фаза 4).

Читает dis/*.asm, строит таблицу «адрес → мнемоника → цель → модификатор
→ символ», сверяет адреса/цели с sym/*.tab и печатает сводку.

Формат строки disbesm6 (проверено на /tmp/.private/azizz/mbe137.bin):

    "  100:04 066 2101 \tA00100\tЭ66\t'2101'(М4)"
      ^addr^ ^:  ^^^^ opcode columns ^  ^label^ ^mnem^ ^operand^

Поля 0..4 — адрес (восьмеричный, right-aligned); поле 5 — ':' (начало
базового блока, W_STARTBB) или пробел; дальше — колонки opcode, затем
через TAB: метка, мнемоника, операнд. Вторая строка слова не имеет адреса
и наследует адрес предыдущей.

Ключи: --dis-dir DIR (по умолчанию dis), --out FILE
(по умолчанию analysis/xref.txt), --symtab FILE (по умолчанию sym/MBE.tab).
"""

import argparse
import os
import re
import sys
from collections import Counter


# Мнемоники-переходы и вызовы (регистр не важен: disbesm6 печатает и 'э66',
# и 'Э66'). Э74 — останов/экстракод, обрывающий трассировку.
BRANCH = {'пб', 'по', 'пе', 'пио', 'пино', 'цикл', 'выпр'}
CALL = {'пв', 'вжм'}
STOP = {'э74'}
DATA_MNEM = {'конд', 'пам', 'nop', 'ноп', 'экв'}

# Первые 5 позиций строки — адрес; 6-я — ':' или пробел; хвост до TAB —
# колонки opcode (могут быть пустыми у 'пам', либо 16-значным словом у 'конд').
HEAD_RE = re.compile(r'^([ 0-7]{5})([: ])([0-7 ]*)\s*$')
LABEL_RE = re.compile(r'^([ADG]\d{5})(\+\d+)?$')   # A#####/D##### (+fuzz)
MOD_RE = re.compile(r'\(М([0-9]{1,2})\)')          # (Мn)
EXTRACT_RE = re.compile(r'^э[0-7][0-7]$')         # экстракод э00..э77


class Ref:
    """Одна строка дизассембля, привязанная к адресу."""

    __slots__ = ('addr', 'addr_text', 'marker', 'src', 'line', 'label',
                 'mnem', 'operand', 'target', 'fuzz', 'mod', 'category',
                 'note', 'symbol')

    def __init__(self, addr, addr_text, marker, src, line, label, mnem,
                 operand, as_data):
        self.addr = addr
        self.addr_text = addr_text
        self.marker = marker
        self.src = src
        self.line = line
        self.label = label
        self.mnem = mnem
        self.operand = operand
        self.target = ''
        self.fuzz = ''
        self.mod = ''
        self.symbol = ''
        low = mnem.lower()
        if low in DATA_MNEM:
            self.category = 'D'
            self.note = ''
        elif not mnem or low in ('старт', 'финиш'):
            self.category = '?'
            self.note = ''
        else:
            self.category = 'K'
            self.note = ''
        if low in BRANCH:
            self.note = 'BR'
        elif low in CALL:
            self.note = 'CALL'
        elif low in STOP:
            self.note = 'STOP'
        elif EXTRACT_RE.match(low):
            self.note = 'EX'
        # "* next insn used as data" — ячейка одновременно код и данные.
        if as_data and self.category == 'K':
            self.category = 'D'
            self.note = 'D+C'
        elif as_data:
            self.note = 'as-data'

        # (Мn) — модификатор индекса; убрать его из операнда, чтобы получить
        # «чистую» цель: A00105, D00641, '2101', 1, -5, START …
        m = MOD_RE.search(operand)
        if m:
            self.mod = 'М' + m.group(1)
        raw = MOD_RE.sub('', operand).strip()
        # "PRINT8, М15" — берём только первый символ
        if ',' in raw:
            raw = raw.split(',', 1)[0].strip()
        if raw:
            lm = LABEL_RE.match(raw)
            if lm:
                self.target = lm.group(1)      # A##### / D#####
                if lm.group(2):
                    self.fuzz = lm.group(2)    # артефакт окна fuzz=64
            elif re.match(r'^[A-Za-z*][\w*.\-]*$', raw) or \
                    re.match(r"^'?[0-7]+'?$", raw):
                self.target = raw              # символ / литерал / число
            else:
                self.target = raw


def read_symtab(path):
    """Считать sym/*.tab формата '%o %d %63s'. 1=данные, 2=код, 0=экв."""
    syms = {}
    if not path or not os.path.isfile(path):
        return syms
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith(('#', ';')):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                addr = int(parts[0], 8)
                typ = int(parts[1], 10)
            except ValueError:
                continue
            name = parts[2] if len(parts) > 2 else '-'
            syms[addr] = (typ, name)
    return syms


def parse_asm(path, refs):
    """Разобрать один .asm; строки без адреса наследуют предыдущий адрес."""
    cur = None
    pending_data = False
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip('\n')
            if line.startswith('*'):
                if 'used as data' in line:
                    pending_data = True      # относится к СЛЕДУЮЩЕЙ строке
                continue
            parts = line.split('\t')
            if len(parts) < 4:
                continue
            m = HEAD_RE.match(parts[0])
            if not m:
                continue
            addr_field, mark, _opcodes = m.groups()
            if addr_field.strip():
                try:
                    cur = int(addr_field.strip(), 8)
                except ValueError:
                    cur = None
            addr_text = addr_field.strip()
            label = parts[1].strip()
            mnem = parts[2].strip()
            operand = parts[3].strip()
            if not (label or mnem or operand):
                continue
            as_data = pending_data and bool(addr_field.strip())
            if addr_field.strip():
                pending_data = False
            refs.append(Ref(cur, addr_text, mark == ':',
                            os.path.basename(path), lineno,
                            label, mnem, operand, as_data))


def mark_symbols(refs, syms):
    """Пометить известные по symtab адреса/цели именем символа."""
    names = {name: addr for addr, (typ, name) in syms.items() if name != '-'}
    for r in refs:
        if r.addr is not None and r.addr in syms:
            nm = syms[r.addr][1]
            if nm != '-':
                r.symbol = nm
        if not r.symbol and r.target:
            if r.target in names:
                r.symbol = r.target
            elif LABEL_RE.match(r.target):
                # A#####/D##### — восьмеричное число после первой буквы.
                try:
                    ta = int(r.target[1:6], 8)
                except ValueError:
                    ta = None
                if ta is not None and ta in syms:
                    nm = syms[ta][1]
                    if nm != '-':
                        r.symbol = nm


def clip(text, width):
    text = text or '-'
    return text if len(text) <= width else text[:width - 2] + '..'


def render(refs, syms, args, files):
    out = []
    out.append('# XREF: граф переходов/вызовов по листингам disbesm6')
    out.append('# dis-dir: %s' % args.dis_dir)
    out.append('# symtab : %s (%d записей)' % (args.symtab, len(syms)))
    out.append('# файлов .asm: %d' % len(files))
    out.append('#')
    out.append('#   АДР     МНЕМ   ЦЕЛЬ              МОД  СИМВ     ПРИМ')
    out.append('#   ------  -------  ----------------  ---  -------  ----')
    for r in refs:
        addr_s = ('%05o' % r.addr) + (':' if r.marker else '') \
            if r.addr is not None else '-'
        note = r.note or '-'
        if r.fuzz:
            note = (note + ' fz' + r.fuzz[1:]).strip()
        line = '%6s  %-7s  %-16s  %-3s  %-7s  %s' % (
            addr_s, clip(r.mnem, 7), clip(r.target, 16),
            clip(r.mod, 3), clip(r.symbol, 7), note)
        out.append(line.rstrip())

    cat = Counter(r.category for r in refs)
    notes = Counter(r.note for r in refs)
    labels = Counter(r.target[0] for r in refs
                     if LABEL_RE.match(r.target))
    fuzz = sum(1 for r in refs if r.fuzz)
    named = sum(1 for r in refs if r.symbol and r.symbol != '-')
    types = Counter(t for t, n in syms.values())

    out.append('#')
    out.append('# ИТОГО')
    out.append('# строк: всего=%d  код=%d  данные=%d  неизв=%d'
               % (len(refs), cat['K'], cat['D'], cat['?']))
    out.append('# переходы BR=%d  вызовы CALL=%d  э74/STOP=%d'
               % (notes['BR'], notes['CALL'], notes['STOP']))
    out.append('# экстракоды эNN=%d  (из них э74=%d)'
               % (sum(1 for r in refs
                      if EXTRACT_RE.match(r.mnem.lower())), notes['STOP']))
    out.append('# метки в целях: A=%d  D=%d  артефакты fuzz=%d'
               % (labels['A'], labels['D'], fuzz))
    out.append('# символы symtab: всего=%d  код(2)=%d  данные(1)=%d'
               % (len(syms), types[2], types[1]))
    out.append('# экв(0)=%d  прочие=%d  строк с символом=%d'
               % (types[0], len(syms) - types[0] - types[1] - types[2], named))
    return '\n'.join(out) + '\n'


def main():
    ap = argparse.ArgumentParser(
        description='Xref-граф переходов/вызовов по листингам disbesm6.')
    ap.add_argument('--dis-dir', default='dis',
                    help='каталог с *.asm (по умолчанию dis)')
    ap.add_argument('--out', default=os.path.join('analysis', 'xref.txt'),
                    help='output-файл (по умолчанию analysis/xref.txt)')
    ap.add_argument('--symtab', default=os.path.join('sym', 'MBE.tab'),
                    help='таблица символов (по умолчанию sym/MBE.tab)')
    args = ap.parse_args()

    if not os.path.isdir(args.dis_dir):
        print('xref: нет каталога dis-dir: %s' % args.dis_dir, file=sys.stderr)
        return 1
    files = sorted(f for f in os.listdir(args.dis_dir) if f.endswith('.asm'))
    if not files:
        print('xref: в каталоге %s нет .asm-файлов (Фаза 3 ещё не выполнена?)'
              % args.dis_dir, file=sys.stderr)
        return 1

    refs = []
    for name in files:
        parse_asm(os.path.join(args.dis_dir, name), refs)
    if not refs:
        print('xref: .asm-файлы есть, но разобрать не удалось: %s'
              % args.dis_dir, file=sys.stderr)
        return 1

    syms = read_symtab(args.symtab)
    if not syms:
        print('xref: предупреждение: таблица символов пуста '
              'или отсутствует: %s' % args.symtab, file=sys.stderr)
    mark_symbols(refs, syms)
    refs.sort(key=lambda r: (r.addr if r.addr is not None else 1 << 30,
                             r.src, r.line))

    text = render(refs, syms, args, files)
    outdir = os.path.dirname(os.path.abspath(args.out))
    if outdir and not os.path.isdir(outdir):
        os.makedirs(outdir, exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print('xref: разобрано %d строк из %d файлов; результат: %s'
          % (len(refs), len(files), args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
