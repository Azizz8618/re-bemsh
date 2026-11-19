# Смежные проекты: что переиспользуем

Изучены `monitor80-re` и `re-dispak` (субагент, 19.11.2026). Остальные смежные
репозитории (`re-siprod`, `besm-crypto`, `dtran`, `dispak/tests`) — в отдельном
отчёте. Файлы исходных репозиториев не изменялись.

## 1. Карта смежных репозиториев

| Репозиторий | Что даёт для re-bemsh |
|---|---|
| `~/Yandex.Disk/monitor80-re` | среда, в которой работает МВЕ60: модули `star%`, `ficmem%`, `ttable%`, `print8`, `givcall%`, `ident6`, `execut`, `givtran%`; точный workflow `.orig`/`.dis`/`.diff`; готовый `tools/debemsh.sh` |
| `~/Yandex.Disk/re-dispak` | корпус листингов `testdks/mbe60_*`, naming `G<зона>-L<длина>` / `S…`, алгоритм `verify.pl`, скрипты `asm.pl`/`rvs.pl`/`zongp.pl` |
| `~/Yandex.Disk/simh/BESM6/scripts` | `disbesm_extract.sh`, `disbesm_verify.sh` — скопированы в `tools/` |
| `~/Yandex.Disk/monitor80-re/matching` | `compare_shifted.py`, `bin_to_octal.py`, `compare_octals.py` — скопированы в `tools/` |

## 2. Конвенции monitor80-re (принимаем)

Форматы: `.asm` (DTRAN/ASSEM), `.masm` (МАДЛЕН), `.dtr` (описание модуля),
`.sym` (таблица символов), `.orig` (дизассембль эталона с диска), `.dis`
(дизассембль реконструкции), `.diff` (пустой маркер успешной сверки).

Проверка (`permanent/Makefile`, `inputcal/Makefile`):

```make
%.diff: %.dis %.orig
	diff -C 3 $^ && touch $@
%.orig:
	../tools/disas.pl $(basename $@)
```

```bash
cd permanent && export WORKVOL=80 && make
cd inputcal && export WORKVOL=80 && make cmp.out
diff -C 3 modname.orig modname.dis   # пустой ⇒ модуль восстановлен верно
```

Второй вариант (`inputcal`) — `gold.bin` (эталон с тома) vs `silver.bin`
(собранный оверлей), сравнение через `../tools/cmp.sh`; дамп → `.bin.dis`
через `disbesm6 -a1760 -e1770 -ninputcal.sym $< > $@`.

Имя модуля: `_` и `%` в имени файла ↔ `/` и `*` в имени модуля библиотеки
(`star%.masm` → `STAR*`, `ficmem%.asm` → `FICMEM*`).

## 3. Модули Монитор-80, релевантные МВЕ60 / МС ДУБНА

| Модуль | Entry / роль | Файл |
|---|---|---|
| `STAR*` | `CALL:` (ст. 204–214): `M14,VTM,MONCARD*+1` → `M13,VJM,IDENT6` → `ATX,MAIN*` → `UJ,CHECKMORE`; `GIV76:` → `GIVCALL*`; `EXECUTE:` → `EXECUT` → `MONITOR*+3`; таблица `SWITCH` (`*MAIN`→`CALL`, `*CALL`→`GIV76`, `*EXECU`→`EXECUTE`) | `permanent/star%.masm` |
| `FICMEM*` | `FULLMEMO:` (12), `YESMEMOR:` (17) — резервирование фиксированной памяти; вызывается `*CALL UESMEMORY` | `permanent/ficmem%.asm` |
| `TTABLE*` | `,ISO,6Н*BEMSH / ,TEXT,8НBEMSH*` — карта `*BEMSH` выбирает модуль `BEMSH*` | `permanent/ttable%.asm` |
| `PRINT8*` | `PRINT8:NAME`, `PRINT80:,ENTRY,` (17); внешние `MON*ITOR`, `SAVE*HID`, `ОН*`, `PLBEG`, `ISO/GOST`, `PLCLO`, `ASAVE*`, `FOR*ALL` — это `PRINT8 01205` из `*EXECUTE` МВЕ60 | `permanent/print8.asm` |
| `GIVCALL*` | разбор карт `*PASCAL`/`OVERLAY`/`EXECUTE`/`OCATALOG`/`SOVCATAL` | `permanent/givcall%.asm` |
| `IDENT6` | распознавание 6-символьного имени карты | `permanent/ident6.asm` |
| `EXECUT` | сокращённый для Монитор-80, переход на загрузку | `permanent/execut.asm` |
| `GIVTRAN*` / `SETTRAN*` | выбор транслятора по `*REGIM`, таблица `TTABLE*` | `permanent/givtran%.asm` |

`tools/debemsh.sh` — готовый шаблон прогона `*BEMSH` через `dispak`:

```
шифр 419900зс5^ / dis 67($WORKVOL-wr)^ / еев1а3 / *name / *bemsh /
inp$$$ / <тело> / eoi$$$ / trn$$$ / 0-0 / бтмалф / end$$$ /
*libra:2 / *call dtran($name) / *stand / *super / *edit / *r:1 / *w:67 / *ee / *end file
```

## 4. Конвенции re-dispak и алгоритм verify.pl

Именование дампов: `G0401-L1`, `S0621-L4`, размер строго `6144 × L` байт
(1024 слова × 6 байт на зону). `G` = gold (физический том), `S` = silver
(реконструкция на рабочем томе 2222).

`rvs.src`: `мдл <имя> … зонгп 43<ZZZZ> <L>` — модуль участвует в верификации;
без `зонгп` — не участвует. `sect.src`: `0401 0123` (сектор = 1536 байт = 256 слов).
`modlist.src`: «BEMSH does not seem to honor the length in ZONMOD…».

`verify.pl` (пошагово): читает `rvs.src` → пары `(зона, длина, имя)`; том эталона
`oct($s) < 512 ? 2053 : 2048`; `$gold`=disk dump если нет/размер неверен, `$silver`
пересоздаётся всегда; `cmp -b` по секторам (`-i <n*1536> -n 1536`) либо по всей
зоне; при различии считает `cmp -l | wc -l`, первый байт → `зона = oct(G)+int(N/6144)`,
`слово = int((N%6144)/6)`; печать `First difference in zone %04o, word %04o`.

**Нюанс адресов:** `besmtool` парсит число по base 0: `00401` = восьмеричное,
`95` = десятичное; оба дают зону `0137₈`. В `re-dispak` и `serp_findzone.py`
используют **ведущий ноль** (`--start=0$s`) — safer convention; зафиксировать
в `AGENTS.md`. `disbesm_extract.sh` тоже паддит через `printf '%06o'`.

## 5. Правила, которые переносим в re-bemsh

Из `re-dispak/AGENTS.md`:

> «ВСЕГДА СВЕРЯЙ СВОИ ВЫВОДЫ С ТЕКСТОМ … СТАРАЙСЯ НЕ ДОМЫСЛИВАТ!!! ПРИ ДЕФИЦИТЕ ИНФОРМАЦИИ СООБЩИ ОБ ЭТОМ.»

> «КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО БЕЗ ПРЯМОГО УКАЗАНИЯ ОПЕРАТОРА: УДАЛЯТЬ ВНЕШНИЕ ССЫЛКИ …; УДАЛЯТЬ МЕТКИ И ПРОЦЕДУРЫ; … МОДИФИЦИРОВАТЬ ИСХОДНИК ЛЮБЫМ ОБРАЗОМ. РАЗРЕШЕНО ТОЛЬКО: ДОБАВЛЯТЬ КОММЕНТАРИИ ПОСЛЕ ЗАПЯТОЙ …»

> «МОНОШИРИННЫЙ ШРИФТ, ШИРИНА СТРОКИ <=60 СИМВОЛОВ …»; «ДЛИНА СТРОКИ КОММЕНТАРИЯ НЕ БОЛЕЕ 55 СИМВОЛОВ, ПЕРЕНОС СО ЗВЕЗДОЧКОЙ "*".»

> «В шапке каждой процедуры: ИМЯ … ВХОД … ВЫХОД … ИСПОЛЬЗУЕТ: РАБОЧИЕ РЕГИСТРЫ М1-М17; ВЫЗЫВАЕТ: ДРУГИЕ ПРОЦЕДУРЫ.»

Из `.clinerules`: «ГИПОТЕЗА → ЭКСПЕРИМЕНТ → ВЫВОД. Не наоборот. Запрещено: Документировать до проверки». «ВСЕГДА создавай .bak ПЕРЕД изменением».

Из `monitor80-re/.clinerules`: «Не коммитить без разрешения пользователя; Не пушить без явного указания»; «Не создавать файлы в корне проекта (кроме README.md, AGENTS.md, .clinerules)».

## 6. Скопированные утилиты (`tools/`)

| Файл | Назначение |
|---|---|
| `disbesm_extract.sh` | `<disk> <zone> <length> [-o file]`; имя `G<зона>-L<длина>`; контроль `L*1024*6` байт |
| `disbesm_verify.sh` | побайтовая сверка, локализация `зона.слово` (oct), `--disasm` с diff |
| `compare_shifted.py` | поиск лучшего смещения шаблона (для 06/78 ↔ 12/77, сдвиг `+0400₈`) |
| `bin_to_octal.py` | 6 байт → 16 восьмеричных цифр |
| `compare_octals.py` | построчное сравнение слов, `*` = wildcard |
