#!/usr/bin/env bash
# rebuild-batch.sh — Фаза A3: реконструкция и побайтовая проверка ВСЕХ зон.
# Для каждой зоны: disbesm6-листинг -> .be -> dispak (0-0) -> silver.bin -> cmp.
# Неудачные .be удаляются; успешные остаются в bemsh/.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="/tmp/.private/azizz/a3-results.txt"
mkdir -p /tmp/.private/azizz/a3
: > "$LOG"

run_group() {
    local kind="$1" first="$2" last="$3"
    for dec in $(seq "$first" "$last"); do
        local z; z=$(printf '%04o' "$dec")
        local prefix
        case "$kind" in
            B) prefix="MBE" ;;
            MBE2) prefix="MBE2" ;;
            ASM) prefix="ASM" ;;
        esac
        local be="bemsh/${prefix}-Z${z}.be"
        python3 "$ROOT/tools/dis2be.py" \
            --input "$ROOT/dis/${prefix}-Z${z}-L1.asm" \
            --output "$ROOT/$be" >/dev/null 2>&1
        if [[ ! -f "$ROOT/$be" ]]; then
            echo "$kind $z CONVERT_FAIL" >> "$LOG"; continue
        fi
        local out
        out=$(bash "$ROOT/tools/rebuild-zone.sh" "$z" "$kind" 2>&1)
        local result ok words
        result=$(printf '%s\n' "$out" | grep -oE 'RESULT: (PASS|FAIL)' | tail -1)
        words=$(printf '%s\n' "$out" | grep -oE 'совпало=[0-9]+' | tail -1)
        if [[ "$result" == "RESULT: PASS" ]]; then
            echo "$kind $z PASS $words" >> "$LOG"
        else
            # Аварийный fallback: побайтово точный RAW-ALL .be.
            python3 "$ROOT/tools/dis2be.py" \
                --input "$ROOT/dis/${prefix}-Z${z}-L1.asm" \
                --output "$ROOT/$be" --raw-all >/dev/null 2>&1
            out=$(bash "$ROOT/tools/rebuild-zone.sh" "$z" "$kind" 2>&1)
            result=$(printf '%s\n' "$out" | grep -oE 'RESULT: (PASS|FAIL)' | tail -1)
            words=$(printf '%s\n' "$out" | grep -oE 'совпало=[0-9]+' | tail -1)
            if [[ "$result" == "RESULT: PASS" ]]; then
                echo "$kind $z PASS-RAW $words" >> "$LOG"
            else
                echo "$kind $z FAIL ($result) $words" >> "$LOG"
                rm -f "$ROOT/$be"
            fi
        fi
    done
}

cd "$ROOT" || exit 1
run_group ASM 45 48
run_group B 95 127
run_group MBE2 352 383

echo "=== summary ===" | tee -a "$LOG"
awk '{c[$3]++} END {for (k in c) print k, c[k]}' "$LOG" | sort | tee -a "$LOG"
