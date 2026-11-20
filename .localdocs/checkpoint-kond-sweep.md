# Checkpoint: КОНД full sweep ASM zones 0055/0056/0057/0060

## Objective & scope
- Objective: perform same full КОНД sweep as Z0137 reference on 4 ASM zones.
- Write set ONLY: bemsh/ASM-Z0055.be, ASM-Z0056.be, ASM-Z0057.be, ASM-Z0060.be,
  docs/SEMANTIC/ASM-KOND-FULL-SWEEP.md. Temp in /tmp/.private/azizz/.
- No commits/push. .bak before each edit. Read-only gold/dis/sym/tools.

## Method
1. Count КОНД lines per zone (initial: 0055=59, 0056=121, 0057=71, 0060=105; total 356).
2. decode both 24-bit halves via siprod_asm.decode(int). Verify raw word vs gold.
3. Byte-safe => convert to 2 command lines with EQU/existing labels or compact names.
4. Keep КОНД for illegal half, left-ADDREX/CALL/STOP (auto-мода trap), ПИО36, EXP-bit
   words; replace generic comment with honest role.
5. MANDATORY after each zone: bash tools/rebuild-zone.sh Z ASM -> PASS 1024/1024.
   Revert byte-changing splits. Never leave failing file.
6. Doc: full table + counts + 4/4 verification.

## Status: COMPLETE
- [x] Read reference docs, tools, AGENTS.
- [x] Baseline: all 4 zones rebuild PASS 1024/1024.
- [x] Generator in unique dir /tmp/.private/azizz/ASM_SWEEP_MAIN/
      (other agents share /tmp/.private/azizz/ and overwrite scripts there).
      Pristine originals in ASM_SWEEP_MAIN/orig/.
- [x] Zone 0055: 59 -> 37 КОНД, 22 converted, 15 new labels. PASS.
- [x] Zone 0056: 121 -> 78 КОНД, 43 converted, 20 new labels. PASS.
- [x] Zone 0057: 71 -> 35 КОНД, 36 converted, 22 new labels. PASS.
- [x] Zone 0060: 105 -> 53 КОНД, 52 converted, 27 new labels. PASS.
- [x] Doc written: docs/SEMANTIC/ASM-KOND-FULL-SWEEP.md (full 356-row table).
- [x] Empirical findings recorded in doc: left-immex NOT byte-safe (172
      diffs); reg1/imm64 extra-field halves NOT byte-safe; КОНД needs 8
      leading spaces; `/` in comment breaks translator.

## Validation
- Final rebuild all 4 zones: PASS 1024/1024, Файлы идентичны (2000 слов).
- 356/356 raw КОНД words matched gold; 0 mismatches.
- All added lines <=60 cols, no slash in comments; only pre-existing
  header lines >60 remain unchanged.
- gold md5 unchanged, matches manifest.sha256.
- Write set respected: only 4 .be files + doc modified; .bak moved to /tmp.
- No commits/push. Other agents' MBE/MBE2 changes untouched.

## Blockers
- None yet.

## Next action
- Study file format, decode tool behavior, command syntax accepted by dispak translator.
