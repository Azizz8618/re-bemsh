# Статические тесты загрузчика 0137-0143

Файл: `tools/tests/test_loader_zones_static.py`.
Команда: `python3 -m unittest
tools/tests/test_loader_zones_static.py -v`.
Результат: 42 теста, PASS, SKIP = 0.
`make unittest`: 406 тестов, OK, SKIP = 0.

## 1. Метод

Статические тесты читают файлы через `pathlib`.
Внешние программы здесь не нужны.
Опциональный класс требует `besmtool` в PATH и
наличие образов 2048, 2148, 2248 в `BESM6_PATH`.
Вызов только один: `besmtool dump <disk>
--start=<зона> --length=<N> --to-file=-`.
Дамп идёт в stdout, записи в каталог образов нет.
Хвост stdout (`Writing N zones...`) отделён по
длине `N * 6144` и проверен.
При отсутствии образа или инструмента класс
пропускается через `skipUnless`.

## 2. Таблица фактов

В колонке «тест» короткий ИД; полные имена в §3.

| факт | источник | тест | статус |
|---|---|---|---|
| 5 зон загрузчика | GUIDE §loader | F1 | PASS |
| 5 gold-файлов есть | gold/ | G1 | PASS |
| каждый 6144 B | gold/ | G2 | PASS |
| склейка 202752 B | gold/ | G3 | PASS |
| файлы в manifest | manifest.sha256 | G4 | PASS |
| код 0000-0004 | Z0137.md | A1 | PASS |
| `зп '70000'`, `рег '3554'` | Z0137.md | A2 | PASS |
| обрыв `пб (М3)` | Z0137.md, dis | A3 | PASS |
| байты KOI-7 0057-0121 | Z0137.md, gold | A4 | PASS |
| мнемоники в .be | bemsh/ | A5 | PASS |
| 51 мнемоника (doc) | Z0137.md | A6 | PASS |
| 8 код-слов 0140 | Z0140.md, dis | B1 | PASS |
| CALL 34562, exit 77430 | Z0140.md, dis | B2 | PASS |
| таблица '150', 64-23 | Z0140.md, dis | B3 | PASS |
| 3 код-слова 0141 | Z0141.md, dis | C1 | PASS |
| 2 CALL 14342/40540 | Z0141.md, dis | C2 | PASS |
| exit `пб '77260'` | Z0141.md, dis | C3 | PASS |
| префикс 7400000X | Z0141.md, gold | C4 | PASS |
| штампа нет 0141 | Z0141.md, dis | C5 | PASS |
| 18 код-слов 0142 | Z0142.md, dis | D1 | PASS |
| 2 CALL 34417/34562 | Z0142.md, dis | D2 | PASS |
| база '36436' x3 | Z0142.md, gold | D3 | PASS |
| префикс 00430016 | Z0142.md, gold | D4 | PASS |
| return `пб (М16)` | Z0142.md, dis | D5 | PASS |
| штампа нет 0142 | Z0142.md, dis | D6 | PASS |
| 16 код-слов 0143 | Z0143.md, dis | E1 | PASS |
| CALL 4231 + 34562 | Z0143.md, dis | E2 | PASS |
| exit `пб '76720'` | Z0143.md, dis | E3 | PASS |
| KOI-7 фрагмент | Z0143.md, gold | E4 | PASS |
| штампа нет 0143 | Z0143.md, dis | E5 | PASS |
| общий CALL 34562 | Z0140/42/43 | F2 | PASS |
| 34562 нет в 0141 | Z0141.md | F3 | PASS |
| штампа нет в 0137-43 | Z0137-43 | F4 | PASS |
| штамп 0147.1315 | Z0147.md, dis | F5 | PASS |
| md5 склейки 2048 | reloc.md §2 | V1 | PASS |
| md5 склейки 2148 | reloc.md §2 | V2 | PASS |
| md5 склейки 2248 | reloc.md §2 | V3 | PASS |
| длина 202752 | reloc.md §2 | V4 | PASS |
| 2148 == 2248 | reloc.md §2 | V5 | PASS |
| 5 зон ~5300 B | reloc.md §3 | V6 | PASS |
| ядро: 147/151/176 | reloc.md §3 | V7 | PASS |
| gold == том 2048 | gold/, 2048 | V8 | PASS |

## 3. Полные имена тестов

G1 TestGoldFiles.five_loader_gold_files_exist
G2 TestGoldFiles.each_loader_gold_is_6144_bytes
G3 TestGoldFiles.full_concat_is_33_zones
G4 TestGoldFiles.manifest_lists_all_five_gold_zones
A1 TestZone0137.init_code_is_five_words
A2 TestZone0137.syscall_and_const_constants
A3 TestZone0137.break_at_m3
A4 TestZone0137.koi7_table_bytes_in_gold
A5 TestZone0137.koi7_mnemonics_in_be
A6 TestZone0137.doc_states_51_mnemonics
B1 TestZone0140.eight_code_words
B2 TestZone0140.common_call_and_exit
B3 TestZone0140.passport_table_words
C1 TestZone0141.three_code_words
C2 TestZone0141.two_calls_and_targets
C3 TestZone0141.exit_77260
C4 TestZone0141.descriptor_prefix_7400000x
C5 TestZone0141.no_version_stamp
D1 TestZone0142.eighteen_code_words
D2 TestZone0142.two_calls_and_targets
D3 TestZone0142.reloc_base_36436_three_times
D4 TestZone0142.descriptor_prefix_00430016
D5 TestZone0142.return_via_m16
D6 TestZone0142.no_version_stamp
E1 TestZone0143.sixteen_code_words
E2 TestZone0143.two_calls_including_common
E3 TestZone0143.exit_76720
E4 TestZone0143.koi7_fragment_bytes
E5 TestZone0143.no_version_stamp
F1 TestLoaderCommon.loader_is_five_zones
F2 TestLoaderCommon.common_call_34562_in_0140_0142_0143
F3 TestLoaderCommon.common_call_absent_in_0141
F4 TestLoaderCommon.no_stamp_in_any_loader_zone
F5 TestLoaderCommon.version_stamp_in_kernel_0147
V1 TestReferenceVolumes.concat_md5_2048
V2 TestReferenceVolumes.concat_md5_2148
V3 TestReferenceVolumes.concat_md5_2248
V4 TestReferenceVolumes.concat_length_202752
V5 TestReferenceVolumes.2148_and_2248_concat_identical
V6 TestReferenceVolumes.loader_zones_differ_about_5300_bytes
V7 TestReferenceVolumes.kernel_diff_exceptions_match_doc
V8 TestReferenceVolumes.gold_loader_zones_match_2048

Имена в §3 даны без префикса `test_`.
Все 42 метода реально выполнялись, не SKIP.

## 4. Почему не чистый Python--read

Проверены два варианта смещения: `зона * 6144`
и `(зона + 4) * 6144`. Оба дают md5, отличные от
`2f503f5b...`. Эталоны используют дескрипторную
(chain) раскладку, поэтому фиксированного
сдвига нет. Проверка через `besmtool dump`
подтвердила: все 5 gold-зон побайтово равны
дампам тома 2048. Поэтому опциональные тесты
читают тома только через `besmtool dump`.

## 5. Оговорки

1. Тесты проверяют документированные факты и
   байты/строки в файлах, НЕ семантику загрузчика.
2. Число 51 мнемоника (A6) прочитано из текста
   документа, а не получено декодированием
   всех 35 перечисленных KOI-7-слов.
3. Префикс `00430016` в задаче отнесён к 0141;
   по `Z0142.md` он относится к 0142 (D4).
   У 0141 префикс `7400000X` (C4).
4. «Ядро 0144-0177 идентично» уточнено:
   отличаются 0147 (1977 B), 0151 (3 B),
   0176 (1 B), остальные зоны равны (V7).
5. Часть опциональных проверок пересекается с
   `tools/tests/test_loader_reloc.py`. Новый файл
   самостоятелен и не импортирует его модули.
6. Образы не изменялись. Выполнялось только
   чтение и дамп в stdout.

## 6. Уверенность

ВЫСОКАЯ для A1-A4, B1-B3, C1-C4, D1-D5,
E1-E4, F1-F5, G1-G4, V1-V8: факты сверены
с dis-, gold- и .be-файлами и эталонами томов.
СРЕДНЯЯ для A5, A6, C5, D6, E5: проверка
отрицательная или основанная на тексте docs.
Общая уверенность в корректности тестов:
ВЫСОКАЯ, в полноте покрытия загрузчика: НИЗКАЯ.
