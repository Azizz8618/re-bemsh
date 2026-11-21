#!/usr/bin/env python3
"""Rename restored A#####/D##### labels into their role ЭКВ names.

For each label at dis address N, find the ЭКВ with value N, rename the label
to that role name and drop the ЭКВ line.

BASE HANDLING (validated on 0137 and 0147):
- base 1 (0147): the label value already equals the literal, no extra edit.
- base != 1 (10000, 74000, ...): a label resolves to START+N-1 while the
  old ЭКВ was the literal N. Replace each reference with
  `ROLE - START_LABEL + 1`, which evaluates back to N (0137 pilot: 3, PASS).

Usage:
  python3 tools/label2role.py <ZONE> <B|MBE2|ASM> [--dry-run]
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NONROLE = re.compile(r"^(P\d+|AM\d+|B\d+|X\w+|C\d+|MB\d+|BR\d+|CA\d+)$")


def pick_role(names):
    for n in names:
        if not NONROLE.match(n):
            return n
    return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    zone, mode = sys.argv[1], sys.argv[2]
    dry = "--dry-run" in sys.argv
    prefix = {"B": "MBE", "MBE2": "MBE2", "ASM": "ASM"}[mode]
    be = os.path.join(ROOT, f"bemsh/{prefix}-Z{zone}.be")
    if not os.path.exists(be):
        be = os.path.join(ROOT, f"bemsh/{prefix}-Z{zone}-L1.be")

    lines = open(be, encoding="utf-8").read().splitlines()

    # Find START label (the symbol on the СТАРТ line) and its base.
    start_label, base = None, 1
    for s in lines:
        m = re.match(r"^(\S+)\s+СТАРТ\s+'?([0-7]+)'?", s)
        if m:
            start_label, base = m.group(1), int(m.group(2), 8)
            break
    offset = base - 1  # 0 for base 1; nonzero otherwise

    eqv = {}
    for i, s in enumerate(lines):
        m = re.match(r"^\s*(\S+)\s+ЭКВ\s+'?([0-7]+)'?", s)
        if m:
            eqv.setdefault(int(m.group(2), 8), []).append((m.group(1), i))

    replace = {}
    for addr, entries in eqv.items():
        role = pick_role([n for n, _ in entries])
        if role:
            replace[addr] = (role, next(i for n, i in entries if n == role))

    drop = set()
    changes = []
    for i, s in enumerate(lines):
        m = re.match(r"^([AGD]\d{5})(\s+)(.*)$", s)
        if m:
            addr = int(m.group(1)[1:], 8)
            if addr in replace:
                role, eidx = replace[addr]
                drop.add(eidx)
                changes.append((addr, m.group(1), role))

    # Short alias for the START label keeps reference expressions compact.
    alias = "S"
    expr_suffix = "-" + alias + "+1" if offset else ""

    # Pass 2: emit. Replace label text and (for base != 1) rewrite references
    # ONLY in the operand part (before the comma), never in trailing comments.
    out = []
    inserted_alias = False
    for i, s in enumerate(lines):
        if i in drop:
            continue
        if offset and not inserted_alias and re.match(r"^\S+\s+СТАРТ\b", s):
            out.append(s)
            out.append("%-8sЭКВ %s" % (alias, start_label))
            inserted_alias = True
            continue
        for addr, old, role in changes:
            if s.startswith(old + "  ") or s.startswith(old + " "):
                skip = len(old)
                while skip < len(s) and s[skip] == " ":
                    skip += 1
                s = role.ljust(8) + s[skip:]
                break
        if offset and not s.lstrip().startswith("*") and "," in s:
            head, sep, tail = s.partition(",")
            for addr, old, role in changes:
                head = re.sub(
                    r"(?<=\s)" + re.escape(role) + r"\b(?!\s*ЭКВ)",
                    role + expr_suffix,
                    head,
                )
            s = head + sep + tail
            if len(s) > 60:
                # Longer operand: shrink only alignment whitespace.
                s = re.sub(r" {2,}", " ", head.rstrip()) + " "
                if sep:
                    s += sep + re.sub(r" {2,}", " ", tail)
        out.append(s)

    print(
        "зона %s: база=%o меток=%d удалено ЭКВ=%d"
        % (zone, base, len(changes), len(drop))
    )
    if dry:
        for addr, old, role in changes[:5]:
            print("  %s -> %s" % (old, role))
        return 0
    open(be, "w", encoding="utf-8").write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
