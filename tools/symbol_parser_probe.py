#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only scanner for symbol declarations in BEMSH (.be) sources.

The tool does not run an emulator and never writes to the input file.
It reports declarations of ЭКВ, ВНЕШН, ВХОДН and their macro wrappers
ВНЕШ / ВХОД, plus a heuristic list of unresolved bare identifiers.

Definitions used here (see analysis/SYMBOL-PARSER-MECH.md):

  ЭКВ value "absolute" means a quoted five-digit octal address whose
  high two octal digits are in the known page set 34..37 octal.  Those
  pages are mapped to zones 0150/0153/0152 by
  analysis/Z0137-LITERALS-INDEX.md section 3.5.  The default set can
  be changed with --absolute-pages.

  unknown_refs are bare identifiers that occur after an operation
  keyword in the code part of a line and are neither declared in this
  file, nor defined as a label, nor a builtin operation.  This is a
  lexical heuristic, not proof of a missing declaration.

Usage:
  python3 tools/symbol_parser_probe.py FILE [--format json|text]
                                            [--absolute-pages 34,35,36,37]
"""

import argparse
import json
import re
import sys

FORMAT_VERSION = 1

# Operations and directives seen in bemsh/*.be (data-derived set).
BUILTIN_OPS = set("""
    ЗП СЧ СЛИА ВЧП КОНД МОДА ПБ НТЖ И УИА ПВ ПО ПЕ СЧИ СДА УИ ИЛИ
    МОД СЛ ЦИКЛ СЛЦ ВЧ РЕГ ВЧАБ СЧИМ УИМ СБР УИИ ПИО ПИНО ВЧОБ
    СЧМ УМН РЗБ Э70 УВВ РЖА КОНК СЧМР ЗПМ ВЫПР СЛИ Э64 СЧРЖ СТОП
    ЧЕД ЗНАК СЛП Е М ФИНИШ ДЕЛ Э50 Э77 НЕД Э60 Э52 Э73 СД СЛПА
    ВЧПА Э63 Э75 Э66 Э74 Э67 РЖ Э62 Э57 Э54 Э65 Э71 Э72 Э55 Э53
    Э56 Э51 Э76
    СТАРТ УПОТР ЭКВ ВНЕШН ВНЕШ ВХОДН ВХОД
""".split())

RE_COMMENT_LINE = re.compile(r"^\s*\*")
RE_IDENT = re.compile(r"^[A-ZА-Я][A-ZА-Я0-9_]*$")
RE_LABEL_DEF = re.compile(r"^([A-ZА-Я][A-ZА-Я0-9_]*)\s+\S")
RE_QUOT_OCTAL = re.compile(r"^'([0-7]+)'$")
RE_EQU = re.compile(r"\bЭКВ\b")
RE_VN = re.compile(r"\bВНЕШН\b")
RE_VH = re.compile(r"\bВХОДН\b")
RE_VNESH = re.compile(r"\bВНЕШ\b")
RE_VHOD = re.compile(r"\bВХОД\b")


def split_code(line):
    """Return the code part of a line, excluding a trailing comment."""
    return re.split(r",\s", line, maxsplit=1)[0]


def first_token(text):
    """Return the first whitespace-delimited token, or an empty string."""
    parts = text.split()
    return parts[0] if parts else ""


def clean_token(token):
    """Drop a trailing dot or comma from a token."""
    return token.rstrip(".,;()")


def classify_equ(value, abs_pages):
    """Classify an ЭКВ operand into a deterministic category."""
    m = RE_QUOT_OCTAL.match(value)
    if not m:
        return "symbolic"
    digits = m.group(1)
    if len(digits) == 5 and digits[:2] in abs_pages:
        return "absolute"
    return "quoted_octal"


def scan(text, abs_pages):
    """Scan source text and return a deterministic result dictionary."""
    lines = text.splitlines()
    equ, vneshn, vhodn = [], [], []
    vnesh_macro, vhod_macro = [], []
    labels = set()

    for lineno, raw in enumerate(lines, 1):
        if RE_COMMENT_LINE.match(raw):
            continue
        code = split_code(raw).strip()

        label_match = RE_LABEL_DEF.match(raw)
        if label_match:
            token = label_match.group(1)
            if token not in BUILTIN_OPS:
                labels.add(token)

        m = RE_EQU.search(code)
        if m:
            name = clean_token(first_token(code[:m.start()]))
            value = clean_token(first_token(code[m.end():]))
            equ.append({
                "line": lineno,
                "name": name,
                "value": value,
                "kind": classify_equ(value, abs_pages),
                "raw": raw.rstrip(),
            })

        m = RE_VN.search(code)
        if m:
            local = clean_token(first_token(code[:m.start()]))
            operand = clean_token(first_token(code[m.end():]))
            if "." in operand:
                owner, symbol = operand.split(".", 1)
            else:
                owner, symbol = "", operand
            vneshn.append({
                "line": lineno,
                "local": local,
                "owner": owner,
                "symbol": symbol,
                "operand": operand,
                "raw": raw.rstrip(),
            })

        m = RE_VH.search(code)
        if m:
            local = clean_token(first_token(code[:m.start()]))
            operand = clean_token(first_token(code[m.end():]))
            vhodn.append({
                "line": lineno,
                "local": local,
                "name": operand,
                "raw": raw.rstrip(),
            })

        m = RE_VNESH.search(code)
        if m:
            owner = clean_token(first_token(code[:m.start()]))
            names = [clean_token(t.strip()) for t in
                     code[m.end():].split(",") if clean_token(t.strip())]
            vnesh_macro.append({
                "line": lineno,
                "owner": owner,
                "names": names,
                "raw": raw.rstrip(),
            })

        m = RE_VHOD.search(code)
        if m:
            local = clean_token(first_token(code[:m.start()]))
            names = [clean_token(t.strip()) for t in
                     code[m.end():].split(",") if clean_token(t.strip())]
            vhod_macro.append({
                "line": lineno,
                "local": local,
                "names": names,
                "raw": raw.rstrip(),
            })

    declared = set()
    for item in equ:
        if item["name"]:
            declared.add(item["name"])
    for item in vneshn:
        if item["local"]:
            declared.add(item["local"])
        if item["symbol"]:
            declared.add(item["symbol"])
    for item in vhodn:
        if item["name"]:
            declared.add(item["name"])
    for item in vnesh_macro + vhod_macro:
        declared.update(item["names"])

    unknown = {}
    for lineno, raw in enumerate(lines, 1):
        if RE_COMMENT_LINE.match(raw):
            continue
        tokens = split_code(raw).split()
        op_index = None
        for idx, token in enumerate(tokens):
            if token in BUILTIN_OPS:
                op_index = idx
                break
        if op_index is None:
            continue
        for token in tokens[op_index + 1:]:
            name = clean_token(token)
            if not RE_IDENT.match(name):
                continue
            if name in BUILTIN_OPS or name in declared or name in labels:
                continue
            if re.fullmatch(r"[МM]\d+", name):
                continue
            unknown.setdefault(name, []).append(lineno)

    unknown_refs = [
        {"name": name, "lines": sorted(set(lineno))}
        for name, lineno in sorted(unknown.items())
    ]

    kinds = {}
    for item in equ:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1

    counts = {
        "equ_total": len(equ),
        "equ_absolute": kinds.get("absolute", 0),
        "equ_quoted_octal_other": kinds.get("quoted_octal", 0),
        "equ_symbolic": kinds.get("symbolic", 0),
        "vneshn_total": len(vneshn),
        "vhodn_total": len(vhodn),
        "vnesh_macro_lines": len(vnesh_macro),
        "vnesh_macro_expansions": sum(len(x["names"]) for x in vnesh_macro),
        "vhod_macro_lines": len(vhod_macro),
        "vhod_macro_expansions": sum(len(x["names"]) for x in vhod_macro),
        "unknown_refs_total": len(unknown_refs),
        "unknown_refs_mentions": sum(len(x["lines"]) for x in unknown_refs),
        "labels": len(labels),
    }

    return {
        "format_version": FORMAT_VERSION,
        "lines": len(lines),
        "absolute_pages": sorted(abs_pages),
        "declared": {
            "equ": equ,
            "vneshn": vneshn,
            "vhodn": vhodn,
            "vnesh_macro": vnesh_macro,
            "vhod_macro": vhod_macro,
        },
        "counts": counts,
        "unknown_refs": unknown_refs,
    }


def render_text(result, source):
    """Render a compact, deterministic text report."""
    out = []
    out.append("SYMBOL PARSER PROBE: " + source)
    out.append("lines: %d" % result["lines"])
    out.append("absolute pages: %s" %
               ",".join(result["absolute_pages"]))
    out.append("")
    out.append("COUNTS")
    for key in sorted(result["counts"]):
        out.append("  %-26s %d" % (key, result["counts"][key]))
    out.append("")
    out.append("VNESHN (primitive)")
    for item in result["declared"]["vneshn"]:
        out.append("  %4d %s -> %s.%s" %
                   (item["line"], item["local"],
                    item["owner"], item["symbol"]))
    out.append("VHODN (primitive)")
    for item in result["declared"]["vhodn"]:
        out.append("  %4d %s" % (item["line"], item["name"]))
    out.append("VNESH / VHOD (macro)")
    for item in result["declared"]["vnesh_macro"]:
        out.append("  %4d ВНЕШ %s: %s" %
                   (item["line"], item["owner"],
                    ",".join(item["names"])))
    for item in result["declared"]["vhod_macro"]:
        out.append("  %4d ВХОД: %s" %
                   (item["line"], ",".join(item["names"])))
    out.append("")
    out.append("EQU absolute pages")
    for item in result["declared"]["equ"]:
        if item["kind"] == "absolute":
            out.append("  %4d %s %s" %
                       (item["line"], item["name"], item["value"]))
    out.append("")
    out.append("UNKNOWN REFS (heuristic)")
    for item in result["unknown_refs"][:20]:
        out.append("  %-10s %s" %
                   (item["name"],
                    ",".join(str(n) for n in item["lines"][:5])))
    if len(result["unknown_refs"]) > 20:
        out.append("  ... %d more" % (len(result["unknown_refs"]) - 20))
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only symbol declaration scanner for BEMSH .be")
    parser.add_argument("file", help="path to a .be file, or - for stdin")
    parser.add_argument("--format", choices=("json", "text"),
                        default="json", help="output format (default json)")
    parser.add_argument("--absolute-pages", default="34,35,36,37",
                        help="octal page prefixes counted as absolute")
    args = parser.parse_args(argv)

    abs_pages = set()
    for part in args.absolute_pages.split(","):
        part = part.strip()
        if not part:
            continue
        if not re.fullmatch(r"[0-7]{2}", part):
            parser.error("absolute pages must be two octal digits")
        abs_pages.add(part)

    if args.file == "-":
        text = sys.stdin.read()
        source = "<stdin>"
    else:
        with open(args.file, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        source = args.file

    result = scan(text, abs_pages)
    if args.format == "json":
        payload = dict(result)
        payload["source"] = source
        sys.stdout.write(json.dumps(payload, ensure_ascii=False,
                                    sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.write(render_text(result, source))
    return 0


if __name__ == "__main__":
    sys.exit(main())
