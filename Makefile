# Makefile — воспроизведение docs/PLAN.md (фазы 0-7).
# Эталонные образы томов НЕ изменяются: только чтение и извлечение в /tmp.
# tools/disbesm_extract.sh ожидает ВОСЬМЕРИЧНЫЕ номера зон (см. AGENTS.md).
# $$z в рецептах = восьмеричная строка вида 0137 / 0540 (printf '%04o').

SHELL := /usr/bin/env bash
DISK  ?= 2348
V     := tools/disbesm_verify.sh

.PHONY: stage0 inventory dis xref verify versions check clean annotate procedures variables \
        rebuild-zone rebuild-all rebuild-check check-all unittest

# Фаза 0 — проверка конфигурации инструментов и образа.
stage0:
	bash tools/stage0-check.sh

# Фаза 1 — инвентаризация (каталог, поиск штампов, «живые» зоны).
# zones.src уже создан в Phase 0 и здесь не перезаписывается.
inventory:
	mkdir -p docs
	besmtool view $(DISK) --start=0 --length=16 --encoding=k > docs/catalog_zone0000.txt
	besmtool search $(DISK) 'ТРАНСЛЯТОР' > docs/search_translator.txt
	for s in 'ТРАНСЛЯТОР' 'МАКРО-БЕМШ' 'ВЕР.06/78' 'ВАР.12/77'; do \
	  besmtool search $(DISK) "$$s"; \
	done
	besmtool view $(DISK) --start=95 --length=1
	besmtool view $(DISK) --start=127 --length=1
	besmtool view $(DISK) --start=352 --length=1
	besmtool view $(DISK) --start=383 --length=1

# Фазы 2+3 — извлечение зон хелпером (ВОСЬМЕРИЧНЫЕ аргументы) и дизассембль.
dis:
	mkdir -p gold dis sym
	for d in 45 46 47 48; do \
	  z=$$(printf '%04o' $$d); \
	  tools/disbesm_extract.sh $(DISK) $$z 1 -o gold/ASM-Z$$z-L1.bin; \
	done
	for d in $$(seq 95 127); do \
	  z=$$(printf '%04o' $$d); \
	  tools/disbesm_extract.sh $(DISK) $$z 1 -o gold/MBE-Z$$z-L1.bin; \
	done
	for d in $$(seq 352 383); do \
	  z=$$(printf '%04o' $$d); \
	  tools/disbesm_extract.sh $(DISK) $$z 1 -o gold/MBE2-Z$$z-L1.bin; \
	done
	for f in gold/*.bin; do stat -c '%s %n' "$$f"; done
	(cd gold && sha256sum *.bin | sed 's|  |  gold/|') > manifest.sha256
	sha256sum -c manifest.sha256
	: > gold/MBE-full.bin
	for d in $$(seq 95 127); do \
	  z=$$(printf '%04o' $$d); \
	  cat gold/MBE-Z$$z-L1.bin >> gold/MBE-full.bin; \
	done
	sha256sum gold/MBE-full.bin >> manifest.sha256
	# Только по одной зоне: MBE-full.bin = 33792 слова > лимит 32768, disbesm6 падает
	for f in gold/*-Z*-L1.bin; do \
	  n=$$(basename "$$f" .bin); \
	  disbesm6 -a0 -e0 "$$f" > "dis/$$n.asm" 2> "dis/$$n.err"; \
	done
	disbesm6 -a10000 -e10000 -nsym/MBE.tab gold/MBE-Z0137-L1.bin > dis/MBE-Z0137-named.asm
	disbesm6 -a0 -e0 -R3=100 gold/MBE-Z0137-L1.bin > dis/MBE-Z0137-R3.asm
	grep -hoE '\b[AG][0-9]{5}\b|\bD[0-9]{5}\b' dis/*.asm | sort -u > dis/labels.raw

# Фаза 4 — символы и переходы (xref.py создаётся в фазе 4).
xref:
	mkdir -p analysis
	grep -nE '\b(пб|пв|по|пе|цикл|выпр|э[0-7][0-7]|вжм)\b' dis/MBE-*.asm > analysis/branches.txt
	grep -nE 'увв|сда|счрж|конд' dis/MBE-*.asm > analysis/io.txt
	python3 tools/xref.py > analysis/xref.txt

# Фаза 5 — независимое переизвлечение из эталона и побайтовая сверка с gold/.
# (Реконструированные .be пока отсутствуют; проверяется round-trip дампов.)
verify:
	bash tools/verify-roundtrip.sh

# Фаза 6 — сравнение версий 06/78 ↔ 12/77 (сдвиг +0400₈).
versions:
	mkdir -p analysis
	# Полные диапазоны: 33 зоны NEW и 32 зоны OLD (не одна зона!)
	besmtool dump $(DISK) --start=95  --length=33 --to-file=/tmp/v137-full.bin > /dev/null
	besmtool dump $(DISK) --start=352 --length=32 --to-file=/tmp/v540-full.bin > /dev/null
	# compare_shifted.py ест 16-разрядные восьмеричные СТРОКИ, не бинарник
	python3 tools/bin_to_octal.py /tmp/v137-full.bin > /tmp/v137-full.oct
	python3 tools/bin_to_octal.py /tmp/v540-full.bin > /tmp/v540-full.oct
	python3 tools/compare_shifted.py 0400 /tmp/v137-full.oct /tmp/v540-full.oct \
	  | tee analysis/mbe_diff.txt
	$(V) /tmp/v137-full.bin /tmp/v540-full.bin \
	  | sed -r 's/\x1B\[[0-9;]*m//g' | tee -a analysis/mbe_diff.txt

# Итоговая проверка воспроизводимости (критерии успеха, раздел 7 PLAN).
check: stage0
	@echo '--- версии инструментов ---'
	@command -v disbesm6 besmtool dispak
	@disbesm6 -h 2>&1 | head -3
	@besmtool --help | head -3
	@echo '--- md5 эталонного образа ---'
	@md5sum /usr/local/share/besm6/2348

# Удаление только порождённых файлов (не трогаем docs/ и эталоны).
clean:
	rm -f gold/*.bin gold/manifest.sha256
	rm -f dis/*.asm dis/*.err dis/labels.raw
	rm -f sym/*.tab
	rm -f verify/*.txt verify/*.bin verify/*.diff
	rm -f analysis/*.txt

# --- Автоматизация аннотирования и аналитических сводок (docs/AUTOMATION.md) ---

# Пересобрать аннотированные листинги из карт bemsh/comments-*.tab.
# Карты комментариев: ADDRESS<TAB>COMMENT; шапка (если есть) — bemsh/header-<zone>.txt.
# Если карт нет — подсказка и успешный выход (ничего не портим).
annotate:
	@for m in bemsh/comments-*.tab; do \
	  if [ ! -e "$$m" ]; then \
	    echo 'annotate: карт комментариев (bemsh/comments-*.tab) нет.'; \
	    echo '  Формат карты: ADDRESS<TAB>COMMENT, комментарий <= 55 символов.'; \
	    echo '  Пример: python3 tools/annotate_zone.py --input dis/MBE-Z0147-L1.asm --output bemsh/annotated-MBE-Z0147-L1.asm --comment-file bemsh/comments-0147.tab'; \
	    echo '  Проверка: python3 tools/annotate_zone.py --verify-only --input dis/MBE-Z0147-L1.asm --output bemsh/annotated-MBE-Z0147-L1.asm'; \
	    exit 0; \
	  fi; \
	  zone=$${m##*/comments-}; zone=$${zone%.tab}; \
	  src="dis/MBE-Z$${zone}-L1.asm"; out="bemsh/annotated-MBE-Z$${zone}-L1.asm"; \
	  hdr="bemsh/header-$${zone}.txt"; \
	  if [ ! -f "$$src" ]; then echo "annotate: нет $$src" >&2; exit 1; fi; \
	  set -- --input "$$src" --output "$$out" --comment-file "$$m" --force; \
	  if [ -f "$$hdr" ]; then set -- "$$@" --header "$$hdr"; fi; \
	  python3 tools/annotate_zone.py "$$@" || exit $$?; \
	done

# grep-сводка границ процедур из analysis/procedures*.md.
procedures:
	@echo '--- сводка границ процедур: analysis/procedures*.md ---'
	@grep -nE '^## |A[0-9]{5}|пб \(М[0-9]+\)|ГИПОТЕЗА' analysis/procedures*.md | head -120

# Валидация таблицы переменных disbesm6 на зоне 0137.
variables:
	@echo '--- валидация sym/MBE.named.validated.tab на зоне 0137 ---'
	@disbesm6 -a10000 -e10000 -nsym/MBE.named.validated.tab \
	  gold/MBE-Z0137-L1.bin > dis/MBE-Z0137-validated-named.asm
	@echo "имен в листинге: $$(grep -cE 'MBEENTRY|INITCELL|CNT[0-6]|SUB[0-9]+' dis/MBE-Z0137-validated-named.asm || true)"

# --- Фаза A2 (docs/PLAN-NEXT.md): универсальная сборка зон из .be ---

# Универсальная сборка одной зоны: make rebuild-zone Z=0137 [MODE=B|MBE2|ASM]
Z ?= 0137
MODE ?= B

rebuild-zone:
	@if [ -z "$(Z)" ]; then \
	  echo 'Использование: make rebuild-zone Z=<восьмеричная_зона> [MODE=B|MBE2|ASM]'; \
	  echo 'Пример: make rebuild-zone Z=0137 MODE=B'; \
	  exit 2; \
	fi
	@echo '=== rebuild-zone: зона $(Z), режим $(MODE) ==='
	env -u BESM6_PATH bash tools/rebuild-zone.sh "$(Z)" "$(MODE)"

# Все зоны, для которых есть .be-исходник (сейчас только 0137).
rebuild-all:
	@found=0; ok=0; fail=0; \
	for be in bemsh/*.be; do \
	  [ -e "$$be" ] || { echo 'rebuild-all: нет .be-исходников'; break; }; \
	  base=$$(basename "$$be" .be); \
	  zone=$$(printf '%s' "$$base" | grep -oE 'Z[0-7]{4}' | head -1 | tr -d Z); \
	  [ -n "$$zone" ] || continue; \
	  case "$$base" in MBE2-*) mode=MBE2;; ASM-*) mode=ASM;; *) mode=B;; esac; \
	  found=$$((found + 1)); \
	  echo "=== rebuild-all: зона $$zone ($$mode) ==="; \
	  if env -u BESM6_PATH bash tools/rebuild-zone.sh "$$zone" "$$mode"; then \
	    ok=$$((ok + 1)); \
	  else \
	    fail=$$((fail + 1)); \
	  fi; \
	done; \
	echo "=== rebuild-all: найдено=$$found PASS=$$ok FAIL=$$fail ==="; \
	[ "$$fail" -eq 0 ]

# Регрессионная проверка эталонной зоны 0137 (1024/1024).
rebuild-check:
	@echo '=== rebuild-check: зона 0137 (эталон 1024/1024) ==='
	@out=$$(env -u BESM6_PATH bash tools/rebuild-zone.sh 0137 B 2>&1); \
	  printf '%s\n' "$$out"; \
	  printf '%s\n' "$$out" | grep -q 'WORDS: всего=1024 совпало=1024 различий=0' \
	    || { echo 'rebuild-check: FAIL (счётчик слов)'; exit 1; }; \
	  printf '%s\n' "$$out" | grep -q '^RESULT: PASS' \
	    || { echo 'rebuild-check: FAIL (RESULT)'; exit 1; }; \
	  echo 'rebuild-check: OK (RESULT: PASS, 1024/1024)'

# 6 unit-тестов аннотатора (docs/AUTOMATION.md).
unittest:
	python3 -m unittest tools/tests/test_annotate_zone.py tools/tests/test_dis2be.py -v

# Агрегатная проверка: фаза 0 + новая реконструкция + round-trip + тесты.
check-all: stage0 rebuild-check verify unittest
	@echo '=== check-all: все проверки пройдены ==='
