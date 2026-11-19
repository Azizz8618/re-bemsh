#!/usr/bin/env bash
# MEMORY-MAP: привязка дисковой зоны транслятора к страницам ОП.
# Опыт на КОПИЯХ образов: dispak -b, breakpoint 03651 и 02000,
# полный дамп ОП (4096 команд по 8 слов), побайтовая сверка
# дампа с gold/MBE-Z<зона>-L1.bin.
# exit 0 — успех (даже если научный результат отрицательный),
# exit 3 — сработала защита (настоящие каталоги образов),
# exit 4/5 — техническая ошибка.
set -uo pipefail

WORK=/tmp/.private/azizz/memory-map
REPO=$(cd "$(dirname "$0")/.." && pwd)
GOLD="$REPO/gold"
JOB="$WORK/MEMMAP-listing.b6"
CMDS="$WORK/memmap.cmds"
RAW="$WORK/memmap.raw"
fail () { echo "FAIL [$1]: $2" >&2; exit "$1"; }

# ---- 0. Защита: анализируем только копии в $WORK ----
if [ -z "${BESM6_PATH:-}" ]; then
    fail 3 "BESM6_PATH не задан (требуется КОПИЯ в $WORK)"
fi
case ":$BESM6_PATH:" in
    *:/usr/local/share*|*:"$HOME"/.besm6:*|*/.besm6:*)
        fail 3 "BESM6_PATH указывает на настоящий каталог образов: $BESM6_PATH"
        ;;
esac
if [ "$BESM6_PATH" != "$WORK" ]; then
    fail 3 "BESM6_PATH должен быть ровно '$WORK'"
fi
command -v dispak >/dev/null 2>&1 || fail 4 "dispak не найден в PATH"
command -v python3 >/dev/null 2>&1 || fail 4 "python3 не найден в PATH"
[ -d "$GOLD" ] || fail 4 "нет каталога $GOLD"

# ---- 1. Копии томов (эталоны только читаются) ----
mkdir -p "$WORK" || fail 4 "не создать $WORK"
for v in 2048 2053 2099 2248; do
    if [ ! -f "$WORK/$v" ]; then
        cp "/usr/local/share/besm6/$v" "$WORK/$v" \
            || fail 4 "не скопировать том $v"
    fi
done

# ---- 2. Минимальное задание МАКРО-БЕМШ (режим 0-0) ----
cat > "$JOB" <<'JOBEOF' || fail 4 "не записать задание"
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

# ---- 3. Команды отладчика ----
# 03651 — ранняя инструкция ОС: к этому моменту транслятор уже
# загружен в ОП. 02000 — первая команда зоны 0154 (сч '6065').
python3 - <<'PYEOF' > "$CMDS" || fail 4 "не записать команды"
print("b 3651")     # breakpoint: ранняя точка после загрузки
print("b 2000")     # breakpoint: вход в макроредактор (зона 0154)
print("g")          # дойти до 03651
for a in range(0, 0o100000, 0o10):
    print("%05o b" % a)   # дамп 8 слов = 6 байт/слово
print("g")          # дойти до 02000
print("q")
PYEOF

# ---- 4. Прогон: stdout = дамп, stderr = служебная информация ----
BESM6_PATH="$WORK" dispak -b -l "$JOB" < "$CMDS" > "$RAW" 2> "$WORK/memmap.err"
DISPAK_STATUS=$?
[ "$DISPAK_STATUS" -eq 0 ] || fail 5 "dispak exit=$DISPAK_STATUS"

# ---- 5. Проверки ----
grep -q '03651:.*xta' "$RAW" \
    || fail 5 "breakpoint 03651 не сработал (транслятор не загружен)"
if grep -q '02000: 00 010 6065' "$RAW"; then
    BP154="confirm: breakpoint 02000 -> xta 6065 = сч '6065' (зона 0154)"
else
    BP154="confirm: breakpoint 02000 НЕ сработал (см. $RAW)"
fi

# ---- 6. Разбор дампа и сверка с gold ----
python3 - "$RAW" "$GOLD" "$BP154" <<'PYEOF' || fail 5 "разбор дампа не удался"
import re, sys, os, glob
raw, gold, bp = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(raw, encoding='utf-8', errors='replace').read().splitlines()
pattern = re.compile(r'^-? ?((?:[0-7]{3} ){5}[0-7]{3}) ?$')
starts = [i for i, l in enumerate(lines)
          if pattern.match(l) and l.startswith('- ')]
if len(starts) < 4096:
    sys.exit("FAIL: найдено %d блоков дампа, ожидалось 4096" % len(starts))
mem = [None] * 32768
for idx, s in enumerate(starts):
    for k in range(8):
        m = pattern.match(lines[s + k])
        if m:
            mem[idx * 8 + k] = tuple(int(x, 8) for x in m.group(1).split())
if any(w is None for w in mem):
    sys.exit("FAIL: дамп ОП неполон")

zones = sorted(glob.glob(os.path.join(gold, 'MBE-Z*-L1.bin')),
               key=lambda f: int(re.search(r'Z(\d+)', os.path.basename(f)).group(1), 8))
print("=== КАРТА: дисковая зона -> адрес ОП ===")
print(bp)
print("| зона | адрес ОП (восьм.) | страница | размер | доказательство |")
print("|------|-------------------|----------|--------|----------------|")
found = 0
for f in zones:
    zone = int(re.search(r'Z(\d+)', os.path.basename(f)).group(1), 8)
    data = open(f, 'rb').read()
    zw = [tuple(data[i * 6:(i + 1) * 6]) for i in range(1024)]
    scores = sorted(((sum(1 for i in range(1024) if mem[p * 1024 + i] == zw[i]), p)
                     for p in range(32)), reverse=True)
    cnt, page = scores[0]
    cnt2, page2 = scores[1]
    if cnt >= 500:
        found += 1
        print("| %04o | %05o | %02o | 1024 слов / 6144 B | %d/1024 точных слов "
              "(2-я стр. %02o = %d) |" % (zone, page * 1024, page, cnt, page2, cnt2))
    else:
        print("| %04o | не найдена | — | 1024 / 6144 | лучшее %d/1024 "
              "на стр. %02o |" % (zone, cnt, page))
print()
print("Найдено зон с надёжной привязкой (>=500/1024):", found)
print("ПРИМЕЧАНИЕ: адрес = страница x 02000_8; зона диска НЕ равна зоне ОП.")
print("Зоны с малым числом совпадений — оверлеи/таблицы, вытесненные")
print("или перемещённые загрузчиком; отсутствие совпадения не доказывает")
print("отсутствие исполнения (см. analysis/MEMORY-MAP.md, §Неопределённость).")
PYEOF
exit 0
