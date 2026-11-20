#!/usr/bin/env bash
# RAM-SNAPSHOT: capture full RAM dumps of a real dispak run.
#
# Each snapshot is one deterministic dispak run on COPIES of the BESM6
# images in $WORK. A single physical breakpoint is set, execution is
# resumed once, and the whole 32768-word core is dumped with 4096
# debugger commands of the form "NNNNN b" (dispak/debug.y:124-133).
# The raw file is written to $WORK/snap-<label>.raw.
#
# exit 0 - all snapshots captured and verified (even if a scientific
#          result later turns out negative)
# exit 3 - guard refused a real image directory
# exit 4 - technical/setup error
# exit 5 - a dump was incomplete or dispak failed
set -uo pipefail

WORK=/tmp/.private/azizz/ram-snap
REPO=$(cd "$(dirname "$0")/.." && pwd)
JOB="$WORK/RAM-listing.b6"
MAPPER="$REPO/tools/ram_page_map.py"
MANIFEST="$WORK/snapshot-manifest.txt"

fail () { echo "FAIL [$1]: $2" >&2; exit "$1"; }

# ---- 0. Guard: work ONLY on copies in $WORK ----
if [ -z "${BESM6_PATH:-}" ]; then
    fail 3 "BESM6_PATH not set (a COPY in $WORK is required)"
fi
case ":$BESM6_PATH:" in
    *:/usr/local/share*|*:"$HOME"/.besm6:*|*/.besm6:*|*/EC5061*)
        fail 3 "BESM6_PATH points at a real image directory: $BESM6_PATH"
        ;;
esac
if [ "$BESM6_PATH" != "$WORK" ]; then
    fail 3 "BESM6_PATH must be exactly '$WORK'"
fi
command -v dispak >/dev/null 2>&1 || fail 4 "dispak not in PATH"
command -v python3 >/dev/null 2>&1 || fail 4 "python3 not in PATH"
[ -f "$MAPPER" ] || fail 4 "no mapper at $MAPPER"

# ---- 1. Copies of the reference volumes (read-only source) ----
mkdir -p "$WORK" || fail 4 "cannot create $WORK"
for v in 2048 2053 2099 2248; do
    if [ ! -f "$WORK/$v" ]; then
        cp "/usr/local/share/besm6/$v" "$WORK/$v" \
            || fail 4 "cannot copy volume $v"
    fi
done

# ---- 2. Minimal BEMSH listing job (mode 0-0), proven deck ----
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

# ---- 3. Snapshot targets ----
# label: physical breakpoint address (octal). "boot" has no breakpoint:
# -b already stops before the first instruction at 00010.
TARGETS=(
    "boot:-"
    "z3651:3651"
    "z1322:1322"
    "z04000:4000"
    "z02000:2000"
    "z06000:6000"
    "z70000:70000"
    "z74000:74000"
)

: > "$MANIFEST" || fail 4 "cannot write manifest"
echo "=== RAM-SNAPSHOT: full core dumps of a real dispak run ==="
echo "work: $WORK"
echo "job:  $JOB"
dispak -h 2>&1 | head -1

for target in "${TARGETS[@]}"; do
    label=${target%%:*}
    addr=${target#*:}
    cmds="$WORK/$label.cmds"
    raw="$WORK/snap-$label.raw"
    err="$WORK/snap-$label.err"

    python3 - "$cmds" "$addr" <<'PYEOF' || fail 4 "cannot write cmds"
import sys
path, addr = sys.argv[1], sys.argv[2]
lines = []
if addr != "-":
    lines.append("b %s" % addr)
    lines.append("g")
for a in range(0, 0o100000, 0o10):
    lines.append("%05o b" % a)
lines.append("q")
open(path, "w").write("\n".join(lines) + "\n")
PYEOF

    echo "--- snapshot $label (breakpoint $addr) ---"
    BESM6_PATH="$WORK" dispak -b -l "$JOB" < "$cmds" \
        > "$raw" 2> "$err"
    status=$?
    [ "$status" -eq 0 ] || fail 5 "dispak exit=$status for $label"

    words=$(python3 - "$MAPPER" "$raw" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1].rsplit('/', 1)[0])
import ram_page_map as m
text = open(sys.argv[2], encoding="utf-8", errors="replace").read()
try:
    mem = m.parse_snapshot(text)
except ValueError as exc:
    print("BAD:%s" % exc)
    sys.exit(1)
print(len(mem))
PYEOF
)
    case "$words" in
        32768) ;;
        *) fail 5 "snapshot $label: $words" ;;
    esac

    hit="-"
    if [ "$addr" != "-" ]; then
        hit=$(grep -aoE "[- ]*0?${addr}:" "$raw" | head -1 \
              | tr -d ' :-' || true)
        [ -n "$hit" ] || hit="requested:$addr (marker not parsed)"
    fi
    printf '%s\tbp=%s\thit=%s\twords=%s\tfile=%s\n' \
        "$label" "$addr" "$hit" "$words" "$raw" >> "$MANIFEST"
done

echo "=== manifest ==="
cat "$MANIFEST"
echo "=== RAM-SNAPSHOT done: ${#TARGETS[@]} snapshots ==="
exit 0
