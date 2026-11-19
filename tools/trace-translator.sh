#!/usr/bin/env bash
# DYNAMIC TRACE транслятора МАКРО-БЕМШ под dispak.
# Запускает минимальное задание на КОПИЯХ образов томов и печатает
# множество исполняемых зон (memory zone = executed_address / 1024).
# tracing: dispak -tt => trace level 2 => каждая машина-я команда
# печатает свой адрес в stderr (dispak/cu.c, "%05o: %-4s").
set -uo pipefail

WORK=/tmp/.private/azizz/trace-poc
JOB="$WORK/TRACE-listing.b6"
AGG="$WORK/agg-dynamic.py"
LIST="$WORK/listing-dynamic.txt"
ZONES="$WORK/zones-dynamic.txt"

fail () { echo "FAIL [$1]: $2" >&2; exit "$1"; }

# ---- 0. Защита: категорический отказ работать с эталонными образами ----
if [ -z "${BESM6_PATH:-}" ]; then
    fail 3 "BESM6_PATH не задан (требуется КОПИЯ в $WORK)"
fi
case ":$BESM6_PATH:" in
    *:/usr/local/share*|*:"$HOME"/.besm6:*|*/.besm6:*)
        fail 3 "BESM6_PATH указывает на настоящий каталог образов: $BESM6_PATH"
        ;;
esac
if [ "$BESM6_PATH" != "$WORK" ]; then
    fail 3 "BESM6_PATH должен быть ровно '$WORK' (без эталонных каталогов)"
fi

command -v dispak >/dev/null 2>&1 || fail 4 "dispak не найден в PATH"
command -v python3 >/dev/null 2>&1 || fail 4 "python3 не найден в PATH"

# ---- 1. Копии образов (эталоны только читаются) ----
mkdir -p "$WORK" || fail 4 "не создать $WORK"
for v in 2048 2053 2099 2248; do
    if [ ! -f "$WORK/$v" ]; then
        cp "/usr/local/share/besm6/$v" "$WORK/$v" \
            || fail 4 "не скопировать том $v (нужно место в /tmp)"
    fi
done

# ---- 2. Минимальное задание (0-0, только листинг) ----
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

# ---- 3. Агрегатор: потоковый разбор трассы (25 МБ НЕ сохраняем) ----
cat > "$AGG" <<'PYEOF' || fail 4 "не записать агрегатор"
import re, sys
from collections import Counter
r = re.compile(r"^([0-7]{5}):\s")
z, a, n = Counter(), Counter(), 0
for line in sys.stdin:
    m = r.match(line)
    if m:
        addr = int(m.group(1), 8)
        a[addr] += 1; z[addr // 1024] += 1; n += 1
print("total executed instructions:", n)
print("distinct instruction addresses:", len(a))
print("executed memory zones (oct / dec / count):")
for k in sorted(z):
    print("  %03o / %3d / %d" % (k, k, z[k]))
print("EXECUTED_ZONE_SET_OCT=" + " ".join("%03o" % k for k in sorted(z)))
if a:
    print("address range (oct): %05o .. %05o" % (min(a), max(a)))
PYEOF

# ---- 4. Прогон: stderr (трасса) в агрегатор, stdout (листинг) в файл ----
# 2>&1 >file: stderr идёт в канал (pipe), stdout -- в файл листинга.
dispak -l -tt "$JOB" 2>&1 >"$LIST" | python3 "$AGG" >"$ZONES"
STATS=("${PIPESTATUS[@]}")
PIPE_STATUS=${STATS[0]}
PY_STATUS=${STATS[1]}
[ "$PIPE_STATUS" -eq 0 ] || fail 5 "dispak exit=$PIPE_STATUS (ожидался 0)"
[ "$PY_STATUS" -eq 0 ] || fail 5 "агрегатор exit=$PY_STATUS"

# ---- 5. Проверки результата ----
[ -s "$ZONES" ] || fail 5 "трасса пуста (net adresov)"
grep -q '^total executed instructions: [1-9]' "$ZONES" \
    || fail 5 "не найдено ни одной исполненной команды"
grep -q 'EXECUTED_ZONE_SET_OCT=' "$ZONES" \
    || fail 5 "агрегатор не выдал множество зон"
if ! grep -q 'КОНЕЦ ЗАДАЧИ' "$LIST"; then
    fail 6 "листинг не содержит 'КОНЕЦ ЗАДАЧИ' (транслятор не доработал)"
fi
# В листинге ОКР-омоглайфы: "ЧИCЛO OШИБOK=0000" (латиница O/K).
if ! grep -qE 'ШИБ[ОO][КK]=0000' "$LIST"; then
    echo "WARN: в листинге есть ошибки (см. $LIST)" >&2
fi

# ---- 6. Отчёт ----
echo "=== dispak -tt: dynamic trace of МАКРО-БЕМШ ==="
echo "job: $JOB"
echo "listing: $LIST"
cat "$ZONES"
echo
echo "ПРИМЕЧАНИЕ: это ЗОНЫ ПАМЯТИ (адрес/1024), не зоны диска 0137-0177."
echo "15-битный адрес abpc <= 077777_8 => зона памяти <= 037_8."
echo "Дисковые зоны 0137-0177 не могут появиться в трассе напрямую."
exit 0
