# Makefile — воспроизведение docs/PLAN.md (фазы 0-7).
# Эталонные образы томов НЕ изменяются: только чтение и извлечение в /tmp.
# tools/disbesm_extract.sh ожидает ВОСЬМЕРИЧНЫЕ номера зон (см. AGENTS.md).
# $$z в рецептах = восьмеричная строка вида 0137 / 0540 (printf '%04o').

SHELL := /usr/bin/env bash
DISK  ?= 2348
V     := tools/disbesm_verify.sh

.PHONY: stage0 inventory dis xref verify versions check clean

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
	for f in gold/*.bin; do \
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

# Фаза 5 — побайтовая сверка эталон ↔ реконструкция, ANSI срезан.
verify:
	mkdir -p verify
	$(V) gold/MBE-Z0137-L1.bin /tmp/reasm/MBE-Z0137-L1.bin --disasm \
	  --disasm-path /usr/local/bin/disbesm6 \
	  | sed -r 's/\x1B\[[0-9;]*m//g' | tee verify/report.txt

# Фаза 6 — сравнение версий 06/78 ↔ 12/77 (сдвиг +0400₈).
versions:
	mkdir -p analysis
	for d in $$(seq 95 127); do \
	  z=$$(printf '%04o' $$d); \
	  tools/disbesm_extract.sh $(DISK) $$z 1 -o /tmp/v137-$$z.bin; \
	done
	for d in $$(seq 352 383); do \
	  z=$$(printf '%04o' $$d); \
	  tools/disbesm_extract.sh $(DISK) $$z 1 -o /tmp/v540-$$z.bin; \
	done
	python3 tools/compare_shifted.py 0400 /tmp/v137-0137.bin /tmp/v540-0540.bin \
	  | tee analysis/mbe_diff.txt
	$(V) /tmp/v137-0137.bin /tmp/v540-0540.bin --disasm \
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
