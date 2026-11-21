#!/usr/bin/env python3
"""Rename restored A#####/D##### labels to their role ЭКВ names.

For each inserted label with dis address N, find an ЭКВ with value N and
rename the label to that name, then delete that ЭКВ line. Alias ЭКВ on the
same address (e.g. P477) are KEPT so all existing references still resolve.

Safety: the word addressed by a label at dis address N is the same word the
ЭКВ 'N' pointed at (verified by pilot on 0147: OUT477, 1024/1024 PASS).

Usage:
  python3 tools/label2role.py <ZONE> <B|MBE2|ASM> [--dry-run]
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Roles that are NOT a role name (aliases / auto numeric constants).
NONROLE = re.compile(r"^(P\d+|AM\d+|B\d+|X\w+|C\d+|MB\d+|BR\d+|CA\d+)$")


def pick_role(names):
    """Pick the primary role ЭКВ name for an address, or None."""
    for n in names:
        if not NONROLE.match(n):
            return n
    return None  # only aliases -> keep the A/D label as-is


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
    eqv = {}
    for i, s in enumerate(lines):
        m = re.match(r"^\s*(\S+)\s+ЭКВ\s+'?([0-7]+)'?", s)
        if m:
            eqv.setdefault(int(m.group(2), 8), []).append((m.group(1), i))

    # map: address N -> role name to use (and ЭКВ line index to drop)
    replace = {}
    for addr, entries in eqv.items():
        role = pick_role([n for n, _ in entries])
        if role:
            idx = next(i for n, i in entries if n == role)
            replace[addr] = (role, idx)

    # Pass 1: decide all drops BEFORE emitting, because an ЭКВ line usually
    # precedes its label; a single pass would already have emitted it.
    drop = set()
    renamed = []
    for i, s in enumerate(lines):
        m = re.match(r"^([AGD]\d{5})(\s+)(.*)$", s)
        if m:
            addr = int(m.group(1)[1:], 8)
            if addr in replace:
                role, eidx = replace[addr]
                drop.add(eidx)
                renamed.append((m.group(1), role))

    out = []
    rename_by_addr = {}
    for s in lines:
        m = re.match(r"^([AGD]\d{5})(\s+)(.*)$", s)
        if m:
            addr = int(m.group(1)[1:], 8)
            if addr in replace:
                rename_by_addr[addr] = replace[addr][0]
    for i, s in enumerate(lines):
        if i in drop:
            continue
        m = re.match(r"^([AGD]\d{5})(\s+)(.*)$", s)
        if m:
            addr = int(m.group(1)[1:], 8)
            if addr in rename_by_addr:
                s = rename_by_addr[addr].ljust(8) + m.group(3)
        out.append(s)

    print(f"зона {zone}: переименовано {len(renamed)}, удалено ЭКВ {len(drop)}")
    if dry:
        for a, b in renamed[:5]:
            print(f"  {a} -> {b}")
        return 0
    open(be, "w", encoding="utf-8").write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
