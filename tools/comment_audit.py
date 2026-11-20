#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Эвристический аудит человеческих комментариев в ``bemsh/*.be``.

Цель — найти *гalledлюцинированные* комментарии: текст после разделителя
`` , `` утверждает адрес/регистр/действие там, где в слове нет операнда
(нулевое полуслово ``00 000 0000``), либо противоречит/opеранду, либо
является тавтологией/штампом/слишком длинным.

Инвариант репозитория соблюдается: скрипт **только читает** ``.be``-файлы
и печатает отчёт. Ни один ``.be``, ``gold/``, ``dis/`` не изменяется.

Запуск:
    python3 tools/comment_audit.py --all
    python3 tools/comment_audit.py --zone 0055
    python3 tools/comment_audit.py --all --top 10 --json
"""

import argparse
import collections
import json
import pathlib
import re
import sys

# --- Константы формата (AGENTS.md §0, COMMENTING-STANDARD.md §6) ------------
SEP = " , "                       # разделитель кода и комментария
MAX_COMMENT = 55                  # предел длины комментария
MAX_LINE = 78                     # предел длины всей строки
REPETITION_THRESHOLD = 20         # «более N повторов» = подозрительный штамп

# Фразы, которые считаются ПРАВИЛЬНОЙ аннотацией нулевого слова.
ZERO_WORD_PATTERNS = (
    "нулевое слово", "нулевой", "нуль", "пустое слово", "забел",
    "забелка", "ноль", "нулевая ячейка", "слово 0", "в'0'",
)
ZERO_WORD_SUGGESTION = ", нулевое слово (забел)"

# Тавтологии / role-free слова, прямо запрещённые COMMENTING-STANDARD.md
# (§1 таблица, §2.6 «не писать конд как финальную роль», §7 п.5).
TAUTOLOGY_PHRASES = (
    "константа", "цель ветвления", "цель перехода", "цель ветвления/перехода",
    "переход/возврат", "обработка", "конд", "утилита", "диспетчер",
    "mbeentry", "sub04", "sub05", "служебное слово",
)

# Латинские слова в комментариях, которые НЕ являются метками операнда
# (ролевые/языковые слова, встречающиеся в корпусе).
LABEL_STOPWORDS = {
    "CALL", "GOST", "TEXT", "ISO", "ITM", "KOI", "ASCII", "NOP",
    "DEKOD", "VARIABLES", "REGISTERS", "MBEENTRY", "SUB04", "SUB05",
}

# Признаки утверждения адреса/регистра/действия в комментарии.
# Используются для пояснения EMPTY-OPERAND-SEMANTIC (какой именно fabricated
# claim сделан). Пустой операнд + ЛЮБОЕ не-нулевое слово уже подозрителен —
# эти шаблоны лишь уточняют причину в отчёте.
CLAIM_PATTERNS = {
    "адрес": re.compile(r"\bадрес\w*", re.I),
    "уиа": re.compile(r"\bуиа\b", re.I),
    "регистр": re.compile(r"[МM]\d{1,2}\b"),
    "через_м": re.compile(r"через\s+[МM]\d{1,2}\b", re.I),
    "сумматор": re.compile(r"сумматор", re.I),
    "метка": re.compile(r"\bметк\w*", re.I),
}

REG_RE = re.compile(r"М\d{1,2}\b")            # регистр БЭСМ-6 (кириллическая М)
LABEL_RE = re.compile(r"\b[A-Z][A-Z0-9]{2,}\b")  # метка вида CEL775, OUT477
ZONE_RE = re.compile(r"Z(\d{4})")

CATEGORIES = (
    "EMPTY-OPERAND-SEMANTIC", "CONTRADICTION", "REPETITION",
    "TAUTOLOGY", "LENGTH",
)


# --- Парсинг ---------------------------------------------------------------
def parse_line(line):
    """Разобрать строку ``.be``.

    Возвращает dict с полями ``mnem``, ``operand``, ``comment`` или ``None``,
    если строка — шапка/директива/ЭКВ/пустая/без комментария.

    >>> parse_line("        ЗП             , записать по адресу из УИА")
    {'mnem': 'ЗП', 'operand': '', 'comment': 'записать по адресу из УИА'}
    """
    if SEP not in line:
        return None
    stripped = line.strip()
    if not stripped or stripped.startswith("*"):
        return None
    code, comment = line.split(SEP, 1)
    parts = code.strip().split(None, 1)
    if not parts:
        return None
    # ЭКВ-определения и метки не являются командами с операндом.
    if parts[0] == "ЭКВ" or (len(parts) > 1 and parts[1] == "ЭКВ"):
        return None
    mnem = parts[0]
    operand = parts[1].strip() if len(parts) > 1 else ""
    return {"mnem": mnem, "operand": operand, "comment": comment.strip()}


def extract_references(text):
    """Вернуть (множество регистров, множество меток) из текста."""
    regs = set(REG_RE.findall(text))
    labels = {t for t in LABEL_RE.findall(text) if t not in LABEL_STOPWORDS}
    return regs, labels


def is_zero_word_comment(comment):
    """True, если комментарий уже корректно описывает нулевое слово."""
    low = comment.lower()
    return any(p in low for p in ZERO_WORD_PATTERNS)


def claim_kinds(comment):
    """Какие именно адресные/регистровые утверждения делает комментарий."""
    return sorted(name for name, rx in CLAIM_PATTERNS.items() if rx.search(comment))


def classify_safe(operand, comment):
    """Классификатор «безопасного» комментария (требование 2).

    Комментарий безопасен, когда:
      * все названные в нём регистры и метки присутствуют в операнде;
      * и либо операнд непуст, либо комментарий явно говорит о нулевом слове.

    >>> classify_safe("CEL775", "записать в CEL775")
    True
    >>> classify_safe("OUT477(М15)", "вызвать OUT477 через М15")
    True
    >>> classify_safe("", "записать по адресу из УИА")
    False
    """
    op_regs, op_labels = extract_references(operand or "")
    cm_regs, cm_labels = extract_references(comment or "")
    missing = (cm_regs - op_regs) | (cm_labels - op_labels)
    if missing:
        return False
    if not (operand or "").strip() and not is_zero_word_comment(comment or ""):
        return False
    return True


def zone_of(path):
    """Извлечь восьмеричный номер зоны из имени файла, иначе ''."""
    m = ZONE_RE.search(pathlib.Path(path).name)
    return m.group(1) if m else ""


def _normalize_zone(zone):
    try:
        return str(int(str(zone), 8 if str(zone).isdigit() and len(str(zone)) > 2 else 10))
    except ValueError:
        return str(zone)


# --- Ядро аудита -----------------------------------------------------------
def audit_corpus(root, zone=None, repeat_threshold=REPETITION_THRESHOLD):
    """Просканировать ``bemsh/*.be`` и вернуть структурированный отчёт.

    ``root`` — корень репозитория. ``zone`` — фильтр (например ``'0055'``).
    """
    root = pathlib.Path(root)
    files = sorted((root / "bemsh").glob("*.be"))
    if zone:
        want = _normalize_zone(zone)
        files = [p for p in files if _normalize_zone(zone_of(p)) == want]

    records = []              # все разобранные строки с комментариями
    for path in files:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            parsed = parse_line(line)
            if parsed is None:
                continue
            parsed.update({
                "file": path.name,
                "zone": zone_of(path),
                "line": lineno,
                "raw": line,
            })
            records.append(parsed)

    # Частоты комментариев по корпусу и по файлу (для REPETITION).
    corpus_counts = collections.Counter(r["comment"] for r in records)
    file_counts = collections.Counter((r["file"], r["comment"]) for r in records)

    findings = []
    safe_count = 0
    for r in records:
        cm = r["comment"]
        op = r["operand"]
        cats = []
        detail = {}

        # 1. EMPTY-OPERAND-SEMANTIC
        if not op.strip() and not is_zero_word_comment(cm):
            cats.append("EMPTY-OPERAND-SEMANTIC")
            detail["claims"] = claim_kinds(cm)
            detail["suggestion"] = ZERO_WORD_SUGGESTION

        # 2. CONTRADICTION
        op_regs, op_labels = extract_references(op)
        cm_regs, cm_labels = extract_references(cm)
        missing_regs = sorted(cm_regs - op_regs)
        missing_labels = sorted(cm_labels - op_labels)
        if missing_regs or missing_labels:
            cats.append("CONTRADICTION")
            detail["missing_regs"] = missing_regs
            detail["missing_labels"] = missing_labels

        # 3. REPETITION
        n_corpus = corpus_counts[cm]
        n_file = file_counts[(r["file"], cm)]
        if n_corpus > repeat_threshold or n_file > repeat_threshold:
            cats.append("REPETITION")
            detail["count_corpus"] = n_corpus
            detail["count_file"] = n_file

        # 4. TAUTOLOGY
        low = cm.lower()
        hit = [p for p in TAUTOLOGY_PHRASES if p in low]
        if hit:
            cats.append("TAUTOLOGY")
            detail["phrases"] = hit

        # 5. LENGTH
        over = []
        if len(cm) > MAX_COMMENT:
            over.append("comment=%d>%d" % (len(cm), MAX_COMMENT))
        if len(r["raw"]) > MAX_LINE:
            over.append("line=%d>%d" % (len(r["raw"]), MAX_LINE))
        if over:
            cats.append("LENGTH")
            detail["over"] = over

        if cats:
            findings.append({
                "zone": r["zone"], "file": r["file"], "line": r["line"],
                "mnem": r["mnem"], "operand": op, "comment": cm,
                "categories": cats, "detail": detail,
            })
        else:
            safe_count += 1

    by_category = collections.Counter()
    by_zone = collections.defaultdict(lambda: collections.Counter())
    for f in findings:
        for c in f["categories"]:
            by_category[c] += 1
            by_zone[f["zone"]][c] += 1
        by_zone[f["zone"]]["SUSPECTS"] += 1

    # Топ нарушающих комментариев (по всем категориям).
    offender = collections.Counter()
    offender_cats = collections.defaultdict(set)
    for f in findings:
        offender[f["comment"]] += 1
        offender_cats[f["comment"]].update(f["categories"])
    top_offenders = [
        {"comment": cm, "count": n,
         "categories": sorted(offender_cats[cm])}
        for cm, n in offender.most_common()
    ]

    # Топ подтверждённых empty-operand шаблонов + рекомендация.
    empty_counter = collections.Counter()
    for f in findings:
        if "EMPTY-OPERAND-SEMANTIC" in f["categories"]:
            empty_counter[f["comment"]] += 1
    top_empty = [
        {"comment": cm, "count": n, "suggestion": ZERO_WORD_SUGGESTION}
        for cm, n in empty_counter.most_common()
    ]

    return {
        "scanned_files": len(files),
        "scanned_comment_lines": len(records),
        "safe_comments": safe_count,
        "total_suspect_lines": len(findings),
        "total_category_hits": sum(by_category.values()),
        "repeat_threshold": repeat_threshold,
        "by_category": dict(sorted(by_category.items())),
        "by_zone": {
            z: dict(sorted(c.items())) for z, c in sorted(by_zone.items())
        },
        "top_offenders": top_offenders,
        "top_empty_operand": top_empty,
        "findings": findings,
    }


def format_text_report(report, top=20):
    """Человекочитаемый отчёт."""
    out = []
    add = out.append
    add("=== COMMENT AUDIT (bemsh/*.be) ===")
    add("scanned files      : %d" % report["scanned_files"])
    add("comment lines      : %d" % report["scanned_comment_lines"])
    add("safe comments      : %d" % report["safe_comments"])
    add("suspect lines      : %d" % report["total_suspect_lines"])
    add("category hits      : %d" % report["total_category_hits"])
    add("repeat threshold   : > %d" % report["repeat_threshold"])
    add("")
    add("--- suspects by category ---")
    for cat in CATEGORIES:
        add("  %-26s %7d" % (cat, report["by_category"].get(cat, 0)))
    add("")
    add("--- suspects by zone (top 15 by total) ---")
    zones = sorted(report["by_zone"].items(),
                   key=lambda kv: -kv[1].get("SUSPECTS", 0))[:15]
    add("  %-6s %8s %10s %8s %9s %10s" %
        ("zone", "suspects", "empty-op", "contrad.", "repeat", "tautol."))
    for z, c in zones:
        add("  %-6s %8d %10d %8d %9d %10d" % (
            z, c.get("SUSPECTS", 0),
            c.get("EMPTY-OPERAND-SEMANTIC", 0),
            c.get("CONTRADICTION", 0),
            c.get("REPETITION", 0),
            c.get("TAUTOLOGY", 0)))
    add("")
    add("--- top %d offending comment patterns ---" % top)
    for row in report["top_offenders"][:top]:
        add("  %7d  %-52s  %s" %
            (row["count"], repr(row["comment"])[:52], ",".join(row["categories"])))
    add("")
    add("--- top %d EMPTY-OPERAND patterns + suggested replacement ---" % top)
    for row in report["top_empty_operand"][:top]:
        add("  %7d  %-42s -> %s" %
            (row["count"], repr(row["comment"])[:42], row["suggestion"]))
    add("")
    add("CAVEATS: эвристика. Комментарий может быть неверным и при отсутствии")
    add("флагов (audit не понимает семантику). EMPTY-OPERAND-SEMANTIC считает")
    add("любой не-нулевой комментарий при пустом операнде подозрительным;")
    add("CONTRADICTION может ловить легитимные role-ссылки (напр. возврат в М15")
    add("при CALL); REPETITION/TAUTOLOGY — индикаторы шаблонов, не доказательство.")
    return "\n".join(out)


def build_parser():
    ap = argparse.ArgumentParser(
        description="Аудит комментариев в bemsh/*.be (только чтение)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true",
                   help="сканировать все 69 модулей (по умолчанию)")
    g.add_argument("--zone", metavar="Z",
                   help="только зона Z, например 0055 или 147")
    ap.add_argument("--top", type=int, default=20,
                    help="сколько топ-шаблонов показывать (по умолчанию 20)")
    ap.add_argument("--repeat-threshold", type=int, default=REPETITION_THRESHOLD,
                    help="порог REPETITION (по умолчанию 20)")
    ap.add_argument("--json", action="store_true",
                    help="вывести полный отчёт в JSON")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = pathlib.Path(__file__).resolve().parents[1]
    report = audit_corpus(root, zone=args.zone,
                          repeat_threshold=args.repeat_threshold)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report, top=args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
