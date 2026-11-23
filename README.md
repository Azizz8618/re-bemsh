# re-bemsh

Реверс-инжиниринг транслятора языка ассемблера БЭСМ-6 (Монитор-80,
магнитный том 2348) и транслятора макроопределений МАКРО-БЕМШ.

**Важно:** `МВЕ60` в листингах — имя тестовой программы связи с ДКС,
написанной *на* БЕМШ и продемонстрированной этим транслятором; это не имя
транслятора и не его исходник. Сам транслятор — запись каталога
`ТРАНСЛЯТОР С М/К БЕМШ` в зонах `0137–0177₈`.

Проект создан на базе пустого репозитория
`git@github.com:Azizz8618/re-bemsh.git`.

## Цель

Восстановить структуру и исходные тексты:

1. транслятора с языка ассемблера БЕМШ, размещённого на томе 2348;
2. транслятора макроопределений МАКРОБЕМШ (`ТРАНСЛЯТОР С М/К БЕМШ`, зоны
   `0137–0177₈`), включая макроредактор и макромашину;
3. механизм вызова процедур МС «ДУБНА» из транслятора;
4. перечень и датировку версий транслятора.

## Быстрый старт

```bash
make stage0      # проверка инструментов и эталонного образа (PASS)
make inventory   # Фаза 1: каталог и штампы
make dis         # Фазы 2-3: 69 зон → gold/ + 71 поозонный .asm
make verify      # Фаза 5: независимое переизвлечение, 69/69 идентично
make versions    # Фаза 6: VER.06/78 ↔ VAR.12/77
make xref        # Фаза 4: граф переходов (требует dis/)
make rebuild-all # Фаза A3: собрать все 69 .be → 0 отличий от gold/
make rebuild-check  # регрессия эталонной зоны 0137 (1024/1024, PASS)
make unittest    # 47 unit-тестов (аннотатор, конвертер, tools/)
make check-all   # агрегат: stage0 + rebuild-check + verify + unittest
make check       # базовая итоговая проверка (версии, md5 образа)
```

Текущий результат: **69/69 зон восстановлены в `.be` побайтово**,
0 отличий от `gold/`; в `0556` оставлено 2 слова `КОНД` (opcode 140
вне таблицы OPS). `make check-all` — все проверки пройдены (47 тестов).
Дальнейшее: `docs/PLAN-NEXT.md`, `docs/ROADMAP.md`, `docs/FINAL-REPORT.md`.
Изучены макрокоманды (37), АРАП-архив, оверлеи 0154/0170; честные
«НЕ ИЗВЕСТНО» — в `FINAL-REPORT.md` §7.

**Процедурные метки и литералы (23.11).** В зоны 0137/0147 вставлены
43 и ~120 абсолютных `ЭКВ`-имён correspondingly; `rebuild-zone` даёт
1024/1024, 0 отличий. Доказано (5 отчётов: `BE-LISTING-MECHANICS.md`,
`BE-LISTING-SOURCE.md`, `BE-LISTING-MODULES.md`,
`LABEL-MODE-EXPERIMENT.md`, `REAL-LABELS-0137.md`), что **настоящая
метка первого поля не даёт 0 отличий** для 0137: значение метки =
HAM + индекс, а эталон хранит индекс без базы (`01036`); HAM=0
недостижим (`НОЛЬ ЗАПР0Щ1`), `ВНЕШН` добавляет relocation. Поэтому
в `.be` используются абсолютные `ЭКВ`-литералы (исключение), а не
метки слова. Полный разбор смысла 323 литералов 0137 —
`analysis/Z0137-LITERALS-{INDEX,G4,G5,G6}.md` (большинство — гипотезы);
активная проверка по трассе — `analysis/Z0137-LITERALS-DYN.md`.

**Последние находки 22.11** (новые отчёты в `analysis/`, сводка:
`FINAL-REPORT.md` §7 п.14-18):

- GOST→БЭСМ: `GS-TABLE-0147-0561.md`, `GOST-TABLE-DETAILS.md`;
- константы 06445/+0o31: `GS-CONSTANTS.md`, `MACRO-RECORD-25.md`;
- дескрипторы: `ARAP-DESCRIPTOR-077143.md`, `DESCRIPTOR-WRITER.md`,
  `POOL-DESCRIPTOR-FIELDS.md`, `DESCRIPTOR-0005.md`;
- B2 и флаг D01167: `B2-ARCHIVE-DYN.md`, `Z0565-ROLE.md`,
  `D01167-WRITER.md`, `D01167-NEGATIVE.md`;
- старшая память и RLE: `HIGH-CORE-076600.md`,
  `HIGH-CORE-LOOP-76600.md`, `LOOP-76600-BRANCHES.md`,
  `CODE-01-EXACT.md`, `RLE-CONSUMER.md`, `ARAP-CODES-40-01.md`;
- карты и эталоны: `CARD-074021.md`, `CARD-ETALONS.md`,
  `FILLER-44-40.md`, `TEXT-POOL-06445.md`.

Механика макрокода НЕ объявлена разобранной до конца.

Эталонный образ — `/usr/local/share/besm6/2348` (только чтение). md5 целого
файла **не инвариант** (том используется другими проектами для PERSO-записи);
инвариант — md5 зон транслятора `0137–0177` = `2f503f5b…`, его проверяет
`make stage0`. Подробности — `docs/IMAGES.md`.

## Инструменты

- `disbesm6` — дизассемблер БЭСМ-6 (6 байт/слово);
- `besmtool` — дамп зон с томов SIMH (8 байт/слово → 6 байт/слово);
- `dispak`, `dtran` — эмуляторы и трансляторы для проверки;
- собственные скрипты в `tools/` (извлечение, сверка, xref, сравнение версий).

## Документация

**Программа 2 (МАКРО-БЕМШ 06/78), полный разбор:**
[PROGRAM2-INDEX.md](docs/PROGRAM2-INDEX.md) — тексты со ссылками, регистры
с динамическими значениями, логика 3 проходов и 20 процедур.

**Как это работает (главное):** [MACRO-BEMSH-ARCHITECTURE.md](docs/MACRO-BEMSH-ARCHITECTURE.md) —
подробное описание языка, конвейера, машинной модели и процедур.

**Человеческие справочники:** [GUIDE-MODULES.md](docs/GUIDE-MODULES.md) — назначение
всех 69 модулей; [GUIDE-PROCEDURES-{ASM,B,B2}.md](docs/GUIDE-PROCEDURES-ASM.md) —
назначение всех 229 процедур простыми словами.

**Монитор и CALL-цели:** [MONITOR80-GENEALOGY.md](docs/MONITOR80-GENEALOGY.md)
(Монитор-80 — ветвь МС «Дубна» в ДИСПАК, не другая ОС),
[RAM-SNAPSHOT-MAP.md](analysis/RAM-SNAPSHOT-MAP.md),
[CALL-TRACE-RUNTIME.md](analysis/CALL-TRACE-RUNTIME.md),
[CALL-TARGETS-MONITOR80.md](analysis/CALL-TARGETS-MONITOR80.md).

**Идентификация и правила БЕМШ:**
[TRANSLATOR-VS-USER-PROGRAM.md](docs/TRANSLATOR-VS-USER-PROGRAM.md)
(зоны 0137–0177 — программа пользователя-транслятор под ДИСПАК;
МВЕ60 — другая, прикладная программа пользователя),
[MBE60-VS-TRANSLATOR.md](docs/MBE60-VS-TRANSLATOR.md).
Внешние связи: [VHODN-VNESHN-MECHANISM.md](docs/VHODN-VNESHN-MECHANISM.md)
(глобальное имя `владелец.символ`, владелец — определяющий модуль),
[EQU-VS-XREF.md](docs/EQU-VS-XREF.md) (`ЭКВ` не является внешней связью),
[VHODN-VNESHN-SYNTAX.md](docs/VHODN-VNESHN-SYNTAX.md),
[XLABEL-AUDIT.md](docs/XLABEL-AUDIT.md).
Коды `020/021/032/047` разобраны в
[OPCODES-020-021-047-032.md](docs/OPCODES-020-021-047-032.md)
(это не экстракоды; `032` = `УВВ`).

**Адреса загрузки:** [RESIDENT-ZONES.md](analysis/RESIDENT-ZONES.md)
(13 резидентов с измеренной базой ОП, 56 нерезидентов-оверлеев),
[RAM-SNAPSHOT-EXTRA.md](analysis/RAM-SNAPSHOT-EXTRA.md);
уточнение 22.11: 0154 и 0170 — **один оверлей page 01 по базе
`02000₈`** в разные моменты (`PASSES-CODE-LOCATION.md`,
`PASSES-OVERLAY-MECH.md`), полная карта баз —
`analysis/ZONE-BASE-MAP.md` (14 зон ФАКТ, 52 НЕ ИЗВЕСТНО).
Шапки `СТАРТ '<база>'`: `docs/SEMANTIC/*-START-TOP-*.md` —
резиденты по карте ОП, остальные `10000₈`. Особые случаи
разобраны в [START-SPECIAL-FIX.md](docs/SEMANTIC/START-SPECIAL-FIX.md),
[Z0147-BASE-RECHECK.md](analysis/Z0147-BASE-RECHECK.md),
[Z0152-Z0157-BASE-RECHECK.md](analysis/Z0152-Z0157-BASE-RECHECK.md),
[RESIDENT-BASE-AUDIT.md](analysis/RESIDENT-BASE-AUDIT.md):
0147 — база 0 не кодируется, пишем `СТАРТ 1` (HAM=00001);
0152/0157 — `СТАРТ '75777'` (0 ошибок; физическая
страница ОП 76000₈ давала `ПЕРЕПОЛН СЧА`, сдвиг на 1
слово принят ради чистой сборки).

**Документация в СИПРОД и ДРАКОН:** [SIPROD/README.md](docs/SIPROD/README.md)
(5 блоков `*RED…*E`, проверены в эмуляторе), [DRAKON/README.md](docs/DRAKON/README.md)
(6 блок-схем, рендер `drakon_markup.py`).

**Семантика всех 69 зон:** [SEMANTIC/INDEX.md](docs/SEMANTIC/INDEX.md)
(стандарт — [SEMANTIC-STANDARD.md](docs/SEMANTIC-STANDARD.md)).

**Сводка и статус:** [FINAL-REPORT.md](docs/FINAL-REPORT.md) — итоговый
отчёт по всем фазам (§7 п.1–21); [STATUS.md](docs/STATUS.md) —
одностраничный статус; [ROADMAP.md](docs/ROADMAP.md) — закрытые пункты
и открытая работа; [PLAN-NEXT.md](docs/PLAN-NEXT.md) — план Фаз A–E.
Механика макрокода **не объявлена разобранной до конца**.

**Механика транслятора (новое):** `analysis/BEMSH-SYNTAX-PARSER.md`,
`BEMSH-MACROEDITOR-MECH.md`, `BEMSH-MACROMACHINE-MECH.md`,
`BEMSH-ARAP-MECH.md` — синтаксический разбор, макроредактор,
макромашина и АРАП; `analysis/DISPAK-LISTING-PAIRS.md` (в репозитории
`re-dispak`) — 138 пар `.be`/`.lst`, 1389 G/D-символов.

**Реконструкция и эксперименты:** [DIS2BE.md](docs/DIS2BE.md) (конвертер),
[REBUILD-TOOL.md](docs/REBUILD-TOOL.md) (универсальная сборка),
[MACRO-COMMANDS.md](docs/MACRO-COMMANDS.md) (каталог из 37 макрокоманд),
[MACRO-TABLE-FORMAT-VERIFIED.md](docs/MACRO-TABLE-FORMAT-VERIFIED.md)
(2 ячейки ГС на макрос; `[TAG|VAL]` не подтверждена),
[DYNAMIC-TRACE.md](docs/DYNAMIC-TRACE.md),
[analysis/MEMORY-MAP.md](analysis/MEMORY-MAP.md) (0154 → `02000₈`),
[analysis/REBUILD-ALL.md](analysis/REBUILD-ALL.md) (69/69 зон, 0 отличий).

**Планы и методы:** [PLAN.md](docs/PLAN.md), [DISBESM6-GUIDE.md](docs/DISBESM6-GUIDE.md),
[TOOLS.md](docs/TOOLS.md), [XREF-METHODOLOGY.md](docs/XREF-METHODOLOGY.md),
[VERIFY.md](docs/VERIFY.md), [AUTOMATION.md](docs/AUTOMATION.md),
[COMMENTING-STANDARD.md](docs/COMMENTING-STANDARD.md).

**Образы и версии:** [ANCHORS.md](docs/ANCHORS.md), [COPIES-2348.md](docs/COPIES-2348.md),
[IMAGES.md](docs/IMAGES.md), [VERSIONS-SCAN.md](docs/VERSIONS-SCAN.md),
[inventory.md](docs/inventory.md), [EXTRACTION.md](docs/EXTRACTION.md).

**Глубокая аннотация:**

- [TEXT-CONSTANTS.md](docs/TEXT-CONSTANTS.md) — 25 строковых констант в 4 кодировках;
- [REGISTERS.md](docs/REGISTERS.md) — роли индексных регистров М1–М17;
- [ANNOT-0147.md](docs/ANNOT-0147.md), [ANNOT-MACRO.md](docs/ANNOT-MACRO.md) —
  аннотации зон `0147`, `0154`, `0170`;
- `analysis/procedures.md` + [procedures-RESOLVED.md](analysis/procedures-RESOLVED.md) —
  33 кандидата в процедуры, 7 неопределённых границ разрешены;
- `analysis/CROSSREF.md` — 273 цели, 1012 перекрёстных ссылок;
- `analysis/VARIABLES.md` + [VARIABLES-VALIDATION.md](analysis/VARIABLES-VALIDATION.md) —
  76 гипотетических имён ячеек, 73 прошли валидацию;
- `analysis/versions.md`, `analysis/reloc.md` — сравнение версий.

**Смежные проекты:** [ADJACENT.md](docs/ADJACENT.md), [ADJACENT-2.md](docs/ADJACENT-2.md).

## Структура

| Каталог      | Назначение                                      |
|--------------|-------------------------------------------------|
| `docs/`      | планы, отчёты, инвентарь, таблицы               |
| `gold/`      | эталонные дампы зон (6 байт/слово), не коммитятся |
| `dis/`       | 71 поозонный дизассембль `disbesm6`             |
| `bemsh/`     | аннотированные листинги (комментарии после запятой) |
| `sym/`       | таблицы символов (плейсхолдер + гипотетические имена) |
| `analysis/`  | процедуры, xref, переменные, версии             |
| `verify/`    | отчёты побайтовой сверки и md5 образов          |
| `tools/`     | скрипты извлечения, сверки, xref, сравнения     |

> Бинарные дампы и дисковые образы в репозиторий не коммитятся
> (см. `.gitignore`). Коммиты и push — только по инструкции.
