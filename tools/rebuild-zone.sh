#!/usr/bin/env bash
# rebuild-zone.sh — собрать ЛЮБУЮ зону из bemsh/<TYPE>-Z<zone>.be и сверить с gold/.
# Обобщение tools/rebuild-0137.sh (рецепт не изменён, только parametrised).
# Использует ТОЛЬКО копии образов в /tmp; листинг (0-0) не пишет в образы.
#
#   bash tools/rebuild-zone.sh <ZONE_OCTAL> [B|MBE2|ASM]
#
#   B     -> bemsh/MBE-Z<zone>[-L1].be,    gold/MBE-Z<zone>-L1.bin   (по умолчанию)
#   MBE2  -> bemsh/MBE2-Z<zone>[-L1].be,   gold/MBE2-Z<zone>-L1.bin
#   ASM   -> bemsh/ASM-Z<zone>[-L1].be,    gold/ASM-Z<zone>-L1.bin
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERIFY="$ROOT/tools/disbesm_verify.sh"

usage() {
    echo "Использование: bash tools/rebuild-zone.sh <ZONE_OCTAL> [B|MBE2|ASM]"
    echo "  ZONE_OCTAL — восьмеричный номер зоны (например, 0137, 0540);"
    echo "  режим по умолчанию — B (MBE 06/78)."
}

[ $# -ge 1 ] || { usage; exit 2; }
[ "${1:-}" = "-h" -o "${1:-}" = "--help" ] && { usage; exit 0; }

RAW_ZONE="$1"
MODE="${2:-B}"
case "$MODE" in
    B)     PREFIX=MBE ;;
    MBE2)  PREFIX=MBE2 ;;
    ASM)   PREFIX=ASM ;;
    *) echo "Неизвестный режим: $MODE (ожидалось B|MBE2|ASM)"; exit 2 ;;
esac

# Номер зоны — строго восьмеричный,Leading zero не обязателен.
[[ "$RAW_ZONE" =~ ^[0-7]+$ ]] || {
    echo "REFUSE: зона должна быть восьмеричным числом (получено: $RAW_ZONE)"; exit 2; }
ZONE="$(printf '%04o' "$((8#$RAW_ZONE))")"

# --- поиск .be и эталона: поддерживаются оба имени (…-Z<zone>.be и …-L1.be) ---
BE=""
for cand in "$ROOT/bemsh/${PREFIX}-Z${ZONE}-L1.be" \
            "$ROOT/bemsh/${PREFIX}-Z${ZONE}.be"; do
    if [ -f "$cand" ]; then BE="$cand"; break; fi
done
if [ -z "$BE" ]; then
    echo "Нет исходника bemsh/${PREFIX}-Z${ZONE}[-L1].be"; exit 1
fi
GOLD="$ROOT/gold/${PREFIX}-Z${ZONE}-L1.bin"

for f in "$BE" "$GOLD" "$VERIFY"; do
    [ -f "$f" ] || { echo "Нет файла: $f"; exit 1; }
done

# --- HARD GUARD: никаких настоящих каталогов образов ---
# dispak ВСЕГДА получает BESM6_PATH, указывающий на копии в /tmp (как в
# rebuild-0137.sh). IMAGE_DIR, если задан пользователем, проверяется строго.
IMAGES="${REBUILD_ALL_IMAGES:-/tmp/.private/azizz/rebuild-all}"
WORK="$IMAGES/$ZONE"

forbidden() {
    local p="$1"
    case "$p" in
        /usr/local/share*|"$HOME"/.besm6*|*/EC5061*) return 0 ;;
    esac
    return 1
}
# Эффективные пути, которые реально использует сборка:
E_BESM6_PATH="$IMAGES"
E_IMAGE_DIR="${IMAGE_DIR:-$IMAGES}"
for p in "$IMAGES" "$WORK" "$E_BESM6_PATH" "$E_IMAGE_DIR"; do
    if forbidden "$p"; then
        echo "REFUSE: путь $p указывает на настоящий каталог образов"
        echo "        (/usr/local/share, ~/.besm6, .../EC5061); работаем только в /tmp"
        exit 3
    fi
done
# Входящий BESM6_PATH из окружения переопределяется на копии — это штатный
# режим (оригинальный rebuild-0137.sh делает то же самое). Явно сообщим об этом.
if [ -n "${BESM6_PATH:-}" ] && forbidden "$BESM6_PATH"; then
    echo "NOTE: BESM6_PATH=$BESM6_PATH (окружение) заменяется на копии: $IMAGES"
    # Полный «строгий» вариант guard-а: REBUILD_STRICT_GUARD=1 отказывается
    # работать и при «настоящем» BESM6_PATH во входящем окружении.
    if [ "${REBUILD_STRICT_GUARD:-0}" = "1" ]; then
        echo "REFUSE: BESM6_PATH=$BESM6_PATH указывает на настоящий каталог образов"
        exit 3
    fi
fi

mkdir -p "$WORK"
SHARE="${BESM6_SHARE:-/usr/local/share/besm6}"
for v in 2048 2053 2099 2248; do
    if [ ! -f "$IMAGES/$v" ]; then
        # Быстрый путь: использовать уже проверенные копии из rebuild-0137,
        # иначе — копия из эталонного SHARE (образы не модифицируются).
        SRC=""
        for c in "/tmp/.private/azizz/rebuild-0137/$v" "$SHARE/$v"; do
            [ -f "$c" ] && { SRC="$c"; break; }
        done
        [ -n "$SRC" ] || { echo "Нет образа $v ни в /tmp, ни в $SHARE"; exit 1; }
        cp "$SRC" "$IMAGES/$v"
    fi
done

echo "=== 1. .be -> задание dispak (0-0, только листинг) ==="
python3 - "$BE" "$WORK/job.b6" <<'PY'
import sys
be, out = sys.argv[1], sys.argv[2]
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
open(out, "w", encoding="utf-8").write("\n".join(job) + "\n")
PY

echo "=== 2. прогон транслятора ИПМ МАКРО-БЕМШ 06/78 ==="
if ! env BESM6_PATH="$IMAGES" dispak -l "$WORK/job.b6" \
         > "$WORK/listing.out" 2>&1; then
    echo "FAIL: dispak вернул ненулевой код"; tail -20 "$WORK/listing.out"; exit 1
fi
# Особый случай: база 76000₈ + 1024 слова упираются в 100000₈
# (15-битный предел). Транслятор даёт 1 benign ошибку ПЕРЕПОЛН СЧА
# на служебном слове ПОСЛЕ модуля; все 1024 слова модуля целы.
BENIGN_OVERFLOW=0
if grep -a "ЧИCЛO OШИБOK=0000" "$WORK/listing.out" >/dev/null; then
    :
elif grep -a "ЧИCЛO OШИБOK=0001" "$WORK/listing.out" >/dev/null \
     && grep -a "ПEPEПOЛH CЧA\|ПЕРЕПОЛН СЧА" "$WORK/listing.out" >/dev/null; then
    BENIGN_OVERFLOW=1
    echo "ЗАМЕЧАНИЕ: benign ПЕРЕПОЛН СЧА (слово после модуля, база 76000)"
else
    echo "FAIL: ошибки транслятора"; grep -a "OШИБOK" "$WORK/listing.out"; exit 1
fi
grep -a "ДЛИHA ПPOГ" "$WORK/listing.out" || true

echo "=== 3. листинг -> объектные слова -> silver.bin ==="
python3 - "$WORK/listing.out" "$GOLD" "$WORK/silver.bin" "$BE" "$BENIGN_OVERFLOW" <<'PY'
import re, sys
listing, gold, silver, be = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
benign_overflow = sys.argv[5] == "1"
# База адресов берётся из СТАРТ в .be: '10000' -> 0o10000, пусто/1 -> 1.
def start_base(be_path):
    for line in open(be_path, encoding="utf-8"):
        if line.lstrip().startswith("*"):
            continue
        m = re.search(r"\bСТАРТ\b\s+'?([0-7]+)'?", line)
        if m:
            return int(m.group(1), 8)
    return 1
HEADER_BASE = start_base(be)
# СТАРТ распознаётся как шапка, только если это первая некомментарная
# строка. В части зон перед ним идут ЭКВ, адреса остаются 1-based.
# Ниже выбираем базу, дающую полное совпадение с эталоном.
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
# Выбираем базу: шапка (если СТАРТ распознан) иначе 1. Берём ту,
# что даёт больше совпадений; при равенстве - 1 (старый порядок).
def matched(base):
    return sum(1 for i in range(NW)
               if words.get(base + i) == int.from_bytes(g[i*6:(i+1)*6], "big"))
BASE = 1
if HEADER_BASE != 1 and matched(HEADER_BASE) > matched(1):
    BASE = HEADER_BASE
ok = bad = 0
out = bytearray()
for i in range(NW):
    got = words.get(BASE + i)       # слово i -> адрес BASE+i
    if got is None:
        bad += 1
        out += b"\x00" * 6
        continue
    want = int.from_bytes(g[i*6:i*6+6], "big")
    ok += (got == want)
    bad += (got != want)
    out += got.to_bytes(6, "big")
open(silver, "wb").write(out)
# Benign-overflow разрешён только при базе в конце ОП (76000).
overflow_ok = benign_overflow and BASE + NW > 0o77777
print("WORDS: всего=%d совпало=%d различий=%d" % (NW, ok, bad))
print("RESULT: " + ("PASS" if bad == 0 and (not benign_overflow or overflow_ok)
                    else "FAIL"))
PY

echo "=== 4. побайтовая сверка (disbesm_verify.sh) ==="
bash "$VERIFY" "$GOLD" "$WORK/silver.bin" \
    | sed -r 's/\x1B\[[0-9;]*m//g'

echo "=== зона $ZONE ($PREFIX): готово ==="
