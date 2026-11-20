# Аудит меток X... ЭКВ в 69 источниках bemsh/*.be

Инструмент: `python3 tools/xlabel_audit.py --out-md docs/XLABEL-AUDIT.md`.
Все файлы читались только на чтение; ни один `.be`, `dis/`, `gold/` не изменялся.

## 1. Главный вывод: ЭКВ не является кросс-ссылкой

**ЭКВ is not a cross-reference.** Директива `ЭКВ` задаёт только символическое имя константы внутри одного файла. Она не порождает слово, не создаёт запись `ВНЕШН`, не выставляет бит 21 и номер символа в команде. Следовательно, имя вида `X70000 ЭКВ '70000'` не объявляет внешнюю связь даже тогда, когда число совпадает с именованным адресом.

Свидетельства:

* `docs/EXTERNAL-CALL-FORMAT.md` §1.1, §1.4: внешний символ объявляется `ВНЕШ/ВНЕШН`; ссылка несёт номер символа и бит перемещаемости; загрузчик подставляет `база(X)+D`.
* `docs/ENTRY-POINTS.md` §3: `PRINT80 E 01205` -- эквивалент, а не четвёртая связь (`ВНЕШН=3`); §4 и §6.1: во всех 69 `.be` только `СТАРТ 1`, ни одной директивы `ВХОД*`/`ВНЕШН` в коде.
* `docs/XREF-METHODOLOGY.md` §2.2: тип `0` в sym-таблице -- экв, тип `2` -- код/точка входа.
* `docs/EXTERNAL-OFFSET-FIX.md` §7 и `docs/CALL-OUT-OF-MODULE.md` §4: все роли X-меток помечены как ГИПОТЕЗЫ; исходника транслятора на диске нет.
* `docs/EQU-VS-XREF.md` §0, §3, §4.4: ЭКВ не порождает слово и не попадает в таблицу связей; `X7417B ЭКВ '7417'` -- ЭКВ, а не внешняя ссылка, хотя комментарий называет её «внешней целью».
* `analysis/VNESHN-BYTE-EXPERIMENT.md` §5, УТОЧНЕНИЕ:
  побайтовая проба. Замена `X2000 ЭКВ '2000'` на
  `X2000 ВНЕШН MBE.X2000` (bemsh/MBE-Z0147.be:362)
  принимается синтаксически, даёт `ЧУЖОЙ CИMBOЛ`,
  1020/1024 слов и 6136/6144 байт.4 слова меняются
  корректно: `X2000 00001CA` и `+ 0001` в `*МЕТ*`.
  Это НЕ доказывает абсолютность: вывод отозван, см.
  docs/VHODN-VNESHN-MECHANISM.md §4.3. 4 слова -
  бит CA/перемещения, который мы САМИ добавили.
  Прежний вывод `METK YЖE 0П0` был двойным
  объявлением и отозван. `ВХОДН` на ЭКВ безопасен
  (gp4.be:3-5; проба vh_x2000: 0 ошибок, 6144/6144).

## 2. Методика

1. Сканер `tools/xlabel_audit.py` читает все 69 `bemsh/*.be` и выбирает строки вида `X... ЭКВ '<восьмеричное>'`.
2. Использования ищутся только в коде (левая часть строки до запятой); строки комментариев и сами определения не считаются.
3. Каждое значение классифицируется тремя классами: `TRUE_EXTERNAL` (совпадение с именем из `docs/ENTRY-POINTS.md` §3 или `docs/CALL-TARGET-RESOLUTION.md` §3-4), `INTERNAL_OFFSET` (значение < 02000₈, то есть внутри зоны из 1024 слов), `UNKNOWN_ABSOLUTE` (имя не восстановлено).
4. Даже класс `TRUE_EXTERNAL` означает только «число совпало с известным адресом», а не «в исходнике объявлена внешняя связь».
5. Таблица переаннотации не правит `.be`: это только рекомендация, которая требует отдельного разрешения оператора.

Отказ от настоящих директив в `.be` объясняют запрет
AGENTS.md §0 и утраченные владельцы, имена и номера СА
(docs/VHODN-VNESHN-MECHANISM.md §5), а не побайтовое
доказательство (§1 отозвано) и не ошибка `METK YЖE 0П0`.

## 3. Сводка

| Показатель | Значение |
|---|---:|
| Файлов `.be` просканировано | 69 |
| Файлов с определениями `X... ЭКВ` | 47 |
| Определений `X... ЭКВ` | 416 |
| Различных X-имён | 353 |
| Различных адресов | 330 |
| Использований в коде | 538 |
| Имён без использований в коде | 43 |

### 3.1 По классам

| Класс | Определений | Различных адресов | Использований |
|---|---:|---:|---:|
| TRUE_EXTERNAL | 27 | 8 | 11 |
| INTERNAL_OFFSET | 41 | 14 | 85 |
| UNKNOWN_ABSOLUTE | 348 | 308 | 442 |

Классы `INTERNAL_OFFSET` и `UNKNOWN_ABSOLUTE` -- ложные кросс-ссылки. Класс `TRUE_EXTERNAL` тоже не даёт права называть `ЭКВ` объявлением внешнего символа.

## 3.2 По семейству зон

| Ключ | Значение |
|---|---:|
| ASM | 17 |
| MBE | 323 |
| MBE2 | 76 |

## 3.3 По шаблону имени

| Ключ | Значение |
|---|---:|
| Xddd[ABCE] (offset-candidate) | 71 |
| XddddB (callout page/symbol) | 23 |
| Xddddd (callout full) | 238 |
| other | 84 |

## 3.4 По зоне

| Ключ | Значение |
|---|---:|
| 0055 | 5 |
| 0056 | 4 |
| 0057 | 4 |
| 0060 | 4 |
| 0137 | 38 |
| 0140 | 56 |
| 0141 | 37 |
| 0142 | 45 |
| 0143 | 30 |
| 0144 | 16 |
| 0145 | 32 |
| 0147 | 12 |
| 0150 | 3 |
| 0151 | 2 |
| 0152 | 1 |
| 0154 | 8 |
| 0155 | 5 |
| 0157 | 5 |
| 0161 | 4 |
| 0162 | 6 |
| 0166 | 1 |
| 0170 | 7 |
| 0171 | 3 |
| 0172 | 3 |
| 0173 | 3 |
| 0174 | 1 |
| 0176 | 4 |
| 0177 | 1 |
| 0540 | 1 |
| 0544 | 3 |
| 0547 | 2 |
| 0550 | 4 |
| 0551 | 1 |
| 0552 | 1 |
| 0554 | 1 |
| 0555 | 2 |
| 0556 | 1 |
| 0557 | 1 |
| 0561 | 5 |
| 0562 | 6 |
| 0565 | 15 |
| 0566 | 21 |
| 0570 | 3 |
| 0571 | 2 |
| 0572 | 2 |
| 0573 | 3 |
| 0576 | 2 |

## 4. Именованные адреса (класс TRUE_EXTERNAL)

| Адрес | Имя | СА | Свидетельство | Примечание |
|---|---|---|---|---|
| 2000 | *PAGE* | 3 | ENTRY-POINTS.md §3:112; EXTERNAL-CALL-FORMAT.md §1.2 | совпадает с базой зоны 0154; роль CALL-OUT: MEM_P01_Z0154 |
| 4000 | MON*ITOR | - | ENTRY-POINTS.md §3:113, §3:128-129 | системный символ ОС, не связь модуля |
| 70000 | SYSCALL | - | CALL-TARGET-RESOLUTION.md §3:170, §4.6:322; LABEL-MAP.md:173 | ячейка приёма системного вызова; роль: MEM_SYSCALL_GATE |
| 7417 | УППСЛУ | - | CALL-TARGET-RESOLUTION.md §4.1:194-202 (TTAB:124, TERM:342/816/312) | сервис ТЕРМ, PROVEN; роль CALL-OUT: MEM_P03_Z0156 |
| 77316 | ДЛЯСВЯ | - | CALL-TARGET-RESOLUTION.md §4.2:264 (S:1663, S:2435, S:2587) | MON СВС, PROVEN; роль CALL-OUT: MEM_P37_Z0157 |
| 77520 | МАКРО | - | CALL-TARGET-RESOLUTION.md §3:147, §4.2:266 (S:1966, S:1982) | MON СВС, PROVEN; роль CALL-OUT: MEM_P37_Z0157 |
| 77474 | ЕСТРР | - | CALL-TARGET-RESOLUTION.md §4.2:267 (S:1939, S:2463) | MON СВС, PROVEN; роль CALL-OUT: MEM_P37_Z0157 |
| 77430 | ВАС76D | - | CALL-TARGET-RESOLUTION.md §4.2:271 (S:1849, S:2528) | MON СВС, PROVEN; роль CALL-OUT: MEM_P37_Z0157 |

04000 (`MON*ITOR`) -- системный символ ОС, а не связь модуля (`ENTRY-POINTS.md` §3:128-129). 02000 (`*PAGE*`) одновременно является базой зоны 0154; совпадение адресов не означает общий код (`ENTRY-POINTS.md` §3:142-144). Адреса 077536 (`ГАШТСЛ`, S:2008) и 077503 (без имени, S:1955) описаны в `CALL-TARGET-RESOLUTION.md` §4.2 как ячейки КОНД/данные, поэтому внешними кодовыми символами не считаются и остаются в классе `UNKNOWN_ABSOLUTE`.

## 5. Топ-10 ложных кросс-ссылок

Ранжирование -- по числу использований в коде `.be`; второй ключ -- число определений.

| X-имя | Значение | Класс | Определений | Использований |
|---|---|---|---:|---:|
| X77420 | 77420 | UNKNOWN_ABSOLUTE | 1 | 23 |
| X120C | 120 | INTERNAL_OFFSET | 4 | 13 |
| X3624 | 3624 | UNKNOWN_ABSOLUTE | 1 | 13 |
| X122C | 122 | INTERNAL_OFFSET | 3 | 10 |
| X116C | 116 | INTERNAL_OFFSET | 2 | 10 |
| X2526 | 2526 | UNKNOWN_ABSOLUTE | 1 | 9 |
| X77777 | 77777 | UNKNOWN_ABSOLUTE | 1 | 9 |
| X120B | 120 | INTERNAL_OFFSET | 3 | 8 |
| X40540 | 40540 | UNKNOWN_ABSOLUTE | 2 | 8 |
| X41471 | 41471 | UNKNOWN_ABSOLUTE | 1 | 8 |

## 6. Классификация каждого различного адреса

| Адрес (восьм.) | Класс | Имя | Свидетельство | Определений | Использований |
|---|---|---|---|---:|---:|
| 63 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 1 | 2 |
| 112 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 4 | 3 |
| 115 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 1 | 4 |
| 116 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 4 | 12 |
| 117 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 2 | 5 |
| 120 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 7 | 21 |
| 122 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 6 | 14 |
| 140 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 3 | 4 |
| 141 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 2 | 4 |
| 142 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 3 | 9 |
| 144 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 2 | 2 |
| 360 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 3 | 2 |
| 1202 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 1 | 1 |
| 1213 | INTERNAL_OFFSET | - | адрес < 02000₈, внутри зоны (0..01777₈) | 2 | 2 |
| 2000 | TRUE_EXTERNAL | *PAGE* | ENTRY-POINTS.md §3:112; EXTERNAL-CALL-FORMAT.md §1.2 | 1 | 4 |
| 2024 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2040 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 2056 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2070 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 2113 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2123 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2133 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2174 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2234 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2247 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 2267 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2276 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2315 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 2320 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2356 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2370 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2376 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 5 |
| 2414 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2446 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 2522 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 2526 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 9 |
| 2545 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2621 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2652 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2724 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 2744 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 2757 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 2762 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 2775 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 2777 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3000 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3007 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3014 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 3016 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3110 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3133 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3153 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3162 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 3 | 1 |
| 3171 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3173 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 3175 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3177 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3200 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3410 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3535 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3572 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3604 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 4 | 0 |
| 3607 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 3612 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 3624 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 13 |
| 3626 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 3650 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 3656 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 3670 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 3676 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 3762 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 4 | 0 |
| 4000 | TRUE_EXTERNAL | MON*ITOR | ENTRY-POINTS.md §3:113, §3:128-129 | 1 | 2 |
| 4012 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 4016 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 4 | 6 |
| 4017 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 4044 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 4064 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 4121 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 4130 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 4157 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 4160 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 4170 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 4266 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 4276 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 1 |
| 4477 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 4652 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 4765 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 5056 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 5125 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 5155 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 0 |
| 5222 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 5413 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 5444 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 5453 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 0 |
| 5465 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 6017 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 6052 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 6112 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 6767 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 7033 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 7417 | TRUE_EXTERNAL | УППСЛУ | CALL-TARGET-RESOLUTION.md §4.1:194-202 (TTAB:124, TERM:342/816/312) | 5 | 1 |
| 7447 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 10014 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 3 | 3 |
| 14342 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 20052 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 20067 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 30662 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 31100 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 5 | 5 |
| 32463 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 33050 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 33445 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 34017 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 34050 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 34417 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 3 | 4 |
| 35340 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 36515 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 36562 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 4 |
| 40000 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 40100 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 3 | 0 |
| 40130 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 40207 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 4 |
| 40540 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 8 |
| 40641 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 41170 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 4 |
| 41200 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 41471 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 8 |
| 41514 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 41527 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 41536 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 41550 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 41554 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 5 |
| 41631 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 41647 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 41770 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 44075 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 44113 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 44241 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 45645 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 50522 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 51270 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 52234 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 53671 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 55241 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 57100 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 70000 | TRUE_EXTERNAL | SYSCALL | CALL-TARGET-RESOLUTION.md §3:170, §4.6:322; LABEL-MAP.md:173 | 6 | 1 |
| 70076 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 74000 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 74316 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75523 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75525 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75531 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75600 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75607 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75621 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75644 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75730 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75740 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75746 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75755 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75757 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 75762 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 75763 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76000 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76027 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 0 |
| 76052 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 76110 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76125 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76147 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76252 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 3 | 0 |
| 76265 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 76267 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 76334 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76357 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76404 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76411 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76423 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 76430 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76436 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76441 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76447 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76455 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76460 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76463 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76473 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76502 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 2 |
| 76505 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76511 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76520 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76526 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76534 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76535 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76543 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76551 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 2 |
| 76560 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76564 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76565 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 76566 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76575 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76576 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76601 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76605 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76607 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76615 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76622 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 3 | 4 |
| 76623 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76625 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76633 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76634 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76641 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76642 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76645 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76646 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76650 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76653 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76660 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76662 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76665 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76671 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76675 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76700 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76703 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76715 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76720 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 3 |
| 76721 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76724 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76727 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76745 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76751 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76760 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 76761 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76772 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 76773 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77005 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77026 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77044 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77046 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77053 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77064 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77067 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77100 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77103 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77111 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77122 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77126 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77132 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77136 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77163 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77166 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77171 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77173 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77175 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77200 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 2 |
| 77203 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77225 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77233 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77242 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77244 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77256 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77257 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 4 |
| 77260 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 3 |
| 77271 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77273 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 77274 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77275 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77277 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77301 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77303 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77306 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77311 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77312 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77314 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77316 | TRUE_EXTERNAL | ДЛЯСВЯ | CALL-TARGET-RESOLUTION.md §4.2:264 (S:1663, S:2435, S:2587) | 6 | 1 |
| 77317 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77321 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77322 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77325 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77326 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77337 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77345 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77350 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77357 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77360 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77364 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77365 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77366 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77371 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77372 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77374 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77376 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77402 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77420 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 23 |
| 77425 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77430 | TRUE_EXTERNAL | ВАС76D | CALL-TARGET-RESOLUTION.md §4.2:271 (S:1849, S:2528) | 1 | 1 |
| 77441 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77451 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 2 |
| 77460 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77464 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77465 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77471 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77474 | TRUE_EXTERNAL | ЕСТРР | CALL-TARGET-RESOLUTION.md §4.2:267 (S:1939, S:2463) | 4 | 1 |
| 77475 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77477 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77503 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 3 | 0 |
| 77520 | TRUE_EXTERNAL | МАКРО | CALL-TARGET-RESOLUTION.md §3:147, §4.2:266 (S:1966, S:1982) | 3 | 0 |
| 77524 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77530 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77536 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77565 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77575 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77611 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77612 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77622 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77623 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77624 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77631 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77635 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77647 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77660 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77710 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 2 | 4 |
| 77727 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77735 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77740 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 3 |
| 77741 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 4 |
| 77751 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77757 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77760 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77765 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77770 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 2 |
| 77774 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 1 |
| 77777 | UNKNOWN_ABSOLUTE | - | нет имени в ENTRY-POINTS.md / CALL-TARGET-RESOLUTION.md | 1 | 9 |

## 7. Полная таблица переаннотации

Формат рекомендуемого комментария: `, ВНЕШ: <name> [СА n], адрес <oct>` для именованных адресов; `, адрес <oct>: внешняя связь, имя не восстановлено` для неопознанных; `, адрес <oct>: локальная цель, не внешняя связь` для внутренних смещений. Формат соответствует `docs/EQU-VS-XREF.md` §5.2; поле `[СА n]` заполняется только там, где номер доказан (здесь только `*PAGE*` -- СА 3). Независимый подсчёт в `docs/EQU-VS-XREF.md` §5.4 (416 определений, 353 имени, 47 файлов) совпадает с этим аудитом. Все комментарии укладываются в 55 символов. Гипотетический характер роли неопознанного адреса должен дополнительно помечаться отдельной строкой `* (ГИПОТЕЗА)`.

| Зона | Строка | X-метка | Значение | Правильная роль | Рекомендуемый комментарий |
|---|---|---|---|---|---|
| 0055 | ASM-Z0055.be:133 | X063A | 63 | LOCAL_OFFSET -> P63 | , адрес 63: локальная цель, не внешняя связь |
| 0055 | ASM-Z0055.be:172 | X360A | 360 | LOCAL_OFFSET -> P360 | , адрес 360: локальная цель, не внешняя связь |
| 0055 | ASM-Z0055.be:213 | X122A | 122 | LOCAL_OFFSET -> P122 | , адрес 122: локальная цель, не внешняя связь |
| 0055 | ASM-Z0055.be:662 | X3604 | 3604 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3604: внешняя связь, имя не восстановлено |
| 0055 | ASM-Z0055.be:664 | X3762 | 3762 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3762: внешняя связь, имя не восстановлено |
| 0056 | ASM-Z0056.be:195 | X360A | 360 | LOCAL_OFFSET -> P360 | , адрес 360: локальная цель, не внешняя связь |
| 0056 | ASM-Z0056.be:227 | X122A | 122 | LOCAL_OFFSET -> P122 | , адрес 122: локальная цель, не внешняя связь |
| 0056 | ASM-Z0056.be:705 | X3604 | 3604 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3604: внешняя связь, имя не восстановлено |
| 0056 | ASM-Z0056.be:707 | X3762 | 3762 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3762: внешняя связь, имя не восстановлено |
| 0057 | ASM-Z0057.be:272 | X016A | 4016 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4016: внешняя связь, имя не восстановлено |
| 0057 | ASM-Z0057.be:759 | X3604 | 3604 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3604: внешняя связь, имя не восстановлено |
| 0057 | ASM-Z0057.be:761 | X3762 | 3762 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3762: внешняя связь, имя не восстановлено |
| 0057 | ASM-Z0057.be:763 | X4012 | 4012 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4012: внешняя связь, имя не восстановлено |
| 0060 | ASM-Z0060.be:163 | X142A | 142 | LOCAL_OFFSET -> P142 | , адрес 142: локальная цель, не внешняя связь |
| 0060 | ASM-Z0060.be:600 | X3604 | 3604 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3604: внешняя связь, имя не восстановлено |
| 0060 | ASM-Z0060.be:602 | X3762 | 3762 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3762: внешняя связь, имя не восстановлено |
| 0060 | ASM-Z0060.be:604 | X6017 | 6017 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 6017: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:106 | X338B | 76334 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76334: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:108 | X622B | 76622 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76622: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:111 | X014B | 10014 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 10014: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:114 | X101B | 31100 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 31100: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:373 | X34417 | 34417 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 34417: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:374 | X35340 | 35340 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 35340: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:375 | X36515 | 36515 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 36515: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:376 | X75523 | 75523 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75523: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:377 | X75525 | 75525 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75525: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:378 | X75531 | 75531 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75531: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:379 | X75600 | 75600 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75600: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:380 | X75607 | 75607 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75607: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:381 | X75621 | 75621 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75621: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:382 | X75644 | 75644 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75644: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:383 | X75730 | 75730 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75730: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:384 | X75740 | 75740 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75740: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:385 | X75746 | 75746 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75746: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:386 | X75762 | 75762 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75762: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:387 | X76125 | 76125 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76125: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:388 | X76265 | 76265 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76265: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:389 | X76267 | 76267 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76267: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:390 | X76357 | 76357 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76357: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:391 | X76460 | 76460 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76460: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:392 | X76502 | 76502 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76502: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:393 | X76576 | 76576 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76576: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:394 | X76622 | 76622 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76622: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:395 | X76646 | 76646 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76646: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:396 | X76662 | 76662 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76662: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:397 | X76772 | 76772 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76772: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:398 | X77005 | 77005 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77005: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:399 | X77044 | 77044 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77044: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:400 | X77046 | 77046 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77046: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:401 | X77111 | 77111 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77111: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:402 | X77200 | 77200 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77200: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:403 | X77203 | 77203 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77203: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:404 | X77316 | 77316 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ДЛЯСВЯ, адрес 77316 |
| 0137 | MBE-Z0137.be:405 | X77322 | 77322 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77322: внешняя связь, имя не восстановлено |
| 0137 | MBE-Z0137.be:406 | X77477 | 77477 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77477: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:306 | X40540 | 40540 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 40540: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:307 | X53671 | 53671 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 53671: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:308 | X76430 | 76430 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76430: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:309 | X76436 | 76436 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76436: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:310 | X76441 | 76441 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76441: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:311 | X76447 | 76447 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76447: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:312 | X76455 | 76455 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76455: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:313 | X76463 | 76463 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76463: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:314 | X76473 | 76473 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76473: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:315 | X76502 | 76502 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76502: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:316 | X76511 | 76511 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76511: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:317 | X76520 | 76520 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76520: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:318 | X76526 | 76526 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76526: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:319 | X76534 | 76534 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76534: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:320 | X76543 | 76543 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76543: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:321 | X76551 | 76551 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76551: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:322 | X76560 | 76560 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76560: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:323 | X76566 | 76566 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76566: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:324 | X76575 | 76575 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76575: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:325 | X76605 | 76605 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76605: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:326 | X76615 | 76615 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76615: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:327 | X76625 | 76625 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76625: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:328 | X76634 | 76634 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76634: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:329 | X76641 | 76641 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76641: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:330 | X76645 | 76645 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76645: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:331 | X76650 | 76650 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76650: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:332 | X76653 | 76653 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76653: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:333 | X76660 | 76660 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76660: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:334 | X76665 | 76665 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76665: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:335 | X76671 | 76671 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76671: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:336 | X76675 | 76675 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76675: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:337 | X76700 | 76700 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76700: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:338 | X76703 | 76703 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76703: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:339 | X76715 | 76715 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76715: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:340 | X76720 | 76720 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76720: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:341 | X76724 | 76724 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76724: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:342 | X76727 | 76727 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76727: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:343 | X77026 | 77026 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77026: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:344 | X77064 | 77064 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77064: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:345 | X77103 | 77103 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77103: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:346 | X77233 | 77233 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77233: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:347 | X77257 | 77257 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77257: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:348 | X77260 | 77260 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77260: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:349 | X77357 | 77357 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77357: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:350 | X77365 | 77365 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77365: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:351 | X77425 | 77425 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77425: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:352 | X77430 | 77430 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ВАС76D, адрес 77430 |
| 0140 | MBE-Z0140.be:353 | X77451 | 77451 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77451: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:354 | X77474 | 77474 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ЕСТРР, адрес 77474 |
| 0140 | MBE-Z0140.be:355 | X77524 | 77524 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77524: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:356 | X77565 | 77565 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77565: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:357 | X77575 | 77575 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77575: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:358 | X77623 | 77623 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77623: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:359 | X77635 | 77635 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77635: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:360 | X77735 | 77735 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77735: внешняя связь, имя не восстановлено |
| 0140 | MBE-Z0140.be:361 | X77770 | 77770 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77770: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:89 | X014B | 10014 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 10014: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:308 | X14342 | 14342 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 14342: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:309 | X36562 | 36562 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 36562: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:310 | X40540 | 40540 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 40540: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:311 | X41770 | 41770 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41770: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:312 | X75755 | 75755 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75755: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:313 | X75757 | 75757 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75757: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:314 | X75763 | 75763 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 75763: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:315 | X76052 | 76052 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76052: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:316 | X76110 | 76110 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76110: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:317 | X76147 | 76147 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76147: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:318 | X77260 | 77260 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77260: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:319 | X77326 | 77326 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77326: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:320 | X77337 | 77337 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77337: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:321 | X77350 | 77350 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77350: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:322 | X77360 | 77360 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77360: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:323 | X77371 | 77371 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77371: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:324 | X77376 | 77376 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77376: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:325 | X77402 | 77402 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77402: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:326 | X77441 | 77441 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77441: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:327 | X77451 | 77451 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77451: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:328 | X77464 | 77464 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77464: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:329 | X77465 | 77465 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77465: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:330 | X77471 | 77471 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77471: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:331 | X77530 | 77530 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77530: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:332 | X77536 | 77536 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77536: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:333 | X77612 | 77612 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77612: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:334 | X77622 | 77622 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77622: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:335 | X77624 | 77624 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77624: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:336 | X77631 | 77631 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77631: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:337 | X77647 | 77647 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77647: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:338 | X77660 | 77660 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77660: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:339 | X77710 | 77710 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77710: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:340 | X77740 | 77740 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77740: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:341 | X77741 | 77741 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77741: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:342 | X77760 | 77760 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77760: внешняя связь, имя не восстановлено |
| 0141 | MBE-Z0141.be:343 | X77774 | 77774 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77774: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:246 | X34417 | 34417 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 34417: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:247 | X36562 | 36562 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 36562: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:248 | X44075 | 44075 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 44075: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:249 | X52234 | 52234 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 52234: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:250 | X76423 | 76423 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76423: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:251 | X76565 | 76565 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76565: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:252 | X76601 | 76601 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76601: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:253 | X76607 | 76607 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76607: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:254 | X76633 | 76633 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76633: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:255 | X77053 | 77053 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77053: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:256 | X77126 | 77126 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77126: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:257 | X77132 | 77132 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77132: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:258 | X77136 | 77136 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77136: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:259 | X77163 | 77163 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77163: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:260 | X77166 | 77166 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77166: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:261 | X77171 | 77171 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77171: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:262 | X77173 | 77173 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77173: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:263 | X77175 | 77175 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77175: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:264 | X77200 | 77200 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77200: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:265 | X77225 | 77225 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77225: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:266 | X77242 | 77242 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77242: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:267 | X77244 | 77244 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77244: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:268 | X77256 | 77256 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77256: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:269 | X77257 | 77257 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77257: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:270 | X77271 | 77271 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77271: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:271 | X77275 | 77275 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77275: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:272 | X77277 | 77277 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77277: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:273 | X77301 | 77301 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77301: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:274 | X77303 | 77303 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77303: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:275 | X77306 | 77306 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77306: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:276 | X77311 | 77311 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77311: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:277 | X77314 | 77314 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77314: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:278 | X77317 | 77317 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77317: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:279 | X77321 | 77321 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77321: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:280 | X77325 | 77325 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77325: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:281 | X77345 | 77345 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77345: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:282 | X77364 | 77364 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77364: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:283 | X77366 | 77366 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77366: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:284 | X77372 | 77372 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77372: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:285 | X77374 | 77374 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77374: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:286 | X77420 | 77420 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77420: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:287 | X77710 | 77710 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77710: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:288 | X77727 | 77727 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77727: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:289 | X77757 | 77757 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77757: внешняя связь, имя не восстановлено |
| 0142 | MBE-Z0142.be:290 | X77765 | 77765 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77765: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:64 | X622B | 76622 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76622: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:279 | X34417 | 34417 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 34417: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:280 | X44113 | 44113 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 44113: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:281 | X44241 | 44241 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 44241: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:282 | X45645 | 45645 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 45645: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:283 | X76404 | 76404 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76404: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:284 | X76411 | 76411 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76411: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:285 | X76505 | 76505 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76505: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:286 | X76535 | 76535 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76535: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:287 | X76551 | 76551 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76551: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:288 | X76564 | 76564 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76564: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:289 | X76623 | 76623 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76623: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:290 | X76642 | 76642 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76642: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:291 | X76720 | 76720 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76720: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:292 | X76721 | 76721 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76721: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:293 | X76745 | 76745 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76745: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:294 | X76751 | 76751 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76751: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:295 | X76760 | 76760 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76760: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:296 | X76761 | 76761 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76761: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:297 | X76773 | 76773 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76773: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:298 | X77067 | 77067 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77067: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:299 | X77100 | 77100 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77100: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:300 | X77122 | 77122 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77122: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:301 | X77273 | 77273 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77273: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:302 | X77274 | 77274 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77274: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:303 | X77312 | 77312 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77312: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:304 | X77460 | 77460 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77460: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:305 | X77475 | 77475 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77475: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:306 | X77611 | 77611 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77611: внешняя связь, имя не восстановлено |
| 0143 | MBE-Z0143.be:307 | X77751 | 77751 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77751: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:110 | X120B | 120 | LOCAL_OFFSET -> P120 | , адрес 120: локальная цель, не внешняя связь |
| 0144 | MBE-Z0144.be:115 | X144B | 144 | LOCAL_OFFSET -> P144 | , адрес 144: локальная цель, не внешняя связь |
| 0144 | MBE-Z0144.be:475 | X40130 | 40130 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 40130: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:476 | X40207 | 40207 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 40207: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:477 | X40641 | 40641 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 40641: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:478 | X41170 | 41170 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41170: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:479 | X41200 | 41200 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41200: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:480 | X41471 | 41471 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41471: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:481 | X41514 | 41514 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41514: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:482 | X41527 | 41527 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41527: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:483 | X41536 | 41536 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41536: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:484 | X41550 | 41550 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41550: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:485 | X41554 | 41554 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41554: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:486 | X41631 | 41631 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41631: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:487 | X41647 | 41647 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 41647: внешняя связь, имя не восстановлено |
| 0144 | MBE-Z0144.be:488 | X7417 | 7417 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: УППСЛУ, адрес 7417 |
| 0145 | MBE-Z0145.be:403 | X2024 | 2024 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2024: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:404 | X2056 | 2056 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2056: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:405 | X2113 | 2113 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2113: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:406 | X2123 | 2123 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2123: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:407 | X2133 | 2133 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2133: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:408 | X2174 | 2174 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2174: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:409 | X2234 | 2234 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2234: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:410 | X2247 | 2247 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2247: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:411 | X2276 | 2276 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2276: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:412 | X2315 | 2315 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2315: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:413 | X2320 | 2320 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2320: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:414 | X2356 | 2356 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2356: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:415 | X2376 | 2376 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2376: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:416 | X2414 | 2414 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2414: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:417 | X2522 | 2522 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2522: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:418 | X2526 | 2526 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2526: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:419 | X2545 | 2545 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2545: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:420 | X2621 | 2621 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2621: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:421 | X2724 | 2724 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2724: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:422 | X2744 | 2744 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2744: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:423 | X2762 | 2762 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2762: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:424 | X2775 | 2775 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2775: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:425 | X2777 | 2777 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2777: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:426 | X3000 | 3000 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3000: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:427 | X3007 | 3007 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3007: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:428 | X3014 | 3014 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3014: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:429 | X3110 | 3110 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3110: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:430 | X3153 | 3153 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3153: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:431 | X3162 | 3162 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3162: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:432 | X3175 | 3175 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3175: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:433 | X3177 | 3177 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3177: внешняя связь, имя не восстановлено |
| 0145 | MBE-Z0145.be:434 | X3200 | 3200 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3200: внешняя связь, имя не восстановлено |
| 0147 | MBE-Z0147.be:234 | X112B | 112 | LOCAL_OFFSET -> P112 | , адрес 112: локальная цель, не внешняя связь |
| 0147 | MBE-Z0147.be:362 | X2000 | 2000 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: *PAGE* [СА 3], адрес 2000 |
| 0147 | MBE-Z0147.be:363 | X30662 | 30662 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 30662: внешняя связь, имя не восстановлено |
| 0147 | MBE-Z0147.be:364 | X34017 | 34017 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 34017: внешняя связь, имя не восстановлено |
| 0147 | MBE-Z0147.be:365 | X3410 | 3410 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3410: внешняя связь, имя не восстановлено |
| 0147 | MBE-Z0147.be:366 | X4000 | 4000 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: MON*ITOR, адрес 4000 |
| 0147 | MBE-Z0147.be:367 | X5056 | 5056 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 5056: внешняя связь, имя не восстановлено |
| 0147 | MBE-Z0147.be:368 | X55241 | 55241 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 55241: внешняя связь, имя не восстановлено |
| 0147 | MBE-Z0147.be:369 | X6767 | 6767 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 6767: внешняя связь, имя не восстановлено |
| 0147 | MBE-Z0147.be:370 | X7033 | 7033 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 7033: внешняя связь, имя не восстановлено |
| 0147 | MBE-Z0147.be:371 | X74000 | 74000 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 74000: внешняя связь, имя не восстановлено |
| 0147 | MBE-Z0147.be:372 | X74316 | 74316 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 74316: внешняя связь, имя не восстановлено |
| 0150 | MBE-Z0150.be:96 | X120B | 120 | LOCAL_OFFSET -> P120 | , адрес 120: локальная цель, не внешняя связь |
| 0150 | MBE-Z0150.be:102 | X142B | 142 | LOCAL_OFFSET -> P142 | , адрес 142: локальная цель, не внешняя связь |
| 0150 | MBE-Z0150.be:434 | X7417B | 7417 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: УППСЛУ, адрес 7417 |
| 0151 | MBE-Z0151.be:526 | X70000 | 70000 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: SYSCALL, адрес 70000 |
| 0151 | MBE-Z0151.be:528 | X7417B | 7417 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: УППСЛУ, адрес 7417 |
| 0152 | MBE-Z0152.be:303 | X70000 | 70000 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: SYSCALL, адрес 70000 |
| 0154 | MBE-Z0154.be:591 | X316B | 77316 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ДЛЯСВЯ, адрес 77316 |
| 0154 | MBE-Z0154.be:593 | X0100B | 40100 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 40100: внешняя связь, имя не восстановлено |
| 0154 | MBE-Z0154.be:595 | X7474B | 77474 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ЕСТРР, адрес 77474 |
| 0154 | MBE-Z0154.be:597 | X503B | 77503 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77503: внешняя связь, имя не восстановлено |
| 0154 | MBE-Z0154.be:599 | X270B | 51270 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 51270: внешняя связь, имя не восстановлено |
| 0154 | MBE-Z0154.be:601 | X252B | 76252 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76252: внешняя связь, имя не восстановлено |
| 0154 | MBE-Z0154.be:603 | X7520B | 77520 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: МАКРО, адрес 77520 |
| 0154 | MBE-Z0154.be:605 | X522B | 50522 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 50522: внешняя связь, имя не восстановлено |
| 0155 | MBE-Z0155.be:542 | X316B | 77316 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ДЛЯСВЯ, адрес 77316 |
| 0155 | MBE-Z0155.be:544 | X7520B | 77520 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: МАКРО, адрес 77520 |
| 0155 | MBE-Z0155.be:546 | X503B | 77503 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77503: внешняя связь, имя не восстановлено |
| 0155 | MBE-Z0155.be:548 | X252B | 76252 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76252: внешняя связь, имя не восстановлено |
| 0155 | MBE-Z0155.be:550 | X7474B | 77474 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ЕСТРР, адрес 77474 |
| 0157 | MBE-Z0157.be:442 | X316B | 77316 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ДЛЯСВЯ, адрес 77316 |
| 0157 | MBE-Z0157.be:444 | X7520B | 77520 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: МАКРО, адрес 77520 |
| 0157 | MBE-Z0157.be:446 | X503B | 77503 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77503: внешняя связь, имя не восстановлено |
| 0157 | MBE-Z0157.be:448 | X252B | 76252 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76252: внешняя связь, имя не восстановлено |
| 0157 | MBE-Z0157.be:450 | X7474B | 77474 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ЕСТРР, адрес 77474 |
| 0161 | MBE-Z0161.be:232 | X122E | 122 | LOCAL_OFFSET -> P122 | , адрес 122: локальная цель, не внешняя связь |
| 0161 | MBE-Z0161.be:233 | X112E | 112 | LOCAL_OFFSET -> P112 | , адрес 112: локальная цель, не внешняя связь |
| 0161 | MBE-Z0161.be:234 | X116E | 116 | LOCAL_OFFSET -> P116 | , адрес 116: локальная цель, не внешняя связь |
| 0161 | MBE-Z0161.be:235 | X360E | 360 | LOCAL_OFFSET -> P360 | , адрес 360: локальная цель, не внешняя связь |
| 0162 | MBE-Z0162.be:40 | X112B | 112 | LOCAL_OFFSET -> P112 | , адрес 112: локальная цель, не внешняя связь |
| 0162 | MBE-Z0162.be:43 | X116B | 116 | LOCAL_OFFSET -> P116 | , адрес 116: локальная цель, не внешняя связь |
| 0162 | MBE-Z0162.be:45 | X117B | 117 | LOCAL_OFFSET -> P117 | , адрес 117: локальная цель, не внешняя связь |
| 0162 | MBE-Z0162.be:48 | X120B | 120 | LOCAL_OFFSET -> P120 | , адрес 120: локальная цель, не внешняя связь |
| 0162 | MBE-Z0162.be:51 | X140B | 140 | LOCAL_OFFSET -> P140 | , адрес 140: локальная цель, не внешняя связь |
| 0162 | MBE-Z0162.be:53 | X141B | 141 | LOCAL_OFFSET -> P141 | , адрес 141: локальная цель, не внешняя связь |
| 0166 | MBE-Z0166.be:59 | X101B | 31100 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 31100: внешняя связь, имя не восстановлено |
| 0170 | MBE-Z0170.be:93 | X101B | 31100 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 31100: внешняя связь, имя не восстановлено |
| 0170 | MBE-Z0170.be:333 | X070B | 2070 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2070: внешняя связь, имя не восстановлено |
| 0170 | MBE-Z0170.be:335 | X4130B | 4130 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4130: внешняя связь, имя не восстановлено |
| 0170 | MBE-Z0170.be:337 | X155B | 5155 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 5155: внешняя связь, имя не восстановлено |
| 0170 | MBE-Z0170.be:339 | X4276B | 4276 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4276: внешняя связь, имя не восстановлено |
| 0170 | MBE-Z0170.be:341 | X2446B | 2446 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2446: внешняя связь, имя не восстановлено |
| 0170 | MBE-Z0170.be:343 | X0100B | 40100 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 40100: внешняя связь, имя не восстановлено |
| 0171 | MBE-Z0171.be:374 | X7417B | 7417 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: УППСЛУ, адрес 7417 |
| 0171 | MBE-Z0171.be:376 | X155B | 5155 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 5155: внешняя связь, имя не восстановлено |
| 0171 | MBE-Z0171.be:378 | X4652B | 4652 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4652: внешняя связь, имя не восстановлено |
| 0172 | MBE-Z0172.be:454 | X676B | 3676 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3676: внешняя связь, имя не восстановлено |
| 0172 | MBE-Z0172.be:456 | X162B | 3162 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3162: внешняя связь, имя не восстановлено |
| 0172 | MBE-Z0172.be:458 | X3656B | 3656 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3656: внешняя связь, имя не восстановлено |
| 0173 | MBE-Z0173.be:482 | X3173B | 3173 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3173: внешняя связь, имя не восстановлено |
| 0173 | MBE-Z0173.be:484 | X157B | 4157 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4157: внешняя связь, имя не восстановлено |
| 0173 | MBE-Z0173.be:486 | X162B | 3162 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3162: внешняя связь, имя не восстановлено |
| 0174 | MBE-Z0174.be:31 | X0100B | 40100 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 40100: внешняя связь, имя не восстановлено |
| 0176 | MBE-Z0176.be:620 | X7417B | 7417 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: УППСЛУ, адрес 7417 |
| 0176 | MBE-Z0176.be:622 | X5465B | 5465 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 5465: внешняя связь, имя не восстановлено |
| 0176 | MBE-Z0176.be:624 | X6112B | 6112 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 6112: внешняя связь, имя не восстановлено |
| 0176 | MBE-Z0176.be:626 | X5453B | 5453 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 5453: внешняя связь, имя не восстановлено |
| 0177 | MBE-Z0177.be:235 | X5453B | 5453 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 5453: внешняя связь, имя не восстановлено |
| 0540 | MBE2-Z0540.be:119 | X014C | 10014 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 10014: внешняя связь, имя не восстановлено |
| 0544 | MBE2-Z0544.be:40 | X120C | 120 | LOCAL_OFFSET -> C120 | , адрес 120: локальная цель, не внешняя связь |
| 0544 | MBE2-Z0544.be:45 | X144C | 144 | LOCAL_OFFSET -> C144 | , адрес 144: локальная цель, не внешняя связь |
| 0544 | MBE2-Z0544.be:109 | X122C | 122 | LOCAL_OFFSET -> C122 | , адрес 122: локальная цель, не внешняя связь |
| 0547 | MBE2-Z0547.be:172 | X120C | 120 | LOCAL_OFFSET -> C120 | , адрес 120: локальная цель, не внешняя связь |
| 0547 | MBE2-Z0547.be:200 | X122C | 122 | LOCAL_OFFSET -> C122 | , адрес 122: локальная цель, не внешняя связь |
| 0550 | MBE2-Z0550.be:62 | X116C | 116 | LOCAL_OFFSET -> C116 | , адрес 116: локальная цель, не внешняя связь |
| 0550 | MBE2-Z0550.be:66 | X120C | 120 | LOCAL_OFFSET -> C120 | , адрес 120: локальная цель, не внешняя связь |
| 0550 | MBE2-Z0550.be:74 | X142C | 142 | LOCAL_OFFSET -> C142 | , адрес 142: локальная цель, не внешняя связь |
| 0550 | MBE2-Z0550.be:422 | X70076 | 70076 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 70076: внешняя связь, имя не восстановлено |
| 0551 | MBE2-Z0551.be:519 | X70000 | 70000 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: SYSCALL, адрес 70000 |
| 0552 | MBE2-Z0552.be:292 | X70000 | 70000 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: SYSCALL, адрес 70000 |
| 0554 | MBE2-Z0554.be:575 | X77316 | 77316 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ДЛЯСВЯ, адрес 77316 |
| 0555 | MBE2-Z0555.be:244 | X016C | 4016 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4016: внешняя связь, имя не восстановлено |
| 0555 | MBE2-Z0555.be:516 | X77316 | 77316 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: ДЛЯСВЯ, адрес 77316 |
| 0556 | MBE2-Z0556.be:56 | X70000 | 70000 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: SYSCALL, адрес 70000 |
| 0557 | MBE2-Z0557.be:431 | X76027 | 76027 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76027: внешняя связь, имя не восстановлено |
| 0561 | MBE2-Z0561.be:27 | X3016 | 3016 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3016: внешняя связь, имя не восстановлено |
| 0561 | MBE2-Z0561.be:28 | X3171 | 3171 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3171: внешняя связь, имя не восстановлено |
| 0561 | MBE2-Z0561.be:52 | X115C | 115 | LOCAL_OFFSET -> C115 | , адрес 115: локальная цель, не внешняя связь |
| 0561 | MBE2-Z0561.be:58 | X140C | 140 | LOCAL_OFFSET -> C140 | , адрес 140: локальная цель, не внешняя связь |
| 0561 | MBE2-Z0561.be:92 | X122C | 122 | LOCAL_OFFSET -> C122 | , адрес 122: локальная цель, не внешняя связь |
| 0562 | MBE2-Z0562.be:59 | X112C | 112 | LOCAL_OFFSET -> C112 | , адрес 112: локальная цель, не внешняя связь |
| 0562 | MBE2-Z0562.be:62 | X116C | 116 | LOCAL_OFFSET -> C116 | , адрес 116: локальная цель, не внешняя связь |
| 0562 | MBE2-Z0562.be:64 | X117C | 117 | LOCAL_OFFSET -> C117 | , адрес 117: локальная цель, не внешняя связь |
| 0562 | MBE2-Z0562.be:67 | X120C | 120 | LOCAL_OFFSET -> C120 | , адрес 120: локальная цель, не внешняя связь |
| 0562 | MBE2-Z0562.be:70 | X140C | 140 | LOCAL_OFFSET -> C140 | , адрес 140: локальная цель, не внешняя связь |
| 0562 | MBE2-Z0562.be:72 | X141C | 141 | LOCAL_OFFSET -> C141 | , адрес 141: локальная цель, не внешняя связь |
| 0565 | MBE2-Z0565.be:24 | X3624 | 3624 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3624: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:25 | X3626 | 3626 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3626: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:26 | X2040 | 2040 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2040: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:27 | X3607 | 3607 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3607: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:28 | X1213 | 1213 | LOCAL_OFFSET -> C1213 | , адрес 1213: локальная цель, не внешняя связь |
| 0565 | MBE2-Z0565.be:29 | X2267 | 2267 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2267: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:30 | X2370 | 2370 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2370: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:31 | X2652 | 2652 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2652: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:32 | X2757 | 2757 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 2757: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:33 | X3133 | 3133 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3133: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:34 | X3535 | 3535 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3535: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:35 | X3572 | 3572 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3572: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:36 | X3612 | 3612 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3612: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:37 | X4044 | 4044 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4044: внешняя связь, имя не восстановлено |
| 0565 | MBE2-Z0565.be:149 | X016C | 4016 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4016: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:24 | X77777 | 77777 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 77777: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:25 | X34050 | 34050 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 34050: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:26 | X4064 | 4064 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4064: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:27 | X4266 | 4266 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4266: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:28 | X5413 | 5413 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 5413: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:29 | X1202 | 1202 | LOCAL_OFFSET -> C1202 | , адрес 1202: локальная цель, не внешняя связь |
| 0566 | MBE2-Z0566.be:30 | X1213 | 1213 | LOCAL_OFFSET -> C1213 | , адрес 1213: локальная цель, не внешняя связь |
| 0566 | MBE2-Z0566.be:31 | X20052 | 20052 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 20052: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:32 | X20067 | 20067 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 20067: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:33 | X32463 | 32463 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 32463: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:34 | X33050 | 33050 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 33050: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:35 | X33445 | 33445 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 33445: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:36 | X40000 | 40000 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 40000: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:37 | X4121 | 4121 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4121: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:38 | X4276 | 4276 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4276: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:39 | X4765 | 4765 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4765: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:40 | X57100 | 57100 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 57100: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:41 | X70000 | 70000 | NAMED_ADDRESS (не объявление ВНЕШН) | , ВНЕШ: SYSCALL, адрес 70000 |
| 0566 | MBE2-Z0566.be:42 | X7447 | 7447 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 7447: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:43 | X76000 | 76000 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 76000: внешняя связь, имя не восстановлено |
| 0566 | MBE2-Z0566.be:122 | X101C | 31100 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 31100: внешняя связь, имя не восстановлено |
| 0570 | MBE2-Z0570.be:32 | X4017 | 4017 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4017: внешняя связь, имя не восстановлено |
| 0570 | MBE2-Z0570.be:33 | X4170 | 4170 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4170: внешняя связь, имя не восстановлено |
| 0570 | MBE2-Z0570.be:149 | X101C | 31100 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 31100: внешняя связь, имя не восстановлено |
| 0571 | MBE2-Z0571.be:23 | X5125 | 5125 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 5125: внешняя связь, имя не восстановлено |
| 0571 | MBE2-Z0571.be:24 | X5222 | 5222 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 5222: внешняя связь, имя не восстановлено |
| 0572 | MBE2-Z0572.be:22 | X3670 | 3670 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3670: внешняя связь, имя не восстановлено |
| 0572 | MBE2-Z0572.be:23 | X3650 | 3650 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 3650: внешняя связь, имя не восстановлено |
| 0573 | MBE2-Z0573.be:28 | X4160 | 4160 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4160: внешняя связь, имя не восстановлено |
| 0573 | MBE2-Z0573.be:29 | X4477 | 4477 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4477: внешняя связь, имя не восстановлено |
| 0573 | MBE2-Z0573.be:410 | X016C | 4016 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 4016: внешняя связь, имя не восстановлено |
| 0576 | MBE2-Z0576.be:26 | X6052 | 6052 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 6052: внешняя связь, имя не восстановлено |
| 0576 | MBE2-Z0576.be:27 | X5444 | 5444 | UNKNOWN_ABSOLUTE (гипотеза) | , адрес 5444: внешняя связь, имя не восстановлено |

## 8. Оговорки

1. Ни один `.be`-файл не изменялся: это только аудит и рекомендации.
2. Внутренние смещения предлагается переименовать в `P...` (ASM/B) или `C...` (B2) по образцу `P201 ЭКВ '201' , цель ПБ/ПВ; [PROC-B2]` (`bemsh/MBE2-Z0562.be:24`).
3. Для класса `UNKNOWN_ABSOLUTE` сам адрес -- гипотеза: физическая страница может быть не привязана (`analysis/MEMORY-MAP.md` §5), а имя не восстановлено.
4. Метки, определённые, но не используемые в коде, остаются подозрительными: они живут только в комментариях.
