#!/usr/bin/env bash
# verify-roundtrip.sh — независимое переизвлечение зон из эталонного образа
# и побайтовая сверка с gold/ (Фаза 5 плана).
# Использует ПРЯМОЙ besmtool dump (десятичные номера зон), то есть не
# зависит от tools/disbesm_extract.sh — это независимая проверка.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DISK="${DISK:-2348}"
TMP="/tmp/.private/azizz/re-bemsh-roundtrip"
V="$ROOT/tools/disbesm_verify.sh"
FAIL=0

rm -rf "$TMP"; mkdir -p "$TMP" "$ROOT/verify"
: > "$ROOT/verify/report.md"

printf '# Фаза 5 — побайтовая верификация\n\n' >> "$ROOT/verify/report.md"
printf 'Эталон: %s образ %s; сравнение direct dump ↔ gold/.\n\n' \
  "$DISK" "${BESM6_PATH:-<default>}" >> "$ROOT/verify/report.md"

check_zone() {
    local dec="$1" name="$2" z8
    z8=$(printf '%04o' "$dec")
    if ! besmtool dump "$DISK" --start="$dec" --length=1 \
         --to-file="$TMP/$name-Z$z8-L1.bin" >/dev/null 2>&1; then
        printf 'FAIL dump %s (%s)\n' "$z8" "$name"; FAIL=$((FAIL+1)); return
    fi
    if ! bash "$V" "$TMP/$name-Z$z8-L1.bin" \
         "$ROOT/gold/$name-Z$z8-L1.bin" \
         | sed -r 's/\x1B\[[0-9;]*m//g' >> "$ROOT/verify/report.md"; then
        FAIL=$((FAIL+1))
    fi
}

for d in 45 46 47 48;  do check_zone "$d" ASM; done
for d in $(seq 95 127);  do check_zone "$d" MBE; done
for d in $(seq 352 383); do check_zone "$d" MBE2; done

echo "=== roundtrip FAIL=$FAIL ===" | tee -a "$ROOT/verify/report.md"
exit "$FAIL"
