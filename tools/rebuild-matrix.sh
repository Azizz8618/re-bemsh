#!/usr/bin/env bash
# rebuild-matrix.sh - test zone rebuilding across dispak regimes/modes.
# NEW file. Does not edit rebuild-zone.sh, Makefile or any .be file.
# Every cell uses FRESH COPIES of the images; reference images are read only.
#
#   bash tools/rebuild-matrix.sh --help
#   bash tools/rebuild-matrix.sh --dry-run [ZONE]
#   bash tools/rebuild-matrix.sh [ZONE]
#
# ZONE defaults to 0137. Output artifacts: $WORK/<cell>/{job.b6,listing.out,
# silver.bin,meta.txt}; images are deleted after each cell.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${REBUILD_MATRIX_WORK:-/tmp/.private/azizz/rebuild-matrix}"
SHARE="${BESM6_SHARE:-/usr/local/share/besm6}"
VERIFY="$ROOT/tools/disbesm_verify.sh"

usage() {
    cat <<'EOF'
Usage: bash tools/rebuild-matrix.sh [OPTIONS] [ZONE_OCTAL]

Test zone rebuilding across dispak regimes. Every run uses fresh copies
of the four system images; reference images are never written.

Options:
  -h, --help     show this help and exit 0 (no guard, no dispak needed)
      --dry-run  print the cell matrix and exit 0 (no dispak needed;
                 guard still applies)
  ZONE_OCTAL     zone to rebuild, default 0137

Cell columns:
  TAG MODE ZONMOD LENT43 FLAGS TIMEOUT
  MODE    job output card: 0-0 (listing) or 1-1 (write object module)
  ZONMOD  yes = include ЗОНМОД433900  0001 card, no = drop it
  LENT43  tape-43 destination card body, e.g. 2248-ЗП
  FLAGS   dispak CLI flags, e.g. -l, (empty), -l -tt, -l -s
  TIMEOUT seconds allowed for dispak (0 = default 300)

Environment:
  REBUILD_MATRIX_WORK  work dir (default /tmp/.private/azizz/rebuild-matrix)
  BESM6_SHARE          read-only source of image copies
  REBUILD_MATRIX_CELLS run only the named cells (space separated)

Guard (exit 3): WORK or incoming BESM6_PATH must not point at
/usr/local/share, ~/.besm6 or .../EC5061... .
EOF
}

# ---------------------------------------------------------------------------
# GUARD. --help is exempt so it works anywhere without dispak.
# ---------------------------------------------------------------------------
[ $# -ge 1 ] && { [ "$1" = "-h" ] || [ "$1" = "--help" ]; } && { usage; exit 0; }

forbidden() {
    local p="$1"
    case "$p" in
        /usr/local/share*|"$HOME"/.besm6*|*/.besm6*|*/EC5061*) return 0 ;;
    esac
    return 1
}
refuse() { echo "REFUSE: $1" >&2; exit 3; }

for p in "$WORK" "${BESM6_PATH:-}"; do
    [ -n "$p" ] && forbidden "$p" && \
        refuse "path '$p' points at a real image directory (/usr/local/share, ~/.besm6, EC5061)"
done

# ---------------------------------------------------------------------------
# CELL MATRIX. Order matters: A0 is the reference baseline.
# ---------------------------------------------------------------------------
CELL_SPECS='
A0-base|0-0|yes|2248-ЗП|-l|0
A1-write11|1-1|yes|2248-ЗП|-l|0
A2-nozonmod|0-0|no|2248-ЗП|-l|0
A3-write11-nozon|1-1|no|2248-ЗП|-l|0
B1-cyrillic|0-0|yes|2248-ЗП||0
B2-trace|0-0|yes|2248-ЗП|-l -tt|0
B3-stats|0-0|yes|2248-ЗП|-l -s|0
B4-noinsnchk|0-0|yes|2248-ЗП|-l --no-insn-check|0
B5-break|0-0|yes|2248-ЗП|-l -b|10
C1-alt43name|0-0|yes|2249-ЗП|-l|0
C2-tape2099|0-0|yes|2099-ЗП|-l|0
C3-nozp|0-0|yes|2248|-l|0
'

cell_fields() {
    local tag="$1" line
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        [ "${line%%|*}" = "$tag" ] && { printf '%s\n' "$line"; return 0; }
    done <<< "$CELL_SPECS"
    return 1
}

print_matrix() {
    echo "Cell            Mode Zonmod Lent43        Flags                Tmo"
    echo "--------------- ---- ------ ------------- -------------------- ---"
    local line
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        local IFS='|'; read -r tag mode zonmod lent flags tmo <<< "$line"
        printf '%-15s %-4s %-6s %-13s %-20s %s\n' \
            "$tag" "$mode" "$zonmod" "$lent" "${flags:--}" "$tmo"
    done <<< "$CELL_SPECS"
    echo "CELLS=$(printf '%s\n' "$CELL_SPECS" | grep -c '|')"
}

# --dry-run: guard already passed above; no dispak needed.
if [ "${1:-}" = "--dry-run" ]; then
    print_matrix
    exit 0
fi

# Tool availability is only required for a real run, never for --help/--dry-run.
command -v dispak >/dev/null 2>&1 || { echo "REFUSE: dispak not in PATH" >&2; exit 4; }
command -v python3 >/dev/null 2>&1 || { echo "REFUSE: python3 not in PATH" >&2; exit 4; }

RAW_ZONE="${1:-0137}"
[[ "$RAW_ZONE" =~ ^[0-7]+$ ]] || {
    echo "REFUSE: zone must be octal (got '$RAW_ZONE')" >&2; exit 2; }
ZONE="$(printf '%04o' "$((8#$RAW_ZONE))")"

BE=""
for cand in "$ROOT/bemsh/MBE-Z${ZONE}-L1.be" "$ROOT/bemsh/MBE-Z${ZONE}.be"; do
    [ -f "$cand" ] && { BE="$cand"; break; }
done
GOLD="$ROOT/gold/MBE-Z${ZONE}-L1.bin"
for f in "$BE" "$GOLD" "$VERIFY"; do
    [ -n "$f" ] && [ -f "$f" ] || { echo "No file: $f" >&2; exit 1; }
done

mkdir -p "$WORK" || { echo "Cannot create $WORK" >&2; exit 4; }
echo "WORK=$WORK  SHARE=$SHARE (read only)  ZONE=$ZONE"
print_matrix
echo

# ---------------------------------------------------------------------------
# Job generation. Reuses the proven ВВД$$$ каркас from rebuild-zone.sh;
# only MODE, ZONMOD and LENT43 are parameterised.
# ---------------------------------------------------------------------------
gen_job() {
    local be="$1" out="$2" mode="$3" zonmod="$4" lent="$5"
    python3 - "$be" "$out" "$mode" "$zonmod" "$lent" <<'PY'
import sys
be, out, mode, zonmod, lent = sys.argv[1:6]
lines = [l for l in open(be, encoding="utf-8").read().splitlines()
         if not l.lstrip().startswith("*")]
job = ["шифр 419999^", "трак 64^", "лент 30(2048-6200)^", "лент 42(2099)^",
       "лент 43(%s)^" % lent, "ацп 40^", "росп 0^", "врем 240^",
       "лист 0-37^", "вход 4000^", "е", "в 4000", "к 00 010 4003",
       "к 15 24 04000", "к 00 066 0001 00 000 0100", "с 3000 67",
       "в 14000", "а1", "ВВД$$$^"]
job += [l + "^" for l in lines]
job += ["КВЧ$$$^", "ТРН$$$^", "ЧТКОМП420070^", mode + "^"]
if zonmod == "yes":
    job.append("ЗОНМОД433900  0001^")
job += ["КНЦ$$$^", "_$ЕКОНЕЦ"]
open(out, "w", encoding="utf-8").write("\n".join(job) + "\n")
PY
}

# ---------------------------------------------------------------------------
# Listing parser + byte compare. Word-extraction logic is copied verbatim
# from the proven tools/rebuild-zone.sh (0-0, СТАРТ base selection).
# ---------------------------------------------------------------------------
parse_and_compare() {
    python3 - "$@" <<'PY'
import re, sys
listing, gold, silver, be = sys.argv[1:5]
def start_base(be_path):
    for line in open(be_path, encoding="utf-8"):
        if line.lstrip().startswith("*"):
            continue
        m = re.search(r"\bСТАРТ\b\s+'?([0-7]+)'?", line)
        if m:
            return int(m.group(1), 8)
    return 1
HEADER_BASE = start_base(be)
RE_WORD = re.compile(r"^([0-7]{16})\b")
RE_CMD  = re.compile(r"^(\d{2})\s+(\d{2,3})\s+(\d{4,5})\b")
words, pending = {}, None
for line in open(listing, encoding="utf-8", errors="replace"):
    a = line[25:30]
    rest = line[31:].lstrip()
    addr = int(a, 8) if re.fullmatch(r"\d{5}", a) else (None if not a.strip() else "bad")
    if addr == "bad":
        continue
    m = RE_WORD.match(rest)
    if m:
        if addr is not None:
            words[addr] = int(m.group(1), 8); pending = None
        continue
    m = RE_CMD.match(rest)
    if m:
        reg, op, af = int(m.group(1), 8), int(m.group(2), 8), int(m.group(3), 8)
        half = (reg << 20) | (op << (15 if len(m.group(3)) == 5 else 12)) | af
        if addr is not None:
            pending = addr; words[addr] = half << 24
        elif pending is not None:
            words[pending] |= half; pending = None
g = open(gold, "rb").read(); NW = len(g) // 6
def matched(base):
    return sum(1 for i in range(NW)
               if words.get(base + i) == int.from_bytes(g[i*6:(i+1)*6], "big"))
BASE = 1
if HEADER_BASE != 1 and matched(HEADER_BASE) > matched(1):
    BASE = HEADER_BASE
ok = bad = 0; out = bytearray()
for i in range(NW):
    got = words.get(BASE + i)
    if got is None:
        bad += 1; out += b"\x00" * 6; continue
    want = int.from_bytes(g[i*6:i*6+6], "big")
    ok += (got == want); bad += (got != want)
    out += got.to_bytes(6, "big")
open(silver, "wb").write(out)
byte_diff = sum(1 for a, b in zip(out, g) if a != b) + abs(len(out) - len(g))
err = "?"
for line in open(listing, encoding="utf-8", errors="replace"):
    m = re.search(r"ШИБ[ОO][КK]=(\d+)", line)
    if m:
        err = m.group(1); break
print("WORDS total=%d match=%d diff=%d BASE=%o BYTE_DIFF=%d ERRS=%s" %
      (NW, ok, bad, BASE, byte_diff, err))
PY
}

md5() { md5sum "$1" 2>/dev/null | cut -d' ' -f1; }

SELECTED="${REBUILD_MATRIX_CELLS:-}"
run_cell() {
    local line="$1"
    local IFS='|'; read -r tag mode zonmod lent flags tmo <<< "$line"
    if [ -n "$SELECTED" ] && ! echo " $SELECTED " | grep -q " $tag "; then
        return 0
    fi
    [ "$tmo" = "0" ] && tmo=300
    local cd="$WORK/$tag"; local imgs="$cd/images"
    mkdir -p "$imgs"
    echo "--- CELL $tag: mode=$mode zonmod=$zonmod lent43=$lent flags='$flags' ---"
    for v in 2048 2053 2099 2248; do
        [ -f "$SHARE/$v" ] || { echo "  No image $SHARE/$v"; return 1; }
        cp "$SHARE/$v" "$imgs/$v"
    done
    # A numerically named copy of 2248: tests another tape-43 destination
    # without using a non-octal letter in the card (which dispak rejects).
    [ "$lent" = "2249-ЗП" ] && cp "$imgs/2248" "$imgs/2249"
    gen_job "$BE" "$cd/job.b6" "$mode" "$zonmod" "$lent"

    local before after; before=$(for v in 2048 2053 2099 2248; do md5 "$imgs/$v"; done | tr '\n' ' ')
    local rc=0
    if [ "$flags" = "-l -tt" ]; then
        # stdin from /dev/null: -b enters the debugger and would otherwise
        # consume the driver loop's here-string (swallowing later cells).
        BESM6_PATH="$imgs" timeout "$tmo" dispak $flags "$cd/job.b6" \
            < /dev/null > "$cd/listing.out" 2> "$cd/trace.err" || rc=$?
        local tl; tl=$(wc -l < "$cd/trace.err" 2>/dev/null || echo 0)
        echo "  TRACE lines=$tl (streamed to file, deleted after count)"
        rm -f "$cd/trace.err"
    else
        BESM6_PATH="$imgs" timeout "$tmo" dispak $flags "$cd/job.b6" \
            < /dev/null > "$cd/listing.out" 2>&1 || rc=$?
    fi
    after=$(for v in 2048 2053 2099 2248; do md5 "$imgs/$v"; done | tr '\n' ' ')
    local changed="no"; [ "$before" != "$after" ] && changed="yes"

    local lsize; lsize=$(stat --format='%s' "$cd/listing.out" 2>/dev/null || echo 0)
    local words_line="PARSE_FAIL"
    if [ "$lsize" -gt 0 ] && [ "$rc" -eq 0 ]; then
        words_line=$(parse_and_compare "$cd/listing.out" "$GOLD" \
                         "$cd/silver.bin" "$BE")
    fi
    local verdict="NO_LISTING"
    [ "$lsize" -gt 0 ] && verdict="LISTING"
    echo "  rc=$rc listing_bytes=$lsize image_changed=$changed"
    echo "  $words_line"
    {
        echo "TAG=$tag MODE=$mode ZONMOD=$zonmod LENT43=$lent FLAGS=$flags"
        echo "RC=$rc LISTING_BYTES=$lsize IMAGE_CHANGED=$changed"
        echo "$words_line"
        echo "MD5_BEFORE=$before"
        echo "MD5_AFTER=$after"
    } > "$cd/meta.txt"
    # Keep artifacts, drop image copies to stay inside tight tmpfs.
    rm -f "$imgs/2048" "$imgs/2053" "$imgs/2099" "$imgs/2248" "$imgs/2249"
    rmdir "$imgs" 2>/dev/null || true
}

while IFS= read -r spec; do
    [ -z "$spec" ] && continue
    run_cell "$spec"
done <<< "$CELL_SPECS"

echo
echo "=== matrix done; artifacts under $WORK ==="
