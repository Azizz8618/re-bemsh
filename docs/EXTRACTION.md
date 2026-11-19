# Фазы 2–3: извлечение и дизассемблирование

**Дата:** 19.11.2026
**Образ:** `/usr/local/share/besm6/2348`
`BESM6_PATH=/usr/local/share/besm6`
**md5 образа до и после работ:**
`b4429a6cb69287309c974fb91a1c8942` (не изменился — только чтение).
**Инструменты:** `/usr/local/bin/{besmtool,disbesm6,dispak}`.

---

## 1. Выполненные команды

Извлечение зон, манифест и дизассембль (одной командой):

```bash
cd /tmp/.private/azizz/re-bemsh
make dis
```

`make dis` (цель из `Makefile`, фазы 2+3) выполняет:

```bash
mkdir -p gold dis sym
# АСМ ИТМ: 0055–0060₈ (dec 45..48), хелпер ждёт ВОСЬМЕРИЧНУЮ зону
for d in 45 46 47 48; do
  z=$(printf '%04o' $d)
  tools/disbesm_extract.sh 2348 $z 1 -o gold/ASM-Z$z-L1.bin
done
# БЕМШ 06/78: 0137–0177₈ (dec 95..127)
for d in $(seq 95 127); do
  z=$(printf '%04o' $d)
  tools/disbesm_extract.sh 2348 $z 1 -o gold/MBE-Z$z-L1.bin
done
# B2 12/77: 0540–0577₈ (dec 352..383); 0537₈ пуста — НЕ брать
for d in $(seq 352 383); do
  z=$(printf '%04o' $d)
  tools/disbesm_extract.sh 2348 $z 1 -o gold/MBE2-Z$z-L1.bin
done
# манифест всех дампов
(cd gold && sha256sum *.bin | sed 's|  |  gold/|') > manifest.sha256
sha256sum -c manifest.sha256
# полный образ БЕМШ (33 зоны)
: > gold/MBE-full.bin
for d in $(seq 95 127); do
  z=$(printf '%04o' $d)
  cat gold/MBE-Z$z-L1.bin >> gold/MBE-full.bin
done
sha256sum gold/MBE-full.bin >> manifest.sha256
# дизассембль каждой зоны: -a0 -e0 (восьмеричные, слитно)
for f in gold/*.bin; do
  n=$(basename "$f" .bin)
  disbesm6 -a0 -e0 "$f" > "dis/$n.asm" 2> "dis/$n.err"
done
disbesm6 -a10000 -e10000 -nsym/MBE.tab gold/MBE-Z0137-L1.bin \
  > dis/MBE-Z0137-named.asm
disbesm6 -a0 -e0 -R3=100 gold/MBE-Z0137-L1.bin \
  > dis/MBE-Z0137-R3.asm
grep -hoE '\b[AG][0-9]{5}\b|\bD[0-9]{5}\b' dis/*.asm \
  | sort -u > dis/labels.raw
```

`make dis` завершился с кодом 0. Хелпер
`tools/disbesm_extract.sh` переводит восьмеричную зону в десятичную
через `ZONE_DEC=$((8#$ZONE))` и зовёт
`besmtool dump ... --start=0<зона> --length=1 --to-file=...`.

---

## 2. Проверка результатов

| Проверка | Ожидалось | Получено | Статус |
|---|---|---|---|
| `gold/*.bin` всего | 70 | 70 | PASS |
| дампов одной зоны `*-L1.bin` | 69 | 69 | PASS |
| размер каждого `*-L1.bin` | 6144 | 6144 (все 69) | PASS |
| `gold/MBE-full.bin` | 202752 | 202752 | PASS |
| `sha256sum -c manifest.sha256` | все ЦЕЛ | 70 ЦЕЛ | PASS |
| строк в `manifest.sha256` | 70 | 70 | PASS |
| `dis/*.asm` всего | 72 | 72 | PASS |
| пустых `dis/*.asm` | 0 | 0 | PASS |
| `dis/*.asm` с СТАРТ и ФИНИШ | 72 | 71 | СМ. §5 |
| непустых `dis/*.err` | 0 | 0 | PASS |

Итого `gold/`: 4 зоны АСМ + 33 зоны БЕМШ + 32 зоны B2 = 69
поозонных дампов + `MBE-full.bin` = **70 файлов `.bin`**.
`dis/`: 70 дизассемблей из `gold/*.bin` + `MBE-Z0137-named.asm`
+ `MBE-Z0137-R3.asm` = **72 файла `.asm`**.

---

## 3. Контрольные суммы (из `manifest.sha256`)

| Файл | SHA-256 |
|---|---|
| `gold/ASM-Z0055-L1.bin` | `ae3602e1a72622ea34c2ea2127e4b3b53fd9851c1cc488da04623ad305363be2` |
| `gold/MBE-Z0137-L1.bin` | `91b06af5b80e8d2e14e6b5aaa3a900845432edd8ec973daa9c25183b91b0fd0d` |
| `gold/MBE2-Z0540-L1.bin` | `9a3b7ed00b1dc820c42561109390949ec8140b36bcbe5e7eb9ce251f302c4556` |
| `gold/MBE-full.bin` | `ec2db4e435043bd5f4c1a4ebfe9eba9488c949de60a99b23df7fe0cf5a4c3e53` |

Полный список из 70 сумм — в `manifest.sha256`. Проверка
`sha256sum -c manifest.sha256` выдала 70 строк «ЦЕЛ», отказов нет.

---

## 4. Контроль дизассембля

`head -20 dis/MBE-Z0137-L1.asm` (BOM в первой строке срезан
для читаемости, числовые поля не менялись):

```
          File: gold/MBE-Z0137-L1.bin
         Type: Binary
         Code: 6144 (02000) words
      Address: 0

                СТАРТ  '0'
* next insn used as data
    0 00 000 0000  START  зп  START
      00 100 0000         зп  '70000'
    1 00 000 0000         зп  START
      00 020 0000         сбр  START
    2 00 000 0000         зп  START
      00 000 0003         зп  D00003
* next insn used as data
    3 00 000 0000  D00003  зп  START
      00 002 3554         рег  '3554'
    4 00 000 0000         зп  START
      03 30 00000         пб  (М3)
    5 0000000000021173    конд  в'0000000000021173'
    6 0000000000021203    конд  в'0000000000021203'
```

Начало осмысленное и совпадает с ожиданием `docs/PLAN.md`:
`СТАРТ '0'`, `зп '70000'`, `пб (М3)`.

Статистика по всем `dis/*.asm`:

| Метрика | Значение |
|---|---|
| Меток кода `A#####` (вхождений) | 473 |
| Меток данных `D#####` (вхождений) | 998 |
| Уникальных меток в `dis/labels.raw` | 294 |
| `* next insn used as data` (вхождений) | 69 |
| Файлов с `next insn used as data` | 25 |

Артефакт `next insn used as data` и метки `D#####` — известные
особенности `disbesm6` (окно `fuzz=64`, см. `AGENTS.md` §2).

---

## 5. Аномалия: сегментный сбой на `MBE-full.bin`

При дизассембле цикла `for f in gold/*.bin` один вызов
`disbesm6 -a0 -e0` завершился сегментным сбоем
(«Ошибка сегментирования», код 139). Воспроизведено отдельно:

```bash
disbesm6 -a0 -e0 gold/MBE-full.bin > /tmp/mbefull-test.asm
# exit=139, stdout 1466368 байт
```

Причина: `MBE-full.bin` = 202752 байт = **33792 слова**, что
превышает предел `disbesm6` `memory[32768]`. Для сравнения,
обычная зона (`MBE-Z0137-L1.bin`, 6144 байт = 1024 слова)
дизассемблируется с кодом 0 (55168 байт вывода).

Следствие: `dis/MBE-full.asm` получился усечённым (1466368 байт) —
содержит `СТАРТ`, но **не содержит `ФИНИШ`**. Остальные 71 файл
`.asm` содержат и `СТАРТ`, и `ФИНИШ`, имеют ненулевой размер.
Это ожидаемое поведение: `docs/PLAN.md` и `AGENTS.md` прямо
запрещают склеивать зоны для дизассембля и требуют обрабатывать
по одной зоне. `MBE-full.bin` нужен лишь как контрольная
конкатенация для манифеста, а не как вход для `disbesm6`.

`make dis` при этом вернул код 0 (рецепт `make` не использует
`set -e` для этого цикла), поэтому сбой не прервал сборку.
С stderr всех зон: файлы `dis/*.err` пусты (0 байт).

---

## 6. Round-trip проверка зоны 0137

Прямое извлечение той же зоны через `besmtool dump` с десятичным
номером (эквивалент восьмеричного `0137`):

```bash
BESM6_PATH=/usr/local/share/besm6 \
  besmtool dump 2348 --start=95 --length=1 \
  --to-file=/tmp/.private/azizz/roundtrip137.bin
cmp /tmp/.private/azizz/roundtrip137.bin gold/MBE-Z0137-L1.bin
```

Результат:

- размер `roundtrip137.bin` = 6144 байт;
- `cmp` — **идентичны** (код 0, расхождений нет);
- md5 обоих: `60e09c375c2ad9e9bcbef1e71e25aefb`;
- sha256 обоих:
  `91b06af5b80e8d2e14e6b5aaa3a900845432edd8ec973daa9c25183b91b0fd0d`.

Штамп `Writing 1 zones (6 kbytes) from disk 2348/0137` подтверждает,
что десятичное `95` и восьмеричное `0137` — одна зона.

---

## 7. Итог

Фазы 2 и 3 выполнены: извлечены 69 поозонных дампов (6144 байт
каждый) и `MBE-full.bin` (202752 байт), построен `manifest.sha256`
(70 сумм, все совпадают), получены 72 файла дизассембля.
Единственная аномалия — сегментный сбой `disbesm6` на
склеенном `MBE-full.bin` (превышение лимита памяти), повлиявший
только на `dis/MBE-full.asm`. Эталонный образ не изменялся
(md5 до и после работ одинаков).
