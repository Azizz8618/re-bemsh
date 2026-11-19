#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MACRO-COMMAND DECODER for the BESM-6 MACRO-BEMSH translator.

Two modes:

  python3 tools/macro_decode.py --catalog
      Print the macro-command catalog (markdown) built from
      /home/azizz/Yandex.Disk/re-dispak/macros.be (234 lines) -- the
      authoritative macro-definition reference for this ecosystem.

  python3 tools/macro_decode.py [--scan-dir dis] [--out analysis/macro_hits.md]
      Scan dis/*.asm text constants for macro-command names, using the
      `конд п'...'` pattern from docs/TEXT-CONSTANTS.md with KOI-7/GOST
      OCR homoglyph-tolerant matching.  Emit a markdown table:
          command | zone.word address | decoded context | semantics

Only reads files.  Never writes under dis/, bemsh/ or gold/.
"""

import argparse
import glob
import os
import re
import sys

# ---------------------------------------------------------------------------
# 1. Homoglyph-tolerant canonicalisation
# ---------------------------------------------------------------------------
# In macros.be the commands are written with mixed Cyrillic/Latin homoglyphs
# (OCR artefacts).  disbesm6 prints GOST text constants in Cyrillic; the KOI-7
# mnemonic table in zone 0137 uses Latin-shaped glyphs.  We fold both to one
# canonical uppercase "Cyrillic-looking" token so that e.g. GВLА == ГВЛА and
# SЕТА == СЕТА.  Ambiguous Latin N is folded to Н (as used in GВLА/АNОР and
# the ∧N local counter), I→И, J→Й -- this is a *matching* aid, not a claim
# about the original character.
LAT2CYR = {
    'A': 'А', 'B': 'В', 'C': 'С', 'D': 'Д', 'E': 'Е', 'F': 'Ф',
    'G': 'Г', 'H': 'Н', 'I': 'И', 'J': 'Й', 'K': 'К', 'L': 'Л',
    'M': 'М', 'N': 'Н', 'O': 'О', 'P': 'Р', 'R': 'Р',
    'S': 'С', 'T': 'Т', 'U': 'У', 'V': 'В', 'X': 'Х',
    'Y': 'У', 'Z': 'З',
}
# Cyrillic lowercase -> uppercase (str.upper already does this, kept explicit
# for clarity).  Digits, punctuation and the '∧' parameter sign are dropped.
_KEEP = set('АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ')


def canon(s):
    """Fold a string to a homoglyph-normalised uppercase token."""
    out = []
    for ch in s.upper():
        if ch in LAT2CYR:
            out.append(LAT2CYR[ch])
        elif ch in _KEEP:
            out.append(ch)
        # digits, '∧', '.', spaces, quotes are ignored
    return ''.join(out)


# ---------------------------------------------------------------------------
# 2. Catalog (extracted from macros.be; line numbers are 1-based)
# ---------------------------------------------------------------------------
# Each entry: name, exact spelling(s) as OCR'd, syntax, semantics,
# formal-parameter convention, example (line no, verbatim line).
CATALOG = [
    dict(name='МАСRО', spell='МАСRО',
         syntax='МАСRО  (далее тело до МЕND)',
         sem='Начало макроопределения. Макроредактор (0154) читает тело '
             'до МЕND и заносит его в таблицу определений.',
         conv='Формальные параметры ∧А…∧Р в шапке тела.',
         ex=(1, 'МАСRО')),
    dict(name='МЕND', spell='МЕND',
         syntax='МЕND',
         sem='Конец макроопределения; закрывает текущий МАСRО-блок.',
         conv='—',
         ex=(6, '.ВСЕ МЕND')),
    dict(name='ФИНИШ', spell='ФИНИШ',
         syntax='ФИНИШ',
         sem='Метка конца файла макрокоманд (последняя строка macros.be).',
         conv='—',
         ex=(234, 'ФИНИШ')),
    dict(name='∧-параметры', spell='∧А … ∧Р',
         syntax='∧А,∧Б,∧В,…,∧Р  (16 букв)',
         sem='Формальные параметры макроса; при вызове подставляются '
             'макромашиной (0170) по позиции. ∧М зарезервировано под имя '
             'макроса, ∧ВS,∧G и др. — под глобальные переменные.',
         conv='Набор из 16 букв А Б В Г Д Е Ж З И Й К Л Н О П Р '
              '(пропущены Ё и М); разделитель — запятая.',
         ex=(2, '∧М ВНЕШ ∧А,∧Б,∧В,…,∧Р')),
    dict(name='GВLА', spell='GВLА',
         syntax='GВLА ∧ИМЯ[,∧ИМЯ…]',
         sem='Объявление глобальных арифметических макропеременных '
             '(∧ВS, ∧G, ∧МЫ, ∧НИП …), общих для всех макросов.',
         conv='Имена с префиксом ∧; тип — арифметический (целое).',
         ex=(17, 'GВLА ∧ВS')),
    dict(name='GВLВ', spell='GВLВ',
         syntax='GВLВ ∧ИМЯ[,∧ИМЯ…]',
         sem='Объявление глобальных булевых макропеременных '
             '(∧З, ∧С, ∧Ф, ∧Ш …); значения 0/1 задаются SЕТВ.',
         conv='Имена с префиксом ∧; тип — логический.',
         ex=(123, 'GВLВ ∧З,∧С,∧Ф,∧Н,∧НИ,∧И,∧К,∧АС,∧П')),
    dict(name='LСLА', spell='LСLА',
         syntax='LСLА ∧ИМЯ[,∧ИМЯ…]',
         sem='Объявление локальных арифметических макропеременных, '
             'действующих внутри одного макроса (счётчик ∧N, ∧К).',
         conv='Имена с префиксом ∧; область — текущий МАСRО…МЕND.',
         ex=(70, 'LСLА ∧N')),
    dict(name='SЕТА', spell='SЕТА',
         syntax='∧ИМЯ SЕТА <арифм. выражение>',
         sem='Присваивание арифметической макропеременной значения '
             '(в т.ч. выражений вида ∧N-1). Управляет циклами.',
         conv='Левая часть — ∧-переменная, уже объявленная GВLА/LСLА.',
         ex=(71, '∧N SЕТА 48')),
    dict(name='SЕТВ', spell='SЕТВ',
         syntax='∧ИМЯ SЕТВ 0|1',
         sem='Присваивание булевой макропеременной значения 0/1; '
             'используется как флаг конфигурации (ВS, С, Н, ЭФ …).',
         conv='Левая часть — ∧-переменная из GВLВ.',
         ex=(125, '∧Ш SЕТВ 0')),
    dict(name='АIF', spell='АIF',
         syntax='АIF (условие).МЕТКА',
         sem='Условная ветка макромашины: при истинности условия '
             'продолжить с метки .МЕТКА, иначе пропустить до неё. '
             'Совместно с SЕТА/.МЕТКА образует цикл.',
         conv='Условие над ∧-переменными; метка начинается с точки.',
         ex=(4, "АIF (∧Б ЕQ '').ВСЕ")),
    dict(name='ЕQ', spell='ЕQ',
         syntax='(∧X ЕQ <значение>)',
         sem='Оператор равенства в условии АIF (в т.ч. сравнение с '
             "пустой строкой '' и числом 0/1).",
         conv='Операнды — ∧-переменные и константы.',
         ex=(4, "АIF (∧Б ЕQ '').ВСЕ")),
    dict(name='NЕ', spell='NЕ',
         syntax='(∧X NЕ <значение>)',
         sem='Оператор неравенства в условии АIF; часто завершает цикл '
             'счётчика (∧N NЕ 0).',
         conv='Операнды — ∧-переменные и константы.',
         ex=(75, 'АIF (∧N NЕ 0).СЛ')),
    dict(name='ОR', spell='ОR',
         syntax='(усл1) ОR (усл2)',
         sem='Логическое ИЛИ между условиями АIF '
             '(напр. (∧ВS ЕQ 0) ОR (∧ЭФ ЕQ 1)).',
         conv='Скобки вокруг каждого подусловия.',
         ex=(161, 'АIF ((∧ВS ЕQ 0) ОR (∧ЭФ ЕQ 1)).НЕТАС')),
    dict(name='.МЕТКА', spell='.ВСЕ .К .СЛ .Х .СП .НЕТАС .SL',
         syntax='.ИМЯ',
         sem='Метка-цель ветки АIF и точка входа в цикл; сама по себе '
             'код не порождает (часто перед АNОР).',
         conv='Имя произвольное, начинается с точки.',
         ex=(4, '.ВСЕ МЕND')),
    dict(name='ЭКВ', spell='ЭКВ',
         syntax='[<метка>] ЭКВ <выражение>',
         sem='Эквивалент (приравнивание символа значению) макромашины; '
             "вычисляет выражение типа '103'+48-∧N и связывает имя.",
         conv='Имя может содержать подстановки ∧-параметров (Е∧N).',
         ex=(63, '∧А(1) ЭКВ ∧А(2)')),
    dict(name='ЭКВИВ', spell='ЭКВИВ',
         syntax='ЭКВИВ <список пар/параметров>',
         sem='Векторное ЭКВ: применяет эквивалент ко списку пар '
             '(М1,1),(М2,2)… или к списку ∧-параметров; рекурсивно '
             'продолжает через запятые.',
         conv='Список через запятые; пары в скобках.',
         ex=(62, 'ЭКВИВ ∧А,∧Б,…,∧Р')),
    dict(name='ВНЕШ', spell='ВНЕШ',
         syntax='[<∧М>] ВНЕШ ∧А[,∧Б…]',
         sem='Объявление внешних символов генерируемого модуля; '
             'попадает в таблицу внешних связей (ВНЕШН=… в листинге).',
         conv='Список ∧-параметров через запятые.',
         ex=(2, '∧М ВНЕШ ∧А,∧Б,…,∧Р')),
    dict(name='ВНЕШН', spell='ВНЕШН',
         syntax='[<∧М>] ВНЕШН ∧М..∧А(N\'∧А)',
         sem='Внешнее объявление в нормальной/диапазонной форме; '
             'формирует внешний символ для каждого элемента списка.',
         conv='Диапазон ∧М..∧А с выражением N\'∧А.',
         ex=(3, "∧А(1) ВНЕШН ∧М..∧А(N'∧А)")),
    dict(name='ВНЕШБ', spell='ВНЕШБ',
         syntax='∧М ВНЕШБ ∧А,…',
         sem='Условное ВНЕШ: разворачивается в ВНЕШ только при '
             'глобальном булевом ∧ВS == 1.',
         conv='Флажок ∧ВS управляет условием (через АIF).',
         ex=(32, '∧М ВНЕШБ ∧А,∧Б,…,∧Р')),
    dict(name='ВНЕШС', spell='ВНЕШС',
         syntax='∧М ВНЕШС ∧А,…',
         sem='Условное ВНЕШ: разворачивается только при ∧ВS == 0.',
         conv='Флажок ∧ВS управляет условием (через АIF).',
         ex=(40, '∧М ВНЕШС ∧А,∧Б,…,∧Р')),
    dict(name='ЕВНЕШ', spell='ЕВНЕШ',
         syntax='ЕВНЕШ ∧А',
         sem='Внешнее объявление для E-префиксных символов (Е∧N); '
             'работает в паре с циклом SЕТА/АIF.',
         conv='Один ∧-параметр; имя строится как Е∧N.',
         ex=(69, 'ЕВНЕШ ∧А')),
    dict(name='ВХОД', spell='ВХОД',
         syntax='[<∧М>] ВХОД ∧А[,∧Б…]',
         sem='Объявление входных точек (entry) генерируемого модуля; '
             'задаёт ВХОДН=N в сводке листинга.',
         conv='Список ∧-параметров через запятые.',
         ex=(9, 'ВХОД ∧А,∧Б,…,∧Р')),
    dict(name='ВХОДН', spell='ВХОДН',
         syntax='ВХОДН ∧А',
         sem='Объявление одной ("нормальной") входной точки.',
         conv='Один ∧-параметр.',
         ex=(10, 'ВХОДН ∧А')),
    dict(name='ВХОДБ', spell='ВХОДБ',
         syntax='ВХОДБ ∧А,…',
         sem='Условный ВХОД: разворачивается только при ∧ВS == 1.',
         conv='Флажок ∧ВS через АIF.',
         ex=(24, 'ВХОДБ ∧А,∧Б,…,∧Р')),
    dict(name='ВХОДС', spell='ВХОДС',
         syntax='ВХОДС ∧А,…',
         sem='Условный ВХОД: разворачивается только при ∧ВS == 0.',
         conv='Флажок ∧ВS через АIF.',
         ex=(16, 'ВХОДС ∧А,∧Б,…,∧Р')),
    dict(name='КОНД', spell='КОНД',
         syntax='[<имя>] КОНД <условие/выражение>',
         sem='Условная вставка слова/данных при сборке '
             '(напр. Е∧N КОНД М∧К.Ю\'1\'). Семантика гипотетическая: '
             'директива макромашины, ставящая слово по условию.',
         conv='Имя и выражение могут содержать ∧-подстановки.',
         ex=(50, '∧М КОНД ∧К')),
    dict(name='КОНДБ', spell='КОНДБ',
         syntax='∧М КОНДБ ∧К',
         sem='Условная генерация КОНД при ∧ВS == 1; иначе АNОР.',
         conv='Флажок ∧ВS через АIF.',
         ex=(48, '∧М КОНДБ ∧К')),
    dict(name='КОНДС', spell='КОНДС',
         syntax='∧М КОНДС ∧К',
         sem='Условная генерация КОНД при ∧ВS == 0; иначе АNОР.',
         conv='Флажок ∧ВS через АIF.',
         ex=(55, '∧М КОНДС ∧К')),
    dict(name='АНОП / АNОР', spell='АНОП, АNОР',
         syntax='АНОП  |  АNОР',
         sem='Пустая операция в теле макроса (заполнитель ветки/цикла); '
             'код не порождает. Встречаются оба написания: '
             'АНОП (Кириллица) и АNОР (омоглифы N, R).',
         conv='Без параметров; часто стоит сразу после .МЕТКА.',
         ex=(20, '.К АНОП')),
    dict(name='DК', spell='DК',
         syntax="[<∧М>] DК '36',<имя>",
         sem='Макрос извлечения кода ("extract code"): выделяет код '
             "'36' в символ ВТ∧SNDХ; подробности семантики не "
             'доказаны (выведено из использования).',
         conv='Первый аргумент — строковая константа в кавычках.',
         ex=(198, "∧М ДК '36',ВТ∧SNDХ")),
    dict(name='МNОТЕ', spell='МNОТЕ',
         syntax='МNОТЕ * <текст>',
         sem='Директива комментария в теле макроса; остаток строки '
             'не разворачивается.',
         conv='Текст произвольный, часто после звёздочки.',
         ex=(203, 'МNОТЕ * СИНХР.ПУСК ОБМЕНА')),
    dict(name='ПВ', spell='ПВ',
         syntax='[<метка>] ПВ <операнд>.(13)',
         sem='Машинная команда БЕМШ "пересылка в" (запись слова), '
             'выпускаемая телом макроса; индекс (13) — регистр М13.',
         conv='Операнд с индексным полем (13) или (М16).',
         ex=(207, 'ПВ ∧ВХОД.(13)')),
    dict(name='УИА', spell='УИА',
         syntax='[<метка>] УИА <операнд>',
         sem='Машинная команда "установить индекс/адрес", порождает '
             'слово в развёрнутом макросе (аналог CALL → ПВО …(М15)).',
         conv='Операнд — имя или ∧-параметр.',
         ex=(225, 'УИА ∧А')),
    dict(name='ПБ', spell='ПБ',
         syntax='[<метка>] ПБ <адрес>|(М15)',
         sem='Машинная команда "переход"; в макросе CALL возврат '
             'делается по ПБ (М15) — адрес возврата в М15.',
         conv='Адрес или индекс (М15).',
         ex=(231, 'ПБ ∧СТОП')),
    dict(name='НОП', spell='НОП',
         syntax='НОП',
         sem='Аппаратная "нет операции"; заполнитель после DК.',
         conv='—',
         ex=(199, 'ВТ∧SNDХ НОП')),
    dict(name='ТЕКСТ / П\'', spell='ТЕКСТ, П\'',
         syntax="ТЕКСТ П'…'",
         sem='Директива вывода текстовой константы в теле макроса '
             '(ШИФР 419919810620).',
         conv='Строка в апострофах после П.',
         ex=(215, "∧М ТЕКСТ П'ШИФР 419919810620'")),
    dict(name='Х\'', spell='Х\'',
         syntax="Х'<16-ричная константа>'",
         sem='Директива вывода 16-ричного слова в теле макроса.',
         conv='Константа в апострофах после Х.',
         ex=(220, "∧М КОНД Х'419919810620'")),
]


# ---------------------------------------------------------------------------
# 3. Catalog markdown
# ---------------------------------------------------------------------------
def catalog_markdown():
    lines = [
        '# Каталог макрокоманд MACRO-BEMSH (из macros.be)',
        '',
        'Источник: `/home/azizz/Yandex.Disk/re-dispak/macros.be` (234 строки). '
        'Написание сохранено как в OCR-источнике (латиница/кириллица — '
        'омоглифы).',
        '',
        '| № | Команда | Варианты написания | Синтаксис | Семантика | '
        'Формальные параметры | Пример (macros.be) |',
        '|---|---------|--------------------|-----------|-----------|----------------------|'
        '--------------------|',
    ]
    for i, c in enumerate(CATALOG, 1):
        n, txt = c['ex']
        txt = txt.replace('|', '\\|')
        row = '| {} | `{}` | `{}` | `{}` | {} | {} | {}: `{}` |'.format(
            i, c['name'], c['spell'], c['syntax'], c['sem'],
            c['conv'], n, txt)
        lines.append(row)
    lines.append('')
    lines.append('Всего макрокоманд: {}.'.format(len(CATALOG)))
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# 4. Scanning dis/*.asm
# ---------------------------------------------------------------------------
# Pattern from docs/TEXT-CONSTANTS.md §1:
#   ^\s*(\d+)\s+([0-7]{16})\s+.*\sконд\s+п'(.*?)'
COND_P = re.compile(r"^\s*(\d+)\s+([0-7]{16})\s+.*?\sконд\s+п'(.*?)'")
WORD_ADDR = re.compile(r'^\s*(\d+)')
ZONE_FROM_FILE = re.compile(r'Z(\d{4})')

def homoglyph_class(canonical_char):
    """Regex character class of all glyphs folding to canonical_char."""
    chars = {canonical_char, canonical_char.lower()}
    for k, v in LAT2CYR.items():
        if v == canonical_char:
            chars.update((k, k.lower()))
    return '[' + ''.join(re.escape(ch) for ch in sorted(chars)) + ']'


def token_pattern(variant):
    """Build a boundary-anchored homoglyph-tolerant regex for a spelling."""
    parts = []
    for ch in variant:
        cu = ch.upper()
        if ch.isspace():
            parts.append(r'\s*')
        elif cu in _KEEP or cu in LAT2CYR:
            c = LAT2CYR.get(cu, cu)  # canonical Cyrillic letter
            parts.append(homoglyph_class(c))
        elif ch.isalpha():
            # Unknown Latin letter (e.g. Q in ЕQ): match it literally.
            parts.append('[' + re.escape(ch.lower()) + re.escape(ch.upper())
                         + ']')
        else:
            # punctuation ('.', "'", '-') -- literal
            parts.append(re.escape(ch))
    body = ''.join(parts)
    if not body:
        return None
    return re.compile(r'(?<![^\W\d_])' + body + r'(?![^\W\d_])',
                      re.UNICODE)


# One compiled pattern set per catalog entry.  Entries whose spelling is a
# convention rather than a literal token (∧-параметры) yield no pattern and
# are skipped during scanning.
_PATTERNS = []
for _c in CATALOG:
    pats = []
    for v in re.split(r'[,/\s]+', _c['spell']):
        v = v.strip()
        if not v:
            continue
        p = token_pattern(v)
        if p is not None:
            pats.append(p)
    _PATTERNS.append(pats)


def scan(scan_dir):
    files = sorted(glob.glob(os.path.join(scan_dir, '*.asm')))
    hits = []
    for path in files:
        mz = ZONE_FROM_FILE.search(os.path.basename(path))
        zone = mz.group(1) if mz else '????'
        try:
            fh = open(path, encoding='utf-8', errors='replace')
        except OSError:
            continue
        with fh:
            for line in fh:
                m = COND_P.match(line)
                if not m:
                    continue
                word = m.group(1)
                text = m.group(3)
                if not text:
                    continue
                for c, pats in zip(CATALOG, _PATTERNS):
                    if not any(p.search(text) for p in pats):
                        continue
                    addr = '{}.{}'.format(zone, word)
                    context = text.strip()
                    hits.append((c['name'], addr, context, c['sem'],
                                 c['ex'][0]))
    return files, hits


def scan_markdown(files, hits):
    lines = [
        '# Поиск макрокоманд в текстовых константах dis/*.asm',
        '',
        'Сканировано файлов: {}. Совпадений: {}.'.format(len(files), len(hits)),
        '',
        'Команда | зона.слово | декодированный контекст | семантика '
        '(из каталога) | строка macros.be',
        '--------|-----------|--------------------------|--------------------|'
        '----------------',
    ]
    for name, addr, ctx, sem, exline in hits:
        ctx = ctx.replace('|', '\\|')
        sem_short = sem if len(sem) <= 90 else sem[:87] + '…'
        sem_short = sem_short.replace('|', '\\|')
        lines.append('| `{}` | `{}` | `{}` | {} | {} |'.format(
            name, addr, ctx, sem_short, exline))
    lines.append('')
    lines.append('Примечание: совпадения основаны на '
                 'омоглиф-толерантной канонизации (см. `canon()`); '
                 'контекст — содержимое `п\'…\'` одного слова GOST. '
                 'Текст может быть продолжен в соседних словах.')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description='MACRO-COMMAND decoder for BESM-6 MACRO-BEMSH.')
    ap.add_argument('--scan-dir', default='dis',
                    help='каталог с dis/*.asm (по умолчанию: dis)')
    ap.add_argument('--out', default='analysis/macro_hits.md',
                    help='файл отчёта (по умолчанию: analysis/macro_hits.md)')
    ap.add_argument('--catalog', action='store_true',
                    help='печать каталога макрокоманд и выход')
    args = ap.parse_args(argv)

    if args.catalog:
        sys.stdout.write(catalog_markdown())
        return 0

    files, hits = scan(args.scan_dir)
    report = scan_markdown(files, hits)
    if args.out:
        d = os.path.dirname(args.out)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as fh:
            fh.write(report)
        sys.stderr.write('scan: {} files, {} hits -> {}\n'.format(
            len(files), len(hits), args.out))
    else:
        sys.stdout.write(report)
    return 0


if __name__ == '__main__':
    sys.exit(main())
