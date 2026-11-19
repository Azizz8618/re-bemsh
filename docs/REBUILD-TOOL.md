# `tools/rebuild-zone.sh` — универсальная сборка зоны из `.be`

Дата: **19.11.2026**. Фаза A2 плана `docs/PLAN-NEXT.md`.
Обобщение проверенного рецепта `tools/rebuild-0137.sh`; оригинальный
скрипт не изменялся.

## 1. Назначение

Собрать объектные слова зоны из исходника МАКРО-БЕМШ 06/78
(`bemsh/<TYPE>-Z<zone>.be`) штатным транслятором `dispak` и сверить
их с эталоном `gold/<TYPE>-Z<zone>-L1.bin`.

Рецепт **не изменён**: задание `0-0` (только листинг, запись `1-1`
не применяется — она добавляет слова перемещений), `BESM6_PATH`
указывает только на копии образов в `/tmp`.

## 2. CLI

```bash
bash tools/rebuild-zone.sh <ZONE_OCTAL> [B|MBE2|ASM]
```

* `ZONE_OCTAL` — восьмеричный номер зоны (`0137`, `0540`);
  ведущий ноль допустим, на выходе всегда 4 цифры;
* режим (по умолчанию `B`):

| Режим | `.be` | эталон |
|---|---|---|
| `B` (по умолчанию) | `bemsh/MBE-Z<zone>[-L1].be` | `gold/MBE-Z<zone>-L1.bin` |
| `MBE2` | `bemsh/MBE2-Z<zone>[-L1].be` | `gold/MBE2-Z<zone>-L1.bin` |
| `ASM` | `bemsh/ASM-Z<zone>[-L1].be` | `gold/ASM-Z<zone>-L1.bin` |

Поддерживаются оба имени исходника: с `-L1` (цель Фазы A1) и без
него (существующий `bemsh/MBE-Z0137.be`).

## 3. Guard (exit 3)

Сборка работает **только** с копиями образов в
`/tmp/.private/azizz/rebuild-all/`. Скрипт отказывается (exit 3),
если рабочий путь, `IMAGE_DIR` или эффективный `BESM6_PATH` указывает
на настоящий каталог образов:

* `/usr/local/share...`;
* `~/.besm6...`;
* `.../EC5061...`.

Переменные окружения:

* `BESM6_PATH` — incoming значение переопределяется на каталог копий
  (как и в `rebuild-0137.sh`); с `REBUILD_STRICT_GUARD=1` такой вызов
  тоже завершается exit 3 (полный строгий вариант guard-а);
* `IMAGE_DIR` — проверяется строго;
* `BESM6_SHARE` — источник копий образов (только чтение)
  (по умолчанию `/usr/local/share/besm6`);
* `REBUILD_ALL_IMAGES` — каталог копий (по умолчанию
  `/tmp/.private/azizz/rebuild-all`).

Примеры проверки guard-а:

```bash
IMAGE_DIR=/usr/local/share/besm6 bash tools/rebuild-zone.sh 0137 B
# REFUSE ... ; rc=3
REBUILD_STRICT_GUARD=1 bash tools/rebuild-zone.sh 0137 B
# REFUSE ... ; rc=3
```

## 4. Точные команды (шаги скрипта)

1. Проверка аргументов и поиск `.be` + `gold` (существование файлов).
2. Guard путей (см. §3); `mkdir -p /tmp/.private/azizz/rebuild-all/<zone>`.
3. Копии `2048`, `2053`, `2099`, `2248` в каталог копий, если их там
   нет (сначала из уже проверенного `rebuild-0137`, затем из SHARE).
4. Генерация задания: `шифр 419999`, ленты 30/42/43, `ВВД$$$ …
   КВЧ$$$ … ТРН$$$`, строки `.be`, `ЧТКОМП420070`, **`0-0`**,
   `ЗОНМОД433900 0001`, `КНЦ$$$`.
5. `env BESM6_PATH=<копии> dispak -l <zone>/job.b6` → `listing.out`;
   обязательный маркер `ЧИCЛO OШИБOK=0000`.
6. Разбор листинга (колонка адреса `[25:30]`, слово `[31:]`,
   `СТАРТ 1`: слово `i` → адрес `i+1`) → `<zone>/silver.bin`.
7. Печать `WORDS: всего=N совпало=M различий=K` и `RESULT: PASS/FAIL`.
8. Побайтовая сверка: `tools/disbesm_verify.sh gold silver`
   (ANSI-коды срезаются).

## 5. Результат на зоне 0137

```bash
cd /tmp/.private/azizz/re-bemsh
bash tools/rebuild-zone.sh 0137 B
```

Наблюдаемый вывод (ключевое):

```
Z0137 ... ДЛИHA ПPOГ=02000 ... ЧИCЛO OШИБOK=0000
WORDS: всего=1024 совпало=1024 различий=0
RESULT: PASS
Размер: 6144 байт (2000 слов, 1+0 зон)
✓ Файлы идентичны (2000 слов)
```

Итог: **1024/1024 words, 0 байт отличий**.

## 6. Makefile-цели

| Цель | Действие |
|---|---|
| `make rebuild-zone Z=0137 [MODE=B]` | сборка одной зоны (есть usage-hint) |
| `make rebuild-all` | все зоны с `.be`; сводка `найдено/PASS/FAIL` |
| `make rebuild-check` | регрессия 0137; требует `RESULT: PASS` и 1024/1024 |
| `make check-all` | `stage0` + `rebuild-check` + `verify` + `unittest` |

Проверка:

```bash
make -n rebuild-zone rebuild-all rebuild-check check-all
make rebuild-check
# rebuild-check: OK (RESULT: PASS, 1024/1024)
```

Сейчас `.be` существует только для зоны 0137, поэтому `rebuild-all`
печатает `найдено=1 PASS=1 FAIL=0`.

## 7. Как добавить новую зону

1. Получить исходник `bemsh/<TYPE>-Z<zone>-L1.be` (например, конвертером
   Фазы A1 `tools/dis2be.py`; правила — в `docs/PLAN-NEXT.md` §A1).
2. Убедиться, что эталон `gold/<TYPE>-Z<zone>-L1.bin` на месте
   (6144 байт = 1024 слова).
3. Запустить `bash tools/rebuild-zone.sh <zone> <MODE>`.
4. При `RESULT: FAIL` править `.be` (не эталон и не оригинальный скрипт),
   повторять шаг 3 до `PASS`.
5. Добавить зону в `analysis/REBUILD-ALL.md` (Фаза A4) и перезапустить
   `make rebuild-all` / `make rebuild-check`.
