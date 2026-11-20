#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""intermodule_xref.py - кросс-ссылки между модулями (зонами) БЭСМ-6.

Отличается от tools/global_xref.py: там «цель -> исходники» по адресам,
здесь «зона-источник -> зона/память-цель» по парам модулей.

Разбор листингов полностью переиспользует проверенный код
tools/global_xref.py (parse_line_operand, scan_asm_files, apply_filters).
Ни один входной файл (gold/, dis/, docs/, sym/) не меняется.

CLI:
  python3 tools/intermodule_xref.py [--out analysis/XREF-INTERMODULE.md]
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import global_xref as G  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ZONE_WORDS = G.ZONE_WORDS          # 02000₈ = 1024 слова одной зоны

# Известные точки загрузки дисковых зон в ОП.
# Источник: docs/SEMANTIC/Z0154.md:14 (breakpoint 02000, 1024/1024),
# sym/GLOBAL.tab:108 (MAC_EDITOR_LOAD). Альтернатива 0554 (Z0554.md:23)
# не принимается как основная: в задании 02000₈ = зона 0154.
ZONE_AT_MEMORY = {0o2000: '0154'}

# Короткие роли для памяти по sym/GLOBAL.tab.
ROLE_SHORT = {
    'CODE_ITM_GATE': 'GATE',
    'SYSCALL_GATE': 'SYSCALL',
    'MEM_MONITOR': 'MONITOR',
    'MEM_PLBEG': 'PLBEG',
    'MAC_EDITOR_LOAD': 'EDITOR_LOAD',
}

FAMILY_RANGES = (('ASM', 0o0055, 0o0060),
                 ('B', 0o0137, 0o0177),
                 ('B2', 0o0540, 0o0577))

HEADER_ADDR_RE = re.compile(r'^\s*Address:\s*([0-7]+)\s*$')


# ---------------------------------------------------------------------------
# 1. Справочники и служебные функции
# ---------------------------------------------------------------------------

def zone_family(zone):
    """Семейство зоны: ASM (0055-0060), B (0137-0177), B2 (0540-0577)."""
    if not zone:
        return '?'
    try:
        z = int(zone, 8)
    except ValueError:
        return '?'
    for name, lo, hi in FAMILY_RANGES:
        if lo <= z <= hi:
            return name
    return '?'


def load_global_names(root):
    """sym/GLOBAL.tab: восьмеричный адрес -> имя роли."""
    names = {}
    path = os.path.join(root, 'sym', 'GLOBAL.tab')
    if not os.path.isfile(path):
        return names
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                value = int(parts[0], 8)
            except ValueError:
                continue
            names[value] = parts[2]
    return names


def short_role(name):
    """Сократить имя роли из GLOBAL.tab для метки MEM_<адрес>_<РОЛЬ>."""
    if name in ROLE_SHORT:
        return ROLE_SHORT[name]
    for prefix in ('MEM_', 'CODE_', 'SYSCALL_', 'MAC_', 'TXT_', 'ERR_'):
        if name.startswith(prefix) and len(name) > len(prefix):
            return name[len(prefix):]
    return name


def memory_label(value, names):
    """Метка для адреса памяти >= 02000₈, не являющегося словом зоны."""
    role = names.get(value)
    if role:
        return 'MEM_%05o_%s' % (value, short_role(role))
    return 'MEM_%05o_UNKNOWN' % value


def listing_base(path):
    """База адресации листинга из шапки disbesm6, 0 для обычных -a0."""
    base = 0
    try:
        with open(path, 'r', encoding='utf-8-sig', errors='replace') as fh:
            for line in fh:
                m = HEADER_ADDR_RE.match(line)
                if m:
                    base = int(m.group(1), 8)
                    break
    except OSError:
        pass
    return base


def is_excluded(ref):
    """Псевдо-ссылки, константы и fill не являются межмодульными."""
    if ref.kind in ('FUZZ', 'TXT', 'DATA', 'SYM', 'EXPR'):
        return True
    if ref.value is None or ref.value < 0:
        return True
    token = ref.key.split(':', 1)[-1]
    if token in G.CHECKERBOARD or (ref.raw or '').strip("'") in G.CHECKERBOARD:
        return True
    if ref.kind == 'IMM':
        # Голое число: praddr печатает малые адреса десятичными.
        # Отрицательные значения и числа >= страницы - константы/сдвиги.
        if ref.mnem.lower() in G.IMM_MNEM or ref.value >= ZONE_WORDS:
            return True
    return False


def relation(src_zone, target_zone, target_kind):
    """Класс связи между модулями."""
    if target_kind == 'MEMORY':
        return 'MEMORY/EXTERNAL'
    if target_kind in ('REGISTER', 'AMBIGUOUS', 'EXCLUDED'):
        return target_kind.title()
    if src_zone == target_zone:
        return 'INTRA'
    sf, tf = zone_family(src_zone), zone_family(target_zone)
    if {sf, tf} == {'B', 'B2'}:
        return 'INTER-B/B2'
    if sf == 'ASM' and tf in ('B', 'B2'):
        return 'ASM→B'
    if sf in ('B', 'B2') and tf == 'ASM':
        return 'B→ASM'
    if sf == tf:
        return 'INTER-' + sf
    return 'OTHER'


def classify(ref, names, zone_local=True):
    """Классифицировать одну ссылку.

    Возвращает словарь: category, relation, target, target_zone,
    target_family, label, evidence.
    """
    lab = '%s.%s' % (ref.zone or '?', ref.addr_text or _oct(ref.addr))
    evidence = '%s  %s  %s  → %s' % (lab, ref.mnem, ref.operand, '')
    row = {
        'category': 'EXCLUDED', 'relation': 'EXCLUDED', 'target': '',
        'target_zone': '', 'target_family': '?', 'label': '',
        'evidence': evidence, 'ref': ref,
    }
    if ref.kind == 'MOD':
        row.update(category='REGISTER', relation='REGISTER',
                   target=ref.key, label=ref.key, target_kind='REGISTER')
        row['evidence'] = '%s  %s  %s  → %s' % (
            lab, ref.mnem, ref.operand, ref.key)
        return row
    if is_excluded(ref):
        row['target_kind'] = 'EXCLUDED'
        return row

    value = ref.value
    if value < ZONE_WORDS:
        if not zone_local:
            tgt = 'NONLOCAL_%s' % (ref.zone or '?')
            row.update(category='AMBIGUOUS', target=tgt, label=tgt,
                       target_kind='AMBIGUOUS')
            row['relation'] = relation(ref.zone, tgt, 'AMBIGUOUS')
            return row
        tgt = ref.zone or '?'
        label = 'ZONE_%s_WORD_%o' % (tgt, value)
        row.update(category='INTRA', target='Z' + tgt, target_zone=tgt,
                   target_family=zone_family(tgt), label=label,
                   target_kind='ZONE')
        row['relation'] = relation(ref.zone, tgt, 'ZONE')
    elif value in ZONE_AT_MEMORY:
        tgt = ZONE_AT_MEMORY[value]
        gname = names.get(value, '')
        label = 'ZONE_%s_AT_%05o' % (tgt, value)
        if gname:
            label += '_' + short_role(gname)
        row.update(category='INTER', target='Z' + tgt, target_zone=tgt,
                   target_family=zone_family(tgt), label=label,
                   target_kind='ZONE')
        row['relation'] = relation(ref.zone, tgt, 'ZONE')
    else:
        label = memory_label(value, names)
        row.update(category='MEMORY', target=label, label=label,
                   target_kind='MEMORY', target_family='MEM')
        row['relation'] = relation(ref.zone, label, 'MEMORY')

    row['evidence'] = '%s  %s  %s  → %s' % (
        lab, ref.mnem, ref.operand, row['label'])
    return row


def _oct(addr):
    if addr is None:
        return '-'
    return '%o' % addr


def classify_all(refs, names, local_map):
    """Прогнать все ссылки через классификатор."""
    return [classify(r, names, local_map.get(r.src, True)) for r in refs]


# ---------------------------------------------------------------------------
# 2. Агрегация
# ---------------------------------------------------------------------------

def build_matrix(rows, sample_limit=3):
    """Матрица: (зона-источник, цель, связь) -> счётчик и примеры."""
    agg = {}
    for row in rows:
        if row['category'] in ('EXCLUDED', 'REGISTER', 'AMBIGUOUS'):
            continue
        key = (row['ref'].zone or '?', row['target'], row['relation'])
        cell = agg.setdefault(key, {
            'source': key[0], 'source_family': zone_family(key[0]),
            'target': key[1], 'relation': key[2],
            'target_zone': row['target_zone'],
            'target_family': row['target_family'],
            'target_kind': row['target_kind'], 'label': row['label'],
            'count': 0, 'samples': [],
        })
        cell['count'] += 1
        if len(cell['samples']) < sample_limit:
            cell['samples'].append(row['evidence'])
    cells = sorted(agg.values(), key=lambda c: (-c['count'], c['source'],
                                                 c['target']))
    return cells


def top_inter_edges(rows, limit=10):
    """Топ ребер между разными зонами, с доказательствами."""
    seen = {}
    for row in rows:
        if row['target_kind'] != 'ZONE' or row['category'] == 'INTRA':
            continue
        key = (row['ref'].zone or '?', row['target'], row['relation'])
        edge = seen.setdefault(key, {
            'source': key[0], 'source_family': zone_family(key[0]),
            'target': key[1], 'target_family': row['target_family'],
            'relation': key[2], 'label': row['label'],
            'count': 0, 'evidence': [],
        })
        edge['count'] += 1
        if len(edge['evidence']) < 3:
            edge['evidence'].append(row['evidence'])
    return sorted(seen.values(), key=lambda e: -e['count'])[:limit]


def top_memory_targets(rows, limit=15):
    """Топ адресов памяти/ОС по всем зонам-источникам."""
    agg = defaultdict(lambda: {'count': 0, 'zones': Counter()})
    for row in rows:
        if row['target_kind'] != 'MEMORY':
            continue
        cell = agg[row['target']]
        cell['count'] += 1
        cell['zones'][row['ref'].zone or '?'] += 1
    out = [{'label': k, 'count': v['count'],
            'zones': ', '.join('%s:%d' % (z, n)
                               for z, n in v['zones'].most_common(5))}
           for k, v in agg.items()]
    return sorted(out, key=lambda x: -x['count'])[:limit]


def clip(text, n):
    text = str(text)
    return text if len(text) <= n else text[:n - 2] + '..'


# ---------------------------------------------------------------------------
# 3. Отчёт
# ---------------------------------------------------------------------------

def write_md(path, rows, matrix, edges, memtop, stats, files, root):
    cats = Counter(r['category'] for r in rows)
    rels = Counter(r['relation'] for r in rows)
    nfiles = len(files)
    nzones = len({r['ref'].zone for r in rows if r['ref'].zone})
    nclass = sum(1 for r in rows if r['category'] != 'EXCLUDED')
    lines = []
    lines.append('# МЕЖМОДУЛЬНЫЙ КРОСС-РЕФЕРЕНС ЗОН БЭСМ-6')
    lines.append('')
    lines.append('Автоматически построен `tools/intermodule_xref.py`. '
                 'Исходные `gold/`, `dis/`, `docs/`, `sym/` НЕ изменялись.')
    lines.append('')
    lines.append('## 1. Что сканировалось')
    lines.append('')
    lines.append('| Каталог | Файлов .asm |')
    lines.append('|---|---|')
    for d in ('dis', 'dis-forced'):
        n = sum(1 for f in files if os.path.dirname(f).endswith(d))
        lines.append('| `%s/` | %d |' % (d, n))
    lines.append('| **ИТОГО** | **%d** |' % nfiles)
    lines.append('')
    lines.append('В `dis/` входят 4 полных листинга `ASM-Z*-full.asm`, '
                 'канонические `-L1` и 2 альтернативные разметки зоны '
                 '0137 (`-R3`, `-named`). Разбор строк и фильтры '
                 'переиспользованы из `tools/global_xref.py`.')
    lines.append('')
    lines.append('## 2. Точные команды')
    lines.append('')
    lines.append('```bash')
    lines.append('cd %s' % root)
    lines.append('python3 tools/intermodule_xref.py \\')
    lines.append('  --out analysis/XREF-INTERMODULE.md')
    lines.append('python3 -m unittest tools.tests.test_intermodule_xref -v')
    lines.append('```')
    lines.append('')
    lines.append('Проверка числа файлов: '
                 '`find dis dis-forced -name "*.asm" | wc -l` → %d.' % nfiles)
    lines.append('')
    lines.append('## 3. Статистика классификации')
    lines.append('')
    lines.append('| Показатель | Значение |')
    lines.append('|---|---|')
    lines.append('| Всего файлов .asm | %d |' % nfiles)
    lines.append('| Зон-источников | %d |' % nzones)
    lines.append('| Ссылок после фильтров | %d |' % len(rows))
    lines.append('| Классифицировано (INTRA+INTER+MEMORY) | %d |' % nclass)
    lines.append('| INTRA (внутри зоны) | %d |' % cats['INTRA'])
    lines.append('| INTER (другая зона) | %d |' % cats['INTER'])
    lines.append('| MEMORY/EXTERNAL | %d |' % cats['MEMORY'])
    lines.append('| REGISTER, не разрешено статически | %d |' % cats['REGISTER'])
    lines.append('| Исключено как псевдо/константа | %d |' % cats['EXCLUDED'])
    lines.append('| AMBIGUOUS (нелокальный листинг) | %d |' % cats['AMBIGUOUS'])
    lines.append('')
    lines.append('### 3.1 Связи по классу')
    lines.append('')
    lines.append('| Класс связи | Ссылок |')
    lines.append('|---|---|')
    all_rels = ('INTRA', 'INTER-B', 'INTER-B/B2', 'INTER-ASM',
                'ASM→B', 'B→ASM', 'MEMORY/EXTERNAL', 'REGISTER',
                'AMBIGUOUS', 'EXCLUDED')
    for rel in all_rels:
        lines.append('| %s | %d |' % (rel, rels.get(rel, 0)))
    for rel in rels:
        if rel not in all_rels:
            lines.append('| %s | %d |' % (rel, rels[rel]))
    lines.append('')
    lines.append('### 3.2 Правила отнесения')
    lines.append('')
    lines.append('1. Адрес `0..1777₈` в листинге с базой `-a0` '
                 'относится к ЭТОЙ ЖЕ зоне: метки `A#####`/`D#####`, '
                 "кавычные `'NNNN'` и малые десятичные операнды "
                 '`praddr()` печатает как смещения слова зоны.')
    lines.append('2. `02000₈` = загрузка зоны `0154` '
                 '(`docs/SEMANTIC/Z0154.md:14`, `sym/GLOBAL.tab:108`). '
                 'Это единственный доказанный переход «память → зона».')
    lines.append('3. Остальные адреса `>= 02000₈` идут в корзину '
                 '`MEM_<адрес>_<РОЛЬ>` по `sym/GLOBAL.tab`: '
                 '`MEM_70707_GATE`, `MEM_04000_MONITOR`, '
                 '`MEM_70000_SYSCALL`.')
    lines.append('4. `(Мn)` не разрешается: регистр-индекс/возврат, '
                 'а не адрес зоны.')
    lines.append('')
    lines.append('## 4. Матрица «зона-источник → цель»')
    lines.append('')
    lines.append('| Источник | Сем. | Цель | Класс | ВХ | Пример (зона.слово '
                 'мнсм операнд → цель) |')
    lines.append('|---|---|---|---|---|---|')
    for c in matrix[:60]:
        lines.append('| `Z%s` | %s | `%s` | %s | %d | `%s` |' % (
            c['source'], c['source_family'], clip(c['target'], 22),
            c['relation'], c['count'], clip(c['samples'][0], 40)))
    if len(matrix) > 60:
        lines.append('')
        lines.append('Показаны первые 60 строк из %d.' % len(matrix))
    lines.append('')
    lines.append('## 5. Топ межмодульных ребер')
    lines.append('')
    lines.append('Ребро = пара «зона-источник → другая зона» с '
                 'доказательствами из листингов.')
    lines.append('')
    if not edges:
        lines.append('Прямых ребер между разными зонами не найдено: '
                     'все адреса зон в листингах локальны (`-a0`), '
                     'а единственная доказанная кросс-зона '
                     '`02000₈ → 0154` учитывается ниже.')
    for i, e in enumerate(edges, 1):
        lines.append('')
        word = 'ссылка' if e['count'] % 10 == 1 and e['count'] % 100 != 11 \
            else 'ссылок'
        lines.append('### %d. Z%s → %s (%s), %d %s' % (
            i, e['source'], e['target'], e['relation'], e['count'], word))
        lines.append('')
        lines.append('Цель: `%s`.' % e['label'])
        lines.append('')
        lines.append('```')
        for ev in e['evidence']:
            lines.append(ev)
        lines.append('```')
    lines.append('')
    lines.append('## 6. Топ целей в памяти/ОС')
    lines.append('')
    lines.append('| Цель | ВХ | Источники (зона:число) |')
    lines.append('|---|---|---|')
    for m in memtop:
        lines.append('| `%s` | %d | %s |' % (
            m['label'], m['count'], clip(m['zones'], 38)))
    lines.append('')
    lines.append('## 7. Почему внутризональных ссылок большинство')
    lines.append('')
    lines.append('1. Каждый `.asm` - это 1024 слова ОДНОЙ дисковой зоны, '
                 'дизассемблированные с `-a0`. Метки `A#####`/`D#####` '
                 'и малые операнды - смещения внутри этой зоны. '
                 'Релокация адресных полей выполняется загрузчиком '
                 'при загрузке оверлея, а не в листинге.')
    lines.append('2. Оверлеи грузятся по фиксированным страницам '
                 '`страница × 02000₈` (`analysis/MEMORY-MAP.md` §3). '
                 'Код зоны обращается к соседним словам своей страницы, '
                 'поэтому `INTRA` - норма, а не ошибка разбора.')
    lines.append('3. Межмодульные переходы идут через память/ОС '
                 '(`MEM_...`), а не через «номер соседней зоны»: '
                 'в команде есть только числовой адрес. '
                 'Поэтому ребер между зонами немного.')
    lines.append('')
    lines.append('## 8. Честные оговорки')
    lines.append('')
    lines.append('1. **Статический анализ.** Косвенные переходы '
                 '`пб (М3)`, `по (М13)`, `пв (М15)` не разрешаются: '
                 'disbesm6 не отслеживает регистры. Такие ссылки '
                 'учтены отдельным классом `REGISTER`, '
                 'в матрицу не входят.')
    lines.append('2. **Карта память → диск неполна.** Из 33 зон B '
                 'надежно привязаны 12 (`analysis/MEMORY-MAP.md` §5). '
                 '`02000₈` имеет два кандидата: 0154 '
                 '(`Z0154.md:14`) и 0554 (`Z0554.md:23`). '
                 'Основным взят 0154 по условию задания.')
    lines.append('3. **Межмодульные ребра занижены.** Часть оверлеев '
                 'не обнаружена в ОП в точках съема трассы '
                 '(например 0170), поэтому переход через их адреса '
                 'попадает в корзину `MEMORY/EXTERNAL`, а не в зону.')
    lines.append('4. **Дублирование листингов.** 75 файлов в `dis/` '
                 '(включая 4 `ASM-Z*-full` и 2 варианта 0137) и 49 '
                 'в `dis-forced/`; одна ячейка попадает в несколько '
                 'файлов. Счетчики отражают число листингов, '
                 'а не число машинных обращений.')
    lines.append('5. **Логические адреса не равны физическим.** '
                 '`MEM_04000_MONITOR` / `MEM_70000_SYSCALL` '
                 'из `*EXECUTE` - адреса памяти тестовой программы, '
                 'а не слова зон 0137-0177 (`XREF-METHODOLOGY` §5.2).')
    lines.append('6. Фильтры `global_xref.py` отсекают fuzz=64, '
                 'шахматный fill, забелы и дубли половин слов; '
                 'числа отсеянных строк приведены в '
                 '`analysis/GLOBAL-XREF.md` §3.1.')
    lines.append('')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')


# ---------------------------------------------------------------------------
# 4. CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Межмодульные кросс-ссылки зон БЭСМ-6.')
    ap.add_argument('--out', default=os.path.join('analysis',
                                                  'XREF-INTERMODULE.md'))
    ap.add_argument('--root', default=ROOT,
                    help='корень репозитория (по умолчанию каталог tools/..)')
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    dirs = [os.path.join(root, 'dis'), os.path.join(root, 'dis-forced')]
    refs, _defs, stats, files = G.scan_asm_files(dirs)
    if not files:
        print('intermodule_xref: нет .asm в dis/ и dis-forced/',
              file=sys.stderr)
        return 1
    clean = G.apply_filters(refs, stats)
    local_map = {os.path.basename(f): (listing_base(f) == 0) for f in files}
    names = load_global_names(root)
    rows = classify_all(clean, names, local_map)
    matrix = build_matrix(rows)
    edges = top_inter_edges(rows)
    memtop = top_memory_targets(rows)
    out = args.out if os.path.isabs(args.out) else os.path.join(root, args.out)
    od = os.path.dirname(os.path.abspath(out))
    if od and not os.path.isdir(od):
        os.makedirs(od, exist_ok=True)
    write_md(out, rows, matrix, edges, memtop, stats, files, root)

    cats = Counter(r['category'] for r in rows)
    print('intermodule_xref: файлов=%d зон=%d ссылок=%d '
          'INTRA=%d INTER=%d MEMORY=%d REGISTER=%d excluded=%d' % (
              len(files),
              len({r['ref'].zone for r in rows if r['ref'].zone}),
              len(rows), cats['INTRA'], cats['INTER'], cats['MEMORY'],
              cats['REGISTER'], cats['EXCLUDED']))
    print('  MD: %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
