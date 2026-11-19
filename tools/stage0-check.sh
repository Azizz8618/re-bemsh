#!/usr/bin/env bash
# stage0-check.sh — самопроверка конфигурации Phase 0 для re-bemsh.
# Эталонные образы НЕ изменяются: только чтение + извлечение в /tmp.
# Проверки:
#   (a) инструменты в PATH;
#   (b) md5 выбранного образа 2348 == docs/COPIES-2348.md;
#   (c) disbesm_extract.sh 2348 137 1 → 6144 байт;
#   (d) disbesm6 -a0 -e0 печатает СТАРТ и ФИНИШ;
#   (e) PASS/FAIL по каждой проверке, exit != 0 при любом FAIL.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${STAGE0_IMAGE:-/usr/local/share/besm6/2348}"
DISK="${DISK:-2348}"
OUT="/tmp/.private/azizz/stage0-check.bin"
ASM="/tmp/.private/azizz/stage0-check.asm"
FAIL=0

pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; FAIL=$((FAIL + 1)); }

echo "=== stage0-check: $(date -u +%FT%TZ) ==="
echo "repo:  $ROOT"
echo "image: $IMAGE"

# (a) все нужные инструменты
for t in disbesm6 besmtool dispak python3; do
    if command -v "$t" >/dev/null 2>&1; then
        pass "command -v $t -> $(command -v "$t")"
    else
        fail "command -v $t (не найден)"
    fi
done

# (b) ИНВАРИАНТ — контрольная сумма ЗОН ТРАНСЛЯТОРА, а не всего образа.
#     Весь том 2348 используется другими проектами (PERSO-запись), поэтому
#     md5 файла может меняться; зоны 0137-0177 должны оставаться прежними.
DOC="$ROOT/docs/COPIES-2348.md"
EXPECTED="2f503f5b8f8fb6ad12632fed6f8cf17f"   # md5(0137-0177, 202752 B)
if [[ -f "$DOC" ]]; then
    DOC_MD5=$(grep -F '2f503f5b8f8fb6ad12632fed6f8cf17f' "$DOC" \
        | grep -oE '[0-9a-f]{32}' | head -1)
    if [[ -n "$DOC_MD5" ]]; then
        EXPECTED="$DOC_MD5"
        pass "md5 зон 0137-0177 из docs/COPIES-2348.md = $EXPECTED"
    else
        fail "эталонный md5 зон 0137-0177 не найден в docs/COPIES-2348.md"
    fi
else
    fail "нет файла $DOC"
fi
if [[ -f "$IMAGE" ]]; then
    echo "INFO md5(всего образа) = $(md5sum "$IMAGE" | awk '{print $1}')"
    ZONES="/tmp/.private/azizz/stage0-zones.bin"
    : > "$ZONES"
    OK=1
    for z in $(seq 95 127); do
        if ! besmtool dump "$DISK" --start="$z" --length=1 \
             --to-file=/tmp/.private/azizz/stage0-one.bin >/dev/null 2>&1; then
            OK=0; break
        fi
        cat /tmp/.private/azizz/stage0-one.bin >> "$ZONES"
    done
    if [[ "$OK" -eq 1 ]]; then
        ACTUAL=$(md5sum "$ZONES" | awk '{print $1}')
        if [[ "$ACTUAL" == "$EXPECTED" ]]; then
            pass "md5(зон 0137-0177 на диске) == $EXPECTED"
        else
            fail "md5(зон) = $ACTUAL, ожидалось $EXPECTED"
        fi
    else
        fail "не удалось выкачать зоны 0137-0177"
    fi
else
    fail "образ не найден: $IMAGE"
fi

# (c) извлечение зоны 0137₈ (аргумент хелпера ВОСЬМЕРИЧНЫЙ) и размер 6144
if [[ -x "$ROOT/tools/disbesm_extract.sh" ]]; then
    if "$ROOT/tools/disbesm_extract.sh" 2348 137 1 -o "$OUT" >/dev/null; then
        SZ=$(stat --format='%s' "$OUT" 2>/dev/null || echo 0)
        if [[ "$SZ" -eq 6144 ]]; then
            pass "extract zone 0137: размер $SZ байт"
        else
            fail "extract zone 0137: размер $SZ != 6144"
        fi
    else
        fail "disbesm_extract.sh 2348 137 1 -o $OUT не отработал"
    fi
else
    fail "tools/disbesm_extract.sh отсутствует или не исполняем"
fi

# (d) дизассемблирование: обязательные -e, штампы СТАРТ/ФИНИШ
if [[ -f "$OUT" ]]; then
    if disbesm6 -a0 -e0 "$OUT" > "$ASM" 2>/dev/null; then
        if grep -q 'СТАРТ' "$ASM" && grep -q 'ФИНИШ' "$ASM"; then
            pass "disbesm6 -a0 -e0: найдены СТАРТ и ФИНИШ"
        else
            fail "disbesm6: в выводе нет СТАРТ/ФИНИШ"
        fi
    else
        fail "disbesm6 -a0 -e0 завершился с ошибкой"
    fi
else
    fail "нет файла для дизассемблирования: $OUT"
fi

echo "=== итого FAIL=$FAIL ==="
if [[ "$FAIL" -eq 0 ]]; then
    echo "STAGE0: PASS"
else
    echo "STAGE0: FAIL"
fi
exit "$FAIL"
