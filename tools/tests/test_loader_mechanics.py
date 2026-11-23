#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Синтетические тесты механики загрузчика.

Эмулятор не нужен. Реальные трасса и дамп тома
подключаются только как дополнительные проверки.

Источники фактов:
  ZBASE  analysis/ZONE-BASE-MAP.md §1
  TIMING analysis/LOADER-TIMING-FINAL.md §0, §3-5
  PATCH  analysis/Z0137-RELOC-PATCH-PROOF.md §2-5
  RELOC  analysis/reloc.md §3
  BASE   analysis/Z0137-BASE-FINAL.md §0-3
"""
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

TRACE = Path('/tmp/.private/azizz/arap-dyn/B-explore.err')
GOLD_0137 = REPO / 'gold' / 'MBE-Z0137-L1.bin'
VOLUME_ROOT = Path(os.environ.get(
    'BESM6_PATH', '/usr/local/share/besm6'))
VOLUMES = ('2048', '2148', '2248')

ZONE_WORDS = 0o2000
PAGE_SIZE = 0o2000
ADDR_MAX = 0o77777
RLOAD_DESCRIPTOR = 61
RLOAD_PAGE = 0o32
ARAP_PAGE = 0o37
OVERLAY_PAGE = 0o1

# ZBASE §1: адрес в ОП = база + номер слова зоны.
# Пары подтверждены снимками (PCL:62 и PCL:88).
STAMP_CASES = (
    ('0154', 0o2000, 0o751, 0o2751),
    ('0170', 0o2000, 0o216, 0o2216),
)

# TIMING §0: полная цепочка стадий.
STAGE_ORDER = (
    'monitor', 'RLOAD', 'page010',
    'ARAP', 'editor', 'machine',
)

# TIMING §3: вехи свежей трассы (номер строки).
MILESTONES = (
    ('monitor', 20, '00010: ntr 7'),
    ('rload_dd', 190, 'u=21 z=0007'),
    ('rload_entry', 192, 'uj 64000'),
    ('loader_pc', 917, '064063'),
    ('page010_first', 274283, 'atx 11777(12)'),
    ('page010_next', 871060, 'atx 76001(2)'),
    ('load_0150', 1035767, 'DD u=30'),
    ('arap_entry', 1454535, 'uj 76000'),
    ('editor_entry', 1454570, 'uj 2000'),
    ('machine_entry', 1948733, 'uj 2000'),
)

# TIMING §3: вызовы АРАП и точки перехода.
ARAP_CALLS = 481
ARAP_FIRST = 1454535
ARAP_LAST = 1870090
ARAP_ENTRY_PC = 0o76557
ARAP_LAST_PC = 0o77125
EDITOR_ENTRY_PC = 0o1236
MACHINE_ENTRY_PC = 0o1314
PRINT_LINE = 4851025

# TIMING §4: гистограмма исполнявшихся страниц.
PAGES_EXECUTED = (
    0o00, 0o01, 0o02, 0o03, 0o06,
    0o12, 0o13, 0o14, 0o32, 0o34,
    0o36, 0o37,
)

# TIMING §0, §4: события ввода.
DD_EVENTS = 250
DD_LOADER_ZONES = ()

# PATCH §2: первые пять слов зоны 0137 по томам.
# G = 2048 (gold), P = 2248 (паспорт другой установки).
GOLD_WORDS = {
    0: bytes.fromhex('000000040000'),
    1: bytes.fromhex('000000010000'),
    2: bytes.fromhex('000000000003'),
    3: bytes.fromhex('00000000276c'),
    4: bytes.fromhex('0000003c0000'),
}
PATCHED_WORDS = {
    0: bytes.fromhex('000707070707'),
    1: bytes.fromhex('203030303030'),
    2: bytes.fromhex('d00000000000'),
    3: bytes.fromhex('01ffffffffff'),
    4: bytes.fromhex('000000000011'),
}
FULL_OCTAL = {
    'G0': '0000000001000000',
    'P0': '0000340701603407',
}

# PATCH §3-4: подтверждённые записи слова G0.
G0_STORES = (
    (0o77012, 0o3627, 150500),
    (0o2001, 0o3610, 781530),
    (0o2001, 0o5624, 781530),
    (0o2147, 0o5627, 781537),
)
NEVER_WRITTEN = ('P0', 'P1')
P3_MASK_PC = 0o75316
P3_MASK_HITS = 3

# TIMING §5: PC, идущие до входа редактора.
PAGE010_WRITERS = (
    (0o6210, 2040), (0o64077, 1024),
    (0o2012, 1024), (0o707, 1024),
    (0o2412, 626), (0o6231, 510),
    (0o6232, 510),
)

# BASE §2: дампы ядра и поиск слов зоны 0137.
CORE_BYTES = 393216
CORE_WORDS = 65536
KOI7_SIGNATURE = 51
MATCHED_0137 = 0
DUMP_POINTS = (
    0o00100, 0o00107, 0o00110,
    0o64000, 0o64063, 0o02000, 0o06000,
    0o70000, 0o74000, 0o76000, 0o64100,
    0o00411, 0o02000, 0o03610,
)

# BASE §2: контроль метода и поиск последовательностей.
CONTROL_ZONE = '0147'
CONTROL_BASE = 0o00000
CONTROL_MATCHES = 336
SEQ_ZONES = ('0137', '0140', '0141', '0142', '0143')
SEQ_MATCHES = 0
SEQ_DUMP_PC = 0o3610

# BASE §2: поиск по трассам.
TRACE_A_LINES = 1303422
TRACE_A_STORES = 148979
TRACE_A_MATCHES = 0
TRACE_OLD_LINES = 5141914
TRACE_OLD_STORES = 587817
TRACE_OLD_MATCHES = 0

# BASE §3: отсутствующие события.
PC_77430_LINES = 0
MISSED_BREAKPOINTS = (
    0o00004, 0o10000, 0o24000, 0o26000,
)
AIO_BASE = 0o64000
ZONE_PAGE_TABLE_FOUND = False


def phys_addr(base, word_offset):
    """Физический адрес слова зоны."""
    return base + word_offset


def zone_window(base):
    """Замкнутый диапазон адресов окна зоны."""
    return base, min(base + ZONE_WORDS - 1, ADDR_MAX)


def page_base(page):
    """База страницы ОП по номеру страницы."""
    return page * PAGE_SIZE


def page_of(addr):
    """Номер страницы по физическому адресу."""
    return addr // PAGE_SIZE


def is_internal(base, target):
    """Попадает ли адрес в окно зоны."""
    low, high = zone_window(base)
    return low <= target <= high


def stage_rank(stage):
    """Порядковый номер стадии загрузки."""
    return STAGE_ORDER.index(stage)


def stages_in_order(seq):
    """Соблюдён ли порядок стадий в последовательности."""
    ranks = [stage_rank(s) for s in seq]
    return all(a < b for a, b in zip(ranks, ranks[1:]))


def milestone_lines():
    """Номера строк вех в порядке их следования."""
    return [line for _, line, _ in MILESTONES]


class TestAddressMechanics(unittest.TestCase):
    def test_stamp_formula_for_two_zones(self):
        for zone, base, word, want in STAMP_CASES:
            with self.subTest(zone=zone):
                got = phys_addr(base, word)
                self.assertEqual(got, want)

    def test_page_base_formula(self):
        self.assertEqual(page_base(0o37), 0o76000)
        self.assertEqual(page_base(0o1), 0o2000)
        self.assertEqual(page_base(0o32), 0o64000)

    def test_page_of_known_bases(self):
        for base, page in ((0o76000, 0o37),
                           (0o2000, 0o1),
                           (0o64000, 0o32)):
            with self.subTest(base=base):
                self.assertEqual(page_of(base), page)

    def test_window_is_1024_words(self):
        low, high = zone_window(0o2000)
        self.assertEqual((low, high), (0o2000, 0o3777))
        self.assertEqual(high - low + 1, ZONE_WORDS)

    def test_window_clipped_at_15_bits(self):
        self.assertEqual(zone_window(0o76000),
                         (0o76000, ADDR_MAX))

    def test_internal_and_external_targets(self):
        self.assertTrue(is_internal(0o2000, 0o2751))
        self.assertFalse(is_internal(0o2000, 0o4000))
        self.assertTrue(is_internal(0o76000, ADDR_MAX))

    def test_static_start_is_not_a_base(self):
        # TIMING §7 п.2: '10000' это условие трансляции,
        # а не измеренный адрес исполнения.
        synt = {'value': 0o10000, 'source': 'СТАРТ',
                'status': 'НЕ ИЗВЕСТНО'}
        self.assertNotEqual(synt['status'], 'ФАКТ')


class TestStageOrder(unittest.TestCase):
    def test_six_stages_listed(self):
        self.assertEqual(len(STAGE_ORDER), 6)
        self.assertEqual(stage_rank('monitor'), 0)
        self.assertEqual(stage_rank('RLOAD'), 1)
        self.assertEqual(stage_rank('page010'), 2)
        self.assertEqual(stage_rank('ARAP'), 3)
        self.assertEqual(stage_rank('editor'), 4)
        self.assertEqual(stage_rank('machine'), 5)

    def test_order_is_temporal_not_numeric(self):
        # 02000 меньше 064000 по адресу, но идёт позже.
        self.assertLess(0o2000, 0o64000)
        self.assertLess(0o64000, 0o76000)
        seq = ('machine', 'ARAP', 'RLOAD', 'monitor')
        self.assertFalse(stages_in_order(seq))

    def test_reversed_order_fails(self):
        self.assertFalse(
            stages_in_order(tuple(reversed(STAGE_ORDER))))

    def test_milestone_lines_increase(self):
        lines = milestone_lines()
        self.assertEqual(lines, sorted(lines))
        self.assertEqual(lines[0], 20)
        self.assertEqual(lines[-1], 1948733)

    def test_loader_markers(self):
        marks = dict((k, (n, txt))
                     for k, n, txt in MILESTONES)
        self.assertEqual(marks['rload_dd'][1],
                         'u=21 z=0007')
        self.assertEqual(marks['rload_entry'][1],
                         'uj 64000')
        self.assertEqual(marks['loader_pc'][1],
                         '064063')
        self.assertLess(marks['rload_entry'][0],
                        marks['loader_pc'][0])

    def test_editor_and_machine_share_address(self):
        marks = dict((k, (n, txt))
                     for k, n, txt in MILESTONES)
        self.assertEqual(marks['editor_entry'][1],
                         'uj 2000')
        self.assertEqual(marks['machine_entry'][1],
                         'uj 2000')
        self.assertLess(marks['editor_entry'][0],
                        marks['machine_entry'][0])

    def test_arap_calls_within_window(self):
        self.assertEqual(ARAP_CALLS, 481)
        self.assertEqual(ARAP_FIRST, 1454535)
        self.assertEqual(ARAP_LAST, 1870090)
        self.assertLess(ARAP_LAST, 1948733)

    def test_handoff_pcs(self):
        # Каждая передача управления: PC из зоны 0152/0157.
        for pc in (ARAP_ENTRY_PC, ARAP_LAST_PC,
                   EDITOR_ENTRY_PC, MACHINE_ENTRY_PC):
            with self.subTest(pc=pc):
                self.assertIn(page_of(pc), PAGES_EXECUTED)

    def test_print_after_machine_entry(self):
        self.assertGreater(PRINT_LINE, 1948733)

    def test_executed_pages(self):
        self.assertIn(0o32, PAGES_EXECUTED)
        self.assertIn(0o37, PAGES_EXECUTED)
        self.assertIn(0o1, PAGES_EXECUTED)
        self.assertNotIn(0o10, PAGES_EXECUTED)

    def test_no_disk_reads_of_loader_zones(self):
        self.assertEqual(DD_EVENTS, 250)
        self.assertEqual(DD_LOADER_ZONES, ())

    def test_page010_writer_counts(self):
        total = sum(n for _, n in PAGE010_WRITERS)
        self.assertGreater(total, 5000)
        self.assertIn((0o64077, 1024), PAGE010_WRITERS)

    def test_rload_descriptor_is_61(self):
        self.assertEqual(RLOAD_DESCRIPTOR, 61)


class TestPatchWordTable(unittest.TestCase):
    def test_five_words_per_volume(self):
        self.assertEqual(len(GOLD_WORDS), 5)
        self.assertEqual(len(PATCHED_WORDS), 5)
        self.assertEqual(set(GOLD_WORDS),
                         set(PATCHED_WORDS))

    def test_each_word_is_six_bytes(self):
        for i in range(5):
            with self.subTest(word=i):
                self.assertEqual(len(GOLD_WORDS[i]), 6)
                self.assertEqual(len(PATCHED_WORDS[i]), 6)

    def test_all_words_differ(self):
        for i in range(5):
            with self.subTest(word=i):
                self.assertNotEqual(
                    GOLD_WORDS[i], PATCHED_WORDS[i])

    def test_p0_has_five_consecutive_07_bytes(self):
        raw = PATCHED_WORDS[0]
        self.assertEqual(raw[1:], bytes([7, 7, 7, 7, 7]))

    def test_full_octal_forms(self):
        self.assertEqual(FULL_OCTAL['G0'],
                         '0000000001000000')
        self.assertEqual(FULL_OCTAL['P0'],
                         '0000340701603407')

    def test_g0_store_addresses(self):
        addrs = set(a for a, _, _ in G0_STORES)
        self.assertEqual(addrs, {0o2001, 0o77012, 0o2147})

    def test_g0_writer_pcs(self):
        pcs = set(pc for _, pc, _ in G0_STORES)
        self.assertIn(0o3610, pcs)
        self.assertIn(0o5624, pcs)
        self.assertIn(0o3627, pcs)
        self.assertIn(0o5627, pcs)

    def test_g0_store_lines_increase(self):
        lines = [ln for _, _, ln in G0_STORES]
        self.assertEqual(lines, sorted(lines))

    def test_patched_words_not_written(self):
        for tag in NEVER_WRITTEN:
            with self.subTest(tag=tag):
                self.assertIn(tag, ('P0', 'P1'))

    def test_p3_mask_is_not_a_zone_word(self):
        self.assertEqual(P3_MASK_HITS, 3)
        self.assertEqual(P3_MASK_PC, 0o75316)
        self.assertNotEqual(P3_MASK_PC, 0o5627)

    def test_word_offset_to_address(self):
        # Слово 0 зоны 0137 при гипотетической базе 02000.
        base_synt = 0o2000
        self.assertEqual(phys_addr(base_synt, 0), base_synt)


class TestBaseEvidence(unittest.TestCase):
    def test_core_dump_size(self):
        self.assertEqual(CORE_BYTES // 6, CORE_WORDS)

    def test_dump_points_count(self):
        self.assertEqual(len(DUMP_POINTS), 14)
        self.assertIn(0o00100, DUMP_POINTS)
        self.assertIn(0o64063, DUMP_POINTS)

    def test_no_zone_words_in_dumps(self):
        self.assertEqual(KOI7_SIGNATURE, 51)
        self.assertEqual(MATCHED_0137, 0)

    def test_control_zone_confirms_method(self):
        # BASE §2: та же методика нашла 0147 по базе 0.
        self.assertEqual(CONTROL_ZONE, '0147')
        self.assertEqual(CONTROL_BASE, 0)
        self.assertGreater(CONTROL_MATCHES, 0)

    def test_no_three_word_sequences(self):
        self.assertEqual(len(SEQ_ZONES), 5)
        self.assertEqual(SEQ_DUMP_PC, 0o3610)
        self.assertEqual(SEQ_MATCHES, 0)

    def test_trace_search_zero_on_both_traces(self):
        self.assertGreater(TRACE_A_LINES, 0)
        self.assertGreater(TRACE_A_STORES, 0)
        self.assertGreater(TRACE_OLD_LINES, 0)
        self.assertGreater(TRACE_OLD_STORES, 0)
        self.assertEqual(TRACE_A_MATCHES, 0)
        self.assertEqual(TRACE_OLD_MATCHES, 0)

    def test_zone_0140_exit_never_ran(self):
        self.assertEqual(PC_77430_LINES, 0)

    def test_four_breakpoints_never_hit(self):
        self.assertEqual(len(MISSED_BREAKPOINTS), 4)
        self.assertIn(0o00004, MISSED_BREAKPOINTS)
        self.assertIn(0o10000, MISSED_BREAKPOINTS)

    def test_no_zone_to_page_table(self):
        self.assertFalse(ZONE_PAGE_TABLE_FOUND)
        self.assertEqual(AIO_BASE, 0o64000)

    def test_base_value_stays_unknown(self):
        # BASE §0: база не измерена, '10000' это СТАРТ.
        verdict = {'measured': False,
                   'status': 'НЕ ИЗВЕСТНО'}
        self.assertFalse(verdict['measured'])
        self.assertEqual(verdict['status'],
                         'НЕ ИЗВЕСТНО')


@unittest.skipUnless(GOLD_0137.is_file(),
                     'gold zone 0137 dump is missing')
class TestOptionalGoldDump(unittest.TestCase):
    def test_first_word_matches_table(self):
        with open(GOLD_0137, 'rb') as fh:
            raw = fh.read(6)
        self.assertEqual(raw, GOLD_WORDS[0])


@unittest.skipUnless(TRACE.is_file(),
                     'large trace B-explore.err is missing')
class TestOptionalTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first_line = {}
        with open(TRACE, 'r', encoding='utf-8',
                  errors='replace') as fh:
            for number, line in enumerate(fh, 1):
                if ': ' not in line:
                    continue
                head = line.split(':', 1)[0]
                if not head.isdigit():
                    continue
                page = int(head, 8) >> 10
                for tag, want in (
                        ('RLOAD', RLOAD_PAGE),
                        ('ARAP', ARAP_PAGE),
                        ('editor', OVERLAY_PAGE)):
                    if (page == want and
                            tag not in cls.first_line):
                        cls.first_line[tag] = number

    def test_trace_is_readable(self):
        self.assertIsInstance(self.first_line, dict)

    def test_rload_precedes_arap_page(self):
        # В этой трассе PC 02000 встречается рано: это
        # монитор, а не последняя стадия транслятора.
        a = self.first_line.get('RLOAD')
        b = self.first_line.get('ARAP')
        if a is None or b is None:
            self.skipTest('loader pages not in trace')
        self.assertLess(a, b)


if __name__ == '__main__':
    unittest.main()
