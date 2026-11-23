# TEST-VERIFICATION-REPORT

Дата: 2026-11-23
Репозиторий: /home/azizz/Yandex.Disk/re-bemsh
Режим: только чтение + новый отчёт. Коммитов и push нет.

## ФАКТ

### 1. Наличие ожидаемых файлов

Все 4 скрипта и все 4 теста обнаружены:

- tools/module_call_graph.py, тест 14
- tools/module_call_trace.py, тест 11
- tools/symbol_parser_probe.py, тест 10
- tools/listing_probe.py, тест 16

### 2. Матрица прогонов (финальная, устоявшееся дерево)

| target               | res  | count | time |
|----------------------|------|-------|------|
| unittest discover    | OK   | 316   | 88s  |
| make test-core       | OK   | 56    | 7s   |
| make test-integration| OK   | 260   | 93s  |
| make test-all        | OK   | 316   | 92s  |
| make test-verify     | PASS | -     | 4s   |
| make check-all       | OK   | 316   | 71s  |

Все exit code = 0. Строк FAILED, FAIL:, ERROR: в логах нет.

test-verify: 2 x RESULT: PASS, rebuild-check 1024/1024,
roundtrip FAIL=0.
check-all: stage0 + rebuild-check + verify + unittest,
финальная строка "все проверки пройдены".

### 3. Подтверждение общего количества

- baseline до новых файлов: 265, OK
- новых тестов: 14 + 11 + 10 + 16 = 51
- 265 + 51 = 316
- core + integration: 56 + 260 = 316

Три независимых счётчика сходятся на 316.

### 4. Отказы

Финальный прогон: отказов нет.

Промежуточный прогон (файлы ещё правились агентами):
один отказ в make test-integration, exit=2.

  FAIL: test_call_and_link_records
  tools/tests/test_module_call_graph.py:48
  AssertionError: Lists differ:
  ['internal','external','indirect','indirect','branch']
  !=
  ['internal','external','indirect','indirect','branch',
   'internal']
  Second list contains 1 additional elements.

Владелец: агент, писавший tools/module_call_graph.py и
tools/tests/test_module_call_graph.py (статический граф
вызовов). Повторный прогон после стабилизации:
Ran 14 tests, OK. Отказ был следствием правки файлов
во время теста, а не дефекта готового кода.

### 5. Проверка новых CLI

Проверены --help и один реальный вызов каждого.
Все exit code = 0, stderr пуст.

| CLI                    | help | real | выход |
|------------------------|------|------|-------|
| module_call_graph.py   | 0    | 0    | 6105b |
| module_call_trace.py   | 0    | 0    | 3834b |
| symbol_parser_probe.py | 0    | 0    | 56086b|
| listing_probe.py       | 0    | 0    | 43964b|

Реальные входы (без эмулятора):

- module_call_graph.py --format text
  старт: "СТАТИЧЕСКИЙ ГРАФ ВЫЗОВОВ 69 ЗОН"
- module_call_trace.py /tmp/.private/azizz/arap-dyn/
  B-explore.err --top 5 --format json
  lines=5141914, 37s
- symbol_parser_probe.py bemsh/MBE-Z0137.be --format json
- listing_probe.py /tmp/.private/azizz/rebuild-all/0137/
  listing.out --format json

### 6. Окружение

Признаков tmpfs ENOSPC нет. После всех прогонов:
/tmp 2,3G из 7,8G (30%), 5,5G свободно;
inodes 5937 из 2031071. /dev/shm 2,0G из 7,8G.

### 7. Итог

Система тестирования репозитория здорова:
все 6 target зелёные, 316 тестов, ресборки PASS.

## ГИПОТЕЗА

- Причиной промежуточного отказа была запись файлов
  агентами во время прогона: метки времени менялись
  в интервале 07:10...07:15, после 07:15 файлы не
  менялись и отказ не воспроизвёлся.
- Ускорение module_call_trace.py с 84s до 37s
  связано с оптимизацией потока чтения агентом.

## НЕ ИЗВЕСТНО

- Идентификаторы четырёх агентов: владельцы указаны
  по именам файлов, а не по ID.
- Стабильность результатов при параллельной записи
  агентов не гарантирована: финальный прогон сделан
  после прекращения правок.
- Причины расхождения --zone 0137 (adjacency пуст)
  с общим графом не разбирались: это не тест-регресс.
