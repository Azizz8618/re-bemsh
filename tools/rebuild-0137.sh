#!/usr/bin/env bash
# rebuild-0137.sh — собрать зону 0137 из bemsh/MBE-Z0137.be и сверить с gold/.
# Использует ТОЛЬКО копии образов в /tmp; листинг (0-0) не пишет в образы.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BE="$ROOT/bemsh/MBE-Z0137.be"
GOLD="$ROOT/gold/MBE-Z0137-L1.bin"
VERIFY="$ROOT/tools/disbesm_verify.sh"
WORK="${REBUILD_0137_WORK:-/tmp/.private/azizz/rebuild-0137}"
SHARE="${BESM6_SHARE:-/usr/local/share/besm6}"

# --- защита: работаем только с копиями образов в /tmp ---
case "$WORK" in
    /tmp/*) : ;;
    *) echo "REFUSE: WORK должен быть под /tmp (получено: $WORK)"; exit 2 ;;
esac
for real in /usr/local/share/besm6 "$HOME/.besm6" \
            /home/azizz/Yandex.Disk/simh/BESM6/MD/EC5061; do
    [ "$WORK" = "$real" ] && {
        echo "REFUSE: нельзя работать с настоящим каталогом образов"; exit 2; }
done

for f in "$BE" "$GOLD" "$VERIFY"; do
    [ -f "$f" ] || { echo "Нет файла: $f"; exit 1; }
done

mkdir -p "$WORK"
for v in 2048 2053 2099 2248; do
    if [ ! -f "$WORK/$v" ]; then
        [ -f "$SHARE/$v" ] || { echo "Нет образа $SHARE/$v"; exit 1; }
        cp "$SHARE/$v" "$WORK/$v"
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
if ! env BESM6_PATH="$WORK" dispak -l "$WORK/job.b6" \
        > "$WORK/listing.out" 2>&1; then
    echo "FAIL: dispak вернул ненулевой код"; tail -20 "$WORK/listing.out"; exit 1
fi
grep -a "ЧИCЛO OШИБOK=0000" "$WORK/listing.out" >/dev/null || {
    echo "FAIL: ошибки транслятора"; grep -a "OШИБOK" "$WORK/listing.out"; exit 1; }
grep -a "ДЛИHA ПPOГ" "$WORK/listing.out" || true

echo "=== 3. листинг -> объектные слова -> silver.bin ==="
python3 - "$WORK/listing.out" "$GOLD" "$WORK/silver.bin" <<'PY'
import re, sys
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
for i in range(NW):
    got = words.get(i + 1)          # СТАРТ 1: слово i -> адрес i+1
    if got is None:
        bad += 1
        out += b"\x00" * 6
        continue
    want = int.from_bytes(g[i*6:i*6+6], "big")
    ok += (got == want)
    bad += (got != want)
    out += got.to_bytes(6, "big")
open(silver, "wb").write(out)
print("WORDS: всего=%d совпало=%d различий=%d" % (NW, ok, bad))
print("RESULT: " + ("PASS" if bad == 0 else "FAIL"))
PY

echo "=== 4. побайтовая сверка (disbesm_verify.sh) ==="
bash "$VERIFY" "$GOLD" "$WORK/silver.bin" \
    | sed -r 's/\x1B\[[0-9;]*m//g'
