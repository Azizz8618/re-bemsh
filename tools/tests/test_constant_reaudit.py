#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for tools/constant_reaudit.py.

Run: python3 -m pytest tools/tests/test_constant_reaudit.py -q
The tests only READ repository files; no .be, sym/ or gold/ file is modified.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import constant_reaudit as C  # noqa: E402


def test_norm_strips_leading_zeros():
    assert C.norm("00777") == "777"
    assert C.norm("00000") == "0"
    assert C.norm("105") == "105"


def test_procedure_starts_from_three_catalogues():
    starts, by_addr = C.load_procedure_starts(ROOT)
    assert ("0161", "105") in starts          # PROCEDURES-B.md 0105-0114
    assert ("0142", "1115") not in starts     # explicitly ДАН (false target)
    assert ("0055", "220") in starts          # PROCEDURES-ASM.md
    assert ("0547", "305") in starts          # PROCEDURES-B2.md section 4
    assert "0161" in by_addr["105"]
    assert starts[("0161", "105")]["doc"] == "PROCEDURES-B.md"


def test_procedure_starts_synthetic_fixture(tmp_path):
    """The B2 parser must ignore section 3 statistics rows."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "PROCEDURES-B2.md").write_text(
        "## 3. СТАТИСТИКА ПО ЗОНАМ\n"
        "0540 1024 1 170 178 0 1 1 1\n"      # statistics, must be ignored
        "## 4. ПОЛНАЯ ТАБЛИЦА ПРОЦЕДУР\n"
        "0540 1115 1115 1 CALLx1 Rn1115 1 7\n",
        encoding="utf-8",
    )
    starts, _ = C.load_procedure_starts(tmp_path)
    assert ("0540", "1115") in starts
    assert ("0540", "1024") not in starts


def test_xref_call_counts():
    xref = C.load_xref(ROOT)
    assert xref["70000"]["calls"] >= 2       # SYSCALL gate, many CALL refs
    assert xref["70000"]["ref_count"] > 300
    assert xref["7777"]["calls"] == 0        # external cell, not a CALL
    assert xref["4114"]["calls"] >= 2


def test_eqv_definition_and_label_usage():
    defs = C.load_eqv_definitions(ROOT)
    hit = [d for d in defs if d["zone"] == "0161"
           and d["label"] == "MB105" and d["value"] == "105"]
    assert len(hit) == 1
    br, data, samples = C.label_usage(ROOT, hit[0]["file"], "MB105")
    assert br >= 1 and data == 0
    assert any("ПО" in s or "ПБ" in s or "ПЕ" in s for s in samples)


def test_kond_half_low_five_octal_digits():
    halves = [h for h in C.load_kond_halves(ROOT)
              if h["zone"] == "0060" and h["line"] == 521]
    assert halves
    assert any(h["value"] == "20" and
               "0000672707100020".endswith("07100020") for h in halves)


def test_candidate_verdicts_and_columns():
    candidates, stats = C.build_candidates(ROOT)
    assert stats["candidates"] == len(candidates)
    assert {"PROCEDURE_LABEL", "POINTER_TO_PROCEDURE", "FALSE_POSITIVE"} & set(
        c["verdict"] for c in candidates)
    assert all(col in candidates[0] for col in C.COLUMNS)

    am220 = [c for c in candidates if c["zone"] == "0055"
             and c["old"] == "AM220" and c["source"] == "EQV"]
    assert am220 and am220[0]["verdict"] == "PROCEDURE_LABEL"
    assert am220[0]["new"] == "P220"

    e50 = [c for c in candidates if c["zone"] == "0161"
           and c["old"] == "Э50" and c["value"] == "105"]
    assert e50 and e50[0]["verdict"] == "POINTER_TO_PROCEDURE"
    assert e50[0]["new"] == "PTR105"

    reg = [c for c in candidates if c["zone"] == "0055"
           and c["old"] == "РЕГ" and c["value"] == "20"]
    assert reg and reg[0]["verdict"] == "FALSE_POSITIVE"
    assert reg[0]["new"] == "РЕГ"


def test_fix_list_excludes_false_positives():
    candidates, _ = C.build_candidates(ROOT)
    fix = C.format_fix_list(candidates)
    assert fix.startswith("zone | line | old label | suggested new label")
    for c in candidates:
        if c["verdict"] == "FALSE_POSITIVE":
            assert c["old"] not in fix or c["new"] == c["old"]


def test_table_contains_required_columns():
    candidates, _ = C.build_candidates(ROOT)
    table = C.format_table(candidates[:3])
    for col in ("zone", "verdict", "new", "context", "proc_doc"):
        assert col in table
    assert table.count("\n") >= 4


def test_cli_json_and_tsv(tmp_path):
    out = tmp_path / "cand.tsv"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "constant_reaudit.py"),
         "--root", str(ROOT), "--json", "--out", str(out)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(proc.stdout)
    assert data["stats"]["candidates"] > 50
    assert out.exists()
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("zone\tline\tfile\tvalue")
