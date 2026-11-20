#!/usr/bin/env bash
# vneshn_probe.sh -- byte-safety experiment for VNESHN/VHODN declarations.
# The job-generation and listing-to-object logic is copied unchanged from
# tools/rebuild-zone.sh; only the .be path is parameterised.
# All writes go under /tmp/.private/azizz/vneshn-probe/.
#
#   bash tools/vneshn_probe.sh job <be> [out]
#   bash tools/vneshn_probe.sh parse <listing>
#   bash tools/vneshn_probe.sh extract <listing> <gold> <silver>
#   bash tools/vneshn_probe.sh compare <gold> <silver>
#   bash tools/vneshn_probe.sh variant <src-be> <zone> <mode> <label> \
#        <placement> <directive>[;<directive>...]
#   bash tools/vneshn_probe.sh probe <be> <zone> <mode> <label>
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SELF="${BASH_SOURCE[0]}"
WORKROOT="${VNESHN_PROBE_WORK:-/tmp/.private/azizz/vneshn-probe}"

refuse() { echo "REFUSE: $1" >&2; exit 3; }
case "$WORKROOT" in
    /tmp/.private/azizz/*) : ;;
    *) refuse "WORKROOT должен быть под /tmp/.private/azizz/ (получено: $WORKROOT)" ;;
esac
for real in /usr/local/share /usr/local/share/besm6 "$HOME/.besm6" \
            /usr/local/share/besm6/2048; do
    [ "$WORKROOT" = "$real" ] && refuse "нельзя работать в каталоге $real"
done
mkdir -p "$WORKROOT/variants" "$WORKROOT/runs"

SUB="${1:-usage}"
[ "$#" -gt 0 ] && shift

case "$SUB" in
job)
exec python3 - "$@" <<'PY'
import sys
be, out = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None
lines = [l for l in open(be, encoding="utf-8").read().splitlines()
         if not l.lstrip().startswith("*")]
job = ["шифр 419999^", "трак 64^", "лент 30(2048-6200)^", "лент 42(2099)^",
       "лент 43(2248-ЗП)^", "ацп 40^", "росп 0^", "врем 240^",
       "лист 0-37^", "вход 4000^", "е", "в 4000", "к 00 010 4003",
       "к 15 24 04000", "к 00 066 0001 00 000 0100", "с 3000 67",
       "в 14000", "а1", "ВВД$$$^"]
job += [l + "^" for l in lines]
job += ["КВЧ$$$^", "ТРН$$$^", "ЧТКОМП420070^", "0-0^",
        "ЗОНМОД433900  0001^", "КНЦ$$$^", "_$ЕКОНЕЦ"]
text = "\n".join(job) + "\n"
if out:
    open(out, "w", encoding="utf-8").write(text)
else:
    sys.stdout.write(text)
PY
;;

parse)
exec python3 - "$@" <<'PY'
import json, re, sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
# The listing mixes Cyrillic and Latin homoglyphs in service words.
RE_ERR = re.compile(r"ЧИ[CС]Л\s*[OО]\s*[OО]\s*[ШЩ]\s*ИБ[OО]\s*[KК]\s*=\s*([0-9]+)")
RE_LEN = re.compile(r"ДЛИ\s*[HН]\s*[AА]\s+П\s*[РP]\s*[ОO]\s*Г\s*=?\s*([0-7]{2,7})")
RE_VH = re.compile(r"[BВ]\s*[XХ]\s*[OО]Д\s*[HН]\s*=\s*([0-9]+)")
RE_VN = re.compile(r"[BВ]\s*[HН]\s*[EЕ]\s*Ш\s*[HН]\s*=\s*([0-9]+)")
errs = RE_ERR.findall(text)
lengths = RE_LEN.findall(text)
vhs = RE_VH.findall(text)
vns = RE_VN.findall(text)
print(json.dumps({
    "errors": int(errs[-1]) if errs else None,
    "program_length_octal": lengths[-1] if lengths else None,
    "vhodn": int(vhs[-1]) if vhs else None,
    "vneshn": int(vns[-1]) if vns else None,
    "listing_lines": len(text.splitlines()),
}, ensure_ascii=False))
PY
;;

extract)
exec python3 - "$@" <<'PY'
import json, re, sys
listing, gold, silver = sys.argv[1], sys.argv[2], sys.argv[3]
RE_WORD = re.compile(r"^([0-7]{16})\b")
RE_CMD  = re.compile(r"^(\d{2})\s+(\d{2,3})\s+(\d{4,5})\b")
words, pending = {}, None
for line in open(listing, encoding="utf-8"):
    a = line[25:30]
    rest = line[31:].lstrip()
    addr = int(a, 8) if re.fullmatch(r"\d{5}", a) else (None if not a.strip() else "bad")
    if addr == "bad":
        continue
    m = RE_WORD.match(rest)
    if m:
        if addr is not None:
            words[addr] = int(m.group(1), 8)
            pending = None
        continue
    m = RE_CMD.match(rest)
    if m:
        reg, op, af = int(m.group(1), 8), int(m.group(2), 8), int(m.group(3), 8)
        half = (reg << 20) | (op << (15 if len(m.group(3)) == 5 else 12)) | af
        if addr is not None:
            pending = addr
            words[addr] = half << 24
        elif pending is not None:
            words[pending] |= half
            pending = None
g = open(gold, "rb").read()
NW = len(g) // 6
ok = bad = 0
out = bytearray()
first_bad = None
for i in range(NW):
    got = words.get(i + 1)
    if got is None:
        bad += 1
        if first_bad is None:
            first_bad = i
        out += b"\x00" * 6
        continue
    want = int.from_bytes(g[i*6:i*6+6], "big")
    ok += (got == want)
    if got != want and first_bad is None:
        first_bad = i
    bad += (got != want)
    out += got.to_bytes(6, "big")
open(silver, "wb").write(out)
print(json.dumps({"words": NW, "matched_words": ok, "bad_words": bad,
                  "first_bad_word": first_bad}, ensure_ascii=False))
PY
;;

compare)
exec python3 - "$@" <<'PY'
import json, sys
g = open(sys.argv[1], "rb").read()
s = open(sys.argv[2], "rb").read()
n = min(len(g), len(s))
diffs = [i for i in range(n) if g[i] != s[i]]
first_word = diffs[0] // 6 if diffs else None
print(json.dumps({
    "gold_bytes": len(g), "silver_bytes": len(s),
    "compared_bytes": n, "matched_bytes": n - len(diffs),
    "different_bytes": len(diffs), "first_different_word": first_word,
    "identical": (len(g) == len(s) and not diffs),
}, ensure_ascii=False))
PY
;;

variant)
exec python3 - "$@" <<'PY'
import os, re, sys
src, zone, mode, label, placement, directives = sys.argv[1:7]
text = open(src, encoding="utf-8").read()
lines = text.splitlines()
# Leading spaces matter: column 1 is the label field, an indented token is
# the operation field. Do not strip them from the inserted directive.
inserts = [d.rstrip() for d in directives.split(";") if d.strip()]
if placement == "before-start":
    idx = next(i for i, l in enumerate(lines) if re.search(r"\bСТАРТ\b", l))
elif placement == "after-m":
    start = next(i for i, l in enumerate(lines) if re.search(r"\bСТАРТ\b", l))
    idx = next(i for i in range(start, len(lines)) if lines[i].strip() == "М") + 1
elif placement == "before-finish":
    idx = next(i for i, l in enumerate(lines) if re.search(r"\bФИНИШ\b", l))
else:
    raise SystemExit("unknown placement: %s" % placement)
lines[idx:idx] = inserts
out = os.path.join(os.environ.get("VNESHN_PROBE_WORK", "/tmp/.private/azizz/vneshn-probe"),
                   "variants", "%s-%s-Z%s.be" % (mode, label, zone))
with open(out, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
print(out)
PY
;;

probe)
BE="$1"; ZONE="$2"; MODE="$3"; LABEL="$4"
case "$BE" in
    "$WORKROOT"/*) : ;;
    *) refuse "исходник должен лежать под $WORKROOT (получено: $BE)" ;;
esac
[[ "$ZONE" =~ ^[0-7]+$ ]] || refuse "зона должна быть восьмеричной: $ZONE"
case "$MODE" in B) PREFIX=MBE ;; MBE2) PREFIX=MBE2 ;; ASM) PREFIX=ASM ;;
    *) refuse "неизвестный режим: $MODE" ;; esac
GOLD="$ROOT/gold/$PREFIX-Z$ZONE-L1.bin"
[ -f "$BE" ] || refuse "нет исходника: $BE"
[ -f "$GOLD" ] || refuse "нет эталона: $GOLD"

# Shared read-only image copies; dispak is given only these via BESM6_PATH.
IMAGES="$WORKROOT/images"
mkdir -p "$IMAGES"
SHARE="${BESM6_SHARE:-/usr/local/share/besm6}"
for v in 2048 2053 2099 2248; do
    if [ ! -f "$IMAGES/$v" ]; then
        SRC=""
        for c in "/tmp/.private/azizz/rebuild-all/$v" "$SHARE/$v"; do
            [ -f "$c" ] && { SRC="$c"; break; }
        done
        [ -n "$SRC" ] || refuse "нет образа $v"
        cp "$SRC" "$IMAGES/$v"
    fi
done

WORK="$WORKROOT/runs/$MODE-Z$ZONE/$LABEL"
mkdir -p "$WORK"
bash "$SELF" job "$BE" "$WORK/job.b6" || { echo "FAIL: job generation"; exit 1; }
env BESM6_PATH="$IMAGES" dispak -l "$WORK/job.b6" > "$WORK/listing.out" 2>&1
RC=$?
bash "$SELF" parse "$WORK/listing.out" > "$WORK/parse.json"
if [ "$RC" -eq 0 ]; then
    bash "$SELF" extract "$WORK/listing.out" "$GOLD" "$WORK/silver.bin" \
        > "$WORK/extract.json"
else
    printf '{"words":0,"matched_words":0,"bad_words":0,"first_bad_word":null}\n' \
        > "$WORK/extract.json"
    : > "$WORK/silver.bin"
fi
bash "$SELF" compare "$GOLD" "$WORK/silver.bin" > "$WORK/compare.json"
python3 - "$LABEL" "$MODE-Z$ZONE" "$RC" "$WORK" <<'PY'
import json, os, sys
label, zone, rc, work = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
def load(name):
    return json.load(open(os.path.join(work, name), encoding="utf-8"))
p, x, c = load("parse.json"), load("extract.json"), load("compare.json")
summary = {"label": label, "zone": zone, "dispak_rc": rc,
           "translator_errors": p["errors"],
           "program_length_octal": p["program_length_octal"],
           "vhodn": p["vhodn"], "vneshn": p["vneshn"],
           "matched_words": x["matched_words"], "bad_words": x["bad_words"],
           "matched_bytes": c["matched_bytes"],
           "different_bytes": c["different_bytes"],
           "byte_safe": (rc == 0 and p["errors"] == 0 and c["identical"])}
print("PROBE_SUMMARY " + json.dumps(summary, ensure_ascii=False, sort_keys=True))
if not summary["byte_safe"]:
    print("LISTING_HEAD:")
    lines = open(os.path.join(work, "listing.out"), encoding="utf-8",
                 errors="replace").read().splitlines()
    print("\n".join(lines[:8]))
PY
;;

*)
    echo "Использование: bash tools/vneshn_probe.sh {job|parse|extract|compare|variant|probe} ..."
    exit 2 ;;
esac
