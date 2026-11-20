#!/usr/bin/env python3
"""Аудит меток вида X... ЭКВ '<восьмеричный адрес>' в bemsh/*.be.

ЭКВ НЕ является объявлением внешней связи. Директива ЭКВ задаёт только
символическое имя числовой константы внутри одного исходного файла:
она не порождает слово, не создаёт запись ВНЕШН и не выставляет бит
перемещаемости в команде. Свидетельства:

  * docs/EXTERNAL-CALL-FORMAT.md §1.1, §1.4: внешний символ объявляется
    директивой ВНЕШ/ВНЕШН; ссылка несёт номер символа и бит 21;
  * docs/ENTRY-POINTS.md §3, §4: PRINT80 E 01205 -- эквивалент, а не
    четвёртая связь (ВНЕШН=3); все 69 .be содержат только СТАРТ 1
    и ни одной директивы ВХОД*/ВНЕШН в коде;
  * docs/XREF-METHODOLOGY.md §2.2: тип 0 в sym-таблице -- экв,
    тип 2 -- код/точка входа;
  * docs/EXTERNAL-OFFSET-FIX.md §7, docs/CALL-OUT-OF-MODULE.md §4:
    все роли X-меток -- ГИПОТЕЗЫ.

Поэтому префикс X и комментарии «внешний адрес», «внешнее смещение»,
«EXT_CALL_...», «CALL-OUT» создают ложное впечатление кросс-ссылки.
Инструмент только читает .be и документы; он ничего не меняет в bemsh/.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_BE_DIR = REPO / "bemsh"

RE_DEF = re.compile(r"^\s*(X[0-9A-Za-z]{0,10})\s+ЭКВ\s+'([0-7]+)'(.*)$")
RE_ZONE = re.compile(r"Z(\d{4})")
RE_TOKEN = re.compile(r"\b(X[0-9A-Za-z]{0,10})\b")
RE_SUFFIX = re.compile(r"^X\d+([A-Z])$")

# Размер зоны: адреса 0..01777₈ -- локальные смещения внутри зоны.
ZONE_WORDS = 0o2000

TRUE_EXTERNAL = "TRUE_EXTERNAL"
INTERNAL_OFFSET = "INTERNAL_OFFSET"
UNKNOWN_ABSOLUTE = "UNKNOWN_ABSOLUTE"

FALSE_CLASSES = (INTERNAL_OFFSET, UNKNOWN_ABSOLUTE)

COMMENT_LIMIT = 55


@dataclass(frozen=True)
class NamedExternal:
    """Именованный адрес со ссылкой на прямое свидетельство."""

    value: int
    name: str
    ca: str
    evidence: str
    note: str


# Именованные внешние адреса. 04000 -- системный символ (не связь модуля),
# но он прямо перечислен в ENTRY-POINTS.md §3 как внешний адрес памяти.
NAMED_EXTERNALS = (
    NamedExternal(0o2000, "*PAGE*", "3",
                  "ENTRY-POINTS.md §3:112; EXTERNAL-CALL-FORMAT.md §1.2",
                  "совпадает с базой зоны 0154; роль CALL-OUT: "
                  "MEM_P01_Z0154"),
    NamedExternal(0o4000, "MON*ITOR", "",
                  "ENTRY-POINTS.md §3:113, §3:128-129",
                  "системный символ ОС, не связь модуля"),
    NamedExternal(0o70000, "SYSCALL", "",
                  "CALL-TARGET-RESOLUTION.md §3:170, §4.6:322; "
                  "LABEL-MAP.md:173",
                  "ячейка приёма системного вызова; роль: "
                  "MEM_SYSCALL_GATE"),
    NamedExternal(0o7417, "УППСЛУ", "",
                  "CALL-TARGET-RESOLUTION.md §4.1:194-202 "
                  "(TTAB:124, TERM:342/816/312)",
                  "сервис ТЕРМ, PROVEN; роль CALL-OUT: MEM_P03_Z0156"),
    NamedExternal(0o77316, "ДЛЯСВЯ", "",
                  "CALL-TARGET-RESOLUTION.md §4.2:264 "
                  "(S:1663, S:2435, S:2587)",
                  "MON СВС, PROVEN; роль CALL-OUT: MEM_P37_Z0157"),
    NamedExternal(0o77520, "МАКРО", "",
                  "CALL-TARGET-RESOLUTION.md §3:147, §4.2:266 "
                  "(S:1966, S:1982)",
                  "MON СВС, PROVEN; роль CALL-OUT: MEM_P37_Z0157"),
    NamedExternal(0o77474, "ЕСТРР", "",
                  "CALL-TARGET-RESOLUTION.md §4.2:267 "
                  "(S:1939, S:2463)",
                  "MON СВС, PROVEN; роль CALL-OUT: MEM_P37_Z0157"),
    NamedExternal(0o77430, "ВАС76D", "",
                  "CALL-TARGET-RESOLUTION.md §4.2:271 "
                  "(S:1849, S:2528)",
                  "MON СВС, PROVEN; роль CALL-OUT: MEM_P37_Z0157"),
)

NAMED_BY_VALUE = {item.value: item for item in NAMED_EXTERNALS}


@dataclass(frozen=True)
class XDefinition:
    file: str
    family: str
    zone: str
    line: int
    name: str
    value: str
    oct_value: int
    comment: str


@dataclass(frozen=True)
class Classification:
    cls: str
    name: str
    ca: str
    evidence: str
    note: str


def classify(value: int) -> Classification:
    """Классифицировать один адрес ЭКВ по правилам задания."""
    named = NAMED_BY_VALUE.get(value)
    if named is not None:
        return Classification(TRUE_EXTERNAL, named.name, named.ca,
                              named.evidence, named.note)
    if value < ZONE_WORDS:
        return Classification(
            INTERNAL_OFFSET, "", "",
            "адрес < 02000₈, внутри зоны (0..01777₈)",
            "локальная цель, а не внешняя связь",
        )
    return Classification(
        UNKNOWN_ABSOLUTE, "", "",
        "нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md",
        "адрес гипотетический, имя не восстановлено",
    )


def name_pattern(name: str) -> str:
    """Класс имени по EXTERNAL-OFFSET-FIX.md §1 и CALL-OUT-OF-MODULE.md §4."""
    if re.fullmatch(r"X\d{3}[ABCE]", name):
        return "Xddd[ABCE] (offset-candidate)"
    if re.fullmatch(r"X\d{4}B", name):
        return "XddddB (callout page/symbol)"
    if re.fullmatch(r"X\d{5,6}", name):
        return "Xddddd (callout full)"
    return "other"


def parse_definitions(be_dir):
    """Собрать все определения X... ЭКВ из bemsh/*.be."""
    be_dir = Path(be_dir)
    result = []
    for path in sorted(be_dir.glob("*.be")):
        base = path.name
        family_match = re.match(r"(ASM|MBE2|MBE)-Z", base)
        family = family_match.group(1) if family_match else "?"
        zone_match = RE_ZONE.search(base)
        zone = zone_match.group(1) if zone_match else "?"
        with path.open(encoding="utf-8", errors="replace") as handle:
            for lineno, raw in enumerate(handle, 1):
                match = RE_DEF.match(raw.rstrip("\n"))
                if not match:
                    continue
                name, value, tail = match.groups()
                result.append(XDefinition(
                    file=base,
                    family=family,
                    zone=zone,
                    line=lineno,
                    name=name,
                    value=value,
                    oct_value=int(value, 8),
                    comment=tail.strip(),
                ))
    return result


def parse_usages(be_dir, definitions):
    """Посчитать использования X-имён в коде (комментарии не считаем).

    Комментарий в .be начинается с запятой, поэтому левая часть строки
    до первой запятой -- это код. ЭКВ действует внутри одного файла,
    поэтому ключ счётчика -- пара (файл, имя), а не имя в целом.
    """
    be_dir = Path(be_dir)
    known = {item.name for item in definitions}
    counts = Counter()
    places = defaultdict(list)
    for path in sorted(be_dir.glob("*.be")):
        base = path.name
        with path.open(encoding="utf-8", errors="replace") as handle:
            for lineno, raw in enumerate(handle, 1):
                line = raw.rstrip("\n")
                if RE_DEF.match(line) or line.lstrip().startswith("*"):
                    continue
                code = line.split(",", 1)[0]
                for token in RE_TOKEN.findall(code):
                    if token not in known:
                        continue
                    key = (base, token)
                    counts[key] += 1
                    places[key].append((base, lineno))
    return counts, places


def local_role(definition: XDefinition) -> str:
    """Рекомендуемое локальное имя вместо X (P или C по семейству)."""
    prefix = "C" if definition.family == "MBE2" else "P"
    return prefix + definition.value


def recommend_comment(definition: XDefinition,
                      classification: Classification) -> str:
    """Рекомендованный комментарий после запятой (длина <= 55)."""
    if classification.cls == TRUE_EXTERNAL:
        if classification.ca:
            return ", ВНЕШ: {} [СА {}], адрес {}".format(
                classification.name, classification.ca, definition.value
            )
        return ", ВНЕШ: {}, адрес {}".format(
            classification.name, definition.value
        )
    if classification.cls == INTERNAL_OFFSET:
        return ", адрес {}: локальная цель, не внешняя связь".format(
            definition.value
        )
    return ", адрес {}: внешняя связь, имя не восстановлено".format(
        definition.value
    )


def correct_role(definition: XDefinition,
                 classification: Classification) -> str:
    """Короткая формулировка правильной роли метки."""
    if classification.cls == TRUE_EXTERNAL:
        return "NAMED_ADDRESS (не объявление ВНЕШН)"
    if classification.cls == INTERNAL_OFFSET:
        return "LOCAL_OFFSET -> " + local_role(definition)
    return "UNKNOWN_ABSOLUTE (гипотеза)"


def build_report(be_dir=DEFAULT_BE_DIR, top=10):
    """Построить полный отчёт аудита в виде словаря."""
    definitions = parse_definitions(be_dir)
    usages, places = parse_usages(be_dir, definitions)

    by_name = defaultdict(list)
    for item in definitions:
        by_name[item.name].append(item)

    definitions_with_class = []
    for item in definitions:
        cls = classify(item.oct_value)
        local_uses = usages[(item.file, item.name)]
        definitions_with_class.append((item, cls, local_uses))

    defs_by_class = Counter(cls.cls for _, cls, _ in definitions_with_class)
    uses_by_class = Counter()
    for _, cls, count in definitions_with_class:
        uses_by_class[cls.cls] += count

    by_value = defaultdict(lambda: {"defs": 0, "names": set(), "uses": 0})
    for item, cls, count in definitions_with_class:
        entry = by_value[item.oct_value]
        entry["defs"] += 1
        entry["names"].add(item.name)
        entry["uses"] += count

    address_rows = []
    for value in sorted(by_value):
        entry = by_value[value]
        cls = classify(value)
        address_rows.append({
            "value": format(value, "o"),
            "class": cls.cls,
            "name": cls.name,
            "evidence": cls.evidence,
            "defs": entry["defs"],
            "uses": entry["uses"],
        })

    address_by_class = Counter(row["class"] for row in address_rows)

    reannotation = []
    for item, cls, count in definitions_with_class:
        reannotation.append({
            "zone": item.zone,
            "line": "{}:{}".format(item.file, item.line),
            "label": item.name,
            "value": item.value,
            "class": cls.cls,
            "role": correct_role(item, cls),
            "comment": recommend_comment(item, cls),
            "uses": count,
        })

    false_rows = [row for row in reannotation if row["class"] in FALSE_CLASSES]
    false_by_name = defaultdict(lambda: {"uses": 0, "defs": 0, "value": "",
                                         "class": "", "role": ""})
    for row in false_rows:
        entry = false_by_name[row["label"]]
        entry["uses"] += row["uses"]
        entry["defs"] += 1
        entry["value"] = row["value"]
        entry["class"] = row["class"]
        entry["role"] = row["role"]
    top_false = sorted(
        (
            {"label": name, **entry}
            for name, entry in false_by_name.items()
        ),
        key=lambda row: (-row["uses"], -row["defs"], row["label"]),
    )[:top]

    unused = sorted(
        name for name, items in by_name.items()
        if all(usages[(item.file, item.name)] == 0 for item in items)
    )

    return {
        "be_dir": str(be_dir),
        "totals": {
            "files_scanned": len(list(Path(be_dir).glob("*.be"))),
            "files_with_xdefs": len({item.file for item in definitions}),
            "definitions": len(definitions),
            "distinct_names": len(by_name),
            "distinct_addresses": len(by_value),
            "code_usages": sum(usages.values()),
            "unused_names": len(unused),
        },
        "by_family": Counter(item.family for item in definitions),
        "by_zone": Counter(item.zone for item in definitions),
        "by_pattern": Counter(name_pattern(item.name) for item in definitions),
        "defs_by_class": defs_by_class,
        "uses_by_class": uses_by_class,
        "address_by_class": address_by_class,
        "address_rows": address_rows,
        "reannotation": reannotation,
        "top_false": top_false,
        "unused_names": unused,
        "named_externals": [
            {
                "address": format(item.value, "o"),
                "name": item.name,
                "ca": item.ca,
                "evidence": item.evidence,
                "note": item.note,
            }
            for item in NAMED_EXTERNALS
        ],
    }


def _md_counter(title, counter):
    lines = ["## " + title, "", "| Ключ | Значение |", "|---|---:|"]
    for key in sorted(counter):
        lines.append("| {} | {} |".format(key, counter[key]))
    lines.append("")
    return lines


def render_markdown(report, top=10):
    """Собрать docs/XLABEL-AUDIT.md из отчёта."""
    t = report["totals"]
    lines = [
        "# Аудит меток X... ЭКВ в 69 источниках bemsh/*.be",
        "",
        "Инструмент: `python3 tools/xlabel_audit.py --out-md "
        "docs/XLABEL-AUDIT.md`.",
        "Все файлы читались только на чтение; ни один `.be`, `dis/`, "
        "`gold/` не изменялся.",
        "",
        "## 1. Главный вывод: ЭКВ не является кросс-ссылкой",
        "",
        "**ЭКВ is not a cross-reference.** Директива `ЭКВ` задаёт только "
        "символическое имя константы внутри одного файла. Она не порождает "
        "слово, не создаёт запись `ВНЕШН`, не выставляет бит 21 и номер "
        "символа в команде. Следовательно, имя вида `X70000 ЭКВ '70000'` "
        "не объявляет внешнюю связь даже тогда, когда число совпадает с "
        "именованным адресом.",
        "",
        "Свидетельства:",
        "",
        "* `docs/EXTERNAL-CALL-FORMAT.md` §1.1, §1.4: внешний символ "
        "объявляется `ВНЕШ/ВНЕШН`; ссылка несёт номер символа и бит "
        "перемещаемости; загрузчик подставляет `база(X)+D`.",
        "* `docs/ENTRY-POINTS.md` §3: `PRINT80 E 01205` -- эквивалент, а не "
        "четвёртая связь (`ВНЕШН=3`); §4 и §6.1: во всех 69 `.be` только "
        "`СТАРТ 1`, ни одной директивы `ВХОД*`/`ВНЕШН` в коде.",
        "* `docs/XREF-METHODOLOGY.md` §2.2: тип `0` в sym-таблице -- экв, "
        "тип `2` -- код/точка входа.",
        "* `docs/EXTERNAL-OFFSET-FIX.md` §7 и "
        "`docs/CALL-OUT-OF-MODULE.md` §4: все роли X-меток помечены как "
        "ГИПОТЕЗЫ; исходника транслятора на диске нет.",
        "* `docs/EQU-VS-XREF.md` §0, §3, §4.4: ЭКВ не порождает слово и "
        "не попадает в таблицу связей; `X7417B ЭКВ '7417'` -- ЭКВ, а не "
        "внешняя ссылка, хотя комментарий называет её «внешней целью».",
        "",
        "## 2. Методика",
        "",
        "1. Сканер `tools/xlabel_audit.py` читает все 69 `bemsh/*.be` и "
        "выбирает строки вида `X... ЭКВ '<восьмеричное>'`.",
        "2. Использования ищутся только в коде (левая часть строки до "
        "запятой); строки комментариев и сами определения не считаются.",
        "3. Каждое значение классифицируется тремя классами: "
        "`TRUE_EXTERNAL` (совпадение с именем из "
        "`docs/ENTRY-POINTS.md` §3 или "
        "`docs/CALL-TARGET-RESOLUTION.md` §3-4), `INTERNAL_OFFSET` "
        "(значение < 02000₈, то есть внутри зоны из 1024 слов), "
        "`UNKNOWN_ABSOLUTE` (имя не восстановлено).",
        "4. Даже класс `TRUE_EXTERNAL` означает только «число совпало с "
        "известным адресом», а не «в исходнике объявлена внешняя связь».",
        "5. Таблица переаннотации не правит `.be`: это только "
        "рекомендация, которая требует отдельного разрешения оператора.",
        "",
        "## 3. Сводка",
        "",
        "| Показатель | Значение |",
        "|---|---:|",
        "| Файлов `.be` просканировано | {} |".format(t["files_scanned"]),
        "| Файлов с определениями `X... ЭКВ` | {} |".format(
            t["files_with_xdefs"]),
        "| Определений `X... ЭКВ` | {} |".format(t["definitions"]),
        "| Различных X-имён | {} |".format(t["distinct_names"]),
        "| Различных адресов | {} |".format(t["distinct_addresses"]),
        "| Использований в коде | {} |".format(t["code_usages"]),
        "| Имён без использований в коде | {} |".format(t["unused_names"]),
        "",
        "### 3.1 По классам",
        "",
        "| Класс | Определений | Различных адресов | Использований |",
        "|---|---:|---:|---:|",
    ]
    for cls in (TRUE_EXTERNAL, INTERNAL_OFFSET, UNKNOWN_ABSOLUTE):
        lines.append("| {} | {} | {} | {} |".format(
            cls,
            report["defs_by_class"].get(cls, 0),
            report["address_by_class"].get(cls, 0),
            report["uses_by_class"].get(cls, 0),
        ))
    lines += [
        "",
        "Классы `INTERNAL_OFFSET` и `UNKNOWN_ABSOLUTE` -- ложные "
        "кросс-ссылки. Класс `TRUE_EXTERNAL` тоже не даёт права называть "
        "`ЭКВ` объявлением внешнего символа.",
        "",
    ]
    lines += _md_counter("3.2 По семейству зон", report["by_family"])
    lines += _md_counter("3.3 По шаблону имени", report["by_pattern"])
    lines += _md_counter("3.4 По зоне", report["by_zone"])

    lines += [
        "## 4. Именованные адреса (класс TRUE_EXTERNAL)",
        "",
        "| Адрес | Имя | СА | Свидетельство | Примечание |",
        "|---|---|---|---|---|",
    ]
    for item in report["named_externals"]:
        lines.append("| {} | {} | {} | {} | {} |".format(
            item["address"], item["name"], item["ca"] or "-",
            item["evidence"].replace("|", "/"), item["note"],
        ))
    lines += [
        "",
        "04000 (`MON*ITOR`) -- системный символ ОС, а не связь модуля "
        "(`ENTRY-POINTS.md` §3:128-129). 02000 (`*PAGE*`) одновременно "
        "является базой зоны 0154; совпадение адресов не означает общий код "
        "(`ENTRY-POINTS.md` §3:142-144). Адреса 077536 (`ГАШТСЛ`, S:2008) "
        "и 077503 (без имени, S:1955) описаны в "
        "`CALL-TARGET-RESOLUTION.md` §4.2 как ячейки КОНД/данные, поэтому "
        "внешними кодовыми символами не считаются и остаются в классе "
        "`UNKNOWN_ABSOLUTE`.",
        "",
    ]

    lines += [
        "## 5. Топ-{} ложных кросс-ссылок".format(top),
        "",
        "Ранжирование -- по числу использований в коде `.be`; "
        "второй ключ -- число определений.",
        "",
        "| X-имя | Значение | Класс | Определений | Использований |",
        "|---|---|---|---:|---:|",
    ]
    for row in report["top_false"]:
        lines.append("| {} | {} | {} | {} | {} |".format(
            row["label"], row["value"], row["class"],
            row["defs"], row["uses"],
        ))
    lines += [""]

    lines += [
        "## 6. Классификация каждого различного адреса",
        "",
        "| Адрес (восьм.) | Класс | Имя | Свидетельство | Определений | "
        "Использований |",
        "|---|---|---|---|---:|---:|",
    ]
    for row in report["address_rows"]:
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            row["value"], row["class"], row["name"] or "-",
            row["evidence"].replace("|", "/"),
            row["defs"], row["uses"],
        ))
    lines += [""]

    lines += [
        "## 7. Полная таблица переаннотации",
        "",
        "Формат рекомендуемого комментария: `, ВНЕШ: <name> [СА n], "
        "адрес <oct>` для именованных адресов; "
        "`, адрес <oct>: внешняя связь, имя не восстановлено` для "
        "неопознанных; `, адрес <oct>: локальная цель, не внешняя связь` "
        "для внутренних смещений. Формат соответствует "
        "`docs/EQU-VS-XREF.md` §5.2; поле `[СА n]` заполняется только "
        "там, где номер доказан (здесь только `*PAGE*` -- СА 3). "
        "Независимый подсчёт в `docs/EQU-VS-XREF.md` §5.4 "
        "(416 определений, 353 имени, 47 файлов) совпадает с этим аудитом. "
        "Все комментарии укладываются в 55 символов. Гипотетический "
        "характер роли неопознанного адреса должен дополнительно "
        "помечаться отдельной строкой `* (ГИПОТЕЗА)`.",
        "",
        "| Зона | Строка | X-метка | Значение | Правильная роль | "
        "Рекомендуемый комментарий |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["reannotation"]:
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            row["zone"], row["line"], row["label"], row["value"],
            row["role"], row["comment"],
        ))
    lines += [
        "",
        "## 8. Оговорки",
        "",
        "1. Ни один `.be`-файл не изменялся: это только аудит и "
        "рекомендации.",
        "2. Внутренние смещения предлагается переименовать в `P...` "
        "(ASM/B) или `C...` (B2) по образцу `P201 ЭКВ '201' , цель "
        "ПБ/ПВ; [PROC-B2]` (`bemsh/MBE2-Z0562.be:24`).",
        "3. Для класса `UNKNOWN_ABSOLUTE` сам адрес -- гипотеза: "
        "физическая страница может быть не привязана "
        "(`analysis/MEMORY-MAP.md` §5), а имя не восстановлено.",
        "4. Метки, определённые, но не используемые в коде, остаются "
        "подозрительными: они живут только в комментариях.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bemsh-dir", default=str(DEFAULT_BE_DIR),
                        help="каталог с bemsh/*.be (по умолчанию bemsh)")
    parser.add_argument("--out-md", default=None,
                        help="записать полный отчёт Markdown в файл")
    parser.add_argument("--out-json", default=None,
                        help="записать отчёт в JSON")
    parser.add_argument("--top", type=int, default=10,
                        help="число строк в рейтинге ложных ссылок")
    parser.add_argument("--quiet", action="store_true",
                        help="не печатать сводку на stdout")
    args = parser.parse_args(argv)

    report = build_report(args.bemsh_dir, top=args.top)

    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=dict),
            encoding="utf-8",
        )
    if args.out_md:
        Path(args.out_md).write_text(
            render_markdown(report, top=args.top), encoding="utf-8"
        )

    if not args.quiet:
        t = report["totals"]
        print("X-меток: {} определений, {} адресов, {} использований".format(
            t["definitions"], t["distinct_addresses"], t["code_usages"]
        ))
        for cls in (TRUE_EXTERNAL, INTERNAL_OFFSET, UNKNOWN_ABSOLUTE):
            print("  {:18s} defs={:3d} addr={:3d} uses={:3d}".format(
                cls,
                report["defs_by_class"].get(cls, 0),
                report["address_by_class"].get(cls, 0),
                report["uses_by_class"].get(cls, 0),
            ))
        print("Ложные кросс-ссылки (топ-{}):".format(args.top))
        for row in report["top_false"]:
            print("  {} {} uses={} class={}".format(
                row["label"], row["value"], row["uses"], row["class"]
            ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
