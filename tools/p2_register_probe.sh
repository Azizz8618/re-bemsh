#!/usr/bin/env bash
# P2-REGISTER-PROBE: dynamic register values for PROGRAM 2
# (MACRO-BEMSH 06/78, disk zones 0137-0177).
# Runs on COPIES of the BESM6 images only. Never writes to the
# reference image directories. exit 0 = success, even when the
# scientific result is negative; exit 3 = guard, 4/5 = technical.
#
# Two capture paths are used (both verified against dispak 2.6):
#   A) -tt stream trace: every indexed instruction prints
#      " r[<oct reg>]=<oct value>" (dispak/cu.c:402-404).
#   B) -b debugger: "v" enables okno(3), which lists reg[1..15]
#      at each breakpoint (debug.c:446-455); "i N -" prints a
#      single register, N in octal (debug.c:248-256).
#
# NOTE: dispak numbers the register field in OCTAL, so r[15]
# is M15 (not decimal 15). Index field is 4 bits, hence M1..M7
# and M10..M17 (octal) exist; there is no M8/M9.
set -uo pipefail

WORK=/tmp/.private/azizz/p2-regs
REPO=$(cd "$(dirname "$0")/.." && pwd)
JOB="$WORK/P2REGS-listing.b6"
CMDS="$WORK/p2-bp.cmds"
BPRAW="$WORK/p2-bp.out"
ICMD="$WORK/p2-icmd.out"
TRACE_ERR="$WORK/p2-trace.err"
LIST="$WORK/p2-listing.txt"
PARSER="$WORK/p2reg_parse.py"

fail () { echo "FAIL [$1]: $2" >&2; exit "$1"; }

# ---- 0. Parser module, emitted for unit tests too (no guard here) ----
if [ "${1:-}" = "--emit-parser" ]; then
    cat <<'PYEOF'
"""Parsers for dispak register traces and debugger register dumps.
Embedded in tools/p2_register_probe.sh; unit tests import it via --emit-parser.
All register names are the OCTAL M-numbers used by disbesm6 (M1..M7, M10..M17).
"""
import re
import sys
from collections import Counter

TRACE_LINE_RE = re.compile(r"\A([0-7]{5}):\s+(\S+)")
TRACE_REG_RE = re.compile(r"\br\[([0-7]+)\]=([0-7]+)")
ADDR_RE = re.compile(r"\A\s*-?\s*([0-7]{5}):\s")
ACC_RE = re.compile(r"\A\s*acc\s*=")

# Translator pages from analysis/MEMORY-MAP.md, section 5.
REGIONS = {
    "0147 core @00000": (0o00000, 0o01777),
    "0154 editor @02000": (0o02000, 0o03777),
    "0155 @04000": (0o04000, 0o05777),
    "0161 @24000": (0o24000, 0o25777),
    "0162 @26000": (0o26000, 0o27777),
}


def parse_trace_line(line):
    """Return (addr_oct_str, mnemonic, [(M_label, value), ...]) or None."""
    m = TRACE_LINE_RE.match(line)
    if not m:
        return None
    regs = [(("M" + n), int(v, 8)) for n, v in TRACE_REG_RE.findall(line)]
    return m.group(1), m.group(2), regs


def bp_index_to_label(idx):
    """Map reg[] decimal index (1..15) to octal M-label."""
    if 1 <= idx <= 7:
        return "M%d" % idx
    if 8 <= idx <= 15:
        return "M%d" % (idx + 2)
    return "M?"


def parse_bp_dump(lines):
    """Parse 4 consecutive lines (addr, acc, reg1..8, reg9..15)."""
    if len(lines) < 4:
        return None
    ma = ADDR_RE.match(lines[0])
    if not ma or not ACC_RE.match(lines[1]):
        return None
    r1 = lines[2].split()
    r2 = lines[3].split()
    if len(r1) != 8 or len(r2) != 7:
        return None
    vals = [int(x, 8) for x in r1 + r2]
    regs = {}
    for idx, val in enumerate(vals, start=1):
        regs[bp_index_to_label(idx)] = val
    return ma.group(1), regs


def region_of(addr_oct_str):
    """Return the translator region name for an octal address, or ''."""
    a = int(addr_oct_str, 8)
    for name, (lo, hi) in REGIONS.items():
        if lo <= a <= hi:
            return name
    return ""


def summarize(values):
    """Return (distinct_count, total_hits, top5 list of (value, count))."""
    c = Counter(values)
    return len(c), sum(c.values()), c.most_common(5)


def fmt_oct(n):
    return "%05o" % n


def run_trace(lines):
    """Print the -tt report for an iterable of trace lines."""
    total, zones = 0, Counter()
    glob, regional = {}, {k: {} for k in REGIONS}
    for line in lines:
        rec = parse_trace_line(line)
        if not rec:
            continue
        addr, mnem, regs = rec
        total += 1
        zones[int(addr, 8) // 1024] += 1
        reg = region_of(addr)
        for label, val in regs:
            glob.setdefault(label, []).append(val)
            if reg:
                regional[reg].setdefault(label, []).append(val)
    print("[A] -tt TRACE: instructions =", total)
    print("[A] memory zones (oct) =", " ".join("%03o" % z for z in sorted(zones)))
    print("[A] r[N] OBSERVATIONS (N is octal = M-number):")
    for label in sorted(glob, key=lambda x: (len(x), x)):
        d, n, top = summarize(glob[label])
        print("    %-3s hits=%-6d distinct=%-5d top5=%s" % (
            label, n, d,
            " ".join("%s:%d" % (fmt_oct(v), c) for v, c in top)))
    print("[A] REGIONAL top5 (only translator memory pages):")
    for reg in sorted(regional):
        if not regional[reg]:
            continue
        print("    " + reg)
        for label in sorted(regional[reg], key=lambda x: (len(x), x)):
            d, n, top = summarize(regional[reg][label])
            print("      %-3s hits=%-5d top3=%s" % (
                label, n, " ".join("%s:%d" % (fmt_oct(v), c) for v, c in top[:3])))


def run_bp(bp_path, icmd_path):
    """Print the breakpoint dump report and the explicit 'i N -' reads."""
    lines = open(bp_path, encoding="utf-8", errors="replace").read().splitlines()
    blocks, i = {}, 0
    while i < len(lines):
        rec = parse_bp_dump(lines[i:i + 4])
        if rec:
            addr, regs = rec
            blocks.setdefault(addr, []).append(regs)
            i += 4
        else:
            i += 1
    print("[B] BREAKPOINT register dumps (visual okno(3)):")
    for addr in sorted(blocks):
        print("    %s: hits=%d" % (addr, len(blocks[addr])))
        for regs in blocks[addr][:3]:
            print("      " + " ".join(
                "%s=%s" % (k, fmt_oct(v))
                for k, v in sorted(regs.items(), key=lambda x: (len(x[0]), x[0]))))
    print("[B] explicit 'i N -' reads (N octal = M-number):")
    for line in open(icmd_path, encoding="utf-8", errors="replace"):
        print("    " + line.rstrip())


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "trace"
    if mode == "trace":
        run_trace(sys.stdin)
    elif mode == "bp":
        run_bp(sys.argv[2], sys.argv[3])
PYEOF
    exit 0
fi

# ---- 1. Guard: refuse real image directories ----
if [ -z "${BESM6_PATH:-}" ]; then
    fail 3 "BESM6_PATH not set (a COPY in $WORK is required)"
fi
case ":$BESM6_PATH:" in
    *:/usr/local/share*|*:"$HOME"/.besm6:*|*/.besm6:*)
        fail 3 "BESM6_PATH points at a real image directory: $BESM6_PATH"
        ;;
esac
if [ "$BESM6_PATH" != "$WORK" ]; then
    fail 3 "BESM6_PATH must be exactly '$WORK'"
fi
command -v dispak >/dev/null 2>&1 || fail 4 "dispak not in PATH"
command -v python3 >/dev/null 2>&1 || fail 4 "python3 not in PATH"

# ---- 2. Image copies (reference volumes are read-only) ----
mkdir -p "$WORK" || fail 4 "cannot create $WORK"
for v in 2048 2053 2099 2248; do
    if [ ! -f "$WORK/$v" ]; then
        cp "/usr/local/share/besm6/$v" "$WORK/$v" \
            || fail 4 "cannot copy volume $v"
    fi
done
bash "$0" --emit-parser > "$PARSER" || fail 4 "cannot write parser"

# ---- 3. Minimal listing job (mode 0-0) ----
cat > "$JOB" <<'JOBEOF' || fail 4 "cannot write job"
шифр 419999^
трак 64^
лент 30(2048-6200)^
лент 42(2099)^
лент 43(2248-ЗП)^
ацп 40^
росп 0^
врем 240^
лист 0-37^
вход 4000^
е
в 4000
к 00 010 4003
к 15 24 04000
к 00 066 0001 00 000 0100
с 3000 67
в 14000
а1
ВВД$$$^
ТЕСТ	СТАРТ 1^
	Е^
	М^
	зп '70000'^
	ФИНИШ^
КВЧ$$$^
ТРН$$$^
ЧТКОМП420070^
0-0^
ЗОНМОД433900  0001^
КНЦ$$$^
_$ЕКОНЕЦ
JOBEOF

echo "=== P2-REGISTER-PROBE: PROGRAM 2 (MACRO-BEMSH 06/78) ==="
echo "work: $WORK"
dispak -h 2>&1 | head -1

# ---- 4. Path A: -tt stream trace, register values per instruction ----
# dispak prints the trace to stderr; route it into the pipe and send
# the listing (stdout) to a file: 2>&1 >file | parser.
BESM6_PATH="$WORK" dispak -l -tt "$JOB" 2>&1 >"$LIST" \
    | python3 "$PARSER" trace
TRACE_STATUS=${PIPESTATUS[0]}
[ "$TRACE_STATUS" -eq 0 ] || fail 5 "dispak -tt exit=$TRACE_STATUS"

# ---- 5. Path B: breakpoints and explicit register reads ----
# Requested entries are disk zone:word. dispak uses PHYSICAL memory.
# Per analysis/MEMORY-MAP.md: zone 0147 @00000, zone 0154 @02000.
# 0477/0534 are 0147 aliases; 1322 in memory is the print routine
# (zone 0151:1322 has no known base, so no valid address exists).
python3 - <<'PYEOF' > "$CMDS" || fail 4 "cannot write debugger commands"
print("v")          # okno(3): list all 15 registers at each stop
print("b 477")      # 0147:0477 alias (zone 0147 based at 00000)
print("b 534")      # 0147:0534 dispatcher alias
print("b 1322")     # print routine in memory; 0151 base unknown
print("b 2000")     # 0154 macro editor entry (first insn)
for i in range(30):
    print("g")
print("q")
PYEOF
BESM6_PATH="$WORK" dispak -b -l "$JOB" < "$CMDS" > "$BPRAW" 2>/dev/null \
    || fail 5 "breakpoint run failed"

printf 'i 15 -\ni 16 -\ni 13 -\ni 1 -\nb 2000\ng\ni 15 -\ni 16 -\ni 13 -\nq\n' \
    | BESM6_PATH="$WORK" dispak -b -l "$JOB" > "$ICMD" 2>/dev/null \
    || fail 5 "register-read run failed"

python3 "$PARSER" bp "$BPRAW" "$ICMD"

echo "=== END P2-REGISTER-PROBE (exit 0: run completed) ==="
exit 0
