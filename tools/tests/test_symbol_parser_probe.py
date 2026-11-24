#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for tools/symbol_parser_probe.py.

Run: python3 -m unittest tools/tests/test_symbol_parser_probe.py -v

The tool is read-only and needs no emulator; all integration checks
only read bemsh/*.be from the repository.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
TOOL = os.path.join(TOOLS, 'symbol_parser_probe.py')
Z0137 = os.path.join(ROOT, 'bemsh', 'MBE-Z0137.be')
Z0147 = os.path.join(ROOT, 'bemsh', 'MBE-Z0147.be')

_spec = importlib.util.spec_from_file_location('symbol_parser_probe', TOOL)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


class SymbolParserProbeTest(unittest.TestCase):

    def scan(self, text, pages=None):
        return probe.scan(text, pages or {'34', '35', '36', '37'})

    def run_cli(self, *args, stdin=None):
        result = subprocess.run(
            [sys.executable, TOOL] + list(args),
            input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def write_be(self, tmp, text):
        path = os.path.join(tmp, 'src.be')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
        return path

    # (a) ЭКВ classification: absolute pages, other octal, symbolic.
    def test_equ_classification(self):
        text = (
            "A1 ЭКВ '34123'\n"
            "A2 ЭКВ '35134'\n"
            "A3 ЭКВ '77044'\n"
            "A4 ЭКВ '137'\n"
            "A5 ЭКВ Z0137\n"
        )
        data = self.scan(text)
        c = data['counts']
        self.assertEqual(c['equ_total'], 5)
        self.assertEqual(c['equ_absolute'], 2)
        self.assertEqual(c['equ_quoted_octal_other'], 2)
        self.assertEqual(c['equ_symbolic'], 1)
        kinds = {x['name']: x['kind'] for x in data['declared']['equ']}
        self.assertEqual(kinds['A1'], 'absolute')
        self.assertEqual(kinds['A3'], 'quoted_octal')
        self.assertEqual(kinds['A5'], 'symbolic')

    # (b) Absolute page set is configurable.
    def test_absolute_pages_option(self):
        text = "A1 ЭКВ '34123'\nA2 ЭКВ '61456'\n"
        self.assertEqual(self.scan(text)['counts']['equ_absolute'], 1)
        other = self.scan(text, {'61'})
        self.assertEqual(other['counts']['equ_absolute'], 1)
        self.assertEqual(other['absolute_pages'], ['61'])

    # (c) ВНЕШН parses the global owner.symbol form and the bare form.
    def test_vneshn_owner_symbol(self):
        text = (
            "X1 ВНЕШН Z0155.Z0155A\n"
            "X2 ВНЕШН SYM2\n"
            "        ВНЕШН X3\n"
        )
        data = self.scan(text)
        vn = data['declared']['vneshn']
        self.assertEqual(data['counts']['vneshn_total'], 3)
        self.assertEqual(
            [(x['local'], x['owner'], x['symbol']) for x in vn],
            [('X1', 'Z0155', 'Z0155A'), ('X2', '', 'SYM2'),
             ('', '', 'X3')])

    # (d) ВХОДН and macro wrappers are counted and expanded.
    def test_vhodn_and_macro_wrappers(self):
        text = (
            "        ВХОДН OUT477\n"
            "OWNER ВНЕШ A,B,C\n"
            "        ВХОД X,Y\n"
        )
        data = self.scan(text)
        c = data['counts']
        self.assertEqual(c['vhodn_total'], 1)
        self.assertEqual(c['vnesh_macro_lines'], 1)
        self.assertEqual(c['vnesh_macro_expansions'], 3)
        self.assertEqual(c['vhod_macro_lines'], 1)
        self.assertEqual(c['vhod_macro_expansions'], 2)
        self.assertEqual(data['declared']['vnesh_macro'][0]['names'],
                         ['A', 'B', 'C'])
        self.assertEqual(data['declared']['vhodn'][0]['name'], 'OUT477')

    # (e) Comment lines and trailing comments never declare symbols.
    def test_comments_are_ignored(self):
        text = (
            "* X9 ЭКВ '34111'\n"
            "* X8 ВНЕШN OWNER.X8\n"
            "A1 ЭКВ '34123' , ВНЕШ: A1 [СА 1]\n"
            "        СЧ   A1 , declaring text A9 ЭКВ '99999'\n"
        )
        data = self.scan(text)
        self.assertEqual(data['counts']['equ_total'], 1)
        self.assertEqual(data['counts']['equ_absolute'], 1)
        self.assertEqual(data['counts']['vneshn_total'], 0)
        self.assertEqual(data['declared']['equ'][0]['name'], 'A1')

    # (f) Heuristic unresolved identifiers: one missing, one declared.
    def test_unknown_refs(self):
        text = (
            "T   СТАРТ 1\n"
            "A1  ЭКВ '10'\n"
            "    СЧ  A1\n"
            "    СЧ  MISSING\n"
            "    ФИНИШ\n"
        )
        data = self.scan(text)
        names = [x['name'] for x in data['unknown_refs']]
        self.assertEqual(names, ['MISSING'])
        self.assertEqual(data['unknown_refs'][0]['lines'], [4])

    # (g) CLI json and text formats, plus stdin, are deterministic.
    def test_cli_formats_and_stdin(self):
        text = "A1 ЭКВ '34123'\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_be(tmp, text)
            j1 = self.run_cli(path, '--format', 'json')
            j2 = self.run_cli(path, '--format', 'json')
            self.assertEqual(j1, j2)
            data = json.loads(j1)
            self.assertEqual(data['format_version'], 1)
            self.assertEqual(data['counts']['equ_absolute'], 1)
            t1 = self.run_cli(path, '--format', 'text')
            self.assertIn('equ_absolute', t1)
            self.assertIn("A1 '34123'", t1)
        s = self.run_cli('-', '--format', 'json', stdin=text)
        self.assertEqual(json.loads(s)['counts']['equ_total'], 1)

    # (h) Integration: Z0137 known totals and three inherited externals.
    def test_z0137_integration(self):
        data = json.loads(self.run_cli(Z0137, '--format', 'json'))
        c = data['counts']
        self.assertEqual(c['equ_total'], 323)
        self.assertEqual(c['equ_absolute'], 43)
        self.assertEqual(c['vneshn_total'], 3)
        self.assertEqual(c['vhodn_total'], 0)
        self.assertEqual(
            [(x['local'], x['owner'], x['symbol'])
             for x in data['declared']['vneshn']],
            [('X4231X', 'Z0155', 'Z0155A'),
             ('X316BD', 'Z0152', 'Z0152A'),
             ('X316D', 'Z0152', 'Z0152A')])
        self.assertEqual(c['unknown_refs_total'], 0)

    # (i) Integration: Z0147 has no real declarations; X2000 is a comment.
    def test_z0147_integration(self):
        data = json.loads(self.run_cli(Z0147, '--format', 'json'))
        c = data['counts']
        self.assertEqual(c['vneshn_total'], 0)
        self.assertEqual(c['vhodn_total'], 0)
        self.assertEqual(c['equ_total'], 165)
        names = {x['name'] for x in data['declared']['equ']}
        self.assertNotIn('X2000', names)
        self.assertEqual(c['unknown_refs_total'], 0)

    # (j) Read-only guarantee: scan does not change the source bytes.
    def test_read_only(self):
        with open(Z0137, 'rb') as fh:
            before = hashlib.sha256(fh.read()).hexdigest()
        with open(Z0137, encoding='utf-8') as fh:
            self.scan(fh.read())
        with open(Z0137, 'rb') as fh:
            after = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(before, after)
        with open(TOOL, encoding='utf-8') as fh:
            source = fh.read()
        self.assertNotIn('subprocess', source)
        self.assertNotIn('os.system', source)


if __name__ == '__main__':
    unittest.main()
