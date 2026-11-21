#!/usr/bin/env python3
"""Restore A#####/D##### labels from dis/*.asm into bemsh/*.be.

A disassembly label lives on a WORD (left half). In .be each word is either
one `КОНД`/`ПАМ` line or a pair of half-lines. A label generates no word.

CRITICAL: .be uses `СТАРТ 1`, dis uses `СТАРТ '0'`. A word whose dis address
is N sits at .be word index N-1 (0-based) among generated words. Verified by
pilot: `P6='6'` restored as a label on word index 5 gave 1024/1024 PASS.

Usage:
  python3 tools/restore_dis_labels.py <ZONE> <B|MBE2|ASM> [--dry-run]
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NONWORD = {"Е", "М", "ФИНИШ"}


def parse_dis_labels(asm):
    """Return {dis_addr_int: label} from A#####/D##### declared on words."""
    out = {}
    for line in open(asm, encoding="utf-8", errors="replace"):
        if line.lstrip().startswith("*"):
            continue
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        first = cols[0]
        label = cols[1].strip()
        mnem = cols[2].strip()
        if not mnem or not re.fullmatch(r"[AGD]\d{5}", label):
            continue
        addr = first[:5].strip()
        if not re.fullmatch(r"[0-7]+", addr):
            continue
        out[int(addr, 8)] = label
    return out


def be_word_lines(path):
    """Return list of (word_index, line_number) for the FIRST line of each word."""
    starts = []
    idx = 0
    pending_half = None
    for n, s in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
        t = s.strip()
        if not t or t.startswith("*") or "ЭКВ" in t or "СТАРТ" in t:
            continue
        if t in NONWORD:
            continue
        if t.startswith("КОНД") or t.startswith("ПАМ"):
            starts.append((idx, n))
            idx += 1
            continue
        if re.match(r"^[А-ЯA-Z][А-ЯA-Z0-9]*\s", t):
            if pending_half is None:
                pending_half = n
                starts.append((idx, n))
            else:
                pending_half = None
                idx += 1
            continue
    return starts, idx


def find_asm(zone, prefix):
    import glob
    for pat in (
        f"dis/{prefix}-Z{zone}-L1.asm",
        f"dis/{prefix}-Z{zone}-full.asm",
        f"dis/Z{zone}.asm",
    ):
        hits = glob.glob(os.path.join(ROOT, pat))
        if hits:
            return hits[0]
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
    asm = find_asm(zone, prefix)
    if not asm:
        print(f"Нет dis/asm для зоны {zone}")
        return 1

    labels = parse_dis_labels(asm)
    starts, total = be_word_lines(be)
    by_index = dict(starts)
    print(f"зона {zone}: меток dis={len(labels)}, слов .be={total}")

    # Only labels whose target map to an existing generated word.
    place = []
    for addr, label in sorted(labels.items()):
        if addr == 0:
            continue  # START word has no separate line
        widx = addr - 1
        if widx not in by_index:
            print(f"  ПРОПУСК {label}@{addr:o}: нет слова {widx}")
            continue
        place.append((widx, label, addr))

    lines = open(be, encoding="utf-8").read().splitlines()
    # apply from bottom to top so line numbers stay valid
    for widx, label, addr in sorted(place, reverse=True):
        n = by_index[widx]
        s = lines[n - 1]
        if not s.startswith("        "):
            print(f"  ПРОПУСК {label}: строка {n} уже с меткой: {s[:40]}")
            continue
        lines[n - 1] = label.ljust(8) + s[8:]
    print(f"  вставлено меток: {len(place)}")
    if dry:
        return 0
    open(be, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
