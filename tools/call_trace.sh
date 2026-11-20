#!/usr/bin/env bash
# CALL-TRACE: dynamic trace of PROGRAM 2 transfer instructions (ПВ/ПБ/
# ПИО/ПИНО) on COPIES of the BESM6 volumes.  A guard refuses real image
# directories.  The proven dispak job deck from tools/ram_snapshot.sh is
# reused unchanged.  dispak -tt prints every instruction address as
#   fprintf(stderr, "%05o: %-4s", abpc, op.o_name)   (cu.c:383)
# so the NEXT executed address after a transfer is its real destination.
#
# exit 0 - trace captured and report written (even for a negative result)
# exit 3 - guard refused a real image directory
# exit 4/5 - technical/setup error
set -uo pipefail

WORK=/tmp/.private/azizz/call-trace
SRC=/usr/local/share/besm6
REPO=$(cd "$(dirname "$0")/.." && pwd)
JOB="$WORK/CALL-listing.b6"
TRACE="$WORK/trace-full.txt"
LISTING="$WORK/listing.txt"
PARSER="$WORK/call_trace_parser.py"
ALL="$WORK/all-calls.tsv"
REPORT="$WORK/call-report.txt"
SNAPMAP=/tmp/.private/azizz/ram-snap/map-all.txt

# ---- 0. The parser is embedded so that the unit tests import the exact
#         code the script runs.  --emit-parser prints it and exits. ----
if [ "${1:-}" = "--emit-parser" ]; then
    awk '/^# === PARSER-START ===$/{f=1} f{print} /^# === PARSER-END ===$/{exit}' "$0"
    exit 0
fi

fail () { echo "FAIL [$1]: $2" >&2; exit "$1"; }

# ---- 1. Guard: work ONLY on copies in $WORK ----
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

# ---- 2. Copies of the reference volumes; md5 of the SOURCE is fixed ----
mkdir -p "$WORK" || fail 4 "cannot create $WORK"
md5sum "$SRC/2048" > "$WORK/image-md5.before.txt" \
    || fail 4 "cannot md5 the reference volume"
# Refresh every copy: dispak writes the job result back into volume 2248,
# so a dirty copy makes the second run differ from the first.
for v in 2048 2053 2099 2248; do
    cp "$SRC/$v" "$WORK/$v" || fail 4 "cannot copy volume $v"
done

# ---- 3. Proven minimal listing job (mode 0-0), from ram_snapshot.sh ----
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

# ---- 4. Extract the parser (single source of truth) ----
awk '/^# === PARSER-START ===$/{f=1} f{print} /^# === PARSER-END ===$/{exit}' \
    "$0" > "$PARSER" || fail 4 "cannot write parser"

# ---- 5. The full trace.  -t increments trace; -tt => trace=2 ----
echo "=== CALL-TRACE: dispak -tt on copies in $WORK ==="
BESM6_PATH="$WORK" dispak -l -tt "$JOB" > "$LISTING" 2> "$TRACE"
status=$?
[ "$status" -eq 0 ] || fail 5 "dispak exit=$status (see $TRACE)"

md5sum "$SRC/2048" > "$WORK/image-md5.after.txt" \
    || fail 4 "cannot md5 the reference volume after the run"
cmp -s "$WORK/image-md5.before.txt" "$WORK/image-md5.after.txt" \
    || fail 5 "reference image 2048 changed during the run"

# ---- 6. Analysis ----
python3 - "$WORK" "$SNAPMAP" "$REPO" <<'PYEOF' || fail 5 "trace analysis failed"
import sys, os, re, collections
work, snapmap_path, repo = sys.argv[1:4]
sys.path.insert(0, work)
import call_trace_parser as ct

trace_path = os.path.join(work, 'trace-full.txt')
with open(trace_path, encoding='utf-8', errors='replace') as fh:
    seq = ct.build_sequence(fh)
if not seq:
    sys.exit('FAIL: empty trace')

sm = ct.SnapshotMap()
if os.path.isfile(snapmap_path):
    sm = ct.SnapshotMap.from_text(open(snapmap_path, encoding='utf-8').read())

focus = [0o34562, 0o7417, 0o77316, 0o51670, 0o2070, 0o4114]
executed_at = collections.Counter(r['addr'] for r in seq)
pages = collections.Counter(r['addr'] >> 10 for r in seq)
calls = ct.find_calls(seq)
by_mnem = collections.Counter(r['mnemonic'] for r in calls)
direct = collections.Counter(r['mnemonic'] for r in calls
                             if ct.operand_number(r['operand']) == r['next_addr'])
target_pages = collections.Counter(r['next_addr'] >> 10 for r in calls
                                   if r['next_addr'] is not None)

with open(os.path.join(work, 'all-calls.tsv'), 'w', encoding='utf-8') as fh:
    fh.write('addr\toct\tmnem\trussian\toperand\tnext_oct\treg\treg_value\traw\n')
    for r in calls:
        fh.write('%o\t%o\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' % (
            r['addr'], r['addr'], r['mnemonic'],
            ct.CALL_MNEMONICS.get(r['mnemonic'], '?'), r['operand'],
            '-' if r['next_addr'] is None else '%o' % r['next_addr'],
            '-' if r['reg'] is None else str(r['reg']),
            '-' if r['reg_value'] is None else '%o' % r['reg_value'],
            r['raw'].replace('\t', ' ')))

listing_cache = {}
def listing_word(zone, word):
    key = (zone, word)
    if key in listing_cache:
        return listing_cache[key]
    path = os.path.join(repo, 'dis', 'MBE-Z%s-L1.asm' % zone)
    out = '-'
    if os.path.isfile(path):
        pat = re.compile(r'^\s*%s\s+([0-7]{16})\s+(\S+)\s+(\S*)' % ('%o' % word))
        with open(path, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                m = pat.match(line)
                if m:
                    out = '%s %s %s' % (m.group(1), m.group(2), m.group(3))
                    break
    listing_cache[key] = out
    return out

out = []
w = out.append
w('=== CALL-TRACE: %d executed instructions, %d distinct addresses ==='
  % (len(seq), len(set(r['addr'] for r in seq))))
w('executed pages: ' + ' '.join('%02o:%d' % (p, c)
                                for p, c in sorted(pages.items())))
w('transfer instructions (dispak mnemonic = Russian name):')
for mn in sorted(by_mnem):
    w('  %-4s %-6s n=%6d  next==operand %6d (%.1f%%)'
      % (mn, ct.CALL_MNEMONICS[mn], by_mnem[mn], direct[mn],
         100.0 * direct[mn] / by_mnem[mn]))
w('destination page histogram (all transfers): '
  + ' '.join('%02o:%d' % (p, c) for p, c in sorted(target_pages.items())))
w('')
for t in focus:
    rows = [r for r in calls
            if ct.operand_number(r['operand']) == t]
    sites = collections.Counter((r['addr'], r['mnemonic'], r['operand'])
                                for r in rows)
    w('=== TARGET %05o_8 (page %02o, offset %04o) ==='
      % (t, t >> 10, t & 0o1777))
    w('  executed as instruction address: %d times; transfer rows: %d; '
      'distinct call sites: %d' % (executed_at[t], len(rows), len(sites)))
    w('  destination attribution: %s' % sm.classify(t))
    for (addr, mn, operand), cnt in sorted(sites.items())[:8]:
        nxt = next(r['next_addr'] for r in rows
                   if r['addr'] == addr and r['mnemonic'] == mn
                   and r['operand'] == operand)
        zinfo = sm.zones_for_addr(addr)
        zones = sorted(set(z for _, z, _ in zinfo))
        src = ';'.join('%s:%04o' % (z, addr & 0o1777) for z in zones) \
              or 'no-resident-zone'
        lwords = ';'.join(listing_word(z, addr & 0o1777) for z in zones) \
                 or '-'
        w('  src %05o -> %s  %s(%s) x%d  next=%s  src_zone %s  L1 %s'
          % (addr, 'o%05o' % nxt, ct.CALL_MNEMONICS.get(mn, mn), operand,
             cnt, '-' if nxt is None else '%o' % nxt, src, lwords))
    w('  evidence: ' + (rows[0]['raw'] if rows else
                        '(no transfer with this operand in the trace)'))
    w('')

report_path = os.path.join(work, 'call-report.txt')
with open(report_path, 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(out) + '\n')
w('=== all-calls rows: %d -> %s ===' % (len(calls),
                                        os.path.join(work, 'all-calls.tsv')))
w('=== report -> %s ===' % report_path)
print('\n'.join(out))
PYEOF

echo "=== CALL-TRACE done ==="
exit 0

# The block below is inert shell data; --emit-parser extracts it verbatim.
: <<'PARSER_ONLY'
# === PARSER-START ===
# Python parser for dispak -tt output.  Extracted verbatim by --emit-parser.
import re

# cu.c:383 prints "%05o: %-4s" for every EXECUTED machine instruction.
# Lines for memory stores are indented and therefore do not match INSN_RE.
INSN_RE = re.compile(r'^([0-7]{5}):\s+(\S+)\s*(.*)$')
REGVAL_RE = re.compile(r'\br\[([0-7]+)\]=([0-7]+)')

# dispak optab.c opcode -> Russian mnemonic of the source language
# (disbesm6.c:117-124: пб=030, пв=031, пио=034, пино=035).
CALL_MNEMONICS = {
    'uj':  'ПБ',     # opcode 030, JMP(addr + reg[i])
    'vjm': 'ПВ',     # opcode 031, reg[i]=nextpc; JMP(addr)
    'vzm': 'ПИО',    # opcode 034, conditional JMP(addr)
    'v1m': 'ПИНО',   # opcode 035, conditional JMP(addr)
    'asn': 'ПИО36',  # opcode 036; dispak never jumps on it (reported)
}


def parse_line(line):
    """Return an instruction record, or None for non-instruction lines."""
    if not isinstance(line, str):
        return None
    m = INSN_RE.match(line.rstrip('\n'))
    if not m:
        return None
    operand_field = m.group(3).split(' (=', 1)[0].strip()
    reg = None
    rm = re.search(r'\((\d+)\)', operand_field)
    if rm:
        reg = int(rm.group(1), 8)
    reg_value = None
    rv = REGVAL_RE.search(line)
    if rv:
        reg_value = int(rv.group(2), 8)
    return {
        'addr': int(m.group(1), 8),
        'mnemonic': m.group(2),
        'operand': operand_field,
        'number': operand_number(operand_field),
        'reg': reg,
        'reg_value': reg_value,
        'raw': line.rstrip('\n'),
        'next_addr': None,
    }


def operand_number(operand):
    """Leading octal number of a dispak operand field, with sign."""
    m = re.match(r'(-?)([0-7]+)', operand or '')
    if not m:
        return None
    value = int(m.group(2), 8)
    return -value if m.group(1) else value


def build_sequence(lines):
    """Parse all lines and attach the next EXECUTED address to each record."""
    seq = []
    for line in lines:
        rec = parse_line(line)
        if rec is not None:
            seq.append(rec)
    for i, rec in enumerate(seq):
        rec['next_addr'] = seq[i + 1]['addr'] if i + 1 < len(seq) else None
    return seq


def find_calls(seq, targets=None):
    """All transfer records, optionally restricted to numeric operands."""
    out = []
    for rec in seq:
        if rec['mnemonic'] not in CALL_MNEMONICS:
            continue
        if targets is not None and rec['number'] not in targets:
            continue
        out.append(rec)
    return out


class SnapshotMap:
    """page -> disk zone, derived from the 8 RAM snapshots (map-all.txt)."""

    def __init__(self):
        self.by_snapshot = {}

    @classmethod
    def from_text(cls, text):
        obj = cls()
        pat = re.compile(
            r'\|\s*(snap-[A-Za-z0-9]+\.raw)\s*\|\s*([0-7]{2})\s*\|'
            r'\s*[0-7]{5}\s*\|\s*MBE(2)?-([0-7]{4})\s*\|\s*(\d+)\s*\|'
            r'.*?\|\s*([A-Z]+)\s*\|')
        for line in text.splitlines():
            m = pat.match(line)
            if not m:
                continue
            snap, page, mbe2, zone, count, conf = m.groups()
            if mbe2 and int(count) >= 1024:
                continue  # B2 copy is byte-equal: ambiguous, not a label
            if conf not in ('EXACT', 'HIGH', 'AMBIG', 'TABLE'):
                continue
            obj.by_snapshot.setdefault(snap, {})[int(page, 8)] = (zone, conf)
        return obj

    def zones_for_addr(self, addr):
        """[(snapshot, zone, confidence)] for the page containing addr."""
        page = addr >> 10
        out = []
        for snap in sorted(self.by_snapshot):
            entry = self.by_snapshot[snap].get(page)
            if entry:
                out.append((snap, entry[0], entry[1]))
        return out

    def classify(self, addr):
        """Attribute an address to a translator zone using the snapshots."""
        z = self.zones_for_addr(addr)
        if not z:
            return 'NO RESIDENT ZONE in 8 snapshots (page %02o)' % (addr >> 10)
        zones = sorted(set(zone for _, zone, _ in z))
        snaps = sorted(set(snap for snap, _, _ in z))
        return ('zone %s (snapshots: %s)'
                % ('/'.join(zones), ','.join(s.replace('snap-', '')
                                            for s in snaps)))
# === PARSER-END ===
PARSER_ONLY
