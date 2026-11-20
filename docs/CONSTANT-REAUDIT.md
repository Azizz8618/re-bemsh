# ПОВТОРНЫЙ АУДИТ ЛИТЕРАЛОВ CONSTANT/DATA

Сгенерировано `python3 tools/constant_reaudit.py`. Статус: **аннотация,
не ground truth**. Файлы `bemsh/`, `gold/`, `dis/`, `sym/`,
`docs/PROCEDURES-*`, `analysis/global_xref.tsv` только читались.
Исправления применяет отдельный агент по списку из §7.

## 1. Почему возник вопрос

`tools/literal_labels.py` классифицирует кавычный восьмеричный операнд
по **мнемонике**: операнды `УИА/ПБ/ПВ/СЧ/ЗП/...` -> `ADDRESS`,
а всё остальное -> `CONSTANT`: экстракоды `Э50 '105'`, маски,
immediate `РЖА '3'`, слова `КОНД`, определения `ЭКВ`.
Число внутри `Э50 '105'` или `ЭКВ '4235'` может быть не
константой, а **адресом входа в процедуру** (указатель в таблице
переходов, дескриптор, слово переадресации). Типичный пример:
`CAL604 ЭКВ '3604'` — внешняя CALL-цель (`PROCEDURES-ASM.md:358`).

## 2. Методика

1. **Процедуры.** Разобраны три каталога: `PROCEDURES-ASM.md`
   (кандидаты вида `0220-0220 001 C3`, зона из заголовка `ЗОНА`),
   `PROCEDURES-B.md` (`0142:1115-1117 size=003 CALL ОСН`),
   `PROCEDURES-B2.md` (только §4, строки `0540 1115 1115 1 CALLx1`).
   Строки со статусом `ДАН` отброшены как ложные цели.
   Получено 246 начал процедур `(зона, адрес)`.
2. **Кросс-ссылки.** Из `global_xref.tsv` (6422 строки) извлечены
   цели `A#####`/`D#####`/`OCT:NNNN`; по колонке `sources` посчитаны
   вхождения `пв/пво/вжм` (CALL) и `пб/по/пе/цикл/...` (ветвления).
   Порог кандидата: >=2 CALL-ссылки. Счётчики отражают число
   листингов, а не машинных обращений (`GLOBAL-XREF.md` §7.5).
3. **Константы.** Переиспользован `literal_labels.scan()` — тот же
   сканер, что и в исходной классификации. Взяты все 38265
   вхождений `kind=CONSTANT`; исключены 16770 строк `ЭКВ`
   (это определения меток), забел `25252/72525` и хвосты комментариев.
   Осталось 1035 настоящих операндов-констант. `sym/ALL_LABELS.tab`
   содержит только 5362 строки `ADDRESS` (по построению `build_index`
   константы туда не попадают), поэтому он использован как
   перекрёстная проверка, а не как источник констант.
4. **Словa КОНД.** Дополнительно сканированы 14742 words
   `В'NNNNNNNNNNNNNNNN'`; каждое делится на два полуслова по 8
   восьмеричных цифр, младшие 5 цифр полуслова — поле адреса БЭСМ-6.
5. **Пересечение.** Значение кандидат, если оно совпадает с началом
   процедуры **в той же зоне** либо имеет >=2 CALL-ссылок в xref.
   Для строк `ЭКВ` дополнительно посчитано использование метки
   внутри своего `.be` (`BR/ПО/ПБ/ПЕ/...` = ветвление, иначе данные).

## 3. Статистика

| Показатель | Значение |
|---|---|
| Начала процедур (без ДАН) | 246 |
| Адресных целей в xref | 5833 |
| Строк ЭКВ (все classified CONSTANT) | 16770 |
| ЭКВ со значением — начало процедуры в своей зоне | 204 |
| из них метка уже процедурная (BR/CA/UTL/SUB/...) | 110 |
| Настоящих операндов CONSTANT (без ЭКВ и забела) | 1035 |
| Слов КОНД с адресом процедуры в младших 5 цифрах | 1 |
| Кандидатов всего | 105 |
| Вердикт PROCEDURE_LABEL | 79 |
| Вердикт POINTER_TO_PROCEDURE | 15 |
| Вердикт FALSE_POSITIVE | 11 |
| Значений с меткой ADDRESS в ALL_LABELS.tab | 5362 |

Распределение по источникам: ЭКВ 94 (79+6+9), операнды 10 (8+2),
КОНД 1. Из 204 операций `ЭКВ`, чьё значение — начало процедуры,
110 уже носят процедурные имена и в список исправлений не входят.

## 4. Вердикты

- **PROCEDURE_LABEL** — метка данных (`MB105`, `AM220`, `DAT643`)
  определена как адрес процедуры и используется как цель перехода.
  Требует переименования. `ПОДТВЕРЖДЕНО` — ветвлений >=1,
  данных-использований 0; `ГИПОТЕЗА` — ячейка двойного назначения.
- **POINTER_TO_PROCEDURE** — данные хранят адрес процедуры
  (экстракод в последовательности `МОДА/Э50/МОДА`, слово КОНД).
  нужен отдельный ролевой префикс `PTR`, а не имя процедуры.
- **FALSE_POSITIVE** — численное совпадение: номер регистра,
  immediate `1`, артефакт `ВХОД` по адресу `0001`.

## 5. Ключевые BYTE-доказательства

### 5.1 `0161:0105` и `0161:0115` — указатели в таблице переходов

Каталог: `PROCEDURES-B.md:994` (`0161:0105-0114 BRANCH ОСН`),
`PROCEDURES-B.md:1003` (`0161:0115-0121 BRANCH ОСН`).
В `bemsh/MBE-Z0161.be` те же адреса встречаются в трёх ипостасях:

```
1401:        Э50  '105'      , экстракод Э50: 105
1403:        Э50  '115'      , экстракод Э50: 115
1188:        ПО   MB105(М14) , перейти по условию MB105 через М14
1471:        ПБ   MB105(М14) , возврат MB105 через М14
1991:        ПЕ   MB105(М14) , перейти MB105 через М14
```

Вокруг строк 1385-1414 — `ПВ (М16)`, `УИА 0(М16)`, `МОДА`,
`СДА 64+33/64-33`, `ЗП 3(М16)/2(М16)`: `М16` — индекс,
а `105/115` загружаются в адресное поле следующих команд.
Это исполняемая таблица переходов, а не экстракод-константа.
Вердикт: `POINTER_TO_PROCEDURE` для обеих строк `Э50`,
`PROCEDURE_LABEL` для `MB105 ЭКВ '105'` (строка 109).

### 5.2 `0060:0020` — процедура внутри слова КОНД

`bemsh/ASM-Z0060.be:521`:

```
КОНД В'0000672707100020'    , код: зп 6727, CALL 020
```

Младшие 5 цифр второго полуслова `07100020` = `00020` —
начало процедуры `0020` (`PROCEDURES-ASM.md:228`,
`PROCEDURES-ASM.md:413`: `numeric: пв 16(М1) ×3; пб (М1)`).
Вердикт: `POINTER_TO_PROCEDURE`, `PTR20`.

### 5.3 `0154:4114` / `0554:4114` — CALL-цель в экстракоде

```
MBE-Z0154.be:867:  Э53  '4114'(М5) , экстракод Э53: 4114 (М5)
MBE2-Z0554.be:848: Э53  '4114'(М5) , экстракод Э53: 4114 (М5)
```

xref: `OCT:4114 MEM_4114_UNKNOWN`, CALL=44, ref=72.
Вердикт: `POINTER_TO_PROCEDURE` (ГИПОТЕЗА: возможна заливка
шахматного теста; роль `MEM_*` не подтверждена штампом).

### 5.4 FALSE_POSITIVE

```
ASM-Z0055.be:764:  РЕГ  '20' , в регистр 20
MBE2-Z0572.be:947: РЖА  '1' , подготовить '1'
```

`20` — номер регистра, `1` — immediate; совпадение с
`0055:0020` и зонным `ВХОД 0001` случайно. Оставляем как есть.

## 6. Полная таблица кандидатов

Колонка `br/data` — число ветвлений / данных-использований метки
в своём файле. `доказательство` — строка каталога процедур.

| зона | строка | файл | восьм. | источник | старое | вердикт | новое | ув. | br/data | доказательство | xref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0055 | 40 | ASM-Z0055.be | `220` | EQV | AM220 | PROCEDURE_LABEL | P220 | ПОДТВ | 4/0 | PROCEDURES-ASM.md:215 | - |
| 0055 | 41 | ASM-Z0055.be | `231` | EQV | AM231 | PROCEDURE_LABEL | P231 | ГИПОТЕЗА | 5/1 | PROCEDURES-ASM.md:217 | - |
| 0055 | 48 | ASM-Z0055.be | `300` | EQV | AM300 | PROCEDURE_LABEL | P300 | ПОДТВ | 4/0 | PROCEDURES-ASM.md:220 | - |
| 0055 | 51 | ASM-Z0055.be | `301` | EQV | AM301 | PROCEDURE_LABEL | P301 | ГИПОТЕЗА | 1/3 | PROCEDURES-ASM.md:221 | - |
| 0055 | 69 | ASM-Z0055.be | `43` | EQV | AM43 | PROCEDURE_LABEL | P43 | ГИПОТЕЗА | 1/1 | PROCEDURES-ASM.md:229 | - |
| 0055 | 160 | ASM-Z0055.be | `366` | EQV | B2366 | PROCEDURE_LABEL | P366 | ПОДТВ | 1/0 | PROCEDURES-ASM.md:226 | - |
| 0055 | 355 | ASM-Z0055.be | `643` | EQV | DAT643 | PROCEDURE_LABEL | P643 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:248 | - |
| 0055 | 356 | ASM-Z0055.be | `650` | EQV | DAT650 | PROCEDURE_LABEL | P650 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:249 | - |
| 0055 | 382 | ASM-Z0055.be | `107` | EQV | MB107 | PROCEDURE_LABEL | P107 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:230 | - |
| 0055 | 385 | ASM-Z0055.be | `121` | EQV | MB121 | PROCEDURE_LABEL | P121 | ПОДТВ | 1/0 | PROCEDURES-ASM.md:231 | - |
| 0055 | 387 | ASM-Z0055.be | `131` | EQV | MB131 | PROCEDURE_LABEL | P131 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:233 | - |
| 0055 | 389 | ASM-Z0055.be | `133` | EQV | MB133 | PROCEDURE_LABEL | P133 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:234 | - |
| 0055 | 394 | ASM-Z0055.be | `145` | EQV | MB145 | PROCEDURE_LABEL | P145 | ПОДТВ | 1/0 | PROCEDURES-ASM.md:235 | - |
| 0055 | 398 | ASM-Z0055.be | `20` | EQV | MB20 | PROCEDURE_LABEL | P20 | ГИПОТЕЗА | 3/2 | PROCEDURES-ASM.md:228 | - |
| 0055 | 404 | ASM-Z0055.be | `225` | EQV | MB225 | PROCEDURE_LABEL | P225 | ГИПОТЕЗА | 3/1 | PROCEDURES-ASM.md:236 | - |
| 0055 | 415 | ASM-Z0055.be | `343` | EQV | MB343 | PROCEDURE_LABEL | P343 | ПОДТВ | 1/0 | PROCEDURES-ASM.md:225 | - |
| 0055 | 425 | ASM-Z0055.be | `364` | EQV | MB364 | PROCEDURE_LABEL | P364 | ПОДТВ | 3/0 | PROCEDURES-ASM.md:240 | - |
| 0055 | 429 | ASM-Z0055.be | `402` | EQV | MB402 | PROCEDURE_LABEL | P402 | ПОДТВ | 4/0 | PROCEDURES-ASM.md:227 | - |
| 0055 | 430 | ASM-Z0055.be | `407` | EQV | MB407 | PROCEDURE_LABEL | P407 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:241 | - |
| 0055 | 437 | ASM-Z0055.be | `453` | EQV | MB453 | PROCEDURE_LABEL | P453 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:242 | - |
| 0055 | 478 | ASM-Z0055.be | `571` | EQV | MB571 | PROCEDURE_LABEL | P571 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:247 | - |
| 0056 | 42 | ASM-Z0056.be | `220` | EQV | AM220 | PROCEDURE_LABEL | P220 | ГИПОТЕЗА | 9/1 | PROCEDURES-ASM.md:297 | - |
| 0056 | 52 | ASM-Z0056.be | `301` | EQV | AM301 | POINTER_TO_PROCEDURE | PTR301 | ГИПОТЕЗА | 0/3 | PROCEDURES-ASM.md:304 | - |
| 0056 | 65 | ASM-Z0056.be | `320` | EQV | AM320 | PROCEDURE_LABEL | P320 | ГИПОТЕЗА | 4/2 | PROCEDURES-ASM.md:306 | - |
| 0056 | 198 | ASM-Z0056.be | `60` | EQV | B260 | POINTER_TO_PROCEDURE | PTR60 | ГИПОТЕЗА | 0/1 | PROCEDURES-ASM.md:302 | - |
| 0056 | 438 | ASM-Z0056.be | `637` | EQV | DAT637 | PROCEDURE_LABEL | P637 | ПОДТВ | 1/0 | PROCEDURES-ASM.md:314 | - |
| 0056 | 464 | ASM-Z0056.be | `121` | EQV | MB121 | PROCEDURE_LABEL | P121 | ПОДТВ | 1/0 | PROCEDURES-ASM.md:292 | - |
| 0056 | 465 | ASM-Z0056.be | `130` | EQV | MB130 | PROCEDURE_LABEL | P130 | ГИПОТЕЗА | 4/2 | PROCEDURES-ASM.md:294 | - |
| 0056 | 466 | ASM-Z0056.be | `131` | EQV | MB131 | PROCEDURE_LABEL | P131 | ГИПОТЕЗА | 1/1 | PROCEDURES-ASM.md:295 | - |
| 0056 | 467 | ASM-Z0056.be | `133` | EQV | MB133 | PROCEDURE_LABEL | P133 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:296 | - |
| 0056 | 515 | ASM-Z0056.be | `357` | EQV | MB357 | PROCEDURE_LABEL | P357 | ПОДТВ | 1/0 | PROCEDURES-ASM.md:310 | - |
| 0057 | 44 | ASM-Z0057.be | `220` | EQV | AM220 | PROCEDURE_LABEL | P220 | ПОДТВ | 3/0 | PROCEDURES-ASM.md:360 | - |
| 0057 | 54 | ASM-Z0057.be | `300` | EQV | AM300 | PROCEDURE_LABEL | P300 | ГИПОТЕЗА | 2/1 | PROCEDURES-ASM.md:363 | - |
| 0057 | 56 | ASM-Z0057.be | `301` | EQV | AM301 | PROCEDURE_LABEL | P301 | ГИПОТЕЗА | 1/1 | PROCEDURES-ASM.md:364 | - |
| 0057 | 503 | ASM-Z0057.be | `637` | EQV | DAT637 | PROCEDURE_LABEL | P637 | ПОДТВ | 5/0 | PROCEDURES-ASM.md:370 | - |
| 0057 | 504 | ASM-Z0057.be | `641` | EQV | DAT641 | PROCEDURE_LABEL | P641 | ПОДТВ | 5/0 | PROCEDURES-ASM.md:371 | - |
| 0057 | 533 | ASM-Z0057.be | `20` | EQV | MB20 | PROCEDURE_LABEL | P20 | ГИПОТЕЗА | 3/1 | PROCEDURES-ASM.md:359 | - |
| 0057 | 553 | ASM-Z0057.be | `356` | EQV | MB356 | PROCEDURE_LABEL | P356 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:365 | - |
| 0057 | 554 | ASM-Z0057.be | `364` | EQV | MB364 | PROCEDURE_LABEL | P364 | ПОДТВ | 4/0 | PROCEDURES-ASM.md:366 | - |
| 0060 | 27 | ASM-Z0060.be | `126` | EQV | AM126 | PROCEDURE_LABEL | P126 | ПОДТВ | 4/0 | PROCEDURES-ASM.md:417 | - |
| 0060 | 38 | ASM-Z0060.be | `1655` | EQV | AM1655 | PROCEDURE_LABEL | P1655 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:432 | - |
| 0060 | 49 | ASM-Z0060.be | `220` | EQV | AM220 | PROCEDURE_LABEL | P220 | ПОДТВ | 10/0 | PROCEDURES-ASM.md:420 | - |
| 0060 | 61 | ASM-Z0060.be | `301` | EQV | AM301 | PROCEDURE_LABEL | P301 | ГИПОТЕЗА | 2/1 | PROCEDURES-ASM.md:424 | - |
| 0060 | 95 | ASM-Z0060.be | `64` | EQV | AM64 | POINTER_TO_PROCEDURE | PTR64 | ГИПОТЕЗА | 0/1 | PROCEDURES-ASM.md:415 | - |
| 0060 | 97 | ASM-Z0060.be | `65` | EQV | AM65 | POINTER_TO_PROCEDURE | PTR65 | ГИПОТЕЗА | 0/1 | PROCEDURES-ASM.md:416 | - |
| 0060 | 350 | ASM-Z0060.be | `641` | EQV | DAT641 | PROCEDURE_LABEL | P641 | ПОДТВ | 4/0 | PROCEDURES-ASM.md:429 | - |
| 0060 | 382 | ASM-Z0060.be | `20` | EQV | MB20 | POINTER_TO_PROCEDURE | PTR20 | ГИПОТЕЗА | 0/1 | PROCEDURES-ASM.md:413 | - |
| 0060 | 418 | ASM-Z0060.be | `614` | EQV | MB614 | PROCEDURE_LABEL | P614 | ПОДТВ | 2/0 | PROCEDURES-ASM.md:427 | - |
| 0144 | 67 | MBE-Z0144.be | `603` | EQV | B2603 | PROCEDURE_LABEL | P603 | ПОДТВ | 2/0 | PROCEDURES-B.md:222 | - |
| 0144 | 68 | MBE-Z0144.be | `605` | EQV | B2605 | PROCEDURE_LABEL | P605 | ГИПОТЕЗА | 1/7 | PROCEDURES-B.md:230 | - |
| 0144 | 233 | MBE-Z0144.be | `110` | EQV | MB110 | PROCEDURE_LABEL | P110 | ПОДТВ | 2/0 | PROCEDURES-B.md:191 | - |
| 0144 | 243 | MBE-Z0144.be | `1310` | EQV | MB1310 | PROCEDURE_LABEL | P1310 | ПОДТВ | 1/0 | PROCEDURES-B.md:322 | - |
| 0144 | 369 | MBE-Z0144.be | `1173` | EQV | PTR173 | PROCEDURE_LABEL | P1173 | ПОДТВ | 1/0 | PROCEDURES-B.md:276 | - |
| 0144 | 376 | MBE-Z0144.be | `734` | EQV | WRK734 | PROCEDURE_LABEL | P734 | ПОДТВ | 1/0 | PROCEDURES-B.md:258 | - |
| 0147 | 127 | MBE-Z0147.be | `301` | EQV | AM301 | PROCEDURE_LABEL | P301 | ПОДТВ | 1/0 | PROCEDURES-B.md:495 | - |
| 0147 | 141 | MBE-Z0147.be | `141` | EQV | B2141 | PROCEDURE_LABEL | P141 | ПОДТВ | 2/0 | PROCEDURES-B.md:459 | - |
| 0147 | 147 | MBE-Z0147.be | `6` | EQV | B26 | PROCEDURE_LABEL | P6 | ПОДТВ | 2/0 | PROCEDURES-B.md:411 | - |
| 0147 | 208 | MBE-Z0147.be | `125` | EQV | MB125 | PROCEDURE_LABEL | P125 | ПОДТВ | 2/0 | PROCEDURES-B.md:448 | - |
| 0147 | 217 | MBE-Z0147.be | `310` | EQV | MB310 | PROCEDURE_LABEL | P310 | ПОДТВ | 1/0 | PROCEDURES-B.md:502 | - |
| 0147 | 219 | MBE-Z0147.be | `324` | EQV | MB324 | PROCEDURE_LABEL | P324 | ГИПОТЕЗА | 1/1 | PROCEDURES-B.md:513 | - |
| 0147 | 220 | MBE-Z0147.be | `340` | EQV | MB340 | PROCEDURE_LABEL | P340 | ПОДТВ | 2/0 | PROCEDURES-B.md:524 | - |
| 0147 | 228 | MBE-Z0147.be | `40` | EQV | MB40 | PROCEDURE_LABEL | P40 | ПОДТВ | 3/0 | PROCEDURES-B.md:420 | - |
| 0147 | 233 | MBE-Z0147.be | `426` | EQV | MB426 | PROCEDURE_LABEL | P426 | ПОДТВ | 1/0 | PROCEDURES-B.md:535 | - |
| 0147 | 234 | MBE-Z0147.be | `436` | EQV | MB436 | PROCEDURE_LABEL | P436 | ПОДТВ | 2/0 | PROCEDURES-B.md:542 | - |
| 0147 | 236 | MBE-Z0147.be | `445` | EQV | MB445 | PROCEDURE_LABEL | P445 | ПОДТВ | 1/0 | PROCEDURES-B.md:549 | - |
| 0147 | 237 | MBE-Z0147.be | `453` | EQV | MB453 | PROCEDURE_LABEL | P453 | ПОДТВ | 2/0 | PROCEDURES-B.md:560 | - |
| 0147 | 242 | MBE-Z0147.be | `61` | EQV | MB61 | PROCEDURE_LABEL | P61 | ПОДТВ | 2/0 | PROCEDURES-B.md:429 | - |
| 0150 | 38 | MBE-Z0150.be | `116` | EQV | B2116 | PROCEDURE_LABEL | P116 | ГИПОТЕЗА | 2/2 | PROCEDURES-B.md:753 | - |
| 0150 | 86 | MBE-Z0150.be | `603` | EQV | B2603 | PROCEDURE_LABEL | P603 | ПОДТВ | 1/0 | PROCEDURES-B.md:816 | - |
| 0150 | 325 | MBE-Z0150.be | `426` | EQV | MB426 | PROCEDURE_LABEL | P426 | ПОДТВ | 2/0 | PROCEDURES-B.md:795 | - |
| 0150 | 340 | MBE-Z0150.be | `614` | EQV | MB614 | PROCEDURE_LABEL | P614 | ПОДТВ | 1/0 | PROCEDURES-B.md:827 | - |
| 0151 | 26 | MBE-Z0151.be | `1345` | EQV | B21345 | PROCEDURE_LABEL | P1345 | ПОДТВ | 2/0 | PROCEDURES-B.md:867 | - |
| 0161 | 23 | MBE-Z0161.be | `177` | EQV | AM177 | PROCEDURE_LABEL | P177 | ПОДТВ | 2/0 | PROCEDURES-B.md:1056 | - |
| 0161 | 37 | MBE-Z0161.be | `115` | EQV | B2115 | PROCEDURE_LABEL | P115 | ГИПОТЕЗА | 3/1 | PROCEDURES-B.md:1003 | - |
| 0161 | 42 | MBE-Z0161.be | `140` | EQV | B2140 | PROCEDURE_LABEL | P140 | ПОДТВ | 2/0 | PROCEDURES-B.md:1043 | - |
| 0161 | 107 | MBE-Z0161.be | `100` | EQV | MB100 | PROCEDURE_LABEL | P100 | ГИПОТЕЗА | 1/2 | PROCEDURES-B.md:981 | - |
| 0161 | 109 | MBE-Z0161.be | `105` | EQV | MB105 | PROCEDURE_LABEL | P105 | ПОДТВ | 3/0 | PROCEDURES-B.md:994 | - |
| 0161 | 124 | MBE-Z0161.be | `131` | EQV | MB131 | PROCEDURE_LABEL | P131 | ГИПОТЕЗА | 1/2 | PROCEDURES-B.md:1019 | - |
| 0161 | 129 | MBE-Z0161.be | `136` | EQV | MB136 | PROCEDURE_LABEL | P136 | ГИПОТЕЗА | 1/1 | PROCEDURES-B.md:1031 | - |
| 0544 | 254 | MBE2-Z0544.be | `1` | EQV | LOG001 | FALSE_POSITIVE | LOG001 | ГИПОТЕЗА | 0/5 | PROCEDURES-B2.md:125 | - |
| 0547 | 159 | MBE2-Z0547.be | `305` | EQV | AM305 | PROCEDURE_LABEL | P305 | ПОДТВ | 1/0 | PROCEDURES-B2.md:127 | - |
| 0547 | 253 | MBE2-Z0547.be | `440` | EQV | MB440 | PROCEDURE_LABEL | P440 | ПОДТВ | 1/0 | PROCEDURES-B2.md:128 | - |
| 0551 | 27 | MBE2-Z0551.be | `1345` | EQV | B21345 | PROCEDURE_LABEL | P1345 | ГИПОТЕЗА | 4/14 | PROCEDURES-B2.md:150 | - |
| 0552 | 31 | MBE2-Z0552.be | `1345` | EQV | B21345 | PROCEDURE_LABEL | P1345 | ГИПОТЕЗА | 1/1 | PROCEDURES-B2.md:158 | - |
| 0553 | 86 | MBE2-Z0553.be | `1` | EQV | LOG001 | FALSE_POSITIVE | LOG001 | ГИПОТЕЗА | 0/8 | PROCEDURES-B2.md:162 | - |
| 0555 | 370 | MBE2-Z0555.be | `1` | EQV | LOG001 | FALSE_POSITIVE | LOG001 | ГИПОТЕЗА | 0/5 | PROCEDURES-B2.md:164 | - |
| 0556 | 26 | MBE2-Z0556.be | `1` | EQV | LOG001 | FALSE_POSITIVE | LOG001 | ГИПОТЕЗА | 0/1 | PROCEDURES-B2.md:165 | - |
| 0557 | 290 | MBE2-Z0557.be | `1` | EQV | LOG001 | FALSE_POSITIVE | LOG001 | ГИПОТЕЗА | 0/2 | PROCEDURES-B2.md:166 | - |
| 0561 | 109 | MBE2-Z0561.be | `1` | EQV | LOG001 | FALSE_POSITIVE | LOG001 | ГИПОТЕЗА | 0/3 | PROCEDURES-B2.md:167 | - |
| 0562 | 121 | MBE2-Z0562.be | `1` | EQV | LOG001 | FALSE_POSITIVE | LOG001 | ГИПОТЕЗА | 0/4 | PROCEDURES-B2.md:168 | - |
| 0565 | 275 | MBE2-Z0565.be | `1` | EQV | LOG001 | FALSE_POSITIVE | LOG001 | ГИПОТЕЗА | 0/3 | PROCEDURES-B2.md:169 | - |
| 0566 | 27 | MBE2-Z0566.be | `1777` | EQV | B21777 | POINTER_TO_PROCEDURE | PTR177 | ГИПОТЕЗА | 0/1 | PROCEDURES-B2.md:170 | - |
| 0572 | 266 | MBE2-Z0572.be | `1` | EQV | LOG001 | FALSE_POSITIVE | LOG001 | ГИПОТЕЗА | 0/1 | PROCEDURES-B2.md:176 | - |
| 0576 | 42 | MBE2-Z0576.be | `1345` | EQV | B21345 | PROCEDURE_LABEL | P1345 | ГИПОТЕЗА | 1/9 | PROCEDURES-B2.md:184 | - |
| 0055 | 764 | ASM-Z0055.be | `20` | OPERAND | РЕГ | FALSE_POSITIVE | РЕГ | ГИПОТЕЗА | 0/0 | PROCEDURES-ASM.md:228 | OCT:20 LOCAL_20[ГИПОТЕЗА] CALL=0 ref=24 |
| 0055 | 2247 | ASM-Z0055.be | `4244` | OPERAND | Э71 | POINTER_TO_PROCEDURE | PTR424 | ГИПОТЕЗА | 0/0 | - | OCT:4244 MEM_4244_UNKNOWN[ГИПОТЕЗА] CALL=6 ref=12 |
| 0057 | 2101 | ASM-Z0057.be | `5433` | OPERAND | Э64 | POINTER_TO_PROCEDURE | PTR543 | ГИПОТЕЗА | 0/0 | - | OCT:5433 MEM_5433_UNKNOWN[ГИПОТЕЗА] CALL=2 ref=32 |
| 0154 | 867 | MBE-Z0154.be | `4114` | OPERAND | Э53 | POINTER_TO_PROCEDURE | PTR411 | ГИПОТЕЗА | 0/0 | - | OCT:4114 MEM_4114_UNKNOWN[ГИПОТЕЗА] CALL=44 ref=72 |
| 0161 | 1401 | MBE-Z0161.be | `105` | OPERAND | Э50 | POINTER_TO_PROCEDURE | PTR105 | ГИПОТЕЗА | 0/0 | PROCEDURES-B.md:994 | A00105 CODE_CHECK[ГИПОТЕЗА] CALL=0 ref=1 |
| 0161 | 1403 | MBE-Z0161.be | `115` | OPERAND | Э50 | POINTER_TO_PROCEDURE | PTR115 | ГИПОТЕЗА | 0/0 | PROCEDURES-B.md:1003 | OCT:115 LOCAL_115[ГИПОТЕЗА] CALL=0 ref=4 |
| 0161 | 1584 | MBE-Z0161.be | `105` | OPERAND | Э50 | POINTER_TO_PROCEDURE | PTR105 | ГИПОТЕЗА | 0/0 | PROCEDURES-B.md:994 | A00105 CODE_CHECK[ГИПОТЕЗА] CALL=0 ref=1 |
| 0554 | 848 | MBE2-Z0554.be | `4114` | OPERAND | Э53 | POINTER_TO_PROCEDURE | PTR411 | ГИПОТЕЗА | 0/0 | - | OCT:4114 MEM_4114_UNKNOWN[ГИПОТЕЗА] CALL=44 ref=72 |
| 0572 | 947 | MBE2-Z0572.be | `1` | OPERAND | РЖА | FALSE_POSITIVE | РЖА | ГИПОТЕЗА | 0/0 | PROCEDURES-B2.md:176 | A00001 CODE_ENTRY[ГИПОТЕЗА] CALL=0 ref=10 |
| 0573 | 1166 | MBE2-Z0573.be | `4621` | OPERAND | Э64 | POINTER_TO_PROCEDURE | PTR462 | ГИПОТЕЗА | 0/0 | - | OCT:4621 MEM_4621_UNKNOWN[ГИПОТЕЗА] CALL=3 ref=8 |
| 0060 | 521 | ASM-Z0060.be | `20` | KOND | 0000672707100020 | POINTER_TO_PROCEDURE | PTR20 | ГИПОТЕЗА | 0/0 | PROCEDURES-ASM.md:413 | - |

## 7. Точный список для fix-агента

Формат: `zone | line | old label | suggested new label`.
`P<адрес>` — процедура (<=6 символов); `PTR<адрес>` — указатель.
Перед применением каждой строки: `.bak`, затем
`bash tools/rebuild-zone.sh <zone> <MODE>` -> `1024/1024, 0 различий`.
Строки `FALSE_POSITIVE` в список НЕ входят. Для строк `OPERAND` и `KOND`
(старое значение — мнемоника или слово `В'...'`) fix-агент должен
вставить новую строку `PTR<адрес> ЭКВ '<адрес>'` после строки `М`
и заменить только операнд, как в `literal_labels.py --apply-zone`.

```
zone | line | old label | suggested new label
0055 | 40 | AM220 | P220
0055 | 41 | AM231 | P231
0055 | 48 | AM300 | P300
0055 | 51 | AM301 | P301
0055 | 69 | AM43 | P43
0055 | 160 | B2366 | P366
0055 | 355 | DAT643 | P643
0055 | 356 | DAT650 | P650
0055 | 382 | MB107 | P107
0055 | 385 | MB121 | P121
0055 | 387 | MB131 | P131
0055 | 389 | MB133 | P133
0055 | 394 | MB145 | P145
0055 | 398 | MB20 | P20
0055 | 404 | MB225 | P225
0055 | 415 | MB343 | P343
0055 | 425 | MB364 | P364
0055 | 429 | MB402 | P402
0055 | 430 | MB407 | P407
0055 | 437 | MB453 | P453
0055 | 478 | MB571 | P571
0056 | 42 | AM220 | P220
0056 | 52 | AM301 | PTR301
0056 | 65 | AM320 | P320
0056 | 198 | B260 | PTR60
0056 | 438 | DAT637 | P637
0056 | 464 | MB121 | P121
0056 | 465 | MB130 | P130
0056 | 466 | MB131 | P131
0056 | 467 | MB133 | P133
0056 | 515 | MB357 | P357
0057 | 44 | AM220 | P220
0057 | 54 | AM300 | P300
0057 | 56 | AM301 | P301
0057 | 503 | DAT637 | P637
0057 | 504 | DAT641 | P641
0057 | 533 | MB20 | P20
0057 | 553 | MB356 | P356
0057 | 554 | MB364 | P364
0060 | 27 | AM126 | P126
0060 | 38 | AM1655 | P1655
0060 | 49 | AM220 | P220
0060 | 61 | AM301 | P301
0060 | 95 | AM64 | PTR64
0060 | 97 | AM65 | PTR65
0060 | 350 | DAT641 | P641
0060 | 382 | MB20 | PTR20
0060 | 418 | MB614 | P614
0144 | 67 | B2603 | P603
0144 | 68 | B2605 | P605
0144 | 233 | MB110 | P110
0144 | 243 | MB1310 | P1310
0144 | 369 | PTR173 | P1173
0144 | 376 | WRK734 | P734
0147 | 127 | AM301 | P301
0147 | 141 | B2141 | P141
0147 | 147 | B26 | P6
0147 | 208 | MB125 | P125
0147 | 217 | MB310 | P310
0147 | 219 | MB324 | P324
0147 | 220 | MB340 | P340
0147 | 228 | MB40 | P40
0147 | 233 | MB426 | P426
0147 | 234 | MB436 | P436
0147 | 236 | MB445 | P445
0147 | 237 | MB453 | P453
0147 | 242 | MB61 | P61
0150 | 38 | B2116 | P116
0150 | 86 | B2603 | P603
0150 | 325 | MB426 | P426
0150 | 340 | MB614 | P614
0151 | 26 | B21345 | P1345
0161 | 23 | AM177 | P177
0161 | 37 | B2115 | P115
0161 | 42 | B2140 | P140
0161 | 107 | MB100 | P100
0161 | 109 | MB105 | P105
0161 | 124 | MB131 | P131
0161 | 129 | MB136 | P136
0547 | 159 | AM305 | P305
0547 | 253 | MB440 | P440
0551 | 27 | B21345 | P1345
0552 | 31 | B21345 | P1345
0566 | 27 | B21777 | PTR177
0576 | 42 | B21345 | P1345
0055 | 2247 | Э71 | PTR424
0057 | 2101 | Э64 | PTR543
0154 | 867 | Э53 | PTR411
0161 | 1401 | Э50 | PTR105
0161 | 1403 | Э50 | PTR115
0161 | 1584 | Э50 | PTR105
0554 | 848 | Э53 | PTR411
0573 | 1166 | Э64 | PTR462
0060 | 521 | 0000672707100020 | PTR20
```

## 8. Честные оговорки

1. Каталоги процедур — ГИПОТЕЗЫ по коду (исходника транслятора
   на диске нет). Факты: адреса, мнемоники, номера строк.
2. `A#####`/`D#####` и числовые адреса зона-локальны: одно число
   в зонах 0055 и 0147 — разные ячейки. Пересечение делалось
   только по `(зона, адрес)`, за исключением xref-ONLY кандидатов.
3. Счётчики xref дублируются между листингами; CALL=44 —
   не 44 машинных вызова, а 44 ссылки в 124 `.asm`.
4. Для `POINTER_TO_PROCEDURE` из xref без подтверждения той же
   зоной (:4114, :4244, :5433, :4621) требуется ручная проверка
   семантики экстракода `Э50/Э53/Э64/Э71`; это гипотезы.
5. Переименование `ЭКВ` меняет только текст: `ЭКВ` не порождает
   слово, байтовая идентичность зоны сохраняется при успешном
   `rebuild-zone.sh`.

