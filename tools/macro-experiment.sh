#!/usr/bin/env bash
# macro-experiment.sh — управляемые эксперименты с таблицей макроопределений
# Фаза B плана docs/PLAN-NEXT.md. Все прогоны — ТОЛЬКО на копиях образов.
# Выход: /tmp/.private/azizz/macro-exp/ (jobs, листинги, объектные слова).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${MACRO_EXP_WORK:-/tmp/.private/azizz/macro-exp}"
SHARE="${BESM6_SHARE:-/usr/local/share/besm6}"

# ---------------------------------------------------------------------------
# GUARD: отказ работать с настоящими каталогами образов (exit 3).
# ---------------------------------------------------------------------------
refuse() { echo "REFUSE (exit 3): $1" >&2; exit 3; }
case "$WORK" in
    /tmp/.private/azizz/*) : ;;
    *) refuse "WORK должен быть под /tmp/.private/azizz/ (получено: $WORK)" ;;
esac
[ "$WORK" = "$SHARE" ] && refuse "WORK == BESM6_SHARE"
for real in /usr/local/share/besm6 "$HOME/.besm6" \
            /home/azizz/Yandex.Disk/simh/BESM6/MD/EC5061 \
            /home/azizz/Yandex.Disk/simh/BESM6/DISKS \
            "$SHARE"; do
    [ "$WORK" = "$real" ] && refuse "нельзя работать с каталогом $real"
done
mkdir -p "$WORK"

# ---------------------------------------------------------------------------
# Копии томов. BESM6_PATH выставляется так, чтобы копии шли ПЕРВЫМИ.
# ---------------------------------------------------------------------------
for v in 2048 2053 2099 2248; do
    [ -f "$SHARE/$v" ] || { echo "Нет образа $SHARE/$v" >&2; exit 1; }
    cp -f "$SHARE/$v" "$WORK/$v"
done

python3 - "$WORK" "${MACRO_EXP_TEMPLATE:-/home/azizz/Yandex.Disk/re-dispak/testdks/mbe60_bemsh.txt}" <<'PY'
import os, re, subprocess, sys

WORK = sys.argv[1]
TEMPLATE = sys.argv[2]
ENV = dict(os.environ)
ENV["BESM6_PATH"] = WORK + ":/usr/local/share/besm6"

# Каркас задания Монитор-80 -> *bemsh (проверен на
# re-dispak/testdks/mbe60_bemsh.txt, 0 ошибок на исходном примере).
HEAD = ["ШИФР 419900ЗС5^", "ОЗУ 32^", "ТРА 100^", "АЦП 64^", "ЕЕВ1А3",
        "*name", "*      call yesmemory", "*      system", "*main mbe60",
        "*bemsh", "inp$$$"]
TAIL = ["eoi$$$", "trn$$$", "0-0", "end$$$", "*libra:2",
        "*call dtran(МВE60)", "base:10,0", "*super", "*assem", "*read:1",
        "*end file", "``````", "еконец"]

# Константная программа (одинакова во всех опытах). Berkeley: берём тело
# проверенного mbe60_bemsh.txt; при отсутствии шаблона — короткий запасной
# вариант (объектный модуль будет пустым, это честно фиксируется в выводе).
if os.path.isfile(TEMPLATE):
    _L = open(TEMPLATE, encoding="utf-8").read().splitlines()
    PROG = _L[_L.index("inp$$$") + 1:_L.index("eoi$$$")]
    print("Программа: %s (%d строк) из %s" % ("шаблон", len(PROG), TEMPLATE))
else:
    PROG = ["ТЕСТ\tСТАРТ 1", "ФИНИШ"]
    print("ВНИМАНИЕ: шаблон %s не найден; короткая программа, объект пуст." % TEMPLATE)

# Три контролируемых набора макроопределений.
# Написания команд сохранены как в macros.be; '∧' заменён на ASCII '&'
# (именно '&' принимает транслятор, см. re-dispak/testdks/*_bemsh.txt).
# Ведущий пробел перед 'macro' обязателен (иначе транслятор их не регистрирует).
EXPERIMENTS = {
    # E0: контроль — ни одного макроопределения.
    "E0": [],
    # E1: один макрос, 1 формальный параметр (macros.be:223-226, «ПРЕ»).
    "E1": [" macro", "&m пре &a", " уиа &a", " mend"],
    # E2: два макроса с разным числом параметров (1 и 2).
    "E2": [" macro", "&m пре &a", " уиа &a", " mend",
           " macro", "&m во &a,&b", " уиа &a", " уиа &b", " mend"],
    # E3: макрос с LСLА / SЕТА / .МЕТКА / АIF (macros.be:100-108, «Е»).
    "E3": [" macro", " е", " lclа &n", "&n seta 48", " .сл анop",
           "е&n экв '103'+48-&n", "&n seta &n-1", " aif (&n ne 0).сл",
           " mend"],
}

RE_GS  = re.compile(r"(\d+)-KOЛИЧ ЯЧ ГC")
RE_ERR = re.compile(r"ЧИCЛO OШИБOK=(\d+)")
RE_WORD = re.compile(r"\b([0-7]{16})\b")

def object_words(path):
    """Объектные слова из листинга (16 восьмеричных цифр в строке)."""
    return [m.group(1) for m in
            (RE_WORD.search(line) for line in open(path, encoding="utf-8")) if m]

results = {}
for tag, macros in EXPERIMENTS.items():
    job = "\n".join(HEAD + macros + PROG + TAIL) + "\n"
    jf = os.path.join(WORK, tag + ".job.b6")
    of = os.path.join(WORK, tag + ".listing.out")
    open(jf, "w", encoding="utf-8").write(job)
    try:
        r = subprocess.run(["dispak", "-l", jf], capture_output=True, text=True,
                           env=ENV, cwd=WORK, timeout=180)
    except subprocess.TimeoutExpired:
        print(f"{tag}: FAIL dispak timeout"); continue
    out = r.stdout + r.stderr
    open(of, "w", encoding="utf-8").write(out)
    g = RE_GS.search(out); e = RE_ERR.search(out)
    words = object_words(of)
    results[tag] = dict(exit=r.returncode,
                        gs=g.group(1) if g else "?",
                        errs=e.group(1) if e else "?",
                        words=words)
    # Зафиксировать ошибки разбора макросов отдельно (они НЕ должны появляться).
    macro_errs = [l.strip() for l in out.splitlines()
                  if "TEPM HE OПP" in l or "TEPM YЖE OПP" in l
                  or "ПOPЯДOK ПPEД" in l]
    results[tag]["macro_errs"] = macro_errs

print("=" * 78)
print("ЭКСПЕРИМЕНТЫ С ТАБЛИЦЕЙ МАКРООПРЕДЕЛЕНИЙ (копии образов в %s)" % WORK)
print("=" * 78)
print(f"{'опыт':<6}{'exit':<6}{'ошибок':<9}{'КОЛИЧ ЯЧ ГС':<14}{'слов':<7}{'ошибки макросов'}")
for tag, d in results.items():
    print(f"{tag:<6}{d['exit']:<6}{d['errs']:<9}{d['gs']:<14}"
          f"{len(d['words']):<7}{len(d['macro_errs'])}")

base = results.get("E1", {}).get("words", [])
print("\nИЗМЕНЕНИЯ КОЛИЧ ЯЧ ГС (восьмеричное):")
g0 = results.get("E0", {}).get("gs")
for tag in ("E1", "E2", "E3"):
    g = results[tag]["gs"]
    if g0 != "?" and g != "?":
        print(f"  E0={g0} -> {tag}={g}  (+{int(g,8)-int(g0,8)} ячеек)")

print("\n ПОБАЙТОВОЕ СРАВНЕНИЕ ОБЪЕКТНЫХ СЛОВ (эталон E1):")
for tag in ("E2", "E3"):
    w = results[tag]["words"]
    if len(w) != len(base):
        print(f"  E1 vs {tag}: длины {len(base)} != {len(w)} -> РАЗЛИЧИЕ")
        continue
    diff = [(i, a, b) for i, (a, b) in enumerate(zip(base, w)) if a != b]
    print(f"  E1 vs {tag}: {len(diff)} отличий из {len(base)} слов"
          + ("  -> ИДЕНТИЧНЫ" if not diff else f"  first={diff[:3]}"))

print("\n ПЕРВЫЕ 8 ОБЪЕКТНЫХ СЛОВ (offset | E1 | E2 | E3):")
for i in range(min(8, len(base))):
    vals = [results[t]["words"][i] if i < len(results[t]["words"]) else "-"
            for t in ("E1", "E2", "E3")]
    print(f"  {i*6:04o} | {vals[0]} | {vals[1]} | {vals[2]}")

verdict = ("НЕ ПОДТВЕРЖДЁН: объектные модули E1/E2/E3 идентичны; "
           "таблица макроопределений в них не попадает.")
print("\nВЕРДИКТ по [TAG(24)|VAL(24)]: " + verdict)
PY

echo
echo "Листинги и задания: $WORK/*.job.b6, $WORK/*.listing.out"
