# Смежные проекты, часть 2: `re-siprod`, `besm-crypto`, `dtran`, `dispak/tests`

Продолжение [`ADJACENT.md`](ADJACENT.md). Изучено субагентом 19.11.2026;
файлы исходных репозиториев не менялись.

## 1. re-siprod — готовый цикл «БЕМШ → эмулятор → побайтовая сверка»

Точки входа: `tools/siprod_bemsh.py` (802 стр.), `drakon/bemsh.py`,
`drakon/asmjob.py`, `notes/linker.md` (439 стр.), `notes/registers.md §3.5`,
`notes/loader.md §7`, `tools/siprod_{lib,asm,dis}.py`.

Колода (`siprod_bemsh.py:407–420`): `шифр 419999^`, `трак 64^`,
`лент 30(2048-6200)^`, `лент 42(2099)^`, `лент 43(2248-ЗП)^`, `ацп 40^`,
`вход 4000^`, `а1`, `ВВД$$$^` + текст + `КВЧ$$$^`, `ТРН$$$^`,
`ЧТКОМП420070^`, `1-1^` (запись модуля; `0-0` — только листинг), `БТМАЛФ^`,
`ЗОНМОД433900 0001^`, `КНЦ$$$^`, `_$ЕКОНЕЦ`.

**Два обязательных элемента:** завершающий `^` после `ВВД$$$` (иначе первая
строка поглощается) и `<ИМЯ> СТАРТ <АДРЕС>`. В `asmjob.py` они нарушены
(`ВВД$$$` без `^`, лента 27) — за основу брать `siprod_bemsh.py`.

Запуск/сверка:

```python
shutil.copy("$BESM6_SHARE/2248", "/tmp/siprod-bemsh/2248")
env = dict(os.environ, BESM6_PATH="/tmp/siprod-bemsh:/usr/local/share/besm6")
subprocess.run(["dispak", "<name>.b6"], env=env, cwd="/tmp/siprod-bemsh")
```

Парсер листинга: `CODE_RE = (\d{2}) (\d{2,3}) +(\d{4,5})$`, RIGHT_COL=49,
`RELOC_RE = \+\s*(\d+)(?:\+(\d+))?`. `check_module()` сверяет opcode, регистр,
адрес, метки `L<oct>`, абсолютные и внешние символы. Результат: 98 модулей
компилируются без ошибок, код совпадает слово в слово.

Правила имён: метка `L<восьм смещение в словах>` (команда = 2×смещение),
`V<n>` — bss, `К<n>` — константы (`К0 КОНД В'…'` — префикс `В` обязателен).
Внешние символы: `<владелец> ВНЕШ <sym>`; `ИМЯ±СМЕЩЕНИЕ` для общих блоков.

Библиотеки кодирования слов: `tools/siprod_asm.py` (таблица `OPS`,
`decode/encode`, `DMS_BIT=0x200000`, `STRUCT_BIT=0x80000`, `EXP_BIT=0x40000`;
слово = `hi<<24 | lo`), `siprod_lib.py` (`Library`, TEXT[64], разбор каталога),
`siprod_dis.py:250–305` (вызов `disbesm6 -a0 -e0 -n…`).
**Замечание:** комментарий в `siprod_dis.py` («тип 2 = data») противоречит
исходнику disbesm6 — там `W_DATA=1`, `W_CODE=2`; доверять исходнику.

Зоны 2348 по re-siprod: `01267` (СИПРОД, 95 модулей), `02100` (рабочая
СИПРОД+DRAKON), `01730` (библиотека Дубны), `02150` (РЕДАКТ+DRAKON).

## 2. besm-crypto / dtran / dispak/tests

**besm-crypto:** `src/gost_2348.pas` (колода `*name Pascal / *call yesmemory /
*system / *libra: 13 / *pascal`), `tools/plcatalog.sh` (чтение каталога PERSO),
`work/*.b6` (шаблоны `*perso:40ZZZZ`, `*to perso`), `zone2500/LIBRARY.md`
(формат каталога PERSO и смещений точек входа). ⚠ Описывает **другое состояние**
тома 2348 (Pascal 2026 в 2000, GOSTLIB в 2500/2560) — перед заимствованием
сверять md5 и каталог зоны 0.

**dtran** (`/home/azizz/Yandex.Disk/dtran/dtran`, не в PATH): `-F dms|pa|pb`,
`-l` (пересобираемая форма), `-e` (раскрыть EQU), `-n`, `-o`, `-c`, `-R N`,
`-f off`, `-E file`, `-D file`, `-d`. Рабочий вызов `dtran -F dms <obj.o>`;
`tests/compare_byte.sh --bin FILE` — дизассемблирование любого бинарника.
11 DMS round-trip тестов. Для re-bemsh: disbesm6 — основной листинг, dtran —
перекрёстная проверка имён/меток.

**dispak/tests:** `run-test.py` читает `options.txt`, гонит `dispak`, сравнивает
`output.run` с `output.txt` (`difflib` + wildcard `#`); `provision_disks()`
распаковывает чистые тома из `*.xz`. Запуск: `run-all-tests.sh` или `ctest`.
`bemsh-ms/bemsh.b6` — колода в Монитор-80 3.7 с `*call yesmemory / *system /
*main prog / *bemsh / … / *execute`. Штампы макроредактора/машины присутствуют
в `pprog01..10` и `sort` (есть макросы), но **отсутствуют** в `bemsh-ms` и
`bemsh-standalone` (`БЛМАК`) — ожидаемо, не признак другой версии.

## 3. re-glissade / re-mrv (запись и контроль зон)

`re-glissade/TOOLS/install-2348.sh`: backup → `besmtool zero 2348 --start=1472
--length=8` → колоды записи → `besmtool view … --encoding=t` → контрольный
`*call`. `dump_zone.py` парсит «сырой» образ (зона **8256 байт** = 6144 данных
+ 1024 конволют + 1088 контроля; не путать с 6144-байтовым дампом besmtool).
`verify-library.py` — приём проверки «изменены только нужные зоны» (с поправкой
`ZONE_OFFSET=-4`).

`re-mrv/docs/mrv_write_4000.md`: `4000₈` в `asmjob.py` — адрес входа паспорта,
не номер зоны; `besmtool zero 2348 --start=2048` соответствует зоне 4000₈.
В МАДЛЕН-диалекте нет `ORG/START/BASE`.

## 4. Шортлист артефактов (часть 2)

1. `re-siprod/tools/siprod_bemsh.py` — каркас задания/парсера/сверки.
2. `re-siprod/tools/siprod_asm.py` + `siprod_lib.py` — декодер/энкодер слов, каталог.
3. `re-siprod/notes/linker.md` — справочник по МАКРО-БЕМШ и РВС.
4. `dtran` + `tests/compare_byte.sh` — перекрёстная верификация.
5. `dispak/tests/run-test.py` — каркас регресс-тестов листингов.
6. `besm-crypto/tools/plcatalog.sh` — инвентаризация PERSO (если понадобится).
7. `re-glissade/TOOLS/install-2348.sh` — безопасная запись в 2348 (только при
   отдельном задании; в нашем проекте эталон read-only).
