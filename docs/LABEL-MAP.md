# GLOBAL LABEL DICTIONARY — глобальный словарь ролевых имён

Дата: 20.11.2026. Построено `tools/build_labels.py` (regex-извлечение из документов; воспроизводимо).

> **Статус: аннотация, а не ground truth.** Ни один адрес не подтверждён исходником транслятора — его на диске нет. `ПОДТВЕРЖДЕНО` означает штамп/пару вызов→возврат/breakpoint, `ГИПОТЕЗА` — шаблон использования. См. `COMMENTING-STANDARD.md` §2.4, `AGENTS.md` §0.1–2.

## 0. Как пользоваться таблицей

```bash
cd /tmp/.private/azizz/re-bemsh
disbesm6 -a0 -e0 -nsym/GLOBAL.tab \
  gold/MBE-Z0147-L1.bin > /tmp/.private/azizz/global-0147.asm
```

`sym/GLOBAL.tab` — формат `%o %d %63s` (адрес печатается `%05o`, читается как `%o`); тип `1`=W_DATA (ячейка/таблица), `2`=W_CODE (точка входа), `0`=эквивалентность/EQU. Адреса уникальны и отсортированы; имя ≤20 символов, латиница, `PREFIX_ROLE` (`COMMENTING-STANDARD.md` §2.2–2.4).

Оговорки:
1. Имена `A#####`/`D#####` и штампы `зона.слово` — **zone-local**: число — 0-based смещение внутри зоны при `-a0`; в другой зоне то же число означает другую ячейку. См. `VARIABLES.md` §6.6.
2. `70707`, `04000`, `04007`, `00001`, `01000` — **логические** адреса листинга/ОП, физический якорь тома для них не доказан (`ANCHORS.md` §1, §3; `MEMORY-MAP.md` §3). Не подставлять их как физические без доказательства (`AGENTS.md` §3).
3. `00001` и `01000` — один и тот же вход в двух системах координат (`ANCHORS.md`:66); это алиас, не конфликт.
4. Имена `SUB*`, `CNT*`, `FLAG*`, `MBEENTRY`, `TAB*` и т.п. из `VARIABLES.md` — авто-имена/шаблоны; они **не** вошли в `GLOBAL.tab` как роли, но сохранены в §10 как исторические.

## 1. Загрузчик и инициализация

| адрес | роль-имя | роль | evidence (file:line) | confidence |
|---|---|---|---|---|
| `00000` | `INIT_ZERO` | нуль, не вход | analysis/VARIABLES-VALIDATION.md:120; FINAL-REPORT §5; dis/MBE-Z0137-L1.asm:8; [docs/LABELS-BE.md:29] | ПОДТВЕРЖДЕНО |
| `00005` | `CODE_DATA` | константа в’21173 | dis/MBE-Z0137-L1.asm:19; [docs/LABELS-BE.md:34] | ГИПОТЕЗА |
| `00050` | `MNEM_TAB_KOI7` | таблица мнемоник, KOI-7 не GOST | dis/MBE-Z0137-L1.asm:54; docs/TEXT-CONSTANTS.md:6.1,204; [docs/LABELS-BE.md:33] | ГИПОТЕЗА |

## 2. Макроредактор (0154/0554)

| адрес | роль-имя | роль | evidence (file:line) | confidence |
|---|---|---|---|---|
| `00011` | `CODE_EXIT` | прямой возврат | dis/MBE-Z0154-L1.asm:9; docs/ANNOT-MACRO.md §3; [docs/LABELS-BE.md:67] | ПОДТВЕРЖДЕНО |
| `00722` | `MAC_FLAG` | флаг/ячейка режима (было FLAG2) | analysis/VARIABLES-VALIDATION.md:127; analysis/CROSSREF.md:150; [docs/LABELS-B.md:77] | ГИПОТЕЗА |
| `00723` | `MAC_FLAG` | флаг (было FLAG3) | dis/MBE-Z0147-L1.asm:90; analysis/VARIABLES.md §6; [docs/LABELS-B.md:78] | ГИПОТЕЗА |
| `00751` | `TXT_STAMP_ED` | штамп «МАКРОРЕДАКТОР ОТ 20.06.78» (0154.0751) | docs/TEXT-CONSTANTS.md:151 | ПОДТВЕРЖДЕНО (GOST 6 бит) |

## 3. Макромашина (0170/0570)

| адрес | роль-имя | роль | evidence (file:line) | confidence |
|---|---|---|---|---|
| `00007` | `CODE_VARIANT` | номер варианта в М16 | dis/MBE-Z0170-L1.asm:7; TC:§5; [docs/LABELS-BE.md:71] | ГИПОТЕЗА |
| `00010` | `CODE_EXIT` | прямой возврат | dis/MBE-Z0170-L1.asm:8; docs/ANNOT-MACRO.md §3; [docs/LABELS-BE.md:72] | ПОДТВЕРЖДЕНО |
| `00216` | `TXT_STAMP_MACH` | штамп «МАКРОМАШИНА ОТ 1.11.78» (0170.0216) | docs/TEXT-CONSTANTS.md:152 | ПОДТВЕРЖДЕНО (GOST 6 бит) |
| `00274` | `TXT_STAMP_MACH_B2` | штамп «МАКРОМАШИНА ОТ 15.12.76» (0570.0274) — B2 | docs/TEXT-CONSTANTS.md:175 | ПОДТВЕРЖДЕНО (GOST 6 бит) |

## 4. АРАП (0152/0552)

| адрес | роль-имя | роль | evidence (file:line) | confidence |
|---|---|---|---|---|
| `01154` | `TXT_STAMP_ARA_B2` | штамп «АРАП ВАР.10/75» (0552.1154) — B2 | docs/TEXT-CONSTANTS.md:129 | ПОДТВЕРЖДЕНО (GOST 6 бит) |
| `01164` | `TXT_STAMP_ARA` | штамп «АРАП ВАР.04/78» (0152.1164) | docs/TEXT-CONSTANTS.md:116 | ПОДТВЕРЖДЕНО (GOST 6 бит) |

## 5. Таблицы ошибок и справок

| адрес | роль-имя | роль | evidence (file:line) | confidence |
|---|---|---|---|---|
| `00275` | `ERR_ADDR` | сообщение «НЕВЕРНЫЙ АДРЕС…» (зона 0144) | docs/SEMANTIC/Z0144.md:143 | ГИПОТЕЗА |
| `00314` | `ERR_BUF` | сообщение «ПРОГРАММА НЕ…» (зона 0144) | docs/SEMANTIC/Z0144.md:145 | ГИПОТЕЗА |
| `00543` | `ERR_OVF` | «ПРПЛН ТАБЛ МЕТОК» — переполнение (зона 0144) | docs/SEMANTIC/Z0144.md:147 | ГИПОТЕЗА |
| `00632` | `ERR_FLG` | флаг, проверка нтж/и | dis/MBE2-Z0547-L1.asm:12; [docs/LABELS-BE.md:99] | ПОДТВЕРЖДЕНО |
| `00641` | `ERR_FLG` | флаг, проверка условия | dis/MBE2-Z0547-L1.asm:106; [docs/LABELS-BE.md:100] | ГИПОТЕЗА |
| `00651` | `ERR_FLG` | флаг, проверка условия | dis/MBE2-Z0547-L1.asm:208; [docs/LABELS-BE.md:102] | ГИПОТЕЗА |
| `00655` | `TXT_SPR_B1` | «ОШ.СПР.НА БЕМШ1» — справка (0173.0655) | docs/TEXT-CONSTANTS.md:153 | ПОДТВЕРЖДЕНО (GOST 6 бит) |
| `01050` | `ERR_MSG` | сообщение «НЕВЕРНЫЙ 1-Й КОМПИЛИР» (0154.1050) | docs/TEXT-CONSTANTS.md:163 | ПОДТВЕРЖДЕНО (GOST 6 бит) |
| `01315` | `TXT_STAMP_B` | штамп «ИПМ МАКРО-БЕМШ ВЕР.06/78» (0147.1315) | docs/TEXT-CONSTANTS.md:149; docs/ANCHORS.md:35 | ПОДТВЕРЖДЕНО (GOST 6 бит, besmtool search) |
| `01450` | `ERR_CNT` | «-КОЛИЧ ЯЧ ГС» — счётчик ГС (0154.1450) | docs/TEXT-CONSTANTS.md:164 | ПОДТВЕРЖДЕНО (GOST 6 бит) |

## 6. ASM ИТМ (0055–0060)

| адрес | роль-имя | роль | evidence (file:line) | confidence |
|---|---|---|---|---|
| `70707` | `CODE_ITM_GATE` | шлюз передачи управления ИТМ: выпр '70707'(М17) | docs/SEMANTIC/Z0055.md:164; docs/SEMANTIC/ASM-CODE-RECOVERY.md:246 | ПОДТВЕРЖДЕНО (дизассембль; логический адрес) |

## 7. Ядро исполняемого кода (0147/0547)

| адрес | роль-имя | роль | evidence (file:line) | confidence |
|---|---|---|---|---|
| `00003` | `CODE_UTIL_003_RET` | утилита; возврат | dis/MBE2-Z0547-L1.asm:19; [docs/LABELS-BE.md:74] | ГИПОТЕЗА |
| `00006` | `CODE_ENTRY` | вход | dis/MBE-Z0147-L1.asm:20; [docs/LABELS-BE.md:35] | ГИПОТЕЗА |
| `00017` | `CODE_ENTRY` | вход, сброс индекса | dis/MBE-Z0147-L1.asm:38; [docs/LABELS-BE.md:37] | ГИПОТЕЗА |
| `00035` | `CODE_UTIL_035` | утилита; цель ветвления | dis/MBE2-Z0547-L1.asm:66; [docs/LABELS-BE.md:76] | ГИПОТЕЗА |
| `00040` | `CODE_ENTRY` | блок CALL-вызовов | dis/MBE-Z0147-L1.asm:72; [docs/LABELS-BE.md:38] | ГИПОТЕЗА |
| `00046` | `CODE_UTIL_046_NEXT` | утилита; следующему элементу | dis/MBE2-Z0547-L1.asm:72; [docs/LABELS-BE.md:77] | ГИПОТЕЗА |
| `00051` | `CODE_ENTRY` | вход после ПО | dis/MBE-Z0147-L1.asm:90; [docs/LABELS-BE.md:40] | ГИПОТЕЗА |
| `00056` | `CODE_UTIL_056` | утилита; цель ветвления | dis/MBE2-Z0547-L1.asm:100; [docs/LABELS-B2.md:48] | ГИПОТЕЗА |
| `00057` | `CODE_ENTRY` | вход, счи М1 | dis/MBE-Z0147-L1.asm:102; [docs/LABELS-BE.md:41] | ГИПОТЕЗА |
| `00061` | `CODE_ENTRY` | вход, уиа −5(М3) | dis/MBE-Z0147-L1.asm:106; [docs/LABELS-BE.md:42] | ГИПОТЕЗА |
| `00062` | `CODE_ENTRY_LOOP` | вход цикла 50(М3) | dis/MBE-Z0147-L1.asm:108; [docs/LABELS-BE.md:43] | ГИПОТЕЗА |
| `00101` | `CODE_ENTRY` | цель ПИО(М7) | dis/MBE-Z0147-L1.asm:138; [docs/LABELS-BE.md:44] | ГИПОТЕЗА |
| `00105` | `CODE_CHECK` | сравнение признака | dis/MBE-Z0147-L1.asm:146; [docs/LABELS-BE.md:45] | ГИПОТЕЗА |
| `00107` | `CODE_UTIL_107_NEXT` | утилита; переход к следующему | dis/MBE2-Z0547-L1.asm:142; [docs/LABELS-BE.md:78] | ГИПОТЕЗА |
| `00122` | `CODE_UTIL_122` | утилита; цель ветвления | dis/MBE2-Z0547-L1.asm:171; [docs/LABELS-BE.md:79] | ГИПОТЕЗА |
| `00125` | `CODE_UTIL` | утилита, CALL через М15 | dis/MBE-Z0147-L1.asm:177; analysis/procedures.md:52; [docs/LABELS-BE.md:46] | ГИПОТЕЗА |
| `00133` | `CODE_UTIL_133` | утилита; цель ветвления | dis/MBE2-Z0547-L1.asm:189; [docs/LABELS-B2.md:51] | ГИПОТЕЗА |
| `00153` | `CODE_UTIL_153` | утилита; цель ветвления | dis/MBE2-Z0547-L1.asm:221; [docs/LABELS-BE.md:80] | ГИПОТЕЗА |
| `00200` | `CODE_UTIL_200_NEXT` | утилита; переход к следующему | dis/MBE2-Z0547-L1.asm:252; [docs/LABELS-BE.md:81] | ГИПОТЕЗА |
| `00223` | `CODE_UTIL_223_NEXT` | утилита; переход к следующему | dis/MBE2-Z0547-L1.asm:107; [docs/LABELS-BE.md:82] | ГИПОТЕЗА |
| `00226` | `CODE_ENTRY` | общая цель 6 переходов | dis/MBE-Z0147-L1.asm:113; [docs/LABELS-B.md:35] | ГИПОТЕЗА |
| `00262` | `CODE_UTIL_262_NEXT` | утилита; переход к следующему | dis/MBE2-Z0547-L1.asm:355; [docs/LABELS-BE.md:83] | ГИПОТЕЗА |
| `00302` | `CODE_UTIL_0302` | утилита: роль по шаблону вызовов, не доказана | dis/MBE2-Z0547-L1.asm:390; [docs/LABELS-B2.md:34] | ГИПОТЕЗА |
| `00305` | `CODE_UTIL_305` | утилита; цель ветвления | dis/MBE2-Z0547-L1.asm:396; [docs/LABELS-BE.md:84] | ГИПОТЕЗА |
| `00310` | `CODE_UTIL` | утилита, CALL через М15 | analysis/procedures.md:50; [docs/LABELS-BE.md:47] | ГИПОТЕЗА |
| `00321` | `CODE_UTIL_321` | утилита; цель ветвления | dis/MBE2-Z0547-L1.asm:393; [docs/LABELS-BE.md:85] | ГИПОТЕЗА |
| `00324` | `CODE_LINK_M15` | запись адреса возврата в М15 | dis/MBE-Z0147-L1.asm:425; docs/REGISTERS.md §3 M15; [docs/LABELS-BE.md:48] | ПОДТВЕРЖДЕНО |
| `00347` | `CODE_UTIL_347_NEXT` | утилита; переход к следующему | dis/MBE2-Z0547-L1.asm:457; [docs/LABELS-BE.md:86] | ГИПОТЕЗА |
| `00400` | `CODE_ENTRY` | вход, счи М4 | dis/MBE-Z0147-L1.asm:511; [docs/LABELS-BE.md:49] | ГИПОТЕЗА |
| `00421` | `CODE_UTIL_421` | утилита; цель ветвления | dis/MBE2-Z0547-L1.asm:545; [docs/LABELS-BE.md:87] | ГИПОТЕЗА |
| `00440` | `CODE_UTIL_0440` | утилита: роль по шаблону вызовов, не доказана | dis/MBE2-Z0547-L1.asm:575; [docs/LABELS-B2.md:35] | ГИПОТЕЗА |
| `00445` | `CODE_UTIL` | утилита, CALL через М15 | analysis/procedures.md:51; [docs/LABELS-BE.md:50] | ГИПОТЕЗА |
| `00446` | `CODE_UTIL_446_NEXT` | утилита; переход к следующему | dis/MBE2-Z0547-L1.asm:583; [docs/LABELS-BE.md:88] | ГИПОТЕЗА |
| `00462` | `CODE_LINK_M11` | вызов через M11 | dis/MBE-Z0147-L1.asm:582; docs/REGISTERS.md §3 M11; [docs/LABELS-B.md:41] | ГИПОТЕЗА |
| `00467` | `CODE_UTIL_467_NEXT` | утилита; переход к следующему | dis/MBE2-Z0547-L1.asm:75; [docs/LABELS-BE.md:89] | ГИПОТЕЗА |
| `00472` | `OUT_PRINT_0472` | вывод/печать: гипотеза по шаблону CALL | dis/MBE2-Z0547-L1.asm:67; [docs/LABELS-B2.md:36] | ГИПОТЕЗА |
| `00474` | `CODE_EXIT` | общий эпилог, 18 входов | analysis/CROSSREF.md:151; analysis/procedures-RESOLVED.md:147; [docs/LABELS-B.md:43] | ГИПОТЕЗА |
| `00477` | `OUT_PRINT` | вызов вывода, возврат в М15 | dis/MBE-Z0147-L1.asm:73,424; docs/REGISTERS.md §3 M15; [docs/LABELS-BE.md:39] | ПОДТВЕРЖДЕНО |
| `00506` | `CODE_UTIL_0506` | ∼B A00513, сдвиг −7₈ | dis/MBE2-Z0547-L1.asm:172; [docs/LABELS-BE.md:90] | ГИПОТЕЗА |
| `00513` | `CODE_UTIL` | утилита, CALL через М15 | analysis/procedures.md:53; [docs/LABELS-BE.md:51] | ГИПОТЕЗА |
| `00514` | `CODE_UTIL_0514` | ∼B A00521 | dis/MBE2-Z0547-L1.asm:454; [docs/LABELS-BE.md:91] | ГИПОТЕЗА |
| `00521` | `CODE_UTIL` | утилита, CALL через M15 | analysis/procedures.md:54; [docs/LABELS-B.md:46] | ГИПОТЕЗА |
| `00522` | `CODE_UTIL_0522` | ∼B A00527 | dis/MBE2-Z0547-L1.asm:174; [docs/LABELS-BE.md:92] | ГИПОТЕЗА |
| `00527` | `CODE_DISP_0527` | диспетчеризация | dis/MBE2-Z0547-L1.asm:389; [docs/LABELS-BE.md:93] | ГИПОТЕЗА |
| `00531` | `CODE_DISP_531` | диспетчер, контекст A00527 | dis/MBE2-Z0547-L1.asm:685; [docs/LABELS-BE.md:94] | ГИПОТЕЗА |
| `00534` | `CODE_DISPATCH` | диспетчер, link M13 | dis/MBE-Z0147-L1.asm:395; docs/REGISTERS.md §3 M13; [docs/LABELS-BE.md:53] | ГИПОТЕЗА |
| `00536` | `CODE_ENTRY` | вход, мода START | dis/MBE-Z0147-L1.asm:694; [docs/LABELS-B.md:49] | ГИПОТЕЗА |
| `00601` | `CODE_UTIL_0601` | ∼B A00610 | dis/MBE2-Z0547-L1.asm:471; [docs/LABELS-BE.md:95] | ГИПОТЕЗА |
| `00606` | `CODE_UTIL_0606` | ∼B A00615 | dis/MBE2-Z0547-L1.asm:95; [docs/LABELS-BE.md:96] | ГИПОТЕЗА |
| `00610` | `CODE_DISPATCH` | диспетчер, link M13 | dis/MBE-Z0147-L1.asm:477; docs/REGISTERS.md §3 M13; [docs/LABELS-BE.md:54] | ГИПОТЕЗА |
| `00615` | `CODE_UTIL` | утилита, CALL через M15 | analysis/procedures.md:58; [docs/LABELS-B.md:51] | ГИПОТЕЗА |
| `00626` | `CODE_CNT` | инкремент счётчика | dis/MBE-Z0147-L1.asm:69; analysis/VARIABLES.md §6; [docs/LABELS-BE.md:57] | ГИПОТЕЗА |
| `00627` | `CODE_CNT` | инкремент счётчика CNT1 | dis/MBE-Z0147-L1.asm:49; analysis/VARIABLES.md §6; [docs/LABELS-B.md:63] | ГИПОТЕЗА |
| `00630` | `CODE_CNT` | инкремент счётчика CNT2 | dis/MBE-Z0147-L1.asm:54; analysis/VARIABLES.md §6; [docs/LABELS-B.md:64] | ГИПОТЕЗА |
| `00631` | `CODE_CNT` | инкремент счётчика CNT3 | dis/MBE-Z0147-L1.asm:64; analysis/VARIABLES.md §6; [docs/LABELS-B.md:65] | ГИПОТЕЗА |
| `00633` | `CODE_CNT` | инкремент (было CNT5) | dis/MBE-Z0147-L1.asm:46; analysis/VARIABLES.md §6; [docs/LABELS-B.md:67] | ГИПОТЕЗА |
| `00634` | `TXT_ARCH` | текст «АРХ..» GOST 6 бит | dis/MBE-Z0147-L1.asm:86,786; docs/TEXT-CONSTANTS.md:149; [docs/LABELS-BE.md:59] | ГИПОТЕЗА |
| `00643` | `CODE_DATA` | цель Э70, адрес → данные | dis/MBE-Z0147-L1.asm:27; [docs/LABELS-B.md:70] | ГИПОТЕЗА |
| `00644` | `CODE_CHECK` | ячейки сравнения НТЖ | dis/MBE-Z0147-L1.asm:77–124; [docs/LABELS-B.md:71] | ГИПОТЕЗА |
| `00646` | `CODE_OFF` | смещение/адресная поправка | dis/MBE2-Z0547-L1.asm:157; [docs/LABELS-BE.md:101] | ГИПОТЕЗА |
| `00656` | `CODE_CHECK` | ячейка сравнения | analysis/CROSSREF.md:152; [docs/LABELS-B.md:73] | ГИПОТЕЗА |
| `00707` | `CODE_DATA` | ячейка данных процедуры 0506 | dis/MBE2-Z0547-L1.asm:25; [docs/LABELS-BE.md:104] | ГИПОТЕЗА |
| `00714` | `CODE_DATA` | ячейка данных процедуры 0514 | dis/MBE2-Z0547-L1.asm:452; [docs/LABELS-B2.md:71] | ГИПОТЕЗА |
| `00717` | `CODE_CNT` | счётчик в цикле | analysis/VARIABLES-VALIDATION.md:122; analysis/CROSSREF.md:146; [docs/LABELS-BE.md:61] | ГИПОТЕЗА |
| `00720` | `CODE_DATA` | флаг/DATA (было FLAG0) | dis/MBE-Z0147-L1.asm:33; analysis/VARIABLES.md §6; [docs/LABELS-B.md:75] | ГИПОТЕЗА |
| `00721` | `CODE_DATA` | флаг/DATA (было FLAG1) | dis/MBE-Z0147-L1.asm:75; analysis/VARIABLES.md §6; [docs/LABELS-B.md:76] | ГИПОТЕЗА |
| `00724` | `CODE_DATA` | ячейка зп/слц | analysis/CROSSREF.md:149; [docs/LABELS-B.md:79] | ГИПОТЕЗА |
| `00727` | `CODE_CNT` | сч/зп счётчика | analysis/CROSSREF.md:147; [docs/LABELS-B.md:80] | ГИПОТЕЗА |
| `00732` | `CODE_DATA` | ячейка данных процедуры | dis/MBE2-Z0547-L1.asm:92; [docs/LABELS-B2.md:74] | ГИПОТЕЗА |
| `00734` | `CODE_DATA` | ячейка адреса/данных | analysis/CROSSREF.md:153; [docs/LABELS-B.md:81] | ГИПОТЕЗА |
| `00735` | `CODE_DATA` | рабочая ячейка (WORKCNT) | dis/MBE-Z0147-L1.asm:45; analysis/VARIABLES.md §6; [docs/LABELS-B.md:82] | ГИПОТЕЗА |
| `00736` | `TXT_BUF` | буфер ввода/текстовых данных | dis/MBE2-Z0547-L1.asm:394; [docs/LABELS-BE.md:106] | ГИПОТЕЗА |
| `00742` | `CODE_CNT` | счётчик/ячейка | analysis/CROSSREF.md:163; [docs/LABELS-B.md:83] | ГИПОТЕЗА |
| `00746` | `CODE_CHECK` | ячейка сравнения | analysis/CROSSREF.md:159; [docs/LABELS-B.md:84] | ГИПОТЕЗА |
| `00747` | `CODE_CHECK` | ячейка-признак | analysis/CROSSREF.md:165; [docs/LABELS-B.md:85] | ГИПОТЕЗА |
| `01004` | `OUT_BUF` | буфер вывода | VAR:OUTBUF; analysis/VARIABLES.md §6; [docs/LABELS-BE.md:62] | ГИПОТЕЗА |
| `01100` | `CODE_EXIT` | уход из зоны | dis/MBE-Z0147-L1.asm:13; analysis/procedures.md:52; [docs/LABELS-BE.md:55] | ГИПОТЕЗА |
| `01217` | `CODE_ENTRY` | цель перехода в хвосте зоны | dis/MBE-Z0147-L1.asm:930; [docs/LABELS-B.md:53] | ГИПОТЕЗА |
| `01220` | `CODE_LINK_M16` | код/ячейка вызова через M16 | dis/MBE-Z0147-L1.asm:933; [docs/LABELS-BE.md:63] | ГИПОТЕЗА |
| `01322` | `CODE_LINK_M16` | вызов через M16 | dis/MBE-Z0147-L1.asm:933; analysis/procedures.md:59; [docs/LABELS-BE.md:56] | ГИПОТЕЗА |
| `01334` | `CODE_DATA` | ячейка данных таблицы 1322+ | dis/MBE2-Z0547-L1.asm:987; [docs/LABELS-BE.md:107] | ГИПОТЕЗА |

## 8. Глобальная память и системные адреса

| адрес | роль-имя | роль | evidence (file:line) | confidence |
|---|---|---|---|---|
| `00001` | `INIT_LOG_ENTRY` | вход МВЕ60 = 00001 (тестовая программа ДКС, не транслятор) | docs/ANCHORS.md:66; docs/PLAN.md:81 | ПОДТВЕРЖДЕНО (logical) |
| `00013` | `CODE_LINK_M13` | EQU-константа: `0147:395; REG:§3M13` | docs/LABELS-BE.md:138 (,EQU,) | ГИПОТЕЗА |
| `01000` | `INIT_LOG_ENTRY` | память 01000₈ = логический вход 00001 + 0777₈ (алиас) | docs/ANCHORS.md:26; docs/PLAN.md:81 | ПОДТВЕРЖДЕНО (logical) |
| `02000` | `MAC_EDITOR_LOAD` | загрузка зоны 0154 (макроредактор) в ОП; breakpoint →xta 6065 | analysis/MEMORY-MAP.md:109 | ПОДТВЕРЖДЕНО (1024/1024 слово, breakpoint) |
| `04000` | `MEM_MONITOR` | MON*ITOR — монитор (адрес из *EXECUTE листинга) | docs/ANCHORS.md:27; analysis/MEMORY-MAP.md:78 | ГИПОТЕЗА (логический/памятный адрес) |
| `04007` | `MEM_PLBEG` | PLBEG — выделение страницы/буфера (*EXECUTE) | analysis/MEMORY-MAP.md:78; docs/PLAN-NEXT.md:108 | ГИПОТЕЗА (логический адрес; исходник не найден) |
| `70000` | `SYSCALL_GATE` | системный вызов/ячейка приёма '70000' (0137.0, 9 зон) | analysis/VARIABLES.md:186; docs/PLAN.md:87 | ГИПОТЕЗА (логический адрес ОП) |

## 9. Конфликты (одно число → разные имена)

Всего конфликтных адресов: **42**.

| адрес | имя A → источник | имя B → источник | verdict |
|---|---|---|---|
| `00000` | INIT_ZERO → docs/LABELS-B.md:60 | INIT_ZERO_DATA → docs/LABELS-BE.md:30 ; MAC_ENTRY → docs/LABELS-BE.md… | каноническое: `INIT_ZERO` (docs/LABELS-BE.md:29) |
| `00003` | CODE_UTIL_003_RET → docs/LABELS-B2.md:44 | INITCELL → analysis/VARIABLES.md:123 ; INIT_ZERO_DATA → docs/LABELS-B… | каноническое: `CODE_UTIL_003_RET` (docs/LABELS-BE.md:74) |
| `00006` | CODE_ENTRY → docs/LABELS-B.md:26 | CODE_UTIL_006 → docs/LABELS-B2.md:45 | каноническое: `CODE_ENTRY` (docs/LABELS-BE.md:35) |
| `00011` | CODE_ENTRY → docs/LABELS-B.md:27 | CODE_EXIT → docs/LABELS-B.md:103 | каноническое: `CODE_EXIT` (docs/LABELS-BE.md:67) |
| `00062` | CODE_ENTRY → docs/LABELS-B.md:33 | CODE_ENTRY_LOOP → docs/LABELS-BE.md:43 | каноническое: `CODE_ENTRY_LOOP` (docs/LABELS-BE.md:43) |
| `00274` | TXT_STAMP_MACH → docs/LABELS-BE.md:116 | TXT_STAMP_MACH_B2 → docs/TEXT-CONSTANTS.md ; TXT_STAMP_MACH` (B2) → d… | каноническое: `TXT_STAMP_MACH_B2` (docs/TEXT-CONSTANTS.md) |
| `00305` | CODE_ENTRY → docs/LABELS-B.md:36 | CODE_UTIL_305 → docs/LABELS-B2.md:56 | каноническое: `CODE_UTIL_305` (docs/LABELS-BE.md:84) |
| `00400` | CODE_ENTRY → docs/LABELS-B.md:39 | ZONE_B2_SHIFT → docs/LABELS-BE.md:142 | каноническое: `CODE_ENTRY` (docs/LABELS-BE.md:49) |
| `00467` | CODE_EXIT → docs/LABELS-B.md:42 | CODE_UTIL_467_NEXT → docs/LABELS-B2.md:61 | каноническое: `CODE_UTIL_467_NEXT` (docs/LABELS-BE.md:89) |
| `00472` | OUT_PRINT_0472 → docs/LABELS-B2.md:36 | SUB0472 → analysis/VARIABLES.md:174 | каноническое: `OUT_PRINT_0472` (docs/LABELS-B2.md:36) |
| `00474` | CODE_EXIT → docs/LABELS-B.md:43 | SUB0474 → analysis/VARIABLES.md:175 | каноническое: `CODE_EXIT` (docs/LABELS-B.md:43) |
| `00477` | OUT_PRINT → docs/LABELS-B.md:44 | SUB0477 → analysis/VARIABLES.md:176 | каноническое: `OUT_PRINT` (docs/LABELS-BE.md:39) |
| `00514` | CODE_UTIL_0514 → docs/LABELS-B2.md:38 | SUB0514 → analysis/VARIABLES.md:126 | каноническое: `CODE_UTIL_0514` (docs/LABELS-BE.md:91) |
| `00521` | CODE_UTIL → docs/LABELS-B.md:46 | SUB0521 → analysis/VARIABLES.md:127 | каноническое: `CODE_UTIL` (docs/LABELS-B.md:46) |
| `00527` | CODE_DISP_0527 → docs/LABELS-B2.md:40 | CODE_UTIL → docs/LABELS-B.md:47 ; SUB0527 → analysis/VARIABLES.md:128 | каноническое: `CODE_DISP_0527` (docs/LABELS-BE.md:93) |
| `00534` | CODE_DISPATCH → docs/LABELS-B.md:48 | SUB0534 → analysis/VARIABLES.md:129 | каноническое: `CODE_DISPATCH` (docs/LABELS-BE.md:53) |
| `00610` | CODE_DISPATCH → docs/LABELS-B.md:50 | CODE_UTIL_610 → docs/LABELS-B2.md:63 ; SUB0610 → analysis/VARIABLES.m… | каноническое: `CODE_DISPATCH` (docs/LABELS-BE.md:54) |
| `00626` | CNT0 → analysis/VARIABLES.md:131 | CODE_CNT → docs/LABELS-B.md:62 | каноническое: `CODE_CNT` (docs/LABELS-BE.md:57) |
| `00627` | CNT1 → analysis/VARIABLES.md:132 | CODE_CNT → docs/LABELS-B.md:63 | каноническое: `CODE_CNT` (docs/LABELS-B.md:63) |
| `00630` | CNT2 → analysis/VARIABLES.md:133 | CODE_CNT → docs/LABELS-B.md:64 | каноническое: `CODE_CNT` (docs/LABELS-B.md:64) |
| `00631` | CNT3 → analysis/VARIABLES.md:134 | CODE_CNT → docs/LABELS-B.md:65 | каноническое: `CODE_CNT` (docs/LABELS-B.md:65) |
| `00632` | CNT4 → analysis/VARIABLES.md:135 | CODE_CNT → docs/LABELS-B.md:66 ; ERR_FLG → docs/LABELS-B2.md:65 | каноническое: `ERR_FLG` (docs/LABELS-BE.md:99) |
| `00633` | CNT5 → analysis/VARIABLES.md:136 | CODE_CNT → docs/LABELS-B.md:67 | каноническое: `CODE_CNT` (docs/LABELS-B.md:67) |
| `00641` | ERR_FLG → docs/LABELS-B2.md:66 | TXT_EDITOR → docs/LABELS-B.md:69 | каноническое: `ERR_FLG` (docs/LABELS-BE.md:100) |
| `00646` | CODE_CHECK → docs/LABELS-B.md:72 | CODE_OFF → docs/LABELS-B2.md:67 | каноническое: `CODE_OFF` (docs/LABELS-BE.md:101) |
| `00655` | CODE_OFF → docs/LABELS-B2.md:69 | TXT_SPR_B1 → docs/TEXT-CONSTANTS.md | каноническое: `TXT_SPR_B1` (docs/TEXT-CONSTANTS.md) |
| `00717` | CNT6 → analysis/VARIABLES.md:137 | CODE_CNT → docs/LABELS-B.md:74 | каноническое: `CODE_CNT` (docs/LABELS-BE.md:61) |
| `00720` | CODE_DATA → docs/LABELS-B.md:75 | FLAG0 → analysis/VARIABLES.md:138 | каноническое: `CODE_DATA` (docs/LABELS-B.md:75) |
| `00721` | CODE_DATA → docs/LABELS-B.md:76 | FLAG1 → analysis/VARIABLES.md:139 | каноническое: `CODE_DATA` (docs/LABELS-B.md:76) |
| `00722` | FLAG2 → analysis/VARIABLES.md:140 | MAC_FLAG → docs/LABELS-B.md:77 | каноническое: `MAC_FLAG` (docs/LABELS-B.md:77) |
| `00723` | FLAG3 → analysis/VARIABLES.md:141 | MAC_FLAG → docs/LABELS-B.md:78 | каноническое: `MAC_FLAG` (docs/LABELS-B.md:78) |
| `00735` | CODE_DATA → docs/LABELS-B.md:82 | WORKCNT → analysis/VARIABLES.md:142 | каноническое: `CODE_DATA` (docs/LABELS-B.md:82) |
| `00751` | TXT_STAMP_ED → docs/LABELS-B.md:106 | TXT_STAMP_ED_B2 → docs/TEXT-CONSTANTS.md | каноническое: `TXT_STAMP_ED` (docs/TEXT-CONSTANTS.md) |
| `01004` | OUTBUF → analysis/VARIABLES.md:143 | OUT_BUF → docs/LABELS-B.md:86 | каноническое: `OUT_BUF` (docs/LABELS-BE.md:62) |
| `01050` | ERR_MSG → docs/LABELS-B.md:108 | ERR_MSG_B2 → docs/LABELS-BE.md:112 | каноническое: `ERR_MSG` (docs/TEXT-CONSTANTS.md) |
| `01100` | CODE_EXIT → docs/LABELS-B.md:52 | CODE_UTIL_100_CHECK → docs/LABELS-B2.md:64 ; SUB1100 → analysis/VARIA… | каноническое: `CODE_EXIT` (docs/LABELS-BE.md:55) |
| `01315` | TXT_STAMP_B → docs/LABELS-B.md:105 | TXT_STAMP_B2 → docs/TEXT-CONSTANTS.md | каноническое: `TXT_STAMP_B` (docs/TEXT-CONSTANTS.md; docs/ANCHORS.md) |
| `01322` | CODE_LINK_M16 → docs/LABELS-B.md:54 | ERR_TAB_1322 → docs/LABELS-B2.md:43 ; SUB1322 → analysis/VARIABLES.md… | каноническое: `CODE_LINK_M16` (docs/LABELS-BE.md:56) |
| `01450` | ERR_CNT → docs/LABELS-B.md:109 | ERR_CNT_B2 → docs/LABELS-BE.md:113 | каноническое: `ERR_CNT` (docs/TEXT-CONSTANTS.md) |
| `02000` | MAC_EDITOR_LOAD → analysis/MEMORY-MAP.md; analysis/MEMORY-MAP.md | TAB0 → analysis/VARIABLES.md:149 ; ZONE_WORDS → docs/LABELS-BE.md:135 | каноническое: `MAC_EDITOR_LOAD` (analysis/MEMORY-MAP.md; analysis/MEM… |
| `04000` | MEM_MONITOR → docs/ANCHORS.md; analysis/MEMORY-MAP.md | TAB1 → analysis/VARIABLES.md:163 | каноническое: `MEM_MONITOR` (docs/ANCHORS.md; analysis/MEMORY-MAP.md) |
| `70000` | SYSCALL → analysis/VARIABLES.md:186 | SYSCALL_GATE → analysis/VARIABLES.md; docs/PLAN.md | каноническое: `SYSCALL_GATE` (analysis/VARIABLES.md; docs/PLAN.md) |

### 9.1 Отвергнутые не-role имена

Имена, не прошедшие фильтр `PREFIX_ROLE`/≤20/запрет авто-имён (`150` записей): `INIT_ZERO–DATA`, `MBEENTRY`, `INITCELL`, `MNEMTAB`, `ZEROBUF`, `SUB0514`, `SUB0521`, `SUB0527`, `SUB0534`, `SUB0610`, `CNT0`, `CNT1`, `CNT2`, `CNT3`, `CNT4`, `CNT5`, `CNT6`, `FLAG0`, `FLAG1`, `FLAG2`, `FLAG3`, `WORKCNT`, `OUTBUF`, `SUB1100`, `SUB1322`, `SUB1345`, `SUB1522`, `LIMIT1777`, `TAB0`, `ERRWORK`, `WORK2032`, `LIMIT2213`, `ERRPTR0`, `ERRPTR1`, `ERRPTR2`, `ERRPTR3`, `ERRPTR4`, `WORK2467`, `LIMIT3100`, `CONST3554` ….

## 10. Унаследованные имена `VARIABLES.md` (73 записей)

Все 73 имени из `sym/MBE.named.validated.tab` собраны здесь для полноты. Это шаблонные имена; как роли они запрещены §2.4 и в `GLOBAL.tab` не используются (если для адреса нет role-имя из §1–8). Ниже — весь список.

| адрес | унаследованное имя | evidence | примечание |
|---|---|---|---|
| `00000` | `MBEENTRY` | analysis/VARIABLES.md:122 (№ 1); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `INIT_ZERO` |
| `00003` | `INITCELL` | analysis/VARIABLES.md:123 (№ 2); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_UTIL_003_RET` |
| `00060` | `MNEMTAB` | analysis/VARIABLES.md:124 (№ 3); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `00377` | `ZEROBUF` | analysis/VARIABLES.md:125 (№ 4); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `00472` | `SUB0472` | analysis/VARIABLES.md:174 (№ 53); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `OUT_PRINT_0472` |
| `00474` | `SUB0474` | analysis/VARIABLES.md:175 (№ 54); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_EXIT` |
| `00477` | `SUB0477` | analysis/VARIABLES.md:176 (№ 55); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `OUT_PRINT` |
| `00514` | `SUB0514` | analysis/VARIABLES.md:126 (№ 5); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_UTIL_0514` |
| `00521` | `SUB0521` | analysis/VARIABLES.md:127 (№ 6); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_UTIL` |
| `00527` | `SUB0527` | analysis/VARIABLES.md:128 (№ 7); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_DISP_0527` |
| `00534` | `SUB0534` | analysis/VARIABLES.md:129 (№ 8); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_DISPATCH` |
| `00610` | `SUB0610` | analysis/VARIABLES.md:130 (№ 9); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_DISPATCH` |
| `00626` | `CNT0` | analysis/VARIABLES.md:131 (№ 10); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_CNT` |
| `00627` | `CNT1` | analysis/VARIABLES.md:132 (№ 11); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_CNT` |
| `00630` | `CNT2` | analysis/VARIABLES.md:133 (№ 12); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_CNT` |
| `00631` | `CNT3` | analysis/VARIABLES.md:134 (№ 13); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_CNT` |
| `00632` | `CNT4` | analysis/VARIABLES.md:135 (№ 14); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `ERR_FLG` |
| `00633` | `CNT5` | analysis/VARIABLES.md:136 (№ 15); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_CNT` |
| `00717` | `CNT6` | analysis/VARIABLES.md:137 (№ 16); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_CNT` |
| `00720` | `FLAG0` | analysis/VARIABLES.md:138 (№ 17); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_DATA` |
| `00721` | `FLAG1` | analysis/VARIABLES.md:139 (№ 18); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_DATA` |
| `00722` | `FLAG2` | analysis/VARIABLES.md:140 (№ 19); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `MAC_FLAG` |
| `00723` | `FLAG3` | analysis/VARIABLES.md:141 (№ 20); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `MAC_FLAG` |
| `00735` | `WORKCNT` | analysis/VARIABLES.md:142 (№ 21); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_DATA` |
| `01004` | `OUTBUF` | analysis/VARIABLES.md:143 (№ 22); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `OUT_BUF` |
| `01100` | `SUB1100` | analysis/VARIABLES.md:144 (№ 23); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_EXIT` |
| `01322` | `SUB1322` | analysis/VARIABLES.md:145 (№ 24); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `CODE_LINK_M16` |
| `01345` | `SUB1345` | analysis/VARIABLES.md:146 (№ 25); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `01522` | `SUB1522` | analysis/VARIABLES.md:147 (№ 26); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `01777` | `LIMIT1777` | analysis/VARIABLES.md:148 (№ 27); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `02000` | `TAB0` | analysis/VARIABLES.md:149 (№ 28); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `MAC_EDITOR_LOAD` |
| `02006` | `ERRWORK` | analysis/VARIABLES.md:150 (№ 29); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `02032` | `WORK2032` | analysis/VARIABLES.md:151 (№ 30); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `02113` | `LIMIT2213` | analysis/VARIABLES.md:152 (№ 31); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `02241` | `ERRPTR0` | analysis/VARIABLES.md:153 (№ 32); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `02243` | `ERRPTR1` | analysis/VARIABLES.md:154 (№ 33); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `02244` | `ERRPTR2` | analysis/VARIABLES.md:155 (№ 34); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `02251` | `ERRPTR3` | analysis/VARIABLES.md:156 (№ 35); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `02253` | `ERRPTR4` | analysis/VARIABLES.md:157 (№ 36); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `02467` | `WORK2467` | analysis/VARIABLES.md:158 (№ 37); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `03100` | `LIMIT3100` | analysis/VARIABLES.md:159 (№ 38); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `03554` | `CONST3554` | analysis/VARIABLES.md:160 (№ 39); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `03722` | `LIMIT3722` | analysis/VARIABLES.md:162 (№ 41); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `04000` | `TAB1` | analysis/VARIABLES.md:163 (№ 42); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `MEM_MONITOR` |
| `04011` | `ERRSUB` | analysis/VARIABLES.md:164 (№ 43); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `04012` | `SUB4012` | analysis/VARIABLES.md:165 (№ 44); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `04015` | `ERRJMP` | analysis/VARIABLES.md:166 (№ 45); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `04135` | `ERRCELL3` | analysis/VARIABLES.md:167 (№ 46); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `04154` | `ERRCELL1` | analysis/VARIABLES.md:168 (№ 47); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `04155` | `ERRCELL4` | analysis/VARIABLES.md:169 (№ 48); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `04157` | `ERRCELL5` | analysis/VARIABLES.md:170 (№ 49); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `04231` | `ERRCELL2` | analysis/VARIABLES.md:171 (№ 50); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `04232` | `SUB4232` | analysis/VARIABLES.md:172 (№ 51); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `04652` | `SUB4652` | analysis/VARIABLES.md:173 (№ 52); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `05263` | `ERRVEC` | analysis/VARIABLES.md:177 (№ 56); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `05615` | `WORK5615` | analysis/VARIABLES.md:179 (№ 58); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `05640` | `WORK5640` | analysis/VARIABLES.md:180 (№ 59); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `05655` | `ERRTBL1` | analysis/VARIABLES.md:181 (№ 60); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `06000` | `TAB2` | analysis/VARIABLES.md:182 (№ 61); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `06173` | `LIMIT6173` | analysis/VARIABLES.md:183 (№ 62); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `06234` | `WORK6234` | analysis/VARIABLES.md:184 (№ 63); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `10000` | `TAB3` | analysis/VARIABLES.md:193 (№ 72); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `10001` | `PTR10001` | analysis/VARIABLES.md:194 (№ 73); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `12000` | `TAB4` | analysis/VARIABLES.md:195 (№ 74); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `14000` | `TAB5` | analysis/VARIABLES.md:196 (№ 75); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `36436` | `WORK36436` | analysis/VARIABLES.md:161 (№ 40); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `54000` | `PATCH54` | analysis/VARIABLES.md:178 (№ 57); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `66666` | `RETM15` | analysis/VARIABLES.md:185 (№ 64); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `70000` | `SYSCALL` | analysis/VARIABLES.md:186 (№ 65); STRONG по analysis/VARIABLES-VALIDATION.md | есть role-имя: `SYSCALL_GATE` |
| `74000` | `SUB74000` | analysis/VARIABLES.md:187 (№ 66); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `74040` | `WORK74040` | analysis/VARIABLES.md:188 (№ 67); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `75364` | `WORK75364` | analysis/VARIABLES.md:189 (№ 68); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `76000` | `LIMIT76000` | analysis/VARIABLES.md:190 (№ 69); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `76001` | `PTR76001` | analysis/VARIABLES.md:197 (№ 76); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `76027` | `ERREXIT` | analysis/VARIABLES.md:191 (№ 70); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |
| `76336` | `WORK76336` | analysis/VARIABLES.md:192 (№ 71); STRONG по analysis/VARIABLES-VALIDATION.md | авто-имя, роли нет |

## 11. Счётчики и воспроизводимость

| Источник | собрано |
|---|---|
| `LABELS-B.md` | 75 |
| `LABELS-B2.md` | 43 |
| `LABELS-BE.md` | 88 |
| `VARIABLES.md (всего)` | 76 |
| `VARIABLES-VALIDATION.md (проверено)` | 73 |
| `SEMANTIC Z*.md (новые роли)` | 6 |
| `глобальные адреса (curated)` | 18 |
| `EQU-константы LABELS-BE §2` | 8 |

• Уникальных адресов: **163**. role-имён в `GLOBAL.tab`: **112**. Конфликтов: **42**. Отвергнутых имён: **150**.
• Провалы поиска evidence: 0.

```bash
python3 tools/build_labels.py --check
```

Перезапуск генератора даёт байт-в-байт тот же `GLOBAL.tab` и этот отчёт. Эталонные образы, `.be`, `dis/`, `analysis/` и `docs/SEMANTIC/*` не изменяются.
