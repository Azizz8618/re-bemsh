# Фаза 0 — верификация инструментов (PHASE 0)

Дата проверки: **19.11.2026**. Все команды выполнялись из
`/tmp/.private/azizz/re-bemsh`; образы томов **не модифицировались**, временные
файлы — только в `/tmp/.private/azizz/`.

## 1. Таблица инструментов

| Инструмент | Точный путь | Версия / справка | md5 бинарника | Критические особенности |
|---|---|---|---|---|
| `disbesm6` | `/usr/local/bin/disbesm6` (обычный файл, не symlink) | `disbesm6 -h` → `Usage: disbesm6 [-r] [-b] [-aN] [-eN] [-nSymtab] file...` (выход **1**, справка разбита: BOM+пробел в stdout, остальное в stderr) | `f40ca3e302c45a5d650d849eb5db2882` | `-a`/`-e`/`-R` — **восьмеричные, только слитно** (`-a10000`, `-R3=100`); `-e` обязателен (иначе весь код → `конд`); `-r`/`-b` **инертны**; метки кода `A#####` (не `G#####`), данные `D#####`; первый байт вывода — UTF-8 BOM `EF BB BF`; `memory[32768]` слов; склейку зон не размечает |
| `besmtool` | `/usr/local/bin/besmtool` | `Version: 2.6.458-9b5cabe`; `besmtool dump --help` — подкоманды `list/pass/arfa*/search/erase/zero/view/dump/write` | `187fed05ecf6013ea22f3fb19038b06b` | `--start` парсится `strtol(..., base=0)`: ведущий `0` = восьмеричное, иначе десятичное (`95 == 0137 == 0000137`); `dump` выдаёт **6 байт/слово**, зона = 6144 байт; файл тома берётся из `BESM6_PATH` |
| `dispak` | `/usr/local/bin/dispak` | `dispak version 2.6.458-9b5cabe, Copyright 1967-1987 USSR` (эмулятор БЭСМ-6; `-h` — список опций, `--path`, `--decode-output` и т.д.) | `944a91c7a0e2adce3cd7763b63774ea7` | Для Фазы 0 не используется напрямую; эмулятор/отладчик, не дизассемблер |
| `dtran` | **НЕ в PATH**; `/home/azizz/Yandex.Disk/dtran/dtran` | `-h`: дизассемблер БЭСМ-6 в MADLEN-псевдоассемблер; контейнеры `dms\|pa\|pb`, ключи `-F/-l/-e/-n/-o/-c/-R/-f/-E/-D/-d` | `a0ac400c5cf1f8b08d42582a5f116838` | ELF 64-bit PIE, `not stripped`; вызывать **только полным путём**; в_plan_-командах написан просто `dtran` — поправьте |
| `cosy2txt` | **НЕ в PATH**; `/home/azizz/Yandex.Disk/monitor80-re/tools/cosy2txt` | `-h` не реализован (молча exit 0); исходник `cosy2txt.cpp` рядом; декодирует COSY-поток (`decode_cosy`, `COSY_READ_OLD`) | `3d6d5d007e4f6e88d3e2e78185ded6ae` | ELF 64-bit PIE, `not stripped`; вызывать полным путём; используется в смежных проектах (monitor80-re), в Фазе 0 не нужен |
| `python3` | `/usr/bin/python3` → `/usr/bin/python3.12` | `Python 3.12.13` | `e95bfd343d5429a84fa678efcfd49436` | Для хелперов `tools/*.py` достаточно стандартной библиотеки |

### Локальные хелперы `tools/` (копии из смежных проектов, 19.11.2026)

| Файл | md5 | Назначение / нюанс |
|---|---|---|
| `tools/disbesm_extract.sh` | `8ecbdc3d0186b51ec88d4031df9b9010` | Извлекает зону через `besmtool dump`. **Номер зоны задаётся ВОСЬМЕРИЧНЫМ** (`137`, `0137`, `537`); `8#$ZONE` → dec. Оригинал из `simh/BESM6/scripts/` имел баг (молча извлекал не ту зону для десятичных 95/351) — здесь исправлено. Принимает `-o\|--output`; проверяет размер `length*6144`. |
| `tools/disbesm_verify.sh` | `bc6af613fdc305798d17232aefeb9faf` | Побайтовое сравнение 6-байтовых слов; при `-e` — ANSI-цвета (срезать `sed -r 's/\x1B\[[0-9;]*m//g'`); exit 0 при 0 отличий, 1 при различии; опции `--disasm`, `--disasm-path`. Внутри пишет `/tmp/_gold_zone.bin`, `/tmp/_silver_zone.bin`. |
| `tools/compare_shifted.py` | `85f3cab6dbef9647711067947d2ac295` | `Usage: tools/compare_shifted.py base_offset FILE_A FILE_B` (сдвиг версий `+0400₈`). |
| `tools/compare_octals.py` | `a63246ebd05029f9012aab2d6a09b360` | `Usage: tools/compare_octals.py FILE1 FILE2`. |
| `tools/bin_to_octal.py` | `71a562139655f63b8225db1d83f134aa` | `Usage: python3 bin_to_octal.py INPUT_BINARY_FILE`; 6 байт → 16-значное восьмеричное число; хвост <6 байт игнорируется. `python3 ... -h` **не** печатает справку (пытается открыть файл `-h`). |
| `tools/README.md` | `a0927bea250985ecdc56c3a500e74340` | Карта источников копий. |

## 2. Расхождение бинарник ↔ исходник `disbesm6` (подтверждено)

- `strings /usr/local/bin/disbesm6 | grep -E '^(A|G)%05o'` → **`A%05o`**.
- `/home/azizz/dispak/disbesm6/disbesm6.c` (1011 стр., md5
  `78cea3282de5dc36c8d9826a71ab3a26`), ст. 892 → `sprintf(buf, "G%05o", addr);`.
- Эмпирически на `/tmp/.private/azizz/mbe137.bin` (6144 байт, md5
  `60e09c375c2ad9e9bcbef1e71e25aefb`):
  - `disbesm6 -a0 -e0 mbe137.bin` → 1038 строк, BOM в начале, метка только
    `D00003` (A/G-меток в этом прогоне нет — трассировка обрывается на
    `пб (М3)`, см. guide);
  - `disbesm6 -a0 -e0 -R3=100 mbe137.bin` → появляется **реальная метка
    `A00100`** в строке `100:04 066 2101 A00100 Э66 '2101'(М4)`.
    Исходник напечатал бы `G00100`. **Вывод: бинарник печатает `A#####`.**

### `-r`/`-b` инертны (подтверждено diff)

```
md5(base)=md5(-r)=md5(-b)=md5(-r -b)=d6ea947c3f79b2ab2c9b113650f38af5
diff base vs -r / vs -b / vs -r-b → IDENTICAL; 'crc' в выводе: 0
```

## 3. Тест исправленного хелпера извлечения/верификации

```bash
cd /tmp/.private/azizz/re-bemsh
bash tools/disbesm_extract.sh 2348 137 1 -o /tmp/.private/azizz/stage0-137.bin
bash tools/disbesm_verify.sh /tmp/.private/azizz/stage0-137.bin \
                             /tmp/.private/azizz/stage0-137.bin
```

| Проверка | Результат | Exit |
|---|---|---|
| `extract 2348 137 1 -o …/stage0-137.bin` | `OK: … (6144 байт, зона 137, 1 зон)` | **0** |
| `stat -c %s …/stage0-137.bin` | **6144 байт** = 1024 слова × 6 | — |
| `md5sum …/stage0-137.bin` | `60e09c375c2ad9e9bcbef1e71e25aefb` (== `mbe137.bin`) | — |
| `verify stage0-137.bin stage0-137.bin` | `✓ Файлы идентичны (2000 слов)` (ANSI-цвет в выводе) | **0** |
| `extract 2348 0137 1` (ведущий ноль) | `OK … зона 0137`; байтово совпадает с `137` | **0** |
| `extract 2348 95 1` (десятичное) | **`stderr`: `8#95: слишком большое значение для основания (неверный маркер «8#95»)`; файл не создан** | **1** |

Вывод: десятичное `95` **корректно отвергается** (в восьмеричной системе цифры
`9` не существует) — это и есть ожидаемое «обработка/decline»: старый баг
молча извлёк бы зону `0117₈`, новый хелпер падает loudly. Для десятичных
номеров зон используйте прямой `besmtool dump 2348 --start=95 --length=1`.

## 4. Окружение

```
BESM6_PATH = /usr/local/share/besm6
uname -a   = Linux N15I 6.12.112-6.12-alt1 #1 SMP PREEMPT_DYNAMIC Sun Oct 4 05:14:06 UTC 2026 x86_64 GNU/Linux
df -h /tmp/.private/azizz = tmpfs 7,8G total / 4,7G used / 3,1G free (61%)
git status = ## main...origin/main ; clean — nothing to commit
```

md5 трёх копий тома 2348 (эталон не трогать, работать с копией в `/tmp`):

| Путь | md5 |
|---|---|
| `~/.besm6/2348` | `f5618ae2df018e2e7bb4bec9e25ef2f7` |
| `/usr/local/share/besm6/2348` (активный через `BESM6_PATH`) | `b4429a6cb69287309c974fb91a1c8942` |
| `~/Yandex.Disk/simh/BESM6/MD/EC5061/2348` | `15e5a52c5efe7b62c53f3bbb335e16cc` |

## 5. Воспроизведение (точные команды)

```bash
# Версии/справки
besmtool --version
besmtool dump --help
disbesm6 -h
dispak -h 2>&1 | head -30
/home/azizz/Yandex.Disk/dtran/dtran -h

# md5 бинарников
md5sum /usr/local/bin/disbesm6 /usr/local/bin/besmtool \
       /usr/local/bin/dispak /home/azizz/Yandex.Disk/dtran/dtran \
       /usr/bin/python3 \
       /home/azizz/Yandex.Disk/monitor80-re/tools/cosy2txt

# Расхождение A/G и -r/-b
strings /usr/local/bin/disbesm6 | grep -E '^(A|G)%05o'
grep -n '"[AG]%05o"' /home/azizz/dispak/disbesm6/disbesm6.c
disbesm6 -a0 -e0 -R3=100 /tmp/.private/azizz/mbe137.bin | grep A00100
for f in '' '-r' '-b' '-r -b'; do disbesm6 $f -a0 -e0 \
  /tmp/.private/azizz/mbe137.bin | md5sum; done

# Хелперы
bash tools/disbesm_extract.sh 2348 137 1 -o /tmp/.private/azizz/stage0-137.bin
bash tools/disbesm_verify.sh /tmp/.private/azizz/stage0-137.bin \
                             /tmp/.private/azizz/stage0-137.bin
bash tools/disbesm_extract.sh 2348 95 1 -o /tmp/.private/azizz/stage0-95.bin  # ожидаем exit 1

# Окружение
echo "$BESM6_PATH"; uname -a; df -h /tmp/.private/azizz
md5sum ~/.besm6/2348 /usr/local/share/besm6/2348 \
       ~/Yandex.Disk/simh/BESM6/MD/EC5061/2348
cd /tmp/.private/azizz/re-bemsh && git status
```

## 6. PHASE 0 STATUS: OK (блокеров нет)

Все инструменты найдены, версии/справки и md5 зафиксированы; расхождение
`A#####`/`G#####` и инертность `-r`/`-b` подтверждены; хелпер извлекает ровно
6144 байт и верифицируется с exit 0; десятичное `95` отвергается корректно;
окружение и md5 копий тома зафиксированы. **Phase 0 можно считать пройденной.**

Неблокирующие замечания (учесть в Фазах 1–7):

1. **`dtran` и `cosy2txt` отсутствуют в PATH** — во всех командах использовать
   полные пути (`/home/azizz/Yandex.Disk/dtran/dtran`,
   `/home/azizz/Yandex.Disk/monitor80-re/tools/cosy2txt`).
2. **`disbesm6 -h` возвращает exit 1** и пишет BOM + пробел в stdout, остаток
   справки — в stderr; `head`/`2>&1` в плане работает, но к exit-коду не
   относится.
3. **Хелпер ждёт восьмеричную зону** — `137`/`0137` правильно, `95` → exit 1.
   В скриптах Фазы 2/6 использовать десятичные номера напрямую в
   `besmtool dump` (как и написано в `docs/PLAN.md`) либо восьмеричные в хелпере.
4. **md5 `~/.besm6/2348` в `docs/PLAN.md` (`29987d5…`) не совпадает с текущим
   (`f5618ae2…`)** — образ изменился с момента написания плана; реальные
   дампы зон при этом побайтово те же (md5 зоны 0137 = `60e09c…`).
   Ориентироваться на актуальные md5 из раздела 4 и `BESM6_PATH`.
5. При `-a0 -e0` A/G-меток может не быть (только `D00003`); метка `A00100`
   появляется с `-R3=100` — это ожидаемое поведение трассировки, не ошибка.
