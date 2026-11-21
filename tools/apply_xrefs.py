#!/usr/bin/env python3
"""Apply canonical ВХОДН/ВНЕШН xrefs with PER-ENTRY rollback.

For each CALL-OUT target (compact X-name + owner zone + consumer zones):
1. Ensure owner has `Z<zone>A ЭКВ Z<zone>` + `ВХОДН Z<zone>A`.
2. For each consumer (except the owner itself), add a NEW declaration
   `<name>X ВНЕШН Z<owner>.Z<owner>A` after its START line.
3. Compile owner then consumer with `make rebuild-zone`.
4. On FAIL, restore ONLY that consumer file from its saved copy.

Special case: target 77316 (str.37) consumed by zone 0137 uses owner
0152 АРАП (RAM-SNAPSHOT-MAP.md:118, per operator), NOT 0157.

All writes are to bemsh/*.be (comments/declarations only); gold untouched.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALL_OUT = os.path.join(ROOT, "docs/CALL-OUT-OF-MODULE.md")


def be_path(zone, family=None):
    for pref in (["MBE", "MBE2", "ASM"] if family is None else [family]):
        for suf in ("", "-L1"):
            p = os.path.join(ROOT, f"bemsh/{pref}-Z{zone}{suf}.be")
            if os.path.exists(p):
                return p
    return None


def mode_of(path):
    b = os.path.basename(path)
    return "ASM" if b.startswith("ASM") else "MBE2" if b.startswith("MBE2") else "B"


def add_owner_entry(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    z = re.search(r"Z(\d{4})", os.path.basename(path)).group(1)
    tag = f"Z{z}A"
    if any(tag in s for s in lines):
        return False
    out = []
    for s in lines:
        m = re.match(r"^(Z\d{4})(\s+СТАРТ\b.*)$", s)
        if m:
            out.append(s)
            out.append(f"{tag} ЭКВ {m.group(1)}")
            out.append("        ВХОДН " + tag)
        else:
            out.append(s)
    open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    return True


def add_consumer_decl(path, owner, decl):
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


def compile_zone(zone, family=None):
    p = be_path(zone, family)
    if not p:
        return None
    m = mode_of(p)
    r = subprocess.run(
        ["make", "rebuild-zone", f"Z={zone}", f"MODE={m}"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return "RESULT: PASS" in r.stdout


def parse_targets():
    txt = open(CALL_OUT, encoding="utf-8").read()
    out = []
    for line in txt.splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) >= 8 and re.match(r"^\d+$", p[1]):
            compact = p[6].strip("`")
            m = re.search(r"Z(\d{4})", p[5])
            if m and compact.startswith("X"):
                zs = sorted(set(re.findall(r"Z(\d{4})\.", p[7])))
                out.append((compact, m.group(1), zs))
    return out


def main():
    targets = parse_targets()
    log = []
    for compact, owner, consumers in targets:
        # Special: 77316 target consumed by 0137 -> owner 0152
        special = []
        real_consumers = []
        for c in consumers:
            if compact == "X316B" and c == "0137":
                special.append((c, "0152"))
            else:
                real_consumers.append(c)
        # ensure owner entry
        op = be_path(owner)
        if op:
            add_owner_entry(op)
            compile_zone(owner)
        # suffix unique per target (last 2 digits of compact)
        suffix = re.sub(r"\W", "", compact)[-3:]
        decl = f"{compact}X ВНЕШН Z{owner}.Z{owner}A"
        for c in real_consumers:
            if c == owner:
                continue  # self-reference not declared (lk:261-264)
            cp = be_path(c)
            if not cp:
                continue
            saved = open(cp, encoding="utf-8").read()
            add_consumer_decl(cp, owner, decl)
            ok = compile_zone(c)
            if not ok:
                open(cp, "w", encoding="utf-8").write(saved)
            log.append((compact, c, "PASS" if ok else "ROLLBACK"))
        for c, o in special:
            op2 = be_path(o)
            if op2:
                add_owner_entry(op2)
                compile_zone(o)
            cp = be_path(c)
            if not cp:
                continue
            saved = open(cp, encoding="utf-8").read()
            add_consumer_decl(cp, o, f"{compact}D ВНЕШН Z{o}.Z{o}A")
            ok = compile_zone(c)
            if not ok:
                open(cp, "w", encoding="utf-8").write(saved)
            log.append((compact, c + "(owner " + o + ")", "PASS" if ok else "ROLLBACK"))
    rb = [x for x in log if x[2] == "ROLLBACK"]
    print(f"applied {len(log)} declarations, rolled back {len(rb)}")
    for x in rb:
        print("  ROLLBACK", x)


if __name__ == "__main__":
    main()
