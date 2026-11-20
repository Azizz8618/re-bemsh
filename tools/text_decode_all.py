#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UNIVERSAL BESM-6 TEXT-CONSTANT DECODER (том 2348, все 69 зон).

Читает gold/*.bin только на чтение. Каждое 48-битное слово (6 байт)
разбирается сразу в четырёх кодировках:

  GOST-8   6 байт, таблица gost_to_unicode_cyr (encoding.cpp:36);
  KOI-7    6 байт, таблица koi7_to_unicode   (encoding.cpp:681);
  TEXT     8 шестибитных групп, код = ASCII-0x20 (docs 19/20 re-forex);
  ITM      6 байт, таблица itm_to_gost        (encoding.cpp:463).

Никаких биасов, поворотов и перестановок: калибровка по 5 штампам
даёт identity 5/5 (docs/TEXT-DECODING-INVESTIGATION.md §3).

Классификатор не верит «кириллическому score» сам по себе: у GOST
почти любой байт из 0x20..0x4D даёт букву. Кандидат принимается
только по словарным словам, частым диграфам и отсутствию шума.

Вызов:
  python3 tools/text_decode_all.py --all
  python3 tools/text_decode_all.py --zone 0147
  python3 tools/text_decode_all.py --zone 0147 --out /tmp/z0147.md

Автор: под poised задания 20.11.2026. Не изменяет эталонные образы.
"""

import argparse
from collections import Counter, defaultdict
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(ROOT, 'gold')
DEFAULT_OUT = os.path.join(ROOT, 'docs', 'TEXT-CONSTANTS-ALL.md')

# ---------------------------------------------------------------------------
# 1. Таблицы (точный порт monitor80-re/tools/encoding.cpp)
# ---------------------------------------------------------------------------

# GOST-10859, 8 бит/символ: gost_to_unicode_cyr[0..127].
# 0 = нет глифа (байт >= 0x80 или служебный код).
GOST_CYR = [
    0x30,0x31,0x32,0x33,0x34,0x35,0x36,0x37,
    0x38,0x39,0x2b,0x2d,0x2f,0x2c,0x2e,0x20,
    0x23e8,0x2191,0x28,0x29,0xd7,0x3d,0x3b,0x5b,
    0x5d,0x2a,0x2018,0x2019,0x2260,0x3c,0x3e,0x3a,
    0x0410,0x0411,0x0412,0x0413,0x0414,0x0415,0x0416,0x0417,
    0x0418,0x0419,0x041a,0x041b,0x041c,0x041d,0x041e,0x041f,
    0x0420,0x0421,0x0422,0x0423,0x0424,0x0425,0x0426,0x0427,
    0x0428,0x0429,0x042b,0x042c,0x042d,0x042e,0x042f,0x44,
    0x46,0x47,0x49,0x4a,0x4c,0x4e,0x51,0x52,
    0x53,0x55,0x56,0x57,0x5a,0x203e,0x2a7d,0x2a7e,
    0x2228,0x2227,0x2283,0xac,0xf7,0x2261,0x25,0x25c7,
    0x7c,0x2015,0x5f,0x21,0x22,0x042a,0xb0,0x2032,
]

# KOI-7 (Н2): koi7_to_unicode[0..127], encoding.cpp:681.
KOI7 = [
    0,0x01,0x02,0x03,0x04,0x042a,0x06,0xd7,
    0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x2a7d,0x2a7e,
    0x2018,0x11,0x12,0x13,0x14,0x2015,0x2191,0x23e8,
    0x2260,0xb0,0xf7,0x2019,0x2283,0x2261,0x2228,0xac,
    0x20,0x21,0x22,0x23,0x24,0x25,0x26,0x27,
    0x28,0x29,0x2a,0x2b,0x2c,0x2d,0x2e,0x2f,
    0x30,0x31,0x32,0x33,0x34,0x35,0x36,0x37,
    0x38,0x39,0x3a,0x3b,0x3c,0x3d,0x3e,0x3f,
    0x40,0x41,0x42,0x43,0x44,0x45,0x46,0x47,
    0x48,0x49,0x4a,0x4b,0x4c,0x4d,0x4e,0x4f,
    0x50,0x51,0x52,0x53,0x54,0x55,0x56,0x57,
    0x58,0x59,0x5a,0x5b,0x203e,0x5d,0x7c,0x5f,
    0x042e,0x0410,0x0411,0x0426,0x0414,0x0415,0x0424,0x0413,
    0x0425,0x0418,0x0419,0x041a,0x041b,0x041c,0x041d,0x041e,
    0x041f,0x042f,0x0420,0x0421,0x0422,0x0423,0x0416,0x0412,
    0x042c,0x042b,0x0417,0x0428,0x042d,0x0429,0x0427,0x7f,
]

# ITM (автокод Чайковского): itm_to_gost[0..255], encoding.cpp:463.
# Значения — коды GOST-10859; 0 означает «нет глифа».
ITM_TO_GOST = [
    0o000,0o001,0o002,0o003,0o004,0o005,0o006,0o007,0o010,0o011,0o000,0o000,0o000,0o000,0o000,0o017,
    0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,
    0o017,0o033,0o127,0o132,0o130,0o026,0o015,0o016,0o115,0o023,0o000,0o027,0o036,0o136,0o037,0o025,
    0o112,0o012,0o126,0o133,0o032,0o037,0o030,0o014,0o013,0o121,0o065,0o000,0o035,0o032,0o022,0o000,
    0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,
    0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o134,0o135,0o000,0o033,
    0o000,0o000,0o000,0o021,0o000,0o123,0o035,0o036,0o013,0o000,0o034,0o000,0o000,0o000,0o000,0o000,
    0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o031,0o000,0o000,0o000,0o000,0o000,0o045,0o000,
    0o000,0o062,0o000,0o056,0o000,0o055,0o105,0o054,0o000,0o104,0o107,0o101,0o102,0o060,0o061,0o112,
    0o045,0o114,0o077,0o042,0o110,0o063,0o100,0o065,0o040,0o113,0o103,0o000,0o111,0o106,0o052,0o000,
    0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,
    0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,
    0o000,0o071,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o053,0o000,0o043,0o050,0o057,0o066,0o046,
    0o074,0o047,0o044,0o041,0o070,0o072,0o064,0o073,0o000,0o067,0o051,0o000,0o075,0o076,0o000,0o000,
    0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,
    0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,0o000,
]

# Маска «уверенных» 6-битных кодов TEXT (dtran.cc:is_likely_text).
TEXT_VALID = frozenset([0, 10, 15, *range(16, 26), 29, 30, *range(33, 59)])

CYR_UP = set(chr(c) for c in range(0x410, 0x42f + 1))
LAT_UP = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
GOST_LAT_GLYPHS = set('DFGIJLNQRSTUVWZ')
PUNCT = set('+-/,. :()*;\'"')
CONF_TEXT = LAT_UP | set('0123456789*/+-')
BOUNDARY = set(' .,-/()*+:;')

# Словарные слова и частые диграфы — защита от «почти любой байт даёт букву».
KNOWN_WORDS = [
    'ИПМ','МАКРО','БЕМШ','БЕМ','МАГ','ВЕР','ВАР','ОШ','СПР','СПРАВКИ',
    'КОНЕЦ','НАЧАЛО','ОШИБКА','ОШИБКИ','ТЕКСТ','МЕТКА','ВНЕШ','ВХОД',
    'ЗАПИСЬ','АРАП','РЕДАКТОР','МАШИНА','НЕТ','УПРАВЛЯЮЩИХ','КАРТ',
    'НЕВЕРНЫЙ','КОМПИЛИР','ЛИМ','СТРЕЛ','ПРГ','СТР','ЗНАЧ',
    'ОПРЕД','ИСПЛЗ','ИМЯ','ЖИЗНЬ','УНЧАП','КОЛИЧ','ЯЧ','ГС','НПК',
    'СВОБ','ПЕРЕМ','АДРЕС','КОМАНДА','ИСП','ГЕН','ИСХ','ОПЕРАЦИЯ',
    'ОПЕРАНД','КОММЕНТАРИЙ','ЗАПИСАН','ЗОНЫ','ДЛЯ','ИЛИ','НА','БЕ',
    'ОТ','В','АП','МК','ПВ','ЦИКЛ','МОДА','СДА','РЖА','УИ','СЧ','СЛ',
    'ВЧ','ЗП','Э','Штамп',
]
# Частые диграфы русского языка (в Uppercase, плюс латинские омоглифы).
DIGRAPHS = set([
    'СТ','НО','ЕН','ТО','НА','НИ','ВА','ОВ','РА','ЛИ','НЕ','ЧА','ЫТ',
    'ШН','РЕ','РО','ИН','ИМ','АЛ','ОК','ОР','ЕК','ЕМ','ЕВ','ИТ','УР',
    'ЛА','ВО','ДЕ','ЕР','ВЕ','ПЕ','ГН','ПР','ЗМ','РШ','МП','МА','КР',
    'АР','БЕ','ЕМ','ШМ','ЛА','ТЬ','СЯ','ЕЙ','ОЙ','ЫЙ','ИЯ','ЬЯ','ИЕ',
    'ЕТ','ЕН','ЕМ','ЕЛ','ИЛ','ИТ','ИН','ИМ','ОВ','ЕВ','ИВ','ЫВ','УЮ',
])

# Калибровочные штаммы: адрес, байты, эталон (docs/TEXT-DECODING-INVESTIGATION §2).
CALIBRATION = [
    ('0147.1315', '28 2f 2c 0f 2c 20', 'ИПМ МА'),
    ('0154.0751', '2c 20 2a 30 2e 30', 'МАКРОР'),
    ('0170.0216', '2c 20 2a 30 2e 2c', 'МАКРОМ'),
    ('0173.0655', '2e 38 0e 31 2f 30', 'ОШ.СПР'),
    ('0176.1732', '28 2f 2c 0f 2c 20', 'ИПМ МА'),
]

# Известные целые фразы (docs/TEXT-CONSTANTS.md §5) -> смысл.
KNOWN_PHRASES = {
    'ИПМ МАКРО БЕМШ ВЕР 06/78': 'штамп версии B (ВЕР.06/78)',
    'ИПМ МАКРО БЕМШ ВАР 12/77': 'штамп версии B2 (ВАР.12/77)',
    'АРАП ВАР 04/78': 'штамп АРАП B',
    'АРАП ВАР 10/75': 'штамп АРАП B2',
    'МАКРОРЕДАКТОР ОТ 20 06 78': 'штамп макроредактора B',
    'МАКРОРЕДАКТОР ОТ 10 04 76': 'штамп макроредактора B2',
    'МАКРОМАШИНА ОТ 1 11 78': 'штамп макромашины B',
    'МАКРОМАШИНА ОТ 15 12 76': 'штамп макромашины B2',
    'ОШ СПР НА БЕМШ1': 'справка по ошибкам B',
    'ЛИМ СТРЕЛ НА БЕМШ1': 'справка по лимитам/стрелкам B',
    'ОШ СПРАВКИ БЕМШ2': 'справка по ошибкам B2',
    'ОШИБКИ НПК СВОБ ПЕРЕМ АДРЕС КОМАНДА А ИСП N ГЕН N ИСХ МЕТКА '
    'ОПЕРАЦИЯ ОПЕРАНД КОММЕНТАРИЙ': 'шапка листинга ошибок',
    'ЗАПИСЬ АП НА АРХИВНУЮ ЛЕНТУ ЗАКОНЧИЛАСЬ': 'сообщение АРАП',
    'НЕТ УПРАВЛЯЮЩИХ КАРТ АРАПА': 'ошибка АРАП',
    'ОШИБКА СПРАВКИ': 'ошибка справки',
    'НЕ ЗАДАНО ИМЕНИ ДЛЯ НЖИЗНЬ ИЛИ УНЧАП': 'ошибка задания имени',
    'НЕВЕРНЫЙ 1 Й КОМПИЛИР': 'ошибка компиляции',
    'МЕТКА ЗНАЧ ОПРЕД ИСПЛЗ': 'заголовок таблицы меток',
    '00 ЗАПИСАН В ЗОНЫ С': 'сообщение о записи зон',
    'БЫЛИ ОШИБКИ В ЗАДАНИИ АРАП': 'сообщение АРАП об ошибках задания',
}

MNEMONICS = set('ЗП СЧ СЛ ВЧ СДА РЖА УИ УИМ Э50 МОДА ПВ ЦИКЛ '
                'ЗПМ СЛМ СЧМ ВЧМ НТЖ КОП ВВД ВЫВ ЧТ СТ АР Штамп'.split())

# Омоглифы KOI-7: латинские начертания вместо кириллических.
KOI_HOMOGLYPHS = {
    'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н', 'I': 'И',
    'J': 'Й', 'K': 'К', 'M': 'М', 'O': 'О', 'P': 'Р', 'S': 'С',
    'T': 'Т', 'X': 'Х', 'Y': 'У', 'Z': 'З',
}


def koi_normalize(s):
    return ''.join(KOI_HOMOGLYPHS.get(c, c) for c in s)

# ---------------------------------------------------------------------------
# 2. Разбор слова и четыре декодера
# ---------------------------------------------------------------------------

def bytes8(word):
    """Шесть байт 48-битного слова, от старшего к младшему."""
    return [(word >> s) & 0xff for s in (40, 32, 24, 16, 8, 0)]


def groups6(word):
    """Восемь шестибитных групп, от старшей к младшей."""
    return [(word >> s) & 0x3f for s in (42, 36, 30, 24, 18, 12, 6, 0)]


def word_from_bytes(bs):
    return int.from_bytes(bytes(bs), 'big')


def decode_gost(word):
    """GOST-8: 6 байт побайтово, тождественно (никакого биаса)."""
    out = []
    for b in bytes8(word):
        u = GOST_CYR[b] if b < len(GOST_CYR) else 0
        out.append(chr(u) if u else '\0')
    return ''.join(out)


def decode_koi7(word):
    """KOI-7: 6 байт, 7 бит на символ."""
    out = []
    for b in bytes8(word):
        u = KOI7[b] if b < len(KOI7) else 0
        if u in (0, 0x7f) or (0 < u < 0x20 and u not in
                              (0x05, 0x06, 0x0e, 0x0f, 0x10, 0x15, 0x16,
                               0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d,
                               0x1e, 0x1f)):
            u = 0
        out.append(chr(u) if u else '\0')
    return ''.join(out)


def decode_text(word):
    """6-битный TEXT: 8 групп, код = ASCII-0x20."""
    return ''.join(chr(c + 0x20) for c in groups6(word))


def decode_itm(word):
    """ITM: 6 байт через itm_to_gost, затем GOST-10859."""
    out = []
    for b in bytes8(word):
        g = ITM_TO_GOST[b] if b < len(ITM_TO_GOST) else 0
        u = GOST_CYR[g] if g and g < len(GOST_CYR) else 0
        out.append(chr(u) if u else '\0')
    return ''.join(out)


def decode_all(word):
    return {
        'GOST': decode_gost(word),
        'KOI7': decode_koi7(word),
        'TEXT': decode_text(word),
        'ITM': decode_itm(word),
    }


# ---------------------------------------------------------------------------
# 3. Оценщик качества: текст или шум
# ---------------------------------------------------------------------------

def is_cyr(c):
    return c in CYR_UP


def known_word_hits(text):
    """Слово из словаря с границами; короткие слова требуют границ."""
    hits = []
    up = text.upper()
    for w in KNOWN_WORDS:
        w = w.upper()
        for m in re.finditer(re.escape(w), up):
            a, b = m.start(), m.end()
            if len(w) >= 3:
                hits.append(w)
            elif ((a == 0 or up[a - 1] in BOUNDARY) and
                  (b == len(up) or up[b] in BOUNDARY)):
                hits.append(w)
    return hits


def digraph_ratio(text):
    """Доля частых русских диграфов среди пар соседних букв."""
    letters = [c.upper() for c in text if is_cyr(c)]
    if len(letters) < 3:
        return 0.0
    pairs = [letters[i] + letters[i + 1] for i in range(len(letters) - 1)]
    return sum(p in DIGRAPHS for p in pairs) / len(pairs)


def gost_word_ok(s):
    """Одно слово GOST-8: не число и не случайный набор букв."""
    if '\0' in s:
        return False, 'нет глифа'
    letters = sum(is_cyr(c) for c in s)
    digits = sum(c.isdigit() for c in s)
    spaces = s.count(' ')
    punct = sum(c in PUNCT for c in s)
    lat = sum(c in GOST_LAT_GLYPHS for c in s)
    if not letters and s.startswith('0') and s.count('0') >= 2:
        return False, 'ведущие нули: число'
    if letters < 2:
        return False, 'мало кириллицы'
    if (letters + spaces + punct) / 6.0 < 0.66:
        return False, 'слишком много цифр/мусора'
    if lat > 1 or digits > 2:
        return False, 'латиница/цифры в слове'
    return True, 'кириллица %d/6' % letters


def text_word_ok(s, word):
    """6-битный TEXT: только «уверенные» коды и осмысленные символы."""
    codes = groups6(word)
    if any(c not in TEXT_VALID for c in codes):
        return False, 'управляющий код TEXT'
    printable = sum(1 for c in s if 0x20 <= ord(c) <= 0x5e)
    if printable < 5:
        return False, 'меньше 5 печатных символов'
    eff = s.rstrip()
    if len(eff) < 4:
        return False, 'короткая строка'
    confident = [c for c in eff if c in CONF_TEXT]
    if len(confident) < 4:
        return False, 'мало печ. символов'
    cnt = Counter(confident)
    if len(cnt) < 3:
        return False, 'однообразие (маска)'
    if max(cnt.values()) / len(confident) > 0.5:
        return False, 'повтор >50% (маска)'
    return True, 'TEXT %d симв., %d various' % (len(eff), len(cnt))


def koi_word_ok(s):
    """Одно слово KOI-7: печатные байты; `\0` допустим только в хвосте."""
    eff = s.rstrip('\0')
    if '\0' in eff:
        return False, 'нет глифа внутри'
    core = eff.strip()
    letters = [c for c in core if is_cyr(c) or c in KOI_HOMOGLYPHS]
    if len(letters) < 2 or any(c.isdigit() for c in core):
        return False, 'мало букв или цифры'
    homo = any(c in KOI_HOMOGLYPHS for c in core)
    cyr = sum(is_cyr(c) for c in core)
    if not homo and cyr < 3:
        return False, 'нет омоглифа и мало кириллицы'
    return True, 'KOI-7 буквы %d/6' % len(letters)


def itm_word_ok(s):
    """Одно слово ITM: разреженная таблица, печатные глифы."""
    if '\0' in s:
        return False, 'нет глифа'
    letters = sum(is_cyr(c) or c in LAT_UP for c in s)
    if letters < 2:
        return False, 'мало букв'
    return True, 'ITM буквы %d/6' % letters


WORD_TESTS = {
    'GOST': gost_word_ok,
    'KOI7': koi_word_ok,
    'TEXT': lambda s, w: text_word_ok(s, w),
    'ITM': itm_word_ok,
}


def score_word(word):
    """Вернёт dict кодировка -> (признак, причина) для всех четырёх."""
    dec = decode_all(word)
    out = {}
    for enc, text in dec.items():
        try:
            out[enc] = WORD_TESTS[enc](text, word)
        except TypeError:
            out[enc] = WORD_TESTS[enc](text)
    return out


def gost_continuation_ok(s):
    """Слово-продолжение GOST-фразы: дата/пробел/кириллица, не число."""
    if '\0' in s:
        return False
    allowed = CYR_UP | set('0123456789') | PUNCT | {' '}
    if any(c not in allowed for c in s):
        return False
    letters = sum(is_cyr(c) for c in s)
    digits = sum(c.isdigit() for c in s)
    punct = sum(c in PUNCT for c in s)
    if letters >= 2:
        return (letters + s.count(' ') + punct) / 6.0 >= 0.5
    if letters == 1:
        return False
    if punct == 0:
        if digits <= 2 and s.strip().isdigit():
            return True  # хвост штампа: год `75    `
        return False
    if digits > 4:
        return False
    if s.startswith('0') and s.count('0') >= 3:
        return False
    return True


def choose_best(word):
    """Выбор правдоподобной кодировки с приоритетом GOST > TEXT > ... ."""
    sc = score_word(word)
    for enc in ('GOST', 'TEXT', 'KOI7', 'ITM'):
        if sc[enc][0]:
            return enc, sc
    return None, sc


def run_credible(enc, pieces):
    """Фразовый уровень: словарное слово или частые диграфы."""
    text = ' '.join(p.rstrip() if enc == 'TEXT' else p for p in pieces)
    hits = known_word_hits(text)
    dg = digraph_ratio(text)
    if enc == 'TEXT':
        return (True, 'TEXT %d симв.' % len(text.replace(' ', '')), 'высокий')
    if enc == 'KOI7':
        hits = known_word_hits(koi_normalize(text))
        mn = [h for h in hits if h in MNEMONICS]
        if mn:
            return True, 'KOI-7 мнемоника:' + '+'.join(sorted(set(mn))), 'высокий'
        if len(text.replace(' ', '')) >= 4 and dg >= 0.3:
            return True, 'KOI-7 диграф=%.2f' % dg, 'средний'
        return False, 'нет мнемоники', ''
    if enc == 'ITM':
        if hits or (len(text.replace(' ', '')) >= 4 and dg >= 0.3):
            return True, 'ITM диграф=%.2f' % dg, 'низкий'
        return False, 'ITM: нет слов', ''
    # GOST: самый строгий фильтр — «почти любой байт даёт букву».
    if hits:
        return (True, 'GOST словарь:' + '+'.join(sorted(set(hits))) +
                '; диграф=%.2f' % dg, 'высокий')
    if len(text.replace(' ', '')) >= 8 and dg >= 0.35:
        return True, 'GOST диграф=%.2f' % dg, 'средний'
    return False, 'GOST: нет слов/диграфов', ''


def compact(s):
    """Сравнительная форма: только буквы и цифры, без пробелов/знаков."""
    return ''.join(c for c in s.upper() if c.isalnum())


def meaning_of(enc, phrase):
    """Смысл фразы по известным константам или по префиксу."""
    key = compact(phrase)
    for known, value in KNOWN_PHRASES.items():
        k = compact(known)
        if key == k:
            return value
        if len(key) >= 12 and len(k) >= 12 and (
                key.startswith(k) or k.startswith(key)):
            return value + ' (неполное совпадение)'
    up = phrase.upper()
    if 'ИПМ МА' in up and ('БЕМШ' in up or 'МАГ' in up):
        return 'штамп версии транслятора'
    if 'АРАП' in up:
        return 'штамп/сообщение АРАП'
    if 'МАКРОРЕДАКТОР' in up:
        return 'штамп макроредактора'
    if 'МАКРОМАШИНА' in up:
        return 'штамп макромашины'
    if 'ОШИБК' in up or 'НЕВЕРН' in up or 'НЕТ ' in up:
        return 'сообщение об ошибке'
    if 'ЗАПИС' in up:
        return 'сообщение о записи'
    if 'МЕТКА' in up or 'ОПЕРАНД' in up:
        return 'заголовок листинга'
    if enc == 'TEXT':
        return '6-битное TEXT-имя (таблица символов)'
    if enc == 'KOI7':
        return 'таблица мнемоник/текст KOI-7'
    if enc == 'ITM':
        return 'текст автокода ИТМ (гипотеза)'
    return 'предположительно текст'


# ---------------------------------------------------------------------------
# 4. Сканирование зон
# ---------------------------------------------------------------------------

def zone_files():
    files = sorted(glob.glob(os.path.join(GOLD, '*.bin')))
    return [f for f in files if 'MBE-full' not in os.path.basename(f)]


def zone_of(path):
    m = re.search(r'Z(\d{4})-L', os.path.basename(path))
    return m.group(1) if m else os.path.basename(path)


def subsystem(zone):
    """Грубая группировка зон по подсистемам (восьмеричные номера)."""
    z = int(zone, 8)
    if 0o055 <= z <= 0o060:
        return 'АСМ ИТМ'
    table = [
        (0o137, 0o146, 'БЕМШ B: ядро/загрузчик/таблицы'),
        (0o147, 0o153, 'БЕМШ B: загрузчик/АРАП'),
        (0o154, 0o157, 'БЕМШ B: макроредактор'),
        (0o160, 0o167, 'БЕМШ B: макрообработка'),
        (0o170, 0o172, 'БЕМШ B: макромашина'),
        (0o173, 0o175, 'БЕМШ B: справки/таблицы'),
        (0o176, 0o177, 'БЕМШ B: старый штамп/вывод'),
        (0o540, 0o546, 'БЕМШ B2: ядро/таблицы (копия)'),
        (0o547, 0o553, 'БЕМШ B2: загрузчик/АРАП (копия)'),
        (0o554, 0o557, 'БЕМШ B2: макроредактор (копия)'),
        (0o560, 0o567, 'БЕМШ B2: макрообработка (копия)'),
        (0o570, 0o572, 'БЕМШ B2: макромашина (копия)'),
        (0o573, 0o575, 'БЕМШ B2: справки (копия)'),
        (0o576, 0o577, 'БЕМШ B2: старый штамп/вывод (копия)'),
    ]
    for lo, hi, name in table:
        if lo <= z <= hi:
            return name
    return 'неклассифицированная зона'


def scan_zone(path):
    """Вернёт (все слова, найденные фразы) для одной зоны."""
    zone = zone_of(path)
    with open(path, 'rb') as fh:
        data = fh.read()
    if len(data) % 6:
        raise ValueError('размер зоны не кратен 6: %s' % path)
    words = []
    for i in range(len(data) // 6):
        w = word_from_bytes(data[i * 6:i * 6 + 6])
        enc, scores = choose_best(w)
        words.append({
            'zone': zone, 'idx': i, 'word': w,
            'addr': '%s.%04o' % (zone, i),
            'hex': ''.join('%02x' % b for b in bytes8(w)),
            'dec': decode_all(w), 'scores': scores, 'best': enc,
        })
    return zone, words, runs_of(words)


def runs_of(words):
    """Группировка соседних слов с одной правдоподобной кодировкой."""
    runs = []
    cur = []
    pending = []
    for w in words:
        eff = w
        if w['best'] is None and gost_continuation_ok(w['dec']['GOST']):
            pending.append(w)
            continue
        if w['best'] is None:
            if pending and cur and cur[-1]['best'] == 'GOST':
                cur.extend(dict(p, best='GOST') for p in pending)
            if cur:
                runs.append(cur)
                cur = []
            pending = []
            continue
        if w['best'] == 'GOST' and pending:
            cur = [dict(p, best='GOST') for p in pending]
            eff = dict(w, best='GOST')
        pending = []
        if cur and (cur[-1]['best'] == eff['best'] and
                    eff['idx'] == cur[-1]['idx'] + 1):
            cur.append(eff)
            continue
        if cur:
            runs.append(cur)
        cur = [eff]
    if pending and cur and cur[-1]['best'] == 'GOST':
        cur.extend(dict(p, best='GOST') for p in pending)
    if cur:
        runs.append(cur)
    out = []
    for run in runs:
        enc = run[0]['best']
        pieces = [w['dec'][enc] for w in run]
        ok, evidence, conf = run_credible(enc, pieces)
        if not ok:
            continue
        phrase = ' '.join(p.rstrip() if enc == 'TEXT' else p
                          for p in pieces).strip()
        phrase = ' '.join(phrase.replace('\0', '·').split())
        meaning = meaning_of(enc, phrase)
        if run[0]['zone'].startswith('05') and meaning.endswith(' B'):
            meaning = meaning[:-2] + ' B2'  # копия B2: та же фраза
        out.append({
            'start': run[0]['addr'], 'end': run[-1]['addr'],
            'span': len(run), 'enc': enc, 'phrase': phrase,
            'meaning': meaning,
            'evidence': evidence, 'confidence': conf,
            'words': run,
        })
    return out


def calibration_report():
    """Проверка 5 штаммов: точное совпадение GOST (identity)."""
    rows = []
    for addr, hexb, exp in CALIBRATION:
        w = word_from_bytes(int(x, 16) for x in hexb.split())
        got = decode_gost(w)
        rows.append((addr, hexb, exp, got, got == exp))
    return rows


# ---------------------------------------------------------------------------
# 5. Печать и отчёт
# ---------------------------------------------------------------------------

def render(s):
    """Печатное представление: `\0` -> `·`, пробелы сохраняем."""
    return ''.join('·' if c == '\0' else c for c in s)


def mdcell(s):
    return render(s).replace('|', '\\|').replace('\n', ' ')


def print_word_table(words):
    """Для --zone: все слова зоны во всех четырёх кодировках."""
    print('адрес       hex           GOST    KOI7    '
          'TEXT      ITM     best  G-ok T-ok K-ok I-ok')
    for w in words:
        sc = w['scores']
        flags = []
        for enc in ('GOST', 'TEXT', 'KOI7', 'ITM'):
            flags.append('+' if sc[enc][0] else '-')
        print('%-11s %-12s %-7s %-7s %-9s %-7s %-5s %s' % (
            w['addr'], w['hex'],
            mdcell(w['dec']['GOST']), mdcell(w['dec']['KOI7']),
            mdcell(w['dec']['TEXT']), mdcell(w['dec']['ITM']),
            w['best'] or '-', ' '.join(flags)))


def build_catalog(zone_reports, all_words):
    """Собирует markdown-каталог по всем зонам."""
    out = []
    add = out.append
    add('# Текстовые константы БЭСМ-6 во всех кодировках: полный каталог')
    add('')
    add('Дата: 20.11.2026. Образ: 2348 (Д-2048/2348 МГУ). '
        'Источник: `gold/*.bin`, 69 зон по 1024 слова (6 байт/слово).')
    add('Инструмент: `python3 tools/text_decode_all.py --all`. '
        'Эталонные образы не изменялись (только чтение).')
    add('')
    add('## 1. Методика')
    add('')
    add('Каждое слово разбирается в 4 кодировках сразу: **GOST-8** '
        '(побайтово, `gost_to_unicode_cyr`), **KOI-7** '
        '(`koi7_to_unicode`), **6-бит TEXT** (8 групп по 6 бит, '
        'код = ASCII−0x20), **ITM** (`itm_to_gost` → GOST).')
    add('Биасов, поворотов и обменов половин нет: калибровка даёт '
        "identity 5/5. disbesm6 печатает п'…' только для GOST-8; "
        "в'…' может быть корректным 6-битным TEXT или KOI-7.")
    add('')
    add('**Отбор.** Кириллический score сам по себе ничего не доказывает: '
        'почти любой байт 0x20…0x4D GOST даёт букву. Поэтому '
        'GOST-кандидат принимается только при словарном слове '
        '(ИПМ, МАКРО, БЕМШ, ВЕР, ВАР, ОШ, СПР, …) или '
        'частом диграфе (≥0.35), плюс отсутствие ведущих нулей и '
        'латиницы. TEXT — ≥5 печатных позиций из 8, только «уверенные» '
        'коды (dtran `is_likely_text`), ≥4 уверенных символа, анти-маска '
        'повтора >50%. KOI-7/ITM — только связная фраза целиком.')
    add('')
    add('Соседние правдоподобные слова объединяются в фразы; '
        'дубликаты по содержимому удаляются. `·` = нет глифа.')
    add('')
    add('## 2. Таблицы кодировок')
    add('')
    add('| Кодировка | Бит/симв. | Симв./слово | Источник таблицы |')
    add('|---|---:|---:|---|')
    add('| GOST-8 | 8 | 6 | encoding.cpp:36, gost10859.h |')
    add('| KOI-7 | 8 | 6 | encoding.cpp:681 (KOI-7 Н2) |')
    add('| TEXT | 6 | 8 | ASCII−0x20, re-forex docs 19/20 |')
    add('| ITM | 8 | 6 | encoding.cpp:463 (автокод Чайковского) |')
    add('')
    add('GOST-8 (кириллица): 0x00…0x09 → `0…9`, '
        '0x0A…0x0F → `+ - / , . пробел`, 0x20…0x3E → `А…Я`, '
        '0x3F…0x4D → латинские омоглифы. '
        'Байт ≥0x80 — глифа нет (`·`).')
    add('KOI-7: 0x20…0x5F — ASCII, 0x60…0x7F — кириллица '
        '(ЮАБЦДЕФГ…), 0x05…0x1F — служебные глифы. '
        'Именно KOI-7 записана таблица мнемоник в `0137.0050–0120`.')
    add('TEXT (6 бит): коды 0, 10, 15, 16–25, 29, 30, 33–58 — '
        'уверенные; остальные — управляющие. Код 0 — пробел/паддинг.')
    add('ITM: таблица разрежена; большинство байт не имеют глифа.')
    add('')
    add('## 3. Калибровка (5 штаммов, 100% совпадение)')
    add('')
    add('| адрес | байты | эталон | GOST-8 | совпадение |')
    add('|---|---|---|---|---|')
    for addr, hexb, exp, got, ok in calibration_report():
        add('| `%s` | `%s` | %s | %s | %s |' %
            (addr, hexb, exp, got, 'Да (100%)' if ok else 'НЕТ'))

    ncal = sum(r[4] for r in calibration_report())
    add('')
    add('Точных прочтений: **%d/5** при identity (никакого биаса).' % ncal)
    add('')

    # Сводка по кодировкам
    stats = Counter()
    phrases_by_enc = Counter()
    total_runs = 0
    total_undecoded = 0
    for zone, words, runs in zone_reports:
        for w in words:
            if w['best']:
                stats[w['best']] += 1
        for r in runs:
            phrases_by_enc[r['enc']] += 1
            total_runs += 1
        total_undecoded += sum(1 for w in words if w['best'] is None)

    add('## 4. Статистика')
    add('')
    add('Всего слов просканировано: **%d** (69 зон × 1024).' %
        len(all_words))
    add('')
    add('| кодировка | слов с правдоподобным прочтением | фраз |')
    add('|---|---:|---:|')
    for enc in ('GOST', 'TEXT', 'KOI7', 'ITM'):
        add('| %s | %d | %d |' % (enc, stats[enc], phrases_by_enc[enc]))
    add('')
    add('Фраз всего: **%d**. Слов без надёжного прочтения: **%d** '
        '(основная масса — машинный код и числовые таблицы).' %
        (total_runs, total_undecoded))
    add('')

    # Топ осмысленных текстов (точные совпадения с известными константами)
    top = []
    for zone, words, runs in zone_reports:
        for r in runs:
            if r['enc'] != 'GOST' or 'неполное' in r['meaning']:
                continue
            if any(k in r['meaning'] for k in
                   ('штамп', 'справк', 'сообщ', 'ошибк', 'заголов',
                    'листинг', 'записи', 'задани')):
                top.append(r)
    add('### Топ-20 осмысленных текстов с адресами')
    add('')
    add('| адрес | кодировка | фраза | смысл |')
    add('|---|---|---|---|')
    seen_top = set()
    shown = 0
    for r in sorted(top, key=lambda x: x['start']):
        if r['phrase'].upper() in seen_top or shown >= 20:
            continue
        seen_top.add(r['phrase'].upper())
        shown += 1
        add('| `%s` | %s | %s | %s |' % (
            r['start'], r['enc'], mdcell(r['phrase'])[:110], r['meaning']))
    add('')

    # Полный каталог по подсистемам
    add('## 5. Полный каталог фраз по подсистемам')
    add('')
    add('Table below is the only wide one (11 columns: 10 по требованию '
        'задания + столбец `phrase`); ширина строк >60 неизбежна. '
        '`zone.word` — физический адрес в зоне (восьмеричный номер '
        'слова). В столбцах GOST/KOI7/TEXT/ITM — прочтение первого '
        'слова фразы; `phrase` содержит всю фразу.')
    add('')
    seen = set()
    grouped = defaultdict(list)
    for zone, words, runs in zone_reports:
        for r in runs:
            grouped[subsystem(zone)].append((zone, r))
    for sub in sorted(grouped):
        add('### %s' % sub)
        add('')
        add('| zone.word | hex | GOST | KOI7 | TEXT | ITM | best | '
            'phrase | meaning | evidence | confidence |')
        add('|---|---|---|---|---|---|---|---|---|---|---|')
        rows = []
        for zone, r in grouped[sub]:
            key = (r['enc'], r['phrase'].upper())
            if key in seen:
                continue
            seen.add(key)
            w0 = r['words'][0]
            w1 = r['words'][-1]
            addr = w0['addr'] if w0['addr'] == w1['addr'] else (
                w0['addr'] + '–' + w1['addr'])
            rows.append((w0['addr'], ' | '.join([
                addr, w0['hex'], mdcell(w0['dec']['GOST']),
                mdcell(w0['dec']['KOI7']), mdcell(w0['dec']['TEXT']),
                mdcell(w0['dec']['ITM']), r['enc'],
                mdcell(r['phrase']), r['meaning'],
                r['evidence'], r['confidence']])))
        for addr, row in sorted(rows):
            add('| ' + row + ' |')
        add('')

    # Неразобранные
    add('## 6. Честный список неразобранных фрагментов')
    add('')
    add('Следующие адреса из docs/TEXT-CONSTANTS.md §6.3 остаются '
        'недешифруемыми ни одной из четырёх таблиц: это смешанные '
        'числа/коды, а не текст. Гипотеза о неправильной таблице '
        'здесь не работает (docs/TEXT-DECODING-INVESTIGATION.md §6.1).')
    add('')
    add('| адрес | пример прочтения | причина |')
    add('|---|---|---|')
    for addr, txt in [
        ('0173.1475', 'АР009А0Р009АА'),
        ('0176.0125', 'К8FV/С/-Х900'),
        ('0170.1653', '2А10+G2А20+I'),
        ('0152.0053', '4,Э7ZЦ9007ZШ9007ZЫ'),
    ]:
        add('| `%s` | %s | смешанные байты (числа + глифы) |' %
            (addr, txt))
    add('')
    add("Оговорка: disbesm6 печатает п'…' и для чисел, если все "
        '6 байт попали в «хороший» диапазон. Пример `0140.0044` '
        '(`40 00 00 09 00 00` → `F00900`) — машинное слово, не текст.')
    add('')
    add('## 7. Воспроизведение')
    add('')
    add('```bash')
    add('cd /tmp/.private/azizz/re-bemsh')
    add('python3 tools/text_decode_all.py --all')
    add('python3 tools/text_decode_all.py --zone 0147')
    add('python3 -m unittest tools/tests/test_text_decode_all.py -v')
    add('```')
    add('')
    add('Источники: docs/TEXT-CONSTANTS.md, '
        'docs/TEXT-DECODING-INVESTIGATION.md, docs/DISASM-CROSSCHECK.md, '
        'tools/text_decode_probe.py, '
        'monitor80-re/tools/encoding.cpp, re-forex docs 19/20.')
    return '\n'.join(out) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--all', action='store_true',
                   help='сканировать все 69 зон (по умолчанию)')
    g.add_argument('--zone', metavar='Z',
                   help='одна зона, восьмеричное число (например 0147)')
    ap.add_argument('--out', metavar='PATH', default=DEFAULT_OUT,
                    help='куда записать каталог markdown')
    args = ap.parse_args(argv)

    files = zone_files()
    if args.zone:
        try:
            z = int(args.zone, 8)
        except ValueError:
            ap.error('--zone должно быть восьмеричным числом')
        files = [f for f in files if zone_of(f) == '%04o' % z]
        if not files:
            ap.error('зона %04o не найдена в gold/' % z)

    reports = []
    for path in files:
        zone, words, runs = scan_zone(path)
        reports.append((zone, words, runs))
        if args.zone:
            print('=== ЗОНА %s (%s) ===' % (zone, subsystem(zone)))
            print_word_table(words)
            print()
            print('=== НАЙДЕННЫЕ ФРАЗЫ ===')
            for r in runs:
                print('%s–%s %s %s | %s | %s | %s' % (
                    r['start'], r['end'], r['enc'], r['phrase'],
                    r['meaning'], r['evidence'], r['confidence']))
            print()

    all_words = [w for _, ws, _ in reports for w in ws]
    catalog = build_catalog(reports, all_words)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(catalog)

    stats = Counter()
    phrases = Counter()
    for _, words, runs in reports:
        for w in words:
            if w['best']:
                stats[w['best']] += 1
        for r in runs:
            phrases[r['enc']] += 1
    undec = sum(1 for w in all_words if w['best'] is None)
    print('Зон: %d. Слов: %d. Каталог: %s' %
          (len(reports), len(all_words), args.out))
    print('GOST=%d TEXT=%d KOI7=%d ITM=%d; фраз=%d; неразобр.=%.1f%%' % (
        stats['GOST'], stats['TEXT'], stats['KOI7'], stats['ITM'],
        sum(phrases.values()), 100.0 * undec / max(1, len(all_words))))
    ncal = sum(r[4] for r in calibration_report())
    print('Калибровка: %d/5 точных прочтений GOST (identity).' % ncal)
    return 0


if __name__ == '__main__':
    sys.exit(main())
