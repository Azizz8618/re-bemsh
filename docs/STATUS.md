# Статус проекта re-bemsh (одна страница)

Дата: 19.11.2026. Все выводы ниже сверены с живыми командами.
Подробности — [FINAL-REPORT.md](FINAL-REPORT.md),
[ROADMAP.md](ROADMAP.md), [REBUILD-ALL.md](../analysis/REBUILD-ALL.md).

## Проверки: команда → ожидаемый результат

| Команда | Ожидаемый результат (проверено 19.11.2026) |
|---|---|
| `make stage0` | `PASS` ×8; md5 зон `0137–0177` = `2f503f5b8f8fb6ad12632fed6f8cf17f` |
| `make check-all` | `=== check-all: все проверки пройдены ===` (47 unit-тест, `OK`) |
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

Все 69 зон собраны семантически; в `0545:0` и `0556:12` оставлено по одному сырому слову `КОНД` (см. `docs/RAW-RECOVERY.md`).

## Фазы

| Фаза | Статус |
|---|---|
| 0–7 | ГОТОВО (извлечение, аннотация, верификация 69/69) |
| A1–A3 | ГОТОВО (69 `.be`, 0 отличий) |
| B | ГОТОВО (2 ячейки ГС на макрос; `[TAG\|VAL]` не подтверждена) |
| C | ГОТОВО (0154 → `02000₈`, breakpoint сработал) |
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
