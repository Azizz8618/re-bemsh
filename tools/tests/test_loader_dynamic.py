"""Dynamic loader-block tests for zones 0137-0143.

Parser tests use SYNTHETIC trace lines only.
The real-trace test streams B-explore.err once.
It is skipped when that file is absent.

Zone 0137 has no measured base. A PC alone does not
name that zone. Absence of its code in this run is
not proof that the loader never works.
"""

import os
import sys
import unittest
from collections import Counter

REPO = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..'))
TOOLS = os.path.join(REPO, 'tools')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import module_call_trace as mct  # noqa: E402

TRACE = '/tmp/.private/azizz/arap-dyn/B-explore.err'

PAGE_014 = 12       # page 014(8) = 12(10)
PAGE_COND = 8       # page 010(8), conditional base
MONITOR_32 = 26     # page 032(8), PC 064000-065777
PROBE_PAGES = 32
PROBE_OFFSETS = 12
PROBE_TOTAL = PROBE_PAGES * PROBE_OFFSETS   # 384
INIT_WORDS = 5      # 0137.0000-0004
TARGET_1322 = 0o1322

SYNTHETIC = [
    '00010: ntr 7 (=0) acc=0',
    '       165465: store 0',
    '30372: xta 1735(3) (=0) acc=0 r[3]=30000',
    '02760: vjm 1322(16) (=0) acc=0 r[16]=00103',
    '64077: atx 76401(2) (=0) acc=0 r[2]=01777',
    '02000: xta 6065 (=0) acc=0',
    'some listing text',
]


def zone_label(pc):
    """Zone candidates for a PC, None if unmapped."""
    return mct.PAGE_ZONES.get(pc >> 10, (None,))[0]


def unique_zone(pc):
    """Name a zone only when the page has just one."""
    label = zone_label(pc)
    if label and '/' not in label:
        return label
    return None


def init_pcs(base):
    """Candidate PCs for 0137.0000-0004 at a base."""
    if base is None:
        return ()
    return tuple(base + off for off in range(INIT_WORDS))


def probe_hits(addresses):
    """Count addresses in the 32 x 12 probe grid."""
    return sum(1 for addr in addresses
               if (addr >> 10) < PROBE_PAGES
               and (addr & 0o1777) < PROBE_OFFSETS)


class LoaderScan(object):
    """Small summary built in one streaming pass."""

    def __init__(self):
        self.lines = 0
        self.instructions = 0
        self.stores = 0
        self.other = 0
        self.dd_lines = 0
        self.monitor_32_atx = 0
        self.vjm_1322 = 0
        self.vjm_1322_pc = []
        self.ntr7_pc = []
        self.low_pc = Counter()
        self.page_insn = Counter()
        self.pc02000 = []

    def feed(self, line):
        self.lines += 1
        if 'DD pc=' in line:
            self.dd_lines += 1
        if mct.STORE_RE.match(line):
            self.stores += 1
            return
        rec = mct.parse_line(line)
        if rec is None:
            self.other += 1
            return
        self.instructions += 1
        page = rec['page']
        self.page_insn[page] += 1
        if rec['pc'] < INIT_WORDS:
            self.low_pc[rec['pc']] += 1
        if (rec['mnemonic'] == 'vjm' and
                mct.call_target(rec) == TARGET_1322):
            self.vjm_1322 += 1
            if len(self.vjm_1322_pc) < 8:
                self.vjm_1322_pc.append(rec['pc'])
        if (rec['mnemonic'] == 'ntr' and
                rec['operand'] == '7'):
            self.ntr7_pc.append(rec['pc'])
        if (page == MONITOR_32 and
                rec['mnemonic'] == 'atx' and
                (rec['number'] or 0) >= 0o76000):
            self.monitor_32_atx += 1
        if rec['pc'] == 0o2000 and len(self.pc02000) < 8:
            self.pc02000.append(rec['raw'])


def scan_trace(path):
    """Stream a dispak -tt trace, keep only counters."""
    scan = LoaderScan()
    with open(path, 'r', encoding='utf-8',
              errors='replace') as fh:
        for line in fh:
            scan.feed(line)
    return scan


class TestSyntheticParser(unittest.TestCase):
    def test_ntr7_line_is_zone_0147_not_0137(self):
        rec = mct.parse_line(SYNTHETIC[0])
        self.assertEqual(rec['pc'], 0o10)
        self.assertEqual(rec['mnemonic'], 'ntr')
        self.assertEqual(rec['operand'], '7')
        self.assertEqual(unique_zone(rec['pc']), '0147')

    def test_store_is_not_an_instruction(self):
        self.assertIsNone(mct.parse_line(SYNTHETIC[1]))
        self.assertIsNotNone(
            mct.STORE_RE.match(SYNTHETIC[1]))

    def test_vjm_target_is_literal_not_link(self):
        rec = mct.parse_line(SYNTHETIC[3])
        self.assertEqual(rec['number'], TARGET_1322)
        self.assertEqual(rec['reg_value'], 0o103)
        self.assertEqual(mct.call_target(rec), TARGET_1322)

    def test_page_never_names_an_overlay_zone(self):
        self.assertEqual(unique_zone(0o1322), '0147')
        self.assertIsNone(unique_zone(0o2000))
        self.assertIsNone(unique_zone(0o30372))
        self.assertEqual(zone_label(0o2000),
                         '0154/0170/0172')

    def test_unknown_base_gives_no_init_candidates(self):
        self.assertEqual(init_pcs(None), ())
        self.assertEqual(
            init_pcs(0o10000),
            (0o10000, 0o10001, 0o10002,
             0o10003, 0o10004))

    def test_probe_grid_has_384_addresses(self):
        self.assertEqual(PROBE_TOTAL, 384)
        self.assertEqual(probe_hits([]), 0)
        self.assertEqual(probe_hits([0o2005]), 1)
        self.assertEqual(probe_hits([0o20020]), 0)
        self.assertEqual(probe_hits([0o77001]), 0)
        self.assertEqual(
            probe_hits([0o20005, 0o76001]), 2)


class TestSyntheticScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scan = LoaderScan()
        for line in SYNTHETIC:
            cls.scan.feed(line)

    def test_counts(self):
        s = self.scan
        self.assertEqual(s.lines, 7)
        self.assertEqual(s.instructions, 5)
        self.assertEqual(s.stores, 1)
        self.assertEqual(s.other, 1)
        self.assertEqual(
            s.lines, s.instructions + s.stores + s.other)

    def test_loader_observations(self):
        s = self.scan
        self.assertEqual(s.page_insn[PAGE_014], 1)
        self.assertEqual(s.vjm_1322, 1)
        self.assertEqual(s.vjm_1322_pc, [0o2760])
        self.assertEqual(s.ntr7_pc, [0o10])
        self.assertEqual(s.monitor_32_atx, 1)
        self.assertEqual(s.pc02000[0],
                         '02000: xta 6065 (=0) acc=0')

    def test_proven_aggregator_agrees_on_page(self):
        stats = mct.TraceStats()
        for line in SYNTHETIC:
            stats.feed(line)
        self.assertEqual(stats.insn_by_page[PAGE_014], 1)
        self.assertEqual(stats.store_lines, 1)


@unittest.skipUnless(
    os.path.exists(TRACE),
    'large trace %s is not present' % TRACE)
class TestRealTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scan = scan_trace(TRACE)

    def test_stream_totals(self):
        s = self.scan
        self.assertEqual(s.lines, 5141914)
        self.assertGreater(s.instructions, 1000000)
        self.assertGreater(s.stores, 0)
        self.assertEqual(
            s.lines, s.instructions + s.stores + s.other)

    def test_page_014_executes_without_zone_map(self):
        s = self.scan
        self.assertEqual(s.page_insn[PAGE_014], 12680)
        self.assertIsNone(
            mct.page_info(PAGE_014)['zones'])
        self.assertIsNone(zone_label(0o30372))

    def test_vjm_1322_is_observed(self):
        s = self.scan
        self.assertEqual(s.vjm_1322, 31)
        self.assertEqual(len(s.vjm_1322_pc), 8)

    def test_no_0137_init_signature_in_this_run(self):
        s = self.scan
        self.assertEqual(s.ntr7_pc, [0o10])
        self.assertEqual(len(s.low_pc), 0)
        self.assertEqual(s.page_insn[PAGE_COND], 0)
        self.assertEqual(init_pcs(None), ())

    def test_monitor_copy_loop_is_observed(self):
        s = self.scan
        self.assertGreater(s.monitor_32_atx, 20000)

    def test_overlay_boundary_evidence(self):
        s = self.scan
        self.assertEqual(s.dd_lines, 0)
        text = ' '.join(s.pc02000)
        self.assertIn('02000: xta 6065', text)
        self.assertIn('ntr 3', text)
        self.assertIsNone(unique_zone(0o2000))


if __name__ == '__main__':
    unittest.main()
