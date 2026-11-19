#!/bin/sh
# rebuild-check.sh — проверка готовности инструментария реконструкции .be
# (docs/ROADMAP.md §1). Ничего не записывает в образы томов.
set -u

RC=0
say() { printf '%s\n' "$*"; }
ok() { printf 'OK   %s\n' "$*"; }
bad() { printf 'FAIL %s\n' "$*"; RC=1; }
skip() { printf 'SKIP %s\n' "$*"; }

POC=/tmp/.private/azizz/rebuild-poc
DTRAN=/home/azizz/Yandex.Disk/dtran/dtran

say '=== (a) Доступность инструментов ==='
for t in dispak besmtool disbesm6 python3 perl; do
    if command -v "$t" >/dev/null 2>&1; then
        ok "$t: $(command -v "$t")"
    else
        bad "$t: не найден в PATH"
    fi
done
if [ -x "$DTRAN" ]; then
    ok "dtran: $DTRAN"
else
    bad "dtran: $DTRAN не найден или не исполняемый"
fi

say ''
say '=== (b) Минимальное задание (если запускалось) ==='
for f in "$POC/TEST-listing.out" "$POC/TEST-write.out"; do
    if [ -f "$f" ]; then
        if grep -q 'OШИБOK=0000' "$f"; then
            ok "$(basename "$f"): ошибок транслятора 0"
        else
            bad "$(basename "$f"): маркер 'OШИБOK=0000' не найден"
        fi
    else
        skip "$(basename "$f"): файл отсутствует"
    fi
done

say ''
say '=== (c) Следующие шаги (module-level rebuild) ==='
cat <<'EOF'
  1. скопировать эталонный том в /tmp (.private):
       cp /usr/local/share/besm6/2348 /tmp/.private/azizz/rebuild-poc/2348
       export BESM6_PATH=/tmp/.private/azizz/rebuild-poc:/usr/local/share/besm6
  2. взять шаблон задания siprod_bemsh.make_job() /
     monitor80-re/tools/debemsh.sh (ВВД$$$^ ... КВЧ$$$^ ... ТРН$$$^).
  3. для модуля зоны 0137: convert() из bemsh/<модуль>.be ->
     исходник МАКРО-БЕМШ, listing_job() (0-0) -> dispak -l -> листинг;
     сверка opcode/регистр/адрес через siprod_asm.decode.
  4. полная запись (1-1 + БТМАЛФ) в рабочий том,
     besmtool dump --start=0<зона> --length=N -> silver.bin.
  5. gold.bin = besmtool dump с эталонного тома;
     cmp/disbesm_verify.sh gold.bin silver.bin -> пустой diff.
  Подробности: docs/RECONSTRUCTION-SETUP.md.
EOF

exit "$RC"
