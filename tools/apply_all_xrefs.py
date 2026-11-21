#!/usr/bin/env python3
"""Apply ALL CALL-OUT xrefs across every zone, per-entry rollback.

Source: docs/CALL-OUT-OF-MODULE.md §6 — 1987 rows, 1100 unique
(operand -> owner-zone) pairs, 8 owner zones.

Recipe (validated byte-safe):
  owner:  Z<zone>A ЭКВ Z<zone>; ВХОДН Z<zone>A
  user:   X<op>X ВНЕШН Z<owner>.Z<owner>A   (NEW name)

Special: for consumer zone 0137, str.37 owner is 0152 АРАП
(RAM-SNAPSHOT-MAP.md:118, operator), not 0157.

Every declaration is applied and compiled separately. On FAIL the
single consumer file is restored (per-entry rollback).
"""
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALL_OUT = os.path.join(ROOT, "docs/CALL-OUT-OF-MODULE.md")


def be_path(zone):
    for pref in ("MBE", "MBE2", "ASM"):
        for suf in ("", "-L1"):
            p = os.path.join(ROOT, f"bemsh/{pref}-Z{zone}{suf}.be")
            if os.path.exists(p):
                return p
    return None


def mode_of(p):
    b = os.path.basename(p)
    return "ASM" if b.startswith("ASM") else "MBE2" if b.startswith("MBE2") else "B"


def compile_zone(zone):
    p = be_path(zone)
    if not p:
        return None
    r = subprocess.run(
        ["make", "rebuild-zone", f"Z={zone}", f"MODE={mode_of(p)}"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return "RESULT: PASS" in r.stdout


def add_owner(path):
    z = re.search(r"Z(\d{4})", os.path.basename(path)).group(1)
    tag = f"Z{z}A"
    lines = open(path, encoding="utf-8").read().splitlines()
    if any(tag in s for s in lines):
        return False
    out = []
    for s in lines:
        m = re.match(r"^(Z\d{4})(\s+СТАРТ\b.*)$", s)
        if m:
            out += [s, f"{tag} ЭКВ {m.group(1)}", "        ВХОДН " + tag]
        else:
            out.append(s)
    open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    return True


def add_decl(path, decl):
    lines = open(path, encoding="utf-8").read().splitlines()
    if any(decl in s for s in lines):
        return False
    out = []
    for s in lines:
        out.append(s)
        if not s.startswith("*") and "СТАРТ" in s:
            out.append(decl)
    open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    return True


def parse_pairs():
    txt = open(CALL_OUT, encoding="utf-8").read()
    sec = txt.split("## 6. Приложение")[1].split("## 7.")[0]
    out = []
    for line in sec.splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) >= 9 and re.match(r"^\d{4}$", p[1]):
            consumer = p[1]
            oper = p[4].strip("'`")
            m = re.search(r"зона (\d{4})", p[7])
            if m and re.match(r"^\d{3,6}$", oper):
                owner = m.group(1)
                if consumer == "0137" and owner == "0157":
                    owner = "0152"  # АРАП phase
                out.append((consumer, oper, owner))
    return out


def main():
    pairs = parse_pairs()
    # group by (consumer, owner) to dedupe declarations
    seen = set()
    owners = set()
    work = []
    for consumer, oper, owner in pairs:
        if consumer == owner:
            continue  # self-ref not declared (lk:261-264)
        key = (consumer, oper, owner)
        if key in seen:
            continue
        seen.add(key)
        owners.add(owner)
        work.append(key)
    # ensure owner entries first
    for o in sorted(owners):
        p = be_path(o)
        if p:
            add_owner(p)
            compile_zone(o)
    applied = 0
    rolled = 0
    for consumer, oper, owner in work:
        cp = be_path(consumer)
        if not cp:
            continue
        decl = f"X{oper}X ВНЕШН Z{owner}.Z{owner}A"
        if len(decl.split()[0]) > 8:
            continue
        saved = open(cp, encoding="utf-8").read()
        add_decl(cp, decl)
        if not compile_zone(consumer):
            open(cp, "w", encoding="utf-8").write(saved)
            rolled += 1
        else:
            applied += 1
    print(f"pairs={len(work)} applied={applied} rolled_back={rolled}")


if __name__ == "__main__":
    main()
