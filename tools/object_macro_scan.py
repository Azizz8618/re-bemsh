#!/usr/bin/env python3
"""object_macro_scan.py -- сканер макро-команд в ОТКРЫТОМ ТЕКСТЕ объектных модулей.

Читает тома БЭСМ-6 (2048/2148/2248) через `besmtool view` в кодировках
KOI-7 / GOST-8 / TEXT / ITM, ищет в строках текста директивы и макрокоманды,
печатает дедублицированную таблицу: команда | класс | зона.слово | кодировка |
контекст.

    python3 tools/object_macro_scan.py 2248 --start-zone 3100 --end-zone 3500

Аргументы зон -- ВОСЬМЕРИЧНЫЕ (4100 = 0o4100). Эталонные тома только читаются.

Классы:
  A  МАКРО-БЕМШ / MACRO-STEM (каталог macros.be, 37 позиций, ∧-параметры);
  B  другой ассемблер (MASM / MACRO-32: MACRO…ENDM, EQU, DB, STRUC, …);
  C  неопределённо (короткий токен,wares сообщение, другой язык: FORTRAN и т.п.).

Скрипт НЕ делает выводов о полноте каталога -- он только печатает факты
(адрес, кодировка, контекст). Интерпретация -- в docs/OBJECT-MODULE-MACROS.md.
"""

import argparse
import itertools
import re
import subprocess
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# 1. Словарь команд. Класс A = МАКРО-БЕМШ, B = MASM/MACRO-32, C = неясно.
#    Для коротких токенов (<=3) нужен сильный контекст, иначе шум.
# ---------------------------------------------------------------------------
VOCAB = {
    # --- A: МАКРО-БЕМШ (macros.be, написания сохранены как в OCR) ----------
    "MACRO":   ("A", "МАСRО -- начало макроопределения"),
    "MEND":    ("A", "МЕND -- конец макроопределения"),
    "FINISH":  ("A", "ФИНИШ -- конец файла макрокоманд"),
    "GBLA":    ("A", "GВLА -- глобальная арифметическая переменная"),
    "GBLB":    ("A", "GВLВ -- глобальная булева переменная"),
    "LCLA":    ("A", "LСLА -- локальная арифметическая переменная"),
    "SETA":    ("A", "SЕТА -- присваивание арифметической переменной"),
    "SETB":    ("A", "SЕТВ -- присваивание булевой переменной"),
    "AIF":     ("A", "АIF -- условная ветка макромашины"),
    "EQ":      ("A", "ЕQ -- оператор равенства в АIF"),
    "NE":      ("A", "NЕ -- оператор неравенства в АIF"),
    "OR":      ("A", "ОR -- логическое ИЛИ в АIF"),
    "EQV":     ("A", "ЭКВ -- эквивалент макромашины"),
    "EQVI":    ("A", "ЭКВИВ -- векторный ЭКВ"),
    "VNESH":   ("A", "ВНЕШ -- внешний символ модуля"),
    "VNESHN":  ("A", "ВНЕШН -- внешний символ (норма/диапазон)"),
    "VNESHB":  ("A", "ВНЕШБ -- условный ВНЕШ (∧ВS=1)"),
    "VNESHS":  ("A", "ВНЕШС -- условный ВНЕШ (∧ВS=0)"),
    "EVNESH":  ("A", "ЕВНЕШ -- внешний символ E-префикса"),
    "VHOD":    ("A", "ВХОД -- входная точка модуля"),
    "VHODN":   ("A", "ВХОДН -- одна входная точка"),
    "VHodb":   ("A", "ВХОДБ -- условный ВХОД (∧ВS=1)"),
    "VHODS":   ("A", "ВХОДС -- условный ВХОД (∧ВS=0)"),
    "KOND":    ("A", "КОНД -- условная вставка слова/данных"),
    "KONDB":   ("A", "КОНДБ -- условный КОНД (∧ВS=1)"),
    "KONDS":   ("A", "КОНДС -- условный КОНД (∧ВS=0)"),
    "ANOP":    ("A", "АНОП/АNОР -- пустая операция в теле макроса"),
    "DK":      ("A", "DК -- макрос извлечения кода"),
    "MNOTE":   ("A", "МNОТЕ -- директива комментария"),
    "PV":      ("A", "ПВ -- машинная команда 'пересылка в'"),
    "UIA":     ("A", "УИА -- машинная команда 'установить индекс/адрес'"),
    "PB":      ("A", "ПБ -- машинная команда 'переход'"),
    "NOP":     ("A", "НОП -- аппаратная 'нет операции'"),
    "TEXT":    ("A", "ТЕКСТ -- вывод текстовой константы"),
    "XHEX":    ("A", "Х'...' -- вывод 16-ричного слова"),
    # --- A2: machine/assembler directives, видимые в листинге БЕМШ --------
    "EQU":     ("A2", "ЭКВ -- эквивалент АРАП (машинный уровень)"),
    "CNC":     ("A2", "КНЦ -- конец (директива ассемблера БЕМШ)"),
    "PAM":     ("A2", "ПАМ -- директива памяти"),
    "ADRES":   ("A2", "АДРЕК/АДРЕС -- адресная директива"),
    "UPOT":    ("A2", "УПОТ -- директива использования"),
    "OTMEM":   ("A2", "ОТМЕМ -- директива отмены/снятия"),
    "STROP":   ("A2", "СТРОП -- директива (строка/оператор)"),
    "STRNH":   ("A2", "СТРНХ -- директива (структура/настройка)"),
    "STAR":    ("A2", "СТАР -- директива старта"),
    "KONK":    ("A2", "КОНК -- директива конкретизации"),
    "SCHI":    ("A2", "СЧИ -- машинная команда (счётчик)"),
    "E70":     ("A2", "Э70 -- машинная команда/макрос"),
    "PNCH":    ("A2", "ПНЧ -- машинная команда (печать)"),
    "SDA":     ("A2", "СДА -- машинная команда (сдача)"),
    "KVCH":    ("A2", "КВЧ -- терминатор задания (КВЧ)"),
    "TRN":     ("A2", "ТРН -- терминатор (трансляция)"),
    "BTMALF":  ("A2", "БТМАЛФ -- служебное слово ДИСПАК"),
    # --- B: MASM / MACRO-32 ------------------------------------------------
    "MACRO32": ("B", "MACRO -- начало макроопределения MASM"),
    "ENDM":    ("B", "ENDM -- конец макроопределения MASM"),
    "REPT":    ("B", "REPT -- повторение (MASM)"),
    "IRP":     ("B", "IRP -- параметрический цикл (MASM)"),
    "IRPC":    ("B", "IRPC -- цикл по символам (MASM)"),
    "IF":      ("B", "IF -- условная сборка (MASM/FORTRAN)"),
    "IFE":     ("B", "IFE -- IF false (MASM)"),
    "IFDEF":   ("B", "IFDEF -- если определено (MASM)"),
    "IFNDEF":  ("B", "IFNDEF -- если не определено (MASM)"),
    "IFB":     ("B", "IFB -- если пусто (MASM)"),
    "IFNB":    ("B", "IFNB -- если не пусто (MASM)"),
    "IFIDN":   ("B", "IFIDN -- сравнение строк (MASM)"),
    "IFDIF":   ("B", "IFDIF -- сравнение строк (MASM)"),
    "ENDIF":   ("B", "ENDIF -- конец условия (MASM)"),
    "ELSE":    ("B", "ELSE -- иначе (MASM)"),
    "EXITM":   ("B", "EXITM -- выход из макроса (MASM)"),
    "DB":      ("B", "DB --.define byte (MASM)"),
    "DW":      ("B", "DW -- define word (MASM)"),
    "DD":      ("B", "DD -- define doubleword (MASM)"),
    "DQ":      ("B", "DQ -- define quadword (MASM)"),
    "DT":      ("B", "DT -- define tenbytes (MASM)"),
    "DUP":     ("B", "DUP -- дублирование (MASM)"),
    "STRUC":   ("B", "STRUC -- структура (MASM)"),
    "STRUCT":  ("B", "STRUCT -- структура (MASM)"),
    "ENDS":    ("B", "ENDS -- конец сегмента/структуры (MASM)"),
    "UNION":   ("B", "UNION -- объединение (MASM)"),
    "ENDU":    ("B", "ENDU -- конец объединения (MASM)"),
    "SEGMENT": ("B", "SEGMENT -- сегмент (MASM)"),
    "PROC":    ("B", "PROC -- процедура (MASM)"),
    "ENDP":    ("B", "ENDP -- конец процедуры (MASM)"),
    "ASSUME":  ("B", "ASSUME -- назначение сегментных регистров (MASM)"),
    "PUBLIC":  ("B", "PUBLIC -- экспорт символа (MASM)"),
    "EXTRN":   ("B", "EXTRN -- внешний символ (MASM)"),
    "EXTERN":  ("B", "EXTERN -- внешний символ (MASM)"),
    "GROUP":   ("B", "GROUP -- группа сегментов (MASM)"),
    "PAGE":    ("B", "PAGE -- разрыв страницы листинга (MASM)"),
    "SUBTTL":  ("B", "SUBTTL -- подзаголовок (MASM)"),
    "TITLE":   ("B", "TITLE -- заголовок (MASM)"),
    "INCLUDE": ("B", "INCLUDE -- включение файла (MASM)"),
    "LOCAL":   ("B", "LOCAL -- локальный символ макроса (MASM)"),
    "OPTION":  ("B", "OPTION -- опция (MASM)"),
    "OFFSET":  ("B", "OFFSET -- смещение (MASM)"),
    "PTR":     ("B", "PTR -- указатель типа (MASM)"),
    "SHORT":   ("B", "SHORT -- короткий переход (MASM)"),
    "TYPE":    ("B", "TYPE -- тип (MASM)"),
    "SIZE":    ("B", "SIZE -- размер (MASM)"),
    "LENGTH":  ("B", "LENGTH -- длина (MASM)"),
    "PUSH":    ("B", "PUSH -- машинная команда (8086)"),
    "POP":     ("B", "POP -- машинная команда (8086)"),
    "MOV":     ("B", "MOV -- машинная команда (8086)"),
    "CALL":    ("B", "CALL -- вызов (8086/FORTRAN)"),
    "LEA":     ("B", "LEA -- загрузка адреса (8086)"),
    "ADD":     ("B", "ADD -- сложение (8086)"),
    "SUB":     ("B", "SUB -- вычитание (8086)"),
    "CMP":     ("B", "CMP -- сравнение (8086)"),
    "JMP":     ("B", "JMP -- переход (8086)"),
    "RET":     ("B", "RET -- возврат (8086)"),
}

# Омоглифы: кириллица <-> латиница. Ключ -- каноническая латиница.
HOMO = {
    "A": "AА", "B": "BВ", "C": "CС", "D": "DД", "E": "EЕ", "F": "FФ",
    "G": "GГ", "H": "HН", "I": "IИ", "K": "KК", "L": "LЛ", "M": "MМ",
    "N": "NН", "O": "OО", "P": "PРП", "R": "RР", "S": "SС", "T": "TТ",
    "U": "UУ", "X": "XХ", "Y": "YУ", "Z": "ZЗ",
}

# Специальные написания, которые не выводятся простой подстановкой.
EXTRA_VARIANTS = {
    "NOP":     ["НОП", "NОП", "АНОП", "АNОР", "НОР"],
    "MACRO":   ["МАСRО", "MACRO", "МАСРО"],
    "MEND":    ["МЕND", "MEND", "МЕНД"],
    "FINISH":  ["ФИНИШ"],
    "SETA":    ["SЕТА", "СЕТА", "SETA"],
    "SETB":    ["SЕТВ", "СЕТВ", "SETB"],
    "GBLA":    ["GВLА", "ГВЛА", "GBLA"],
    "GBLB":    ["GВLВ", "ГВЛВ", "GBLB"],
    "LCLA":    ["LСLА", "ЛСЛА", "LCLA"],
    "AIF":     ["АIF", "AIF", "АИФ"],
    "EQV":     ["ЭКВ", "ЭKV", "EQV"],
    "EQVI":    ["ЭКВИВ", "ЭKVIV"],
    "VNESH":   ["ВНЕШ"],
    "VNESHN":  ["ВНЕШН"],
    "VNESHB":  ["ВНЕШБ"],
    "VNESHS":  ["ВНЕШС"],
    "EVNESH":  ["ЕВНЕШ"],
    "VHOD":    ["ВХОД"],
    "VHODN":   ["ВХОДН"],
    "VHodb":   ["ВХОДБ"],
    "VHODS":   ["ВХОДС"],
    "KOND":    ["КОНД"],
    "KONDB":   ["КОНДБ"],
    "KONDS":   ["КОНДС"],
    "MNOTE":   ["МNОТЕ", "МНоте"],
    "DK":      ["DК", "ДК", "DK"],
    "PV":      ["ПВ", "PV"],
    "UIA":     ["УИА", "UIA"],
    "PB":      ["ПБ", "PB"],
    "TEXT":    ["ТЕКСТ", "TEXT"],
    "XHEX":    ["Х'", "X'"],
    "CNC":     ["КНЦ"],
    "PAM":     ["ПАМ"],
    "ADRES":   ["АДРЕК", "АДРЕС"],
    "UPOT":    ["УПОТ"],
    "OTMEM":   ["ОТМЕМ"],
    "STROP":   ["СТРОП", "СТРО"],
    "STRNH":   ["СТРНХ", "СТРН"],
    "STAR":    ["СТАР"],
    "KONK":    ["КОНК"],
    "SCHI":    ["СЧИ"],
    "E70":     ["Э70", "E70"],
    "PNCH":    ["ПНЧ"],
    "SDA":     ["СДА"],
    "KVCH":    ["КВЧ"],
    "TRN":     ["ТРН", "TRN"],
    "BTMALF":  ["БТМАЛФ"],
    "EQ":      ["ЕQ", "EQ", "ЕКВ"],
    "NE":      ["NЕ", "НЕ", "NE"],
    "OR":      ["ОR", "ОР", "OR"],
}


def build_patterns():
    """Строит regex для каждого канонического токена с учётом омоглифов."""
    patterns = {}
    for canon in VOCAB:
        variants = set(EXTRA_VARIANTS.get(canon, []))
        if canon not in EXTRA_VARIANTS:
            # генерация омоглифных вариантов (декартово произведение, лимит)
            letters = []
            ok = True
            for ch in canon:
                up = ch.upper()
                if up in HOMO:
                    letters.append(HOMO[up])
                elif up.isalpha():
                    letters.append(up)
                else:
                    ok = False
                    break
            if ok and len(letters) <= 9:
                for combo in itertools.product(*letters):
                    variants.add("".join(combo))
        variants = {v for v in variants if v}
        if not variants:
            continue
        # сортируем по убыванию длины, чтобы 'ENDM' не перехватывалось 'END'
        alt = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
        patterns[canon] = re.compile(r"(?<![A-Za-zА-Яа-я])(" + alt + r")(?![A-Za-zА-Яа-я])")
    return patterns


# Маркеры сильного контекста: строка -- действительно текст макроопределения.
MARKERS = ("MACRO", "ENDM", "MEND", "∧", "&", "!",
           "EQUATES", "DEFINITIONS", "MACRO-32", "SOURCE", "ASSEMBLER",
           "Й00", "П'", "Э70", "КВЧ", "ТРН", "SЕТА", "ЕQUАТЕS")

# Маркеры контекста MASM/MACRO-32 (класс B) и листинга БЕМШ (класс A/A2).
MASM_MARK = ("!", "SEGMENT", "STRUC", "STRUCT", "PROC", "ENDP", "ASSUME",
             "PUBLIC", "EXTRN", "GROUP", "OFFSET", "PTR", "SUBTTL",
             "DS:", "CS:", "PARA", "DB", "DW", "EQU", "MACRO-32")
BEMSH_MARK = ("Й00", "П'", "Э70", "КВЧ", "ТРН", "SЕТА", "ВНЕШ", "ВХОД",
              "ЭКВ", "∧", "FIELD", "СЧИ", "УИА")

LINE_RE = re.compile(r"^(\d{4})\.(\d{4}):\s?(.*)$")
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9']+")


def classify_context(text, canon):
    """Классhit-а по контексту строки. Не смешиваем B и A."""
    up = text.upper()
    masm = sum(1 for m in MASM_MARK if m in up)
    bemsh = sum(1 for m in BEMSH_MARK if m in up)
    base = VOCAB[canon][0]
    if masm > bemsh and masm >= 1:
        return "B" if base in ("A", "A2", "B") else base
    if bemsh > masm and bemsh >= 1:
        return base if base in ("A", "A2") else ("A2" if base == "B" else base)
    if masm and bemsh:
        return "C"
    return base


def run_view(disk, zone, length, enc):
    """Вызывает besmtool view для диапазона зон; Возвращает список строк."""
    # besmtool парсит --start через strtol(base=0): ведущий 0 = восьмеричное.
    cmd = ["besmtool", "view", disk,
           "--start=0" + format(zone, "04o"),
           "--length=" + str(length),
           "--encoding=" + enc]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print("timeout: " + " ".join(cmd), file=sys.stderr)
        return []
    return p.stdout.splitlines()


def scan(disk, start, end, encs, chunk):
    patterns = build_patterns()
    # hit: canon -> list of (class, zone.word, enc, context, strong)
    hits = defaultdict(list)
    for enc in encs:
        z = start
        while z <= end:
            length = min(chunk, end - z + 1)
            for line in run_view(disk, z, length, enc):
                m = LINE_RE.match(line)
                if not m:
                    continue
                zone_s, word_s, text = m.groups()
                strong = any(mk.lower() in text.lower() for mk in MARKERS)
                addr = zone_s + "." + word_s
                # ищем каждый токен отдельно (перекрытия допустимы)
                for canon, rx in patterns.items():
                    mm = rx.search(text)
                    if mm:
                        cls = classify_context(text, canon)
                        ctx = text.strip()
                        if len(ctx) > 60:
                            ctx = ctx[:60] + "*"
                        key = (cls, addr, enc, ctx, strong)
                        if key not in hits[canon]:
                            hits[canon].append(key)
            z += length
    return hits


def print_table(disk, start, end, hits, min_conf):
    print("# Сканер макро-команд в открытом тексте: том {}, зоны {:04o}-{:04o}".format(
        disk, start, end))
    print("# Классы: A=МАКРО-БЕМШ(catalog), A2=уровень АРАП, B=MASM/MACRO-32, C=неясно")
    print()
    order = {"A": 0, "A2": 1, "B": 2, "C": 3}
    rows = []
    for canon, hs in hits.items():
        # класс -- большинство по контексту; при равенстве -- избыточный
        from collections import Counter
        cnt = Counter(h[0] for h in hs)
        cls = max(cnt, key=lambda c: (cnt[c], -order.get(c, 9)))
        # лучший пример: с сильным контекстом и совпадающим классом
        cand = [h for h in hs if h[4] and h[0] == cls] or [h for h in hs if h[0] == cls] or hs
        best = cand[0]
        n = len(hs)
        rows.append((order.get(cls, 9), canon, cls, n, best))
    rows.sort()
    print("{:<10} {:<4} {:>5}  {:<12} {:<2} {:<60}".format(
        "команда", "кл.", "н.адр", "адрес", "к", "контекст"))
    print("-" * 100)
    for _, canon, cls, n, best in rows:
        _, addr, enc, ctx, _ = best
        print("{:<10} {:<4} {:>5}  {:<12} {:<2} {:<60}".format(
            canon, cls, n, addr, enc[0], ctx))
    print()
    print("Всего различных команд: {}".format(len(rows)))
    for cls in ("A", "A2", "B", "C"):
        c = sum(1 for r in rows if r[2] == cls)
        if c:
            print("  класс {}: {}".format(cls, c))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("disk", help="номер тома (2048, 2148, 2248)")
    ap.add_argument("--start-zone", default="0", help="начальная зона, ВОСЬМЕРИЧНОЕ (по умолчанию 0)")
    ap.add_argument("--end-zone", default="7777", help="конечная зона, ВОСЬМЕРИЧНОЕ (по умолчанию 7777)")
    ap.add_argument("--enc", default="k,g", help="кодировки через запятую: k,g,t,i (по умолчанию k,g)")
    ap.add_argument("--chunk", type=int, default=64, help="зон за один вызов besmtool view (по умолчанию 64)")
    ap.add_argument("--min-len", type=int, default=2, help="минимальная длина токена (по умолчанию 2)")
    args = ap.parse_args()

    start = int(args.start_zone, 8)
    end = int(args.end_zone, 8)
    encs = [e.strip() for e in args.enc.split(",") if e.strip()]
    if start > end:
        ap.error("--start-zone должен быть <= --end-zone")

    hits = scan(args.disk, start, end, encs, args.chunk)
    # отсечь короткие токены без сильного контекста
    for canon in list(hits):
        hs = [h for h in hits[canon]
              if len(canon) >= args.min_len or h[4]]
        if hs:
            hits[canon] = hs
        else:
            del hits[canon]
    print_table(args.disk, start, end, hits, args.min_len)


if __name__ == "__main__":
    main()
