#!/usr/bin/env bash
# disbesm_extract.sh — извлечение зоны диска через besmtool dump
# Используется как预备 для disbesm_verify.sh
#
# disbesm_extract.sh <disk> <zone> <length> [--output <file>]

set -euo pipefail

DISK=""; ZONE=""; LENGTH="1"; OUTPUT=""; HAVE_LENGTH=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output) OUTPUT="$2"; shift 2 ;;
        -o) OUTPUT="$2"; shift 2 ;;
        -h|--help) echo "disbesm_extract.sh <disk> <zone-octal> [length] [-o <file>]"; exit 0 ;;
        *)
            if [[ -z "$DISK" ]]; then DISK="$1"
            elif [[ -z "$ZONE" ]]; then ZONE="$1"
            elif [[ "$HAVE_LENGTH" -eq 0 ]]; then LENGTH="$1"; HAVE_LENGTH=1; fi
            shift ;;
    esac
done

[[ -z "$DISK" || -z "$ZONE" ]] && { echo "Ошибка: укажите disk и zone"; exit 1; }

command -v besmtool >/dev/null 2>&1 || \
    { echo "ОШИБКА: besmtool не найден в PATH"; exit 1; }

if [[ -z "$OUTPUT" ]]; then
    OUTPUT="G${ZONE}-L${LENGTH}"
fi

# Номер зоны ЗАДАЁТСЯ ВОСЬМЕРИЧНЫМ (137, 537; ведущий ноль допустим).
# Исправлено 19.11.2026: исходная версия использовала printf '%d' "0${ZONE}",
# из-за чего bash трактовал число как восьмеричное и десятичные 95/351
# молча извлекали НЕ те зоны.
ZONE_DEC=$((8#$ZONE))
ZONE_PAD=$(printf '%06o' "$ZONE_DEC")

if ! besmtool dump "$DISK" --start="0${ZONE_PAD}" --length="$LENGTH" --to-file="$OUTPUT" > /dev/null 2>&1; then
    echo "ОШИБКА: besmtool dump не удался для zone=$ZONE, length=$LENGTH"
    exit 1
fi

FILESIZE=$(stat --format='%s' "$OUTPUT")
EXPECTED=$((LENGTH * 1024 * 6))
if [[ "$FILESIZE" -ne "$EXPECTED" ]]; then
    echo "ОШИБКА: размер $FILESIZE != ожидаемый $EXPECTED (zone=$ZONE, len=$LENGTH)"
    exit 1
fi

echo "OK: $OUTPUT ($FILESIZE байт, зона $ZONE, $LENGTH зон)"
