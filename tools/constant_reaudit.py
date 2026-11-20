#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-audit of literals classified CONSTANT/DATA by tools/literal_labels.py.

The original classifier is mnemonic-driven: operands of branch/load
mnemonics become ADDRESS, while extract codes (E50/... in Russian: Э50),
masks, immediates, EQU definitions and KOND data words become CONSTANT.
This tool re-checks the CONSTANT bucket against three independent pieces
of evidence:

  1. procedure catalogues (docs/PROCEDURES-{ASM,B,B2}.md),
  2. the global cross-reference graph (analysis/global_xref.tsv),
  3. usage of each EQU label inside its own .be file.

A CONSTANT value that is a procedure entry in the SAME zone, or that is a
frequent CALL target in the xref graph, is a candidate misclassification.

The tool is READ-ONLY with respect to bemsh/, gold/, dis/, sym/ and docs/.
It never calls literal_labels.py --apply-zone and writes nothing by default.

Usage
-----
    python3 tools/constant_reaudit.py
    python3 tools/constant_reaudit.py --out /tmp/candidates.tsv
    python3 tools/constant_reaudit.py --root /path/to/repo --json

Verdicts
--------
  PROCEDURE_LABEL      data-ish EQU label that is a same-zone procedure
                       entry and is used as a branch target -> rename.
  POINTER_TO_PROCEDURE data word / extract operand holding a procedure
                       address -> needs a distinct PTR role, not a rename.
  FALSE_POSITIVE       numeric coincidence (register number, immediate,
                       shared low word 00000, global gate constant).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

# The scanner lives next to this file; import it instead of re-implementing
# the quoted-octal extraction so both tools share one byte-level definition.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import literal_labels as LL  # noqa: E402


ROOT_DEFAULT = pathlib.Path(__file__).resolve().parent.parent

# Mnemonics that consume their operand as a control-transfer target.
BRANCH_MNEMONICS = {
    "ПБ", "ПО", "ПЕ", "ПВ", "НТЖ", "ЦИКЛ", "ПИО", "ПИНО", "СБР", "ВЫПР",
}

# EQU label prefixes already used for procedures by earlier annotation passes.
PROC_LABEL_RE = re.compile(r"^(BR|CA|UTL|SUB|OUT|EXIT|EPI|ENT|CALL|JMP|DSP)\d")

# Values that are known non-address constants (chessboard fill, gates, etc.).
NON_ADDRESS_VALUES = {"25252", "72525", "7777", "70000"}

# Comment markers that turn a KOND half match into real evidence.
KOND_CODE_HINT = re.compile(r"код|переход|CALL|вызов|шлюз|вектор", re.I)


def norm(value: str) -> str:
    """Normalise an octal spelling by dropping insignificant leading zeros."""
    return (value or "0").lstrip("0") or "0"


# ---------------------------------------------------------------------------
# 1. Procedure starts
# ---------------------------------------------------------------------------

def load_procedure_starts(root: pathlib.Path):
    """Return (starts, by_addr).

    starts: (zone, address) -> {'family', 'status', 'doc', 'line'}
    by_addr: address -> sorted list of zones where it is a procedure start.
    Rows explicitly marked ДАН (false data target) are excluded.
    """
    starts: dict[tuple[str, str], dict] = {}
    docs = root / "docs"

    cur_zone = None
    p = docs / "PROCEDURES-ASM.md"
    if p.exists():
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r"^##\s+\d+\.\s+ЗОНА\s+(\d{4})", line)
            if m:
                cur_zone = m.group(1)
                continue
            m = re.match(r"^\s*(\d{3,4})-(\d{3,4})\s+\d+\s+([CB]\d*)", line)
            if m and cur_zone:
                starts.setdefault((cur_zone, norm(m.group(1))), {
                    "family": "ASM", "status": m.group(3),
                    "doc": p.name, "line": lineno,
                })

    p = docs / "PROCEDURES-B.md"
    if p.exists():
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r"^(\d{4}):(\d{3,4})-(\d{3,4})\s+size=\d+\s+"
                         r"(\S+)\s+(\S+)", line)
            if m:
                starts.setdefault((m.group(1), norm(m.group(2))), {
                    "family": "B", "status": m.group(5),
                    "doc": p.name, "line": lineno,
                })

    p = docs / "PROCEDURES-B2.md"
    if p.exists():
        in_table = False
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("## 4."):
                in_table = True
            elif line.startswith("## "):
                in_table = False  # §6 is a zone-correspondence table
            if not in_table:
                continue
            m = re.match(r"^(\d{4})\s+(\d{3,4})\s+(\d{3,4})\s+\d+\s+(\S+)", line)
            if m:
                starts.setdefault((m.group(1), norm(m.group(2))), {
                    "family": "B2", "status": m.group(4),
                    "doc": p.name, "line": lineno,
                })

    starts = {k: v for k, v in starts.items() if v["status"] != "ДАН"}
    by_addr = collections.defaultdict(set)
    for zone, addr in starts:
        by_addr[addr].add(zone)
    return starts, {a: sorted(zs) for a, zs in by_addr.items()}


def load_xref(root: pathlib.Path):
    """Return address -> CALL/branch evidence from global_xref.tsv."""
    out = {}
    p = root / "analysis" / "global_xref.tsv"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 5:
            continue
        target, zones, label, rc, sources = cols[0], cols[1], cols[2], cols[3], cols[4]
        m = re.match(r"^[AD](\d{4,5})$", target) or re.match(r"^OCT:([0-7]+)$", target)
        if not m:
            continue
        addr = norm(m.group(1))
        calls = len(re.findall(r":(?:пв|пво|вжм)\b", sources, re.I))
        branches = len(re.findall(
            r":(?:пб|по|пе|цикл|пио|пино|выпр)\b", sources, re.I))
        out[addr] = {
            "target": target, "label": label, "ref_count": int(rc),
            "calls": calls, "branches": branches,
            "zones": [z for z in zones.split(",") if re.fullmatch(r"\d{4}", z)],
            "sources": sources,
        }
    return out


def load_address_values(root: pathlib.Path):
    """Values already carrying an ADDRESS label in sym/ALL_LABELS.tab."""
    out = set()
    p = root / "sym" / "ALL_LABELS.tab"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) >= 3 and cols[2] == "ADDRESS":
            out.add(norm(cols[1]))
    return out


# ---------------------------------------------------------------------------
# 2. CONSTANT-classified literals
# ---------------------------------------------------------------------------

def _be_files(root: pathlib.Path):
    for path in sorted((root / "bemsh").glob("*.be")):
        m = re.search(r"-Z(\d{4})\.be$", path.name)
        if m:
            yield path, m.group(1)


def load_eqv_definitions(root: pathlib.Path):
    """EQU definitions (classified CONSTANT by literal_labels.py)."""
    defs = []
    for path, zone in _be_files(root):
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, 1):
            m = re.match(r"^\s*([A-Z][A-Z0-9]{1,9})\s+ЭКВ\s+'([0-7]+)'", line)
            if m:
                defs.append({
                    "zone": zone, "line": lineno, "file": path.name,
                    "label": m.group(1), "value": norm(m.group(2)),
                    "raw": line.strip(),
                })
    return defs


def label_usage(root: pathlib.Path, file: str, label: str):
    """Count branch vs data uses of a label in its own .be file."""
    path = root / "bemsh" / file
    if not path.exists():
        return 0, 0, []
    branches = data = 0
    samples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        code = LL._code_part(line)
        if not code or re.search(r"\bЭКВ\b", code):
            continue
        if not re.search(r"\b" + re.escape(label) + r"\b", code):
            continue
        toks = code.split()
        mnem = toks[0] if toks else ""
        if mnem in BRANCH_MNEMONICS:
            branches += 1
        else:
            data += 1
        if len(samples) < 3:
            samples.append(line.strip())
    return branches, data, samples


def load_operands(root: pathlib.Path):
    """Real (non-EQU) operands classified CONSTANT by literal_labels.py."""
    out = []
    for occ in LL.scan(root):
        if occ["kind"] != "CONSTANT" or occ["is_eqv"]:
            continue
        if occ["value"] in ("25252", "72525"):
            continue  # documented chessboard fill
        out.append(occ)
    return out


def load_kond_halves(root: pathlib.Path):
    """KOND data words whose 24-bit halves address a procedure.

    A 48-bit word is printed as 16 octal digits = two 8-digit halves.
    The low 5 octal digits of a half are the BESM-6 address field.
    """
    out = []
    for path, zone in _be_files(root):
        for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("*") or "КОНД" not in line:
                continue
            m = re.search(r"В'([0-7]{16})'", line)
            if not m:
                continue
            word = m.group(1)
            for half in (word[:8], word[8:]):
                high, low = half[:3], half[3:]
                addr = norm(low)
                out.append({
                    "zone": zone, "line": lineno, "file": path.name,
                    "value": addr, "high": high, "word": word,
                    "raw": line.strip(),
                })
    return out


# ---------------------------------------------------------------------------
# 3. Candidates and verdicts
# ---------------------------------------------------------------------------

def _suggest(label_kind: str, value: str) -> str:
    stem = "P" if label_kind == "PROCEDURE_LABEL" else "PTR"
    return (stem + value)[:6]


def build_candidates(root: pathlib.Path):
    """Return (candidates, stats) for the three CONSTANT sub-populations."""
    starts, by_addr = load_procedure_starts(root)
    xref = load_xref(root)
    address_values = load_address_values(root)

    candidates = []
    stats = collections.Counter()

    # --- 3a. EQU definitions -------------------------------------------------
    for d in load_eqv_definitions(root):
        stats["eqv_total"] += 1
        if d["zone"] not in by_addr.get(d["value"], []):
            continue
        stats["eqv_proc"] += 1
        if PROC_LABEL_RE.match(d["label"]):
            stats["eqv_already_proc"] += 1
            continue
        br, data, samples = label_usage(root, d["file"], d["label"])
        ev = starts[(d["zone"], d["value"])]
        if br and not data:
            verdict, confidence = "PROCEDURE_LABEL", "ПОДТВЕРЖДЕНО"
            reason = f"branch target x{br}, no data use in {d['file']}"
        elif br and data:
            verdict, confidence = "PROCEDURE_LABEL", "ГИПОТЕЗА"
            reason = f"branch target x{br}, also data x{data} (dual-use cell)"
        elif data and d["value"] == "1":
            # Address 0001 is the zone ВХОД marker in many catalogues; LOG001
            # is documented as INIT_LOG_ENTRY, not a callable entry point.
            verdict, confidence = "FALSE_POSITIVE", "ГИПОТЕЗА"
            reason = "0001 zone-ВХОД artifact; INIT_LOG_ENTRY is data"
        elif data:
            verdict, confidence = "POINTER_TO_PROCEDURE", "ГИПОТЕЗА"
            reason = f"data-only use x{data}; value is a same-zone entry"
        else:
            verdict, confidence = "FALSE_POSITIVE", "ГИПОТЕЗА"
            reason = "no use found; coincidence"
        stats[verdict] += 1
        candidates.append({
            "zone": d["zone"], "line": d["line"], "file": d["file"],
            "value": d["value"], "source": "EQV", "old": d["label"],
            "context": d["raw"], "branch_uses": br, "data_uses": data,
            "usage": samples, "proc_doc": f"{ev['doc']}:{ev['line']}",
            "xref": "", "reason": reason,
            "verdict": verdict, "confidence": confidence,
            "new": (d["label"] if verdict == "FALSE_POSITIVE"
                    else _suggest(verdict, d["value"])),
        })

    # --- 3b. Extract-code / immediate operands ------------------------------
    for o in load_operands(root):
        stats["operand_total"] += 1
        same = o["zone"] in by_addr.get(o["value"], [])
        xi = xref.get(o["value"], {})
        calls = xi.get("calls", 0)
        is_extract = o["mnem"].startswith("Э")
        if same and is_extract:
            verdict, confidence = "POINTER_TO_PROCEDURE", "ГИПОТЕЗА"
            reason = "same-zone procedure entry in extract operand"
        elif same and o["mnem"] in ("РЕГ", "РЖ", "РЖА"):
            verdict, confidence = "FALSE_POSITIVE", "ГИПОТЕЗА"
            reason = "register/immediate number coincides with entry"
        elif calls >= 2 and o["value"] not in NON_ADDRESS_VALUES and is_extract:
            verdict, confidence = "POINTER_TO_PROCEDURE", "ГИПОТЕЗА"
            reason = f"xref CALL target ({calls} CALL refs)"
        else:
            continue
        path = root / "bemsh" / o["file"]
        lines = path.read_text(encoding="utf-8").splitlines()
        raw = lines[o["line"] - 1].strip() if o["line"] <= len(lines) else ""
        stats[verdict] += 1
        candidates.append({
            "zone": o["zone"], "line": o["line"], "file": o["file"],
            "value": o["value"], "source": "OPERAND", "old": o["mnem"],
            "context": raw, "branch_uses": 0, "data_uses": 0, "usage": [],
            "proc_doc": (f"{starts[(o['zone'], o['value'])]['doc']}:"
                         f"{starts[(o['zone'], o['value'])]['line']}") if same else "",
            "xref": (f"{xi.get('target', '')} {xi.get('label', '')} "
                     f"CALL={calls} ref={xi.get('ref_count', 0)}"),
            "reason": reason, "verdict": verdict, "confidence": confidence,
            "new": (o["mnem"] if verdict == "FALSE_POSITIVE"
                    else _suggest(verdict, o["value"])),
        })

    # --- 3c. KOND word halves -----------------------------------------------
    for h in load_kond_halves(root):
        if h["value"] == "0":  # low half 00000 matches every zone START
            continue
        if h["zone"] not in by_addr.get(h["value"], []):
            continue
        if not KOND_CODE_HINT.search(h["raw"]):
            continue
        ev = starts[(h["zone"], h["value"])]
        stats["kond_proc"] += 1
        stats["POINTER_TO_PROCEDURE"] += 1
        candidates.append({
            "zone": h["zone"], "line": h["line"], "file": h["file"],
            "value": h["value"], "source": "KOND", "old": h["word"],
            "context": h["raw"], "branch_uses": 0, "data_uses": 0,
            "usage": [], "proc_doc": f"{ev['doc']}:{ev['line']}",
            "xref": "", "reason": "KOND half low-5 = procedure address",
            "verdict": "POINTER_TO_PROCEDURE", "confidence": "ГИПОТЕЗА",
            "new": _suggest("POINTER_TO_PROCEDURE", h["value"]),
        })

    stats["candidates"] = len(candidates)
    stats["xref_entries"] = len(xref)
    stats["procedure_starts"] = len(starts)
    stats["address_label_values"] = len(address_values)
    return candidates, dict(stats)


# ---------------------------------------------------------------------------
# 4. Output
# ---------------------------------------------------------------------------

COLUMNS = ["zone", "line", "file", "value", "source", "old", "verdict",
           "new", "confidence", "branch_uses", "data_uses", "reason",
           "proc_doc", "xref", "context"]


def format_table(candidates) -> str:
    """Render a compact markdown table of candidates."""
    lines = ["| " + " | ".join(COLUMNS) + " |",
             "|" + "|".join("---" for _ in COLUMNS) + "|"]
    for c in candidates:
        cells = []
        for col in COLUMNS:
            v = str(c.get(col, "")).replace("|", "/").replace("\n", " ")
            cells.append(v[:90])
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def format_fix_list(candidates) -> str:
    """The precise zone | line | old label | suggested new label list."""
    lines = ["zone | line | old label | suggested new label"]
    for c in candidates:
        if c["verdict"] == "FALSE_POSITIVE":
            continue
        lines.append(f"{c['zone']} | {c['line']} | {c['old']} | {c['new']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=pathlib.Path, default=ROOT_DEFAULT,
                    help="repo root (default: parent of tools/)")
    ap.add_argument("--out", type=pathlib.Path,
                    help="write the candidate table as TSV to this path")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of a markdown table")
    ap.add_argument("--fix-list", action="store_true",
                    help="print only the zone|line|old|new fix list")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    candidates, stats = build_candidates(root)

    if args.json:
        print(json.dumps({"stats": stats, "candidates": candidates},
                         ensure_ascii=False, indent=2))
    elif args.fix_list:
        print(format_fix_list(candidates))
    else:
        print("CONSTANT RE-AUDIT -- candidates that match procedure starts")
        print("stats: " + " ".join(f"{k}={v}" for k, v in sorted(stats.items())))
        print()
        print(format_table(candidates))

    if args.out:
        with args.out.open("w", encoding="utf-8") as f:
            f.write("\t".join(COLUMNS) + "\n")
            for c in candidates:
                f.write("\t".join(str(c.get(col, "")) for col in COLUMNS) + "\n")
        print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
