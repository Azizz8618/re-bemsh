#!/usr/bin/env python3
"""Map 1024-word RAM pages of a dispak snapshot to gold disk zones.

A snapshot is the raw stdout of a `dispak -b` run after 4096 debugger
dump commands of the form "NNNNN b" (dispak/debug.y:124-133). Each
such command prints 8 words; each word is 6 octal byte groups of 3
digits ("%03o "). The dump commands are interleaved with banner text
and debugger messages, which the parser ignores.

Only stdlib is used. No gold file, image, or repository artifact is
modified: every input is opened read-only.
"""
import argparse
import glob
import os
import re
import sys
from collections import Counter

PAGE_WORDS = 1024
N_PAGES = 32
EXPECTED_WORDS = N_PAGES * PAGE_WORDS

# One word = 6 octal bytes. Optional leading debugger prompt "-".
WORD_LINE_RE = re.compile(
    r"^\s*-?\s*((?:[0-7]{3}\s+){5}[0-7]{3})\s*$"
)
AA = tuple([0xAA] * 6)
FIVE = tuple([0x55] * 6)


def parse_snapshot(text, expected=EXPECTED_WORDS):
    """Return a list of `expected` words, each a tuple of 6 byte ints.

    Lines that are not pure 6-byte octal dumps are ignored. Raises
    ValueError when the number of recovered words differs from the
    requested count.
    """
    words = []
    for line in text.splitlines():
        m = WORD_LINE_RE.match(line)
        if not m:
            continue
        groups = m.group(1).split()
        if len(groups) != 6:
            continue
        words.append(tuple(int(g, 8) for g in groups))
    if len(words) != expected:
        raise ValueError(
            "expected %d words, got %d" % (expected, len(words))
        )
    return words


def load_zones(gold_dir):
    """Load all gold/*.bin zone dumps as {label: [word, ...]}.

    The full-image file MBE-full.bin is skipped. Every other *.bin
    file must be exactly 1024 words; shorter or longer files are
    ignored so a malformed fixture cannot corrupt the analysis.
    """
    zones = {}
    pattern = re.compile(r"(ASM|MBE2|MBE)-Z(\d+)-L1\.bin$")
    for path in sorted(glob.glob(os.path.join(gold_dir, "*.bin"))):
        base = os.path.basename(path)
        m = pattern.search(base)
        if not m:
            continue
        data = open(path, "rb").read()
        words = [
            tuple(data[i * 6:(i + 1) * 6])
            for i in range(len(data) // 6)
        ]
        if len(words) != PAGE_WORDS:
            continue
        zones["%s-%s" % (m.group(1), m.group(2))] = words
    return zones


def is_fill_zone(words):
    """True for an AA/55 chessboard fill zone (PROGRAM2-REGISTERS 3)."""
    counts = Counter(words)
    if len(counts) > 4:
        return False
    top, _ = counts.most_common(1)[0]
    return top in (AA, FIVE)


def is_zero_table(words):
    """True for a low-entropy, mostly-zero table zone."""
    counts = Counter(words)
    top, n = counts.most_common(1)[0]
    return top == tuple([0] * 6) and n >= 500


def is_zero_page(page):
    """True for a page that is at least 900 all-zero words (empty RAM)."""
    zeros = tuple([0] * 6)
    return sum(1 for w in page if w == zeros) >= 900


def match_count(page, zone):
    """Number of word positions where page and zone are byte-identical."""
    return sum(1 for a, b in zip(page, zone) if a == b)


def page_matches(page, zones):
    """Return [(count, label), ...] sorted by descending exact count."""
    return sorted(
        ((match_count(page, zw), name) for name, zw in zones.items()),
        key=lambda t: (-t[0], t[1]),
    )


def classify(count, second, fill, zero, zeropage=False):
    """Return a confidence label for one page-to-zone match."""
    if zeropage:
        return "ZERO"
    if fill:
        return "FILL"
    if count < 100:
        return "NONE"
    if abs(count - second) <= 20:
        return "AMBIG"
    if zero:
        return "TABLE"
    if count == PAGE_WORDS:
        return "EXACT"
    if count >= 990:
        return "HIGH"
    if count >= 500:
        return "MEDIUM"
    return "LOW"


def build_table(snapshot, mem, zones):
    """Return one result row per 1024-word page of the snapshot."""
    rows = []
    for page_no in range(N_PAGES):
        page = mem[page_no * PAGE_WORDS:(page_no + 1) * PAGE_WORDS]
        scored = page_matches(page, zones)
        count, name = scored[0]
        second_count, second_name = (
            scored[1] if len(scored) > 1 else (0, "-")
        )
        zone_words = zones[name]
        conf = classify(
            count, second_count,
            is_fill_zone(zone_words), is_zero_table(zone_words),
            is_zero_page(page),
        )
        rows.append({
            "snapshot": snapshot,
            "page": page_no,
            "base": "%05o" % (page_no * PAGE_WORDS),
            "zone": name,
            "count": count,
            "second_zone": second_name,
            "second_count": second_count,
            "confidence": conf,
        })
    return rows


def render_markdown(rows):
    """Render result rows as a fixed-width-friendly markdown table."""
    out = [
        "| snapshot | page | base | zone | exact/1024 | "
        "2nd zone | 2nd | conf |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            "| %s | %02o | %s | %s | %d | %s | %d | %s |" % (
                r["snapshot"], r["page"], r["base"], r["zone"],
                r["count"], r["second_zone"], r["second_count"],
                r["confidence"],
            )
        )
    return "\n".join(out)


def summarize(rows):
    """Return (found set, excluded set) of zone labels for a snapshot."""
    found, excluded = set(), set()
    for r in rows:
        if r["confidence"] in ("EXACT", "HIGH", "MEDIUM", "GOOD"):
            found.add(r["zone"])
        elif r["confidence"] in ("FILL", "TABLE"):
            excluded.add(r["zone"])
    return found, excluded


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot", nargs="+",
                    help="raw dispak snapshot file(s)")
    ap.add_argument("--gold-dir", default=None,
                    help="directory with gold/*-L1.bin dumps")
    ap.add_argument("--label", action="append", default=None,
                    help="override snapshot label (one per file)")
    args = ap.parse_args(argv)

    if args.gold_dir is None:
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        args.gold_dir = os.path.join(repo, "gold")
    zones = load_zones(args.gold_dir)
    if not zones:
        sys.exit("no gold zones found in %s" % args.gold_dir)

    all_rows = []
    for i, path in enumerate(args.snapshot):
        text = open(path, encoding="utf-8", errors="replace").read()
        try:
            mem = parse_snapshot(text)
        except ValueError as exc:
            sys.exit("snapshot %s: %s" % (path, exc))
        label = (
            args.label[i] if args.label and i < len(args.label)
            else os.path.basename(path)
        )
        rows = build_table(label, mem, zones)
        all_rows.extend(rows)
        found, excluded = summarize(rows)
        print("=== %s (%s) ===" % (label, path))
        print(render_markdown(rows))
        print("found zones: %s" % (
            " ".join(sorted(found)) if found else "(none)"))
        print("excluded (fill/table): %s" % (
            " ".join(sorted(excluded)) if excluded else "(none)"))
        print()
    print("zones loaded from %s: %d" % (args.gold_dir, len(zones)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
