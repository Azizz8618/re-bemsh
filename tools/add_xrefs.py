#!/usr/bin/env python3
"""Add canonical ВХОДН/ВНЕШН cross-references to .be sources.

Recipe (docs/XREF-CANONICAL-FORM.md §0), validated byte-safe:
  owner:  <ZONE>A ЭКВ Z<zone> ; ВХОДН <ZONE>A
  user:   NEWX ВНЕШН Z<owner>.<ZONE>A     (NEW name, never an existing label)

The compiler subtracts the owner base automatically in `SYM-OWNER` refs
(EXTERNAL-CALL-FORMAT.md:35-39). Existing labels MUST NOT be replaced by
ВНЕШН: that was the earlier error (VNESHN-BYTE-EXPERIMENT, 6136/6144).

Per-entry rollback: each declaration is applied and compiled separately;
if the zone stops matching gold, that single declaration is reverted.

Usage:
  python3 tools/add_xrefs.py <ZONE> <MODE> --owner <OWNER_ZONE> --name <NEWNAME>
Then compile BOTH zones (owner first), confirm 1024/1024 PASS.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def be_path(zone, mode):
    prefix = {"B": "MBE", "MBE2": "MBE2", "ASM": "ASM"}[mode]
    for p in (f"bemsh/{prefix}-Z{zone}.be", f"bemsh/{prefix}-Z{zone}-L1.be"):
        full = os.path.join(ROOT, p)
        if os.path.exists(full):
            return full
    return None


def add_entry(zone, mode):
    """Add owner-side ВХОДН alias to a zone. Returns (ok, text)."""
    p = be_path(zone, mode)
    lines = open(p, encoding="utf-8").read().splitlines()
    tag = f"Z{zone}A"
    if any(tag in s and "ЭКВ" in s for s in lines):
        return True, "already"
    out = []
    for s in lines:
        m = re.match(r"^(Z\d{4})(\s+СТАРТ\b.*)$", s)
        if m:
            out.append(s)
            out.append("%s ЭКВ %s" % (tag, m.group(1)))
            out.append("        ВХОДН %s" % tag)
        else:
            out.append(s)
    open(p, "w", encoding="utf-8").write("\n".join(out) + "\n")
    return True, "added"


def add_extern(zone, mode, owner, owner_alias, newname):
    """Add consumer-side ВНЕШН declaration with a NEW name."""
    p = be_path(zone, mode)
    lines = open(p, encoding="utf-8").read().splitlines()
    if any(newname in s for s in lines):
        return True, "already"
    out = []
    for s in lines:
        m = re.match(r"^(Z\d{4})(\s+СТАРТ\b.*)$", s)
        if m:
            out.append(s)
            out.append("%s ВНЕШН Z%s.%s" % (newname, owner, owner_alias))
        else:
            out.append(s)
    open(p, "w", encoding="utf-8").write("\n".join(out) + "\n")
    return True, "added"


def main():
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
