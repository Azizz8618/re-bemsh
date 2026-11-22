# Статус проекта re-bemsh (одна страница)

Дата: 22.11.2026. Все выводы ниже сверены с живыми командами.
Подробности — [FINAL-REPORT.md](FINAL-REPORT.md),
[ROADMAP.md](ROADMAP.md), [REBUILD-ALL.md](../analysis/REBUILD-ALL.md).
Новые отчёты: `analysis/ARAP-*.md`, `analysis/PASSES-*.md`,
`analysis/REG-DYN-*.md`, `analysis/MACRO-OPS-*.md`,
`analysis/MACRO-VNESHN-MECH.md`, `MACRO-VS-FLAG.md`,
`MACRO-DK-EVNESH.md`, `GS-CELLS-DIRECT.md`,
`MACHINE-PAGE6-ZONE.md`, `GS-WORD-FIELDS.md`, `VS-FLAG-CELL.md`,
`ARAP-CARD-COMPARE.md`, `LOADER-064063.md`, `ARAP-PF-EXPANSION.md`, `GOST-BYTE-FORMULA.md`,
`GS-TAG-06445.md`, `ARAP-DISPATCH-06452.md`,
`MONITOR80-LOADER-SRC.md`, `PF00-B2-BRANCH.md`,
`MACHINE-ARAP-FINAL.md`, `GS-TABLE-0147-0561.md`,
`GS-CONSTANTS.md`, `ARAP-DESCRIPTOR-077143.md`,
`B2-ARCHIVE-DYN.md`, `HIGH-CORE-076600.md`, `GOST-TABLE-DETAILS.md`,
`MACRO-RECORD-25.md`, `DESCRIPTOR-WRITER.md`,
`Z0565-ROLE.md`, `HIGH-CORE-LOOP-76600.md`, `ARAP-CODES-40-01.md`,
`LOOP-76600-BRANCHES.md`, `D01167-WRITER.md`,
`CARD-074021.md`, `TEXT-POOL-06445.md`, `CODE-01-EXACT.md`,
`D01167-NEGATIVE.md`, `CARD-ETALONS.md`,
`POOL-DESCRIPTOR-FIELDS.md`, `RLE-CONSUMER.md`,
`FILLER-44-40.md`, `DESCRIPTOR-0005.md`, `LITERALS-ABSOLUTE-PROOF.md`,
`JUMP-TARGET-DYNAMIC.md`, `PROC-LABEL-INVENTORY.md`, `ZONE-BASE-MAP.md`,
`PROC-LABEL-SCOPE-STATIC.md`, `PROC-LABEL-SCOPE-DYN.md`,
`PROC-LABEL-SCHEME.md`.

**Последние находки 22.11** (сводка: `FINAL-REPORT.md` §7 п.14-18):
GOST→БЭСМ-таблица 0147.0561; 0x40 = пробел, 0x01 = счётчик серии
(5×0x40 → 01..05); потребитель RLE 014011-014014 → буфер 012000+;
0x44 = `$`-паддинг, не пустая колонка; 06445 = 0o2000+L, +0o31 есть
статическая константа; дескриптор [2010|N|0005|200K]; writer
D01167 кончается `asn 136` (знак стёрт); 0565 = код B2 (151 CALL,
в опытах не выбирается); старшая память 076600/077xxx. Механика
макрокода НЕ объявлена разобранной до конца.

## Проверки: команда → ожидаемый результат

| Команда | Ожидаемый результат (проверено 19.11.2026) |
|---|---|
| `make stage0` | `PASS` ×8; md5 зон `0137–0177` = `2f503f5b8f8fb6ad12632fed6f8cf17f` |
| `make check-all` | `=== check-all: все проверки пройдены ===` (47 unit-тест, `OK`; сверено 22.11.2026) |
| Финальная сводка | `docs/FINAL-REPORT.md` §7 п.1-18: АРАП-архив, 3 прохода, регистры, все 37 макрокоманд, находки 22.11 |
| `make rebuild-check` | `rebuild-check: OK (RESULT: PASS, 1024/1024)` — зона 0137 |
| `make rebuild-all` | `найдено=69 PASS=69 FAIL=0` — все `.be` собираются в 0 отличий |
| `make unittest` | `Ran 47 tests … OK` |
| `grep -c PASS analysis/REBUILD-ALL.md` | `71` (69 PASS + 2 шапки) |
| `ls bemsh/*.be \| wc -l` | `69` |
| `md5sum /usr/local/share/besm6/2348` | `2739b7a25a07d82fc20ba034a85ae661` (не инвариант) |
| md5 зон `0137–0177` из `make stage0` | `2f503f5b8f8fb6ad12632fed6f8cf17f` (инвариант) |

## Реконструкция (Фаза A3)

| Режим | Зон | Слов | Отличий |
|---|---:|---:|---:|
| PASS (семантика) | 69 | 70688 | 0 |
| PASS-RAW (полностью сырой дамп) | 0 | 0 | — |
| FAIL | 0 | 0 | — |
| **ИТОГО** | **69** | **70688** | **0** |

Все 69 зон собраны семантически; в `0556` оставлено 2 слова `КОНД` (12 и 14:
`УИ`, opcode 140 вне таблицы OPS). `0545:0` переведена в семантику.
См. `docs/RAW-RECOVERY.md`.

## Фазы

| Фаза | Статус |
|---|---|
| 0–7 | ГОТОВО (извлечение, аннотация, верификация 69/69) |
| A1–A3 | ГОТОВО (69 `.be`, 0 отличий) |
| B | ГОТОВО (2 ячейки ГС на макрос; `[TAG\|VAL]` не подтверждена) |
| C | ГОТОВО (+ уточнено 22.11): 0154 и 0170 — оверлей по `02000₈`; `01311: *70 1144` → Э70 `ddio()`, зона 0170; 0137 не грузилась. См. `analysis/PASSES-OVERLAY-MECH.md` |
| D | ГОТОВО: 50 зон (7 + 43 из §4.2b, 4 ASM — ЭКВ уже в LABELS-ASM-BE); 0-diff (см. `docs/PHASE-D-CONTINUATION.md`) |
| E | ГОТОВО: `make check-all` — stage0 PASS, rebuild-check 1024/1024, verify FAIL=0, unittest 47 OK |

## Remotes

```
origin      git@github.com:Azizz8618/re-bemsh.git          (fetch/push)
sourcecraft ssh://ssh.sourcecraft.dev/al-azizz/re-bemsh.git (fetch/push)
```

Последние коммиты (`git log --oneline -3`):

```
bfb37ff Reconstruct all 69 zones byte-identically (phases A1-A3)
ea59bed Add detailed forward plan A-E for full-zone reconstruction
020ac1f Reconstruct zone 0137 byte-identically and analyze macro internals
```

## Правило: read-only образы

- **Эталонные образы не изменять.** `/usr/local/share/besm6/*` — только
  `besmtool dump/view/search` и чтение; все эксперименты — на **копиях**
  в `/tmp/.private/azizz/` с выставленным `BESM6_PATH`.
- `make rebuild-*` и скрипты имеют guard: отказ работать, если каталог
  образов настоящий (exit 3). В Makefile используется `env -u BESM6_PATH`.
- Инвариант — md5 зон `2f503f5b…`, а не md5 всего файла: том используется
  другими проектами для PERSO-записи. См. [IMAGES.md](IMAGES.md).
- **Коммиты — только с разрешения, push — только по явной инструкции**
  (`AGENTS.md`). В обе ветки (GitHub и sourcecraft) — по указанию оператора.
