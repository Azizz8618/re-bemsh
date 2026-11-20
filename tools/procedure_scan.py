#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""procedure_scan.py -- generic candidate-procedure scanner for
forced-code disassembly listings of BESM-6 (disbesm6) zones.

The tool is deliberately format-agnostic with respect to the *label*
prefix: it accepts `A#####`, `D#####`, `C#####` and bare octal
operands `'NNNN'`.  It reads whatever .asm files are in --dir, so it
works with `dis-forced/` (23 B zones), with the complete forced set
produced per docs/SEMANTIC/B-ZONES-FORCECODE.md (33 B zones), or with
any other directory of disbesm6 listings.

Detection rules (see docs/PROCEDURES-B.md, "Методика"):
  entry = target of CALL (`пв`, `пво`, `вжм`) OR target of a branch
          (`по`, `пе`, `цикл`, `пб`, `пио`, `пино`, `выпр`) with >=
          --min-branch-refs incoming references;
  exit  = RET (`пб (Мn)`), STOP (`э74`, `стоп`), or the first address
          of a data/zeros run (>= --min-data-run consecutive
          data-like words);
  range = [entry, exit] in octal words; size = exit-entry+1.

Cross-checks:
  - analysis/CROSSREF.md  (top-20 targets, §4)  -> `xref` column;
  - docs/REGISTERS.md     (register roles)     -> `regs` column;
  - docs/TEXT-CONSTANTS.md (decoded phrases)    -> `text` column;
  - docs/SEMANTIC/INDEX.md (zone role)          -> meaning hint.

Only stdout and the optional --out file are written; no repository
input file is ever modified.  Python 3, standard library only.
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

# ------------------------------------------------------------------
# constants / conventions
# ------------------------------------------------------------------
CALL_MNEMS = frozenset(("пв", "пво", "вжм"))
BRANCH_MNEMS = frozenset(
    ("по", "пе", "цикл", "пб", "пио", "пио36", "пино", "выпр")
)
RET_MNEMS = frozenset(("пб",))
STOP_MNEMS = frozenset(("э74", "стоп"))
DATA_MNEMS = frozenset(("конд", "пам", "nop", "ноп"))
FILL_PATTERNS = (
    ("слиа", "25252"),
    ("вчп", "72525"),
)

ZONE_FAMILIES = {
    "B": ["0137"] + ["%04o" % n for n in range(0o140, 0o150)]
         + ["%04o" % n for n in range(0o150, 0o160)]
         + ["%04o" % n for n in range(0o160, 0o170)]
         + ["%04o" % n for n in range(0o170, 0o200)],
    "B2": ["%04o" % n for n in range(0o540, 0o600)],
    "ASM": ["%04o" % n for n in range(0o55, 0o61)],
}

RE_FILE_ZONE = re.compile(r"[zZ](\d{4})")
RE_ADDR = re.compile(
    r"^\s*([0-7]{1,5})\s*:?\s*([0-7]{2,3}\s+[0-7]{2,3}\s+[0-7]{3,5})"
    r"\s*(.*)$"
)
RE_CONT = re.compile(
    r"^\s+([0-7]{2,3}\s+[0-7]{2,3}\s+[0-7]{3,5})\s*(.*)$"
)
RE_MNEM = re.compile(
    r"\b(пво|пв|вжм|пб|по|пе|пио36|пио|пино|выпр|цикл|э74|стоп|"
    r"конд|пам|зп|ноп|nop|слиа|вчп|сч|счи|уи|уиа|мод|мода|сда|нтж|"
    r"слц|вч|сбр|э70|э72|э73|э75|э76|э77)\b"
)
RE_TARGET = re.compile(r"\b(?:[ACD])?(\d{4,5})\b|'([0-7]{4,5})'")
RE_REG = re.compile(r"\(?М(\d{1,2})\)?")
RE_RET_REG = re.compile(r"\(М(\d{1,2})\)")
RE_DATA_TEXT = re.compile(r"конд\s+[пв]'")

# ------------------------------------------------------------------
# small parsers for the cross-reference documents
# ------------------------------------------------------------------
def repo_root():
    """Repository root = parent directory of this script's directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_registers(path):
    """Return {n: short_role} from the summary table in REGISTERS.md."""
    roles = {}
    if not path or not os.path.isfile(path):
        return roles
    for line in open(path, encoding="utf-8", errors="replace"):
        if not line.startswith("| М"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        m = re.match(r"М(\d{1,2})", cells[0])
        if not m:
            continue
        role = cells[3] if len(cells) > 5 else cells[2]
        role = role.split("(")[0].split(",")[0].strip()
        role = role.replace("**", "").replace("`", "").strip()
        if len(role) > 22:
            role = role[:21] + "…"
        roles[int(m.group(1))] = role or "индекс"
    return roles


def parse_text_constants(path):
    """Return {zone: [(lo, hi, phrase)]} from a text-constants catalog.

    Supports both the classic table in docs/TEXT-CONSTANTS.md
    (``| `0147.1315–1320` | `ИПМ ...` | штамп |``) and the richer
    docs/TEXT-CONSTANTS-ALL.md format
    (``| `0144.1205` | GOST | ВНЕШ. МЕТКА | ... |``).
    """
    out = collections.defaultdict(list)
    if not path or not os.path.isfile(path):
        return out
    classic = re.compile(
        r"^\|\s*`?([0-7]{4})\.([0-7]{4})(?:[–\-]([0-7]{4}))?`?\s*\|"
        r"\s*`?([^|`]+?)`?\s*\|"
    )
    rich = re.compile(
        r"^\|\s*`([0-7]{4})\.([0-7]{4})(?:[–\-]([0-7]{4}))?`\s*\|"
        r"\s*(GOST|TEXT|KOI7|ITM)\s*\|\s*([^|]+?)\s*\|"
    )
    seen = set()
    for line in open(path, encoding="utf-8", errors="replace"):
        m = rich.match(line)
        if m:
            z, lo, hi, phrase = m.group(1), m.group(2), m.group(3), m.group(5)
        else:
            m = classic.match(line)
            if not m:
                continue
            z, lo, hi, phrase = m.group(1), m.group(2), m.group(3), m.group(4)
        hi = hi or lo
        phrase = phrase.strip().strip("`")
        if not re.search(r"[А-Яа-я]", phrase):
            continue
        key = (z, lo, hi, phrase)
        if key in seen:
            continue
        seen.add(key)
        out[z].append((int(lo, 8), int(hi, 8), phrase))
    return out


def parse_xref(path):
    """Return set of targets named in CROSSREF.md §4 (e.g. 'A00474')."""
    names = set()
    if not path or not os.path.isfile(path):
        return names
    for line in open(path, encoding="utf-8", errors="replace"):
        if not line.startswith("|"):
            continue
        m = re.match(r"^\|\s*([AD]\d{5})\s*\|", line)
        if m:
            names.add(m.group(1))
    return names


def parse_zone_roles(path):
    """Return {zone: role} from SEMANTIC/INDEX.md."""
    roles = {}
    if not path or not os.path.isfile(path):
        return roles
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^\|\s*`([0-7]{4})`\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            roles[m.group(1)] = m.group(2).strip()
    return roles


# ------------------------------------------------------------------
# listing parser
# ------------------------------------------------------------------
def parse_listing(path):
    """Parse one disbesm6 listing into per-word halfword records.

    Returns dict: address -> {"hw": [(mnem, operand), ...],
                              "labels": set(), "text": str}
    """
    words = {}
    cur = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.lstrip("\ufeff").rstrip("\n")
            if not line.strip() or line.startswith("*"):
                continue
            m = RE_ADDR.match(line)
            if m:
                cur = int(m.group(1), 8)
                rest = m.group(3)
            else:
                m = RE_CONT.match(line)
                if not m or cur is None:
                    continue
                rest = m.group(2) or ""
                if not RE_MNEM.search(rest):
                    continue
            mm = RE_MNEM.search(rest)
            if not mm:
                continue
            mnem = mm.group(1)
            operand = rest[mm.end():].strip()
            rec = words.setdefault(cur, {"hw": [], "labels": set(), "text": ""})
            if mnem not in ("nop", "ноп") or operand:
                rec["hw"].append((mnem, operand))
            for lm in re.finditer(r"\b([ACD]\d{5})\b", rest[:mm.start()]):
                rec["labels"].add(lm.group(1))
            if mnem in ("конд", "пам"):
                tm = RE_DATA_TEXT.search(rest)
                if tm:
                    rec["text"] = tm.group(0)
    return words


def target_addr(operand):
    """Extract a numeric (octal) target address from an operand.

    Rejects fuzz artefacts like ``C1777+57`` / ``D01776+2``:
    praddr() prints name+decimal offset within +/-64 of a known
    label, which is NOT a physical address (CROSSREF.md §5.1).
    """
    if not operand:
        return None
    if re.search(r"\b[ACD]?\d{4,5}[+-]\d+", operand):
        return None
    m = RE_TARGET.search(operand)
    if not m:
        return None
    val = m.group(1) or m.group(2)
    try:
        return int(val, 8)
    except ValueError:
        return None


def parse_base_code_mask(base_dir, zone):
    """Addresses that the *base* (-a0 -e0) trace reached as code.

    A halfword printed as ``конд``/``пам`` was not traced and is
    therefore data.  The mask lets us discard CALL/branch/RET
    references that appeared only because forced coding turned a
    data word into a plausible instruction.  Returns None when no
    base listing is available.
    """
    if not base_dir:
        return None
    for name in ("MBE-Z%s-L1.asm" % zone, "MBE2-Z%s-L1.asm" % zone):
        path = os.path.join(base_dir, name)
        if not os.path.isfile(path):
            continue
        mask = set()
        with open(path, encoding="utf-8", errors="replace") as fh:
            cur = None
            for raw in fh:
                line = raw.lstrip("\ufeff")
                m = RE_ADDR.match(line)
                if m:
                    cur = int(m.group(1), 8)
                    rest = m.group(3)
                else:
                    m2 = RE_CONT.match(line)
                    if not m2 or cur is None:
                        continue
                    rest = m2.group(2) or ""
                if re.search(r"\b(конд|пам)\b", rest):
                    continue
                if rest.strip():
                    mask.add(cur)
        return mask
    return None


def is_data_like(rec):
    """True when a word is a zero/data/fill word rather than code."""
    if not rec or not rec["hw"]:
        return True
    hws = rec["hw"]
    mnems = [m for m, _ in hws]
    ops = [o for _, o in hws]
    if any(m in DATA_MNEMS for m in mnems):
        return True
    if all(m == "зп" for m in mnems) and len(set(o.split("(")[0] for o in ops)) <= 1:
        return True
    for mnem, needle in FILL_PATTERNS:
        if sum(1 for mm, oo in hws if mm == mnem and needle in oo) >= 2:
            return True
    return False


def data_run_starts(words, min_run):
    """Return sorted addresses that begin a run of >= min_run data words."""
    addresses = sorted(words)
    starts = []
    run = []
    for a in addresses:
        if is_data_like(words[a]):
            run.append(a)
        else:
            if len(run) >= min_run:
                starts.append(run[0])
            run = []
    if len(run) >= min_run:
        starts.append(run[0])
    return starts


# ------------------------------------------------------------------
# candidate construction
# ------------------------------------------------------------------
def parse_base_data_addrs(base_dir, zone):
    """Addresses printed as `конд`/`пам` (or absent) in the base trace.

    Returns None when no base listing exists.  A CALL target that is
    `конд` in the base listing is a data word misdecoded by forced
    coding, i.e. a false procedure entry.
    """
    if not base_dir:
        return None
    for name in ("MBE-Z%s-L1.asm" % zone, "MBE2-Z%s-L1.asm" % zone):
        path = os.path.join(base_dir, name)
        if not os.path.isfile(path):
            continue
        data = set(range(0o2000))
        with open(path, encoding="utf-8", errors="replace") as fh:
            cur = None
            for raw in fh:
                line = raw.lstrip("\ufeff")
                m = RE_ADDR.match(line)
                if m:
                    cur = int(m.group(1), 8)
                    rest = m.group(3)
                else:
                    m2 = RE_CONT.match(line)
                    if not m2 or cur is None:
                        continue
                    rest = m2.group(2) or ""
                if re.search(r"\b(конд|пам)\b", rest):
                    continue
                if rest.strip():
                    data.discard(cur)
        return data
    return None


def parse_base_data_runs(base_dir, zone, min_run):
    """Start addresses of >= min_run consecutive `конд` words in base.

    Unlike --use-base-mask this does NOT discard references: it only
    gives the exit detector a reliable code/data boundary, because
    forced coding happily turns GOST text/constants into commands.
    """
    if not base_dir:
        return set()
    for name in ("MBE-Z%s-L1.asm" % zone, "MBE2-Z%s-L1.asm" % zone):
        path = os.path.join(base_dir, name)
        if not os.path.isfile(path):
            continue
        data = set(range(0o2000))
        with open(path, encoding="utf-8", errors="replace") as fh:
            cur = None
            for raw in fh:
                line = raw.lstrip("\ufeff")
                m = RE_ADDR.match(line)
                if m:
                    cur = int(m.group(1), 8)
                    rest = m.group(3)
                else:
                    m2 = RE_CONT.match(line)
                    if not m2 or cur is None:
                        continue
                    rest = m2.group(2) or ""
                if not re.search(r"\b(конд|пам)\b", rest) and rest.strip():
                    data.discard(cur)
        runs = []
        cur_run = []
        for a in sorted(data):
            if cur_run and a != cur_run[-1] + 1:
                if len(cur_run) >= min_run:
                    runs.append(cur_run[0])
                cur_run = []
            cur_run.append(a)
        if len(cur_run) >= min_run:
            runs.append(cur_run[0])
        return set(runs)
    return set()


def collect_refs(words, code_mask=None):
    """Return call_refs, branch_refs, ret_addrs, stop_addrs, reg_use.

    When ``code_mask`` is given, only references originating from
    words traced as code in the base listing are counted.
    """
    calls = collections.defaultdict(list)   # target -> [(addr, reg)]
    branches = collections.defaultdict(list)  # target -> [(addr, mnem)]
    rets = []
    stops = []
    reg_use = collections.defaultdict(collections.Counter)
    for addr in sorted(words):
        traced = code_mask is None or addr in code_mask
        for mnem, operand in words[addr]["hw"]:
            reg_use[addr].update(int(x) for x in RE_REG.findall(operand))
            if mnem in CALL_MNEMS:
                t = target_addr(operand)
                if t is not None and traced:
                    rm = RE_REG.search(operand)
                    calls[t].append((addr, "М" + rm.group(1) if rm else "?"))
            elif mnem in BRANCH_MNEMS:
                t = target_addr(operand)
                if t is not None and traced:
                    branches[t].append((addr, mnem))
            if traced and mnem in RET_MNEMS and RE_RET_REG.search(operand):
                rets.append(addr)
            if traced and mnem in STOP_MNEMS:
                stops.append(addr)
    return calls, branches, rets, stops, reg_use


def find_exit(entry, entries, rets, stops, data_starts, last_word):
    """Return (end, exit_evidence) for a candidate entry.

    A real exit (RET/STOP/data run) is preferred.  Only when none
    is found do we cut the range at the next candidate entry
    (``ГРАН``) so that overlapping ranges can still be reported
    and deduplicated by the caller.
    """
    bounds = []
    for a in rets:
        if a > entry:
            bounds.append((a, "RET@%04o" % a))
    for a in stops:
        if a > entry:
            bounds.append((a, "STOP@%04o" % a))
    for a in data_starts:
        if a > entry:
            bounds.append((a - 1, "ДАН@%04o" % a))
    if not bounds:
        nxt = min((e for e in entries if e > entry), default=last_word + 1)
        end = min(nxt - 1, entry + 0o177)
        return max(end, entry), "ГРАН@%04o" % nxt
    end, ev = min(bounds, key=lambda t: t[0])
    if end < entry:
        end, ev = entry, "ТОЧКА"
    return end, ev


def fmt_hex_words(vals, limit=3):
    return ", ".join("%04o" % v for v in vals[:limit])


def meaning_for(zone, entry, end, words, reg_use, reg_roles,
                text_phrases, zone_role, kind, call_refs):
    """Build a 1-2 sentence *functional* description from observed ops."""
    body = []
    for a in range(entry, end + 1):
        body.extend(words.get(a, {}).get("hw", []))
    cnt = collections.Counter(m for m, _ in body)
    ops = [o for _, o in body]
    data_cells = []
    for o in ops:
        for m in re.finditer(r"\bD(\d{4,5})\b|\bC(\d{4,5})\b", o):
            v = int(m.group(1) or m.group(2), 8)
            if v < 0o2000:
                data_cells.append(v)
    top_cells = [c for c, _ in collections.Counter(data_cells).most_common(3)]
    regs = sorted({r for _, o in body for r in (int(x) for x in RE_REG.findall(o))})
    reg_txt = ", ".join(
        "М%d(%s)" % (r, reg_roles.get(r, "индекс"))
        for r in regs[:3]
    ) or "без индексных регистров"

    # dominant behaviour
    body_addrs = [a for a in range(entry, min(end, max(words)) + 1)]
    data_ratio = (sum(1 for a in body_addrs if is_data_like(words.get(a)))
                  / max(1, len(body_addrs)))
    if data_ratio >= 0.5:
        return "Область данных/забел: более половины слов тела — " \
               "константы или регулярный fill. Процедурой не является."
    if cnt["зп"] >= 4 and all(
        "0000" in o or "START" in o for o in ops if o
    ):
        return "Забел нулей: серия зп C0000. Не процедура, а данные."
    phrases = []
    for lo, hi, phrase in text_phrases:
        if lo - 0o400 <= entry <= hi + 0o400:
            phrases.append(phrase)
    text_note = " Текст рядом: «%s»." % phrases[0] if phrases else ""

    if cnt["э70"] or cnt["э72"] or cnt["э73"] or cnt["э75"]:
        ex = sorted({m for m, _ in body if re.match(r"э\d+", m)})
        action = "вызывает экстракод %s для специальной операции" % "/".join(ex)
    elif cnt["пио"] + cnt["пио36"] + cnt["пино"] + cnt["выпр"] >= 2:
        action = "передаёт управление через таблицу переходов (пио/выпр)"
    elif cnt["цикл"] + cnt["уи"] + cnt["счи"] >= 3:
        action = "пробегает по элементам таблицы с индексом, " \
                 "наращивая счётчик"
    elif cnt["пв"] >= 2:
        action = "вызывает подпрограммы %s и обрабатывает результат" % (
            fmt_hex_words([target_addr(o) or 0 for _, o in body
                           if target_addr(o) is not None])
        )
    elif cnt["сда"] + cnt["нтж"] + cnt["слц"] >= 2:
        action = "выделяет битовое поле и сравнивает его с признаком"
    elif cnt["мод"] + cnt["мода"] >= 2 and cnt["зп"] + cnt["сч"] >= 2:
        action = "готовит модифицированную адресацию и обменивает " \
                 "данные с ячейками зоны"
    elif cnt["зп"] + cnt["сч"] >= 3:
        action = "читает и перезаписывает рабочие ячейки/счётчики зоны"
    elif cnt["пб"] >= 1 or kind == "BRANCH":
        action = "выполняет узкую проверку условия и завершает " \
                 "текущую ветвь обработки"
    else:
        action = "выполняет короткую обработку операндов зоны"

    cells = (" Ячейки: %s." % ", ".join("D%04o" % c for c in top_cells)
             if top_cells else "")
    role = " В зоне «%s»." % zone_role[:48] if zone_role else ""
    callers = (" Вызов из %s." % fmt_hex_words([a for a, _ in call_refs[:3]])
               if call_refs else "")
    return ("%s: %s.%s%s%s%s Использует %s." % (
        "Процедура" if kind == "CALL" else "Вход",
        action, cells, callers, text_note, role, reg_txt))


# ------------------------------------------------------------------
# main scan
# ------------------------------------------------------------------
def scan(args):
    root = repo_root()
    reg_roles = parse_registers(
        args.registers or os.path.join(root, "docs", "REGISTERS.md"))
    if args.text:
        text_paths = [args.text]
    else:
        text_paths = [os.path.join(root, "docs", "TEXT-CONSTANTS-ALL.md"),
                      os.path.join(root, "docs", "TEXT-CONSTANTS.md")]
    texts = collections.defaultdict(list)
    for tp in text_paths:
        if os.path.isfile(tp):
            for z, vals in parse_text_constants(tp).items():
                texts[z].extend(vals)
    xref_names = parse_xref(
        args.xref or os.path.join(root, "analysis", "CROSSREF.md"))
    zone_roles = parse_zone_roles(
        os.path.join(root, "docs", "SEMANTIC", "INDEX.md"))

    families = ZONE_FAMILIES.get(args.zone_family)
    if families is None and args.zone_family != "ALL":
        raise SystemExit("--zone-family must be B, B2, ASM or ALL")

    files = sorted(glob.glob(os.path.join(args.dir, "*.asm")))
    rows = []
    zone_stats = collections.defaultdict(lambda: collections.Counter())
    all_calls_global = collections.Counter()
    all_aliases = []

    for path in files:
        fm = RE_FILE_ZONE.search(os.path.basename(path))
        if not fm:
            continue
        zone = fm.group(1)
        if families is not None and zone not in families:
            continue
        if args.zone and zone != args.zone:
            continue
        words = parse_listing(path)
        if not words:
            continue
        code_mask = (parse_base_code_mask(args.base_dir, zone)
                     if args.use_base_mask else None)
        calls, branches, rets, stops, reg_use = collect_refs(
            words, code_mask)
        # external CALL targets are counted for statistics only
        for t, refs in calls.items():
            all_calls_global[t] += len(refs)
        local_calls = {t: r for t, r in calls.items() if t < 0o2000}
        local_branches = {
            t: r for t, r in branches.items()
            if t < 0o2000 and len(r) >= args.min_branch_refs
        }
        data_starts = data_run_starts(words, args.min_data_run)
        data_starts = sorted(set(data_starts) | parse_base_data_runs(
            args.base_dir, zone, args.min_data_run))
        base_data = parse_base_data_addrs(args.base_dir, zone)
        # Only trust the base code/data split when the base trace is
        # substantial; zones 0137/0170 have ~1 traced word.
        trust_base = (base_data is not None
                      and 0o2000 - len(base_data) >= 16)
        last_word = max(words)

        candidates = []
        for t, refs in local_calls.items():
            candidates.append((t, "CALL", refs))
        for t, refs in local_branches.items():
            if t in local_calls:
                continue
            candidates.append((t, "BRANCH", refs))
        entries = sorted(t for t, _, _ in candidates)

        raw = []
        for entry, kind, refs in candidates:
            end, exit_ev = find_exit(
                entry, entries, rets, stops, data_starts, last_word)
            # A very long BRANCH block that contains other candidate
            # entries is almost certainly a jump table / loop region,
            # not one procedure.  Cut it at the next entry.
            if kind == "BRANCH" and end - entry > 0o77:
                inside = [e for e in entries if entry < e < end]
                if inside:
                    nxt = min(inside)
                    end, exit_ev = nxt - 1, "ГРАН@%04o" % nxt
            raw.append({
                "zone": zone, "start": entry, "end": end,
                "size": end - entry + 1, "kind": kind,
                "entry_refs": refs, "exit_ev": exit_ev,
                "words": words, "reg_use": reg_use,
                "data_like": (is_data_like(words.get(entry))
                              or (trust_base and entry in base_data)),
            })

        # ---- deduplication -------------------------------------
        # CALL-targeted entries have priority: a long BRANCH block
        # must not swallow the real procedures that lie inside it.
        raw.sort(key=lambda r: (r["kind"] != "CALL", r["start"],
                                -len(r["entry_refs"])))
        primary = []
        aliases = []
        for rec in raw:
            if rec["data_like"]:
                rec["status"] = "ДАН"
                aliases.append(rec)
                continue
            overlap = None
            for p in primary:
                # either we sit inside an accepted procedure, or we
                # cover one (a long block around a real CALL entry)
                if (p["start"] <= rec["start"] <= p["end"]
                        or rec["start"] < p["start"] <= rec["end"]):
                    overlap = p
                    break
            if overlap:
                rec["status"] = "ВЛОЖ"
                rec["alias_of"] = overlap["start"]
                aliases.append(rec)
            else:
                rec["status"] = "ОСН"
                primary.append(rec)

        all_aliases.extend(aliases)
        zone_stats[zone]["words"] = len(words)
        zone_stats[zone]["candidates"] += len(raw)
        zone_stats[zone]["primary"] += len(primary)
        zone_stats[zone]["nested"] += sum(
            1 for r in aliases if r["status"] == "ВЛОЖ")
        zone_stats[zone]["data"] += sum(
            1 for r in aliases if r["status"] == "ДАН")
        zone_stats[zone]["calls"] += sum(len(v) for v in local_calls.values())
        zone_stats[zone]["rets"] += len(rets)
        zone_stats[zone]["stops"] += len(stops)

        for rec in primary:
            entry, end = rec["start"], rec["end"]
            refs = rec["entry_refs"]
            reg_counter = collections.Counter()
            for a in range(entry, min(end, last_word) + 1):
                reg_counter.update(rec["reg_use"].get(a, {}))
            regs = sorted(reg_counter)
            reg_txt = ", ".join(
                "М%d:%s" % (r, reg_roles.get(r, "индекс"))
                for r in regs[:5]
            ) or "—"
            examples = ["%s:%04o" % (zone, a) for a, _ in refs[:3]]
            callers = "%d [%s]" % (len(refs), ", ".join(examples))
            if rec["kind"] == "CALL":
                entry_ev = "ПВ@%s" % examples[0] if examples else "ПВ"
                if len(refs) > 1:
                    entry_ev += "+%d" % (len(refs) - 1)
            else:
                entry_ev = "ВЕТВ×%d@%s" % (len(refs), examples[0])
            phrases = texts.get(zone, [])
            # "near entry" = same zone, within +/- 0400 octal words
            near = [p for lo, hi, p in phrases
                    if lo - 0o400 <= entry <= hi + 0o400]
            text_ev = near[0][:28] if near else "—"
            xref_ev = "XR" if any(
                "%04o" % entry in n for n in xref_names
            ) else "—"
            meaning = meaning_for(
                zone, entry, end, words, reg_use, reg_roles,
                phrases, zone_roles.get(zone, ""),
                rec["kind"], refs)
            # confidence: call+ret pair AND text evidence
            has_ret = rec["exit_ev"].startswith("RET@")
            has_stop = rec["exit_ev"].startswith("STOP@")
            conf = ("ПОДТВЕРЖДЕНО"
                    if rec["kind"] == "CALL" and has_ret and near
                    else "ГИПОТЕЗА")
            rows.append({
                "zone": zone,
                "start": "%04o" % entry,
                "end": "%04o" % end,
                "size": "%03o" % rec["size"],
                "kind": rec["kind"],
                "entry_ev": entry_ev,
                "exit_ev": rec["exit_ev"],
                "callers": callers,
                "n_callers": len(refs),
                "regs": reg_txt,
                "text": text_ev,
                "xref": xref_ev,
                "meaning": meaning,
                "conf": conf,
                "status": rec["status"],
                "stop": has_stop,
            })

    rows.sort(key=lambda r: (r["zone"], int(r["start"], 8)))
    # rank by incoming callers for the "top-N" report
    top = sorted(rows, key=lambda r: -r["n_callers"])
    return rows, zone_stats, all_aliases, top, all_calls_global


# ------------------------------------------------------------------
# output
# ------------------------------------------------------------------
COLUMNS = [
    ("zone", "ЗОНА"), ("start", "НАЧ"), ("end", "КОН"),
    ("size", "РАЗМ"), ("kind", "ВХОД"), ("entry_ev", "ВХ-СВИД"),
    ("exit_ev", "ВЫХ-СВИД"), ("callers", "ВЫЗЫВАЮЩИЕ"),
    ("regs", "РЕГИСТРЫ"), ("text", "ТЕКСТ"), ("xref", "XR"),
    ("conf", "УВЕРЕН."),
]


def print_table(rows, show_meaning=False):
    hdr = " | ".join(title for _, title in COLUMNS)
    print(hdr)
    print("-+-".join("-" * len(title) for _, title in COLUMNS))
    for r in rows:
        vals = [str(r[key]) for key, _ in COLUMNS]
        print(" | ".join(vals))
    if show_meaning:
        print("\nСМЫСЛ (по тем же строкам):")
        for r in rows:
            print("%s:%s  %s" % (r["zone"], r["start"], r["meaning"]))


def write_out(path, rows, stats, aliases, top):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        data = {"rows": rows, "stats": {k: dict(v) for k, v in stats.items()},
                "aliases": [
                    {"zone": a["zone"], "start": "%04o" % a["start"],
                     "end": "%04o" % a["end"], "status": a["status"],
                     "alias_of": "%04o" % a.get("alias_of", 0)}
                    for a in aliases
                ]}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# zone\tstart\tend\tsize\tkind\tentry\texit\t"
                 "n_callers\tcallers\tregs\ttext\txref\tconf\t"
                 "status\tmeaning\n")
        for r in rows:
            fh.write("\t".join(str(r[k]) for k in (
                "zone", "start", "end", "size", "kind", "entry_ev",
                "exit_ev", "n_callers", "callers", "regs", "text",
                "xref", "conf", "status", "meaning")) + "\n")


def print_stats(stats, aliases, top, rows):
    print("\nСТАТИСТИКА ПО ЗОНАМ")
    print("зона слов кандид. осн. влож. дан CALL RET STOP")
    for z in sorted(stats):
        c = stats[z]
        print("%s %4d %5d %4d %4d %4d %4d %3d %4d" % (
            z, c["words"], c["candidates"], c["primary"],
            c["nested"], c["data"], c["calls"], c["rets"], c["stops"]))
    print("\nИТОГО: осн=%d, влож=%d, дан=%d" % (
        len(rows), sum(1 for a in aliases if a["status"] == "ВЛОЖ"),
        sum(1 for a in aliases if a["status"] == "ДАН")))
    conf = collections.Counter(r["conf"] for r in rows)
    print("Уверенность: " + ", ".join("%s=%d" % kv for kv in conf.items()))
    par = sum(1 for r in rows if r["kind"] == "CALL"
              and r["exit_ev"].startswith("RET@"))
    print("CALL+RET пар (без текста): %d" % par)
    print("\nТОП-10 ПО ВХОДЯЩИМ ВЫЗОВАМ")
    for r in top[:10]:
        print("%s:%s-%s size=%s calls=%d %s | %s" % (
            r["zone"], r["start"], r["end"], r["size"],
            r["n_callers"], r["conf"], r["meaning"][:70]))


def main():
    ap = argparse.ArgumentParser(
        description="Generic scanner of candidate procedures in "
                    "forced-code disbesm6 listings.")
    ap.add_argument("--dir", default="dis-forced",
                    help="directory with .asm listings (default: dis-forced)")
    ap.add_argument("--base-dir", default=None,
                    help="directory with base dis/*.asm (used only with "
                         "--use-base-mask)")
    ap.add_argument("--use-base-mask", action="store_true",
                    help="discard CALL/branch/RET references that the "
                         "base trace printed as конд (strict mode; "
                         "loses forced-only procedures)")
    ap.add_argument("--zone-family", default="B",
                    choices=["B", "B2", "ASM", "ALL"],
                    help="zone family filter (default: B = 0137-0177)")
    ap.add_argument("--zone", default=None,
                    help="focus on a single zone, e.g. 0147")
    ap.add_argument("--out", default=None,
                    help="write full table to .tsv or .json")
    ap.add_argument("--xref", default=None,
                    help="path to analysis/CROSSREF.md")
    ap.add_argument("--registers", default=None,
                    help="path to docs/REGISTERS.md")
    ap.add_argument("--text", default=None,
                    help="path to text-constants catalog "
                         "(default: TEXT-CONSTANTS-ALL.md if present, "
                         "else TEXT-CONSTANTS.md)")
    ap.add_argument("--min-branch-refs", type=int, default=2,
                    help="min incoming refs for a branch target "
                         "(default: 2)")
    ap.add_argument("--min-data-run", type=int, default=4,
                    help="min consecutive data words for a run "
                         "(default: 4)")
    ap.add_argument("--show-meaning", action="store_true",
                    help="print suggested meaning under the table")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress table and statistics (use with --out)")
    args = ap.parse_args()

    if args.base_dir is None:
        sibling = os.path.join(
            os.path.dirname(os.path.abspath(args.dir)), "dis")
        if os.path.isdir(sibling):
            args.base_dir = sibling
        elif os.path.isdir("dis"):
            args.base_dir = os.path.abspath("dis")

    rows, stats, aliases, top, _ = scan(args)
    if not args.quiet:
        print_table(rows, args.show_meaning)
        print_stats(stats, aliases, top, rows)
    if args.out:
        write_out(args.out, rows, stats, aliases, top)
        print("\nЗаписано: %s (%d строк)" % (args.out, len(rows)))


if __name__ == "__main__":
    main()
