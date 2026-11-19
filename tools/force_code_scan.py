#!/usr/bin/env python3
"""Forced-code recovery scan of all 69 transport-2348 zone dumps.

Method (proven on zones 0055-0060, see docs/SEMANTIC/Z0055.md):

  1. Read a read-only gold/*-Z<zone>-L1.bin (1024 x 48-bit words).  Decode
     BOTH 24-bit halves of every word with siprod_asm.decode (the OPS table
     from re-siprod/tools/siprod_asm.py).  A half is "valid" when decode()
     returns a named opcode (name is not None and kind != 'illegal').
     valid% = valid_halves / 2048 * 100.

  2. Detect the checkerboard FILL separately.  Fill words are 0xAAAAAA... /
     0x555555... with the 0xDB6DB6 phase-shift terminator; both halves
     decode as legal opcodes (слиа М12 / вчп М5 / по М15), so decodability
     ALONE would call them code.  Rule: >=95% of halves in
     {0xAAAAAA, 0x555555, 0xDB6DB6} AND <=8 distinct words.

  3. For non-fill zones, force every word address 0..01777 as W_CODE via
     a disbesm6 symbol table ("%o 2 -") and run

         disbesm6 -a0 -e0 -n<symtab> <gold-bin>

     Compare the forced listing with the original dis/<zone>.asm:
     count `конд` lines and decoded-instruction lines before/after.

  4. Classify: FILL / DATA / ALREADY-CODE / CODE / MIXED using the rules
     in classify() below (documented in docs/FORCED-CODE-SCAN.md).

  HONEST CAVEAT: a high valid% and a full forced listing do NOT prove that
  a cell was ever executed.  Byte patterns (zeros, AA/55, repeated data
  words) and independent evidence (CALL/return pairs, GOST text stamps,
  CROSSREF) decide code vs data.  The tool reports measurements, not truth.

Usage:
    python3 tools/force_code_scan.py [--all | --zone 0137] [--out-dir dis-forced]
    python3 tools/force_code_scan.py --all --markdown
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

# ── configuration ──────────────────────────────────────────────────────────
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS_DIR)
SIPROD_TOOLS = os.environ.get(
    "SIPROD_TOOLS", "/home/azizz/Yandex.Disk/re-siprod/tools"
)
GOLD = os.path.join(REPO, "gold")
DIS = os.path.join(REPO, "dis")
SEMANTIC = os.path.join(REPO, "docs", "SEMANTIC")
DEFAULT_OUT = os.path.join(REPO, "dis-forced")
DISBESM6 = os.environ.get("DISBESM6", "disbesm6")

sys.path.insert(0, SIPROD_TOOLS)
try:
    import siprod_asm
except ImportError as exc:  # pragma: no cover - environment failure
    sys.exit("force_code_scan: cannot import siprod_asm from %s: %s"
             % (SIPROD_TOOLS, exc))

# 24-bit fill halves (checkerboard AA/55 and the phase-shift terminator)
FILL_HALVES = (0xAAAAAA, 0x555555, 0xDB6DB6)

# Control-flow / call / stop mnemonics (lower-case names from OPS)
FLOW_MNEMONICS = {
    "пв", "пб", "по", "пе", "пио", "пино", "пио36", "цикл",
    "выпр", "стоп", "э74",
}

# Mnemonics counted as decoded instructions in a listing (not data markers)
DATA_MARKERS = {"конд", "пам", "экв", "nop"}
OPNAMES = set(n.lower() for n, _c, _m, _k in siprod_asm.OPS)

# Phrases in docs/SEMANTIC/Z<zone>.md §1 that describe a zone as non-code.
# The regex is applied to whitespace-normalised section-1 text; it is a
# *flag for manual review*, never a proof that the doc is wrong.
NONCODE_PHRASES = (
    r"почти вс[яе].{0,24}данн",
    r"\bНЕ исполняемый код\b",
    r"\bне исполняемый код\b",
    r"\bКод/текстов НЕТ\b",
    r"вс[её]\s*`?конд`?",
    r"вспомогательная таблица",
    r"таблица классов символов",
    r"ТАБЛИЦА ДЕСКРИПТОРОВ",
    r"отладочных таблиц",
    r"внутренних таблиц",
    r"чисто табличные данные",
    r"почти целиком занята числовыми таблицами",
    r"не содержит ни текста",
    r"ни исполняемого кода",
    r"почти пустая",
    r"свободная зона",
    r"только START-слово",
    r"единственное код-слово",
    r"\b\d+ слов кода\b",
    r"\b\d+ код-слов\b",
)
NONCODE_RE = re.compile("|".join("(?:%s)" % p for p in NONCODE_PHRASES))

# A doc that already reports the forced-W_CODE experiment has already
# received the correction (0055-0060, 0561); do not flag it again.
ALREADY_FIXED_RE = re.compile(
    r"принудительн|как W_CODE|W_CODE на все адреса|"
    r"принудительной разметке", re.I)


# ── helpers ────────────────────────────────────────────────────────────────
def zone_paths():
    """Return [(zone, gold_path, orig_asm_path)] for every zone dump."""
    out = []
    for name in sorted(os.listdir(GOLD)):
        m = re.match(r"^(?:ASM|MBE|MBE2)-Z(\d{4})-L1\.bin$", name)
        if not m:
            continue
        z = m.group(1)
        out.append((z,
                    os.path.join(GOLD, name),
                    os.path.join(DIS, name[:-4] + ".asm")))
    return out


def read_words(path):
    """Read a 6144-byte zone as 1024 big-endian 48-bit words."""
    data = open(path, "rb").read()          # read-only
    if len(data) % 6:
        raise ValueError("%s: size %d is not a multiple of 6"
                         % (path, len(data)))
    return [int.from_bytes(data[i:i + 6], "big")
            for i in range(0, len(data), 6)]


def half_stats(words):
    """valid%, unique-word count, fill% and mnemonic histogram of halves."""
    valid = 0
    fill = 0
    names = Counter()
    for w in words:
        for half in (w >> 24, w & 0xFFFFFF):
            dec = siprod_asm.decode(half)
            if dec["name"] is not None and dec["kind"] != "illegal":
                valid += 1
                names[dec["name"]] += 1
            if half in FILL_HALVES:
                fill += 1
    total = 2 * len(words)
    return {
        "valid_pct": 100.0 * valid / total,
        "valid": valid,
        "total_halves": total,
        "unique": len(set(words)),
        "fill_pct": 100.0 * fill / total,
        "names": names,
    }


def listing_stats(text):
    """Count `конд` lines and decoded-instruction lines in a disbesm6 listing."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)   # strip ANSI if any
    lines = text.splitlines()
    kond = 0
    insn = 0
    for line in lines:
        if "конд" in line:
            kond += 1
        for tok in re.split(r"\s+", line):
            low = tok.lower()
            if low in OPNAMES:
                insn += 1
                break
    return {"kond": kond, "insn": insn, "lines": len(lines)}


def forced_listing(gold_path, symtab_fd, symtab_path):
    """Run disbesm6 with a W_CODE-everywhere symbol table."""
    # (re)write the shared symbol table for this run
    os.lseek(symtab_fd, 0, os.SEEK_SET)
    os.ftruncate(symtab_fd, 0)
    os.write(symtab_fd, b"".join(
        ("%05o 2 -\n" % addr).encode("ascii") for addr in range(1024)))
    os.fsync(symtab_fd)
    res = subprocess.run(
        [DISBESM6, "-a0", "-e0", "-n" + symtab_path, gold_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if res.returncode and not res.stdout:
        sys.stderr.write("force_code_scan: disbesm6 failed on %s: %s\n"
                         % (gold_path, res.stderr.decode("utf-8", "replace")))
    return res.stdout.decode("utf-8", "replace")


def doc_flags_noncode(zone):
    """True when the zone's semantic doc §1 describes it as non-code."""
    path = os.path.join(SEMANTIC, "Z%s.md" % zone)
    if not os.path.exists(path):
        return False
    txt = open(path, encoding="utf-8", errors="replace").read()
    if ALREADY_FIXED_RE.search(txt):
        return False
    m = re.search(r"## 1\..*?\n(.*?)(?=\n## |\Z)", txt, re.S)
    if not m:
        return False
    section = re.sub(r"\s+", " ", m.group(1))
    return bool(NONCODE_RE.search(section))


def classify(stats):
    """Classify one zone from its measurements.

    Order matters: FILL first (byte pattern), then DATA (dominant single
    opcode + almost no control flow, or a near-uniform repeated word),
    then ALREADY-CODE (original listing already traced the code), then
    CODE (was overwhelmingly `конд`), else MIXED.
    """
    hp = stats["half"]
    orig = stats["before"]
    top_pct = stats["top_pct"]
    flow = stats["flow"]
    calls = stats["calls"]

    if hp["fill_pct"] >= 95.0 and hp["unique"] <= 8:
        return "FILL"
    if hp["unique"] <= 8 or (top_pct >= 70.0 and flow < 150 and calls <= 30):
        return "DATA"
    kond_ratio = 100.0 * orig["kond"] / max(orig["lines"], 1)
    if kond_ratio < 50.0:
        return "ALREADY-CODE"
    if kond_ratio >= 85.0:
        return "CODE"
    return "MIXED"


# ── core scan ──────────────────────────────────────────────────────────────
def scan_zone(zone, gold_path, orig_asm_path, out_dir, want_listing,
              symtab_fd, symtab_path):
    words = read_words(gold_path)
    hp = half_stats(words)

    orig_text = ""
    if os.path.exists(orig_asm_path):
        orig_text = open(orig_asm_path, encoding="utf-8",
                         errors="replace").read()
    before = listing_stats(orig_text)

    forced_text = forced_listing(gold_path, symtab_fd, symtab_path)
    after = listing_stats(forced_text)

    names = Counter()
    for line in forced_text.splitlines():
        for tok in re.split(r"\s+", line):
            low = tok.lower()
            if low in OPNAMES:
                names[low] += 1
                break
    top = names.most_common(5)
    total_insn = sum(names.values())
    top_pct = 100.0 * top[0][1] / max(total_insn, 1) if top else 0.0
    flow = sum(names[k] for k in FLOW_MNEMONICS)
    calls = names.get("пв", 0)

    stats = {
        "zone": zone,
        "half": hp,
        "before": before,
        "after": after,
        "top": top,
        "top_pct": top_pct,
        "flow": flow,
        "calls": calls,
    }
    stats["class"] = classify(stats)
    stats["doc_fix"] = (stats["class"] in ("CODE", "MIXED")
                        and doc_flags_noncode(zone))

    # Save a full forced listing only for zones whose class is CODE or
    # MIXED (the ones that were mostly `конд` in the original listing).
    # Metrics for all other zones are still computed and reported above.
    if want_listing and stats["class"] in ("CODE", "MIXED"):
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "Z%s.asm" % zone)
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(forced_text)
        stats["out"] = out_path
    return stats


def format_table(rows, markdown=False):
    hdr = ("zone", "valid%", "uniq", "fill%", "top mnemonics",
           "конд b→a", "insn b→a", "class", "doc fix?")
    if markdown:
        print("| " + " | ".join(hdr) + " |")
        print("|" + "|".join(["---"] * len(hdr)) + "|")
        for r in rows:
            h = r["half"]
            top = ", ".join("%s:%d" % (n, c) for n, c in r["top"][:3])
            print("| %s | %.1f | %d | %.1f | %s | %d→%d | %d→%d | %s | %s |" % (
                r["zone"], h["valid_pct"], h["unique"], h["fill_pct"],
                top, r["before"]["kond"], r["after"]["kond"],
                r["before"]["insn"], r["after"]["insn"],
                r["class"], "YES" if r["doc_fix"] else "no"))
        return
    widths = [6, 7, 5, 6, 34, 12, 12, 13, 9]
    fmt = "  ".join("%%-%ds" % w for w in widths)
    print(fmt % hdr)
    print(fmt % tuple("-" * (w - 2) for w in widths))
    for r in rows:
        h = r["half"]
        top = ", ".join("%s:%d" % (n, c) for n, c in r["top"][:3])
        print(fmt % (
            r["zone"], "%.1f" % h["valid_pct"], str(h["unique"]),
            "%.1f" % h["fill_pct"], top[:34],
            "%d→%d" % (r["before"]["kond"], r["after"]["kond"]),
            "%d→%d" % (r["before"]["insn"], r["after"]["insn"]),
            r["class"], "YES" if r["doc_fix"] else "no"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sel = ap.add_mutually_exclusive_group()
    sel.add_argument("--all", action="store_true",
                     help="scan all 69 zone dumps (default)")
    sel.add_argument("--zone", metavar="Z",
                     help="scan one zone, octal (e.g. 0137 or 137)")
    ap.add_argument("--out-dir", default=DEFAULT_OUT,
                    help="directory for forced listings (default: dis-forced)")
    ap.add_argument("--markdown", action="store_true",
                    help="print the table as Markdown")
    ap.add_argument("--no-listings", action="store_true",
                    help="do not write forced .asm files")
    args = ap.parse_args(argv)

    all_zones = zone_paths()
    if args.zone:
        z = args.zone.lstrip("Zz").zfill(4)
        selected = [p for p in all_zones if p[0] == z]
        if not selected:
            sys.exit("force_code_scan: unknown zone %s" % args.zone)
    else:
        selected = all_zones

    out_dir = args.out_dir
    rows = []
    with tempfile.TemporaryDirectory(prefix="force-code-") as td:
        symtab_path = os.path.join(td, "all-code.tab")
        fd = os.open(symtab_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            for zone, gold_path, orig_asm in selected:
                # write listings for CODE and MIXED zones (the deliverable);
                # metrics are computed for every zone.
                rows.append(scan_zone(
                    zone, gold_path, orig_asm, out_dir,
                    want_listing=(not args.no_listings),
                    symtab_fd=fd, symtab_path=symtab_path))
        finally:
            os.close(fd)

    format_table(rows, markdown=args.markdown)
    counts = Counter(r["class"] for r in rows)
    print()
    print("summary:", ", ".join("%s=%d" % (k, v)
                                for k, v in sorted(counts.items())))
    fix = [r["zone"] for r in rows if r["doc_fix"]]
    print("need doc fix (%d): %s" % (len(fix), " ".join(fix) if fix else "-"))
    if not args.no_listings:
        written = [r["zone"] for r in rows if "out" in r]
        print("forced listings written to %s: %d" % (out_dir, len(written)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
