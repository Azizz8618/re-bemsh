"""Unit tests for tools/module_call_trace.py.

All parser tests use SYNTHETIC trace lines.
The optional integration test is skipped unless
the large trace file is present.
"""

import os
import sys
import unittest

REPO = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..'))
TOOLS = os.path.join(REPO, 'tools')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import module_call_trace as mct  # noqa: E402

TRACE = '/tmp/.private/azizz/arap-dyn/B-explore.err'


class TestParseLine(unittest.TestCase):
    def test_pc_and_page(self):
        rec = mct.parse_line(
            '03651: wtc 2157(1)          '
            '(=6040000000065366) '
            'acc=2031463100000000 r[1]=00141')
        self.assertEqual(rec['pc'], 0o3651)
        self.assertEqual(rec['page'], 1)
        self.assertEqual(rec['mnemonic'], 'wtc')
        self.assertEqual(rec['operand'], '2157(1)')
        self.assertEqual(rec['reg'], 1)
        self.assertEqual(rec['reg_value'], 0o141)

    def test_low_and_high_core_pages(self):
        rec0 = mct.parse_line(
            '00010: ntr 7 (=0) acc=0')
        self.assertEqual(rec0['page'], 0)
        rec = mct.parse_line(
            '74100: uj 76000 (=0) acc=0')
        self.assertEqual(rec['page'], 30)
        self.assertEqual(
            mct.page_info(rec['page'])['page_octal'],
            '36')
        rec31 = mct.parse_line(
            '77600: atx 1 (=0) acc=0')
        self.assertEqual(rec31['page'], 31)

    def test_store_address_before_colon(self):
        line = '       165465: store 2031463100000000'
        self.assertIsNone(mct.parse_line(line))
        self.assertIsNotNone(mct.STORE_RE.match(line))
        stats = mct.TraceStats()
        stats.feed('03651: atx 65465 (=0) acc=0')
        stats.feed(line)
        self.assertEqual(stats.instructions, 1)
        self.assertEqual(stats.store_lines, 1)
        self.assertEqual(
            stats.store_sample.strip(), line.strip())

    def test_other_lines_are_ignored(self):
        stats = mct.TraceStats()
        stats.feed('')
        stats.feed('some listing text')
        stats.feed('WATCH 00010L ntr')
        self.assertEqual(stats.instructions, 0)
        self.assertEqual(stats.other_lines, 3)


class TestOperandAndTarget(unittest.TestCase):
    def test_operand_number(self):
        self.assertEqual(
            mct.operand_number('65465'), 0o65465)
        self.assertEqual(
            mct.operand_number('-73(15)'),
            (0o100000 - 0o73) & 0o77777)
        self.assertIsNone(mct.operand_number('(15)'))

    def test_vjm_target_is_literal_not_link(self):
        rec = mct.parse_line(
            '03470: vjm 77316(16)        '
            '(=0000660100360114) '
            'acc=0000000000000000 r[16]=03470')
        self.assertEqual(rec['number'], 0o77316)
        self.assertEqual(rec['reg_value'], 0o3470)
        self.assertEqual(mct.call_target(rec), 0o77316)

    def test_uj_target_is_literal_plus_index(self):
        rec = mct.parse_line(
            '26151: uj  11(14) (=0) acc=0 '
            'r[14]=26150')
        self.assertEqual(mct.call_target(rec), 0o26161)
        plain = mct.parse_line(
            '01331: uj 74002 (=0) acc=0')
        self.assertEqual(mct.call_target(plain), 0o74002)
        indirect = mct.parse_line(
            '70075: uj  (13) (=0) acc=0 '
            'r[13]=70006')
        self.assertEqual(mct.call_target(indirect),
                         0o70006)

    def test_unresolved_call(self):
        rec = mct.parse_line(
            '02000: vjm (16) (=0) acc=0 r[16]=00001')
        self.assertIsNone(mct.call_target(rec))


class TestAggregation(unittest.TestCase):
    def test_page_stats_and_edges(self):
        lines = [
            '02000: ntr 3          (=0) acc=0',
            '02760: vjm 1322(16)   (=0) acc=0 '
            'r[16]=00103',
            '03443: uj  157(2)     (=0) acc=0 '
            'r[2]=74000',
            '       165465: store 0',
            '01322: uj  (13)       (=0) acc=0 '
            'r[13]=02761',
        ]
        stats = mct.TraceStats()
        for line in lines:
            stats.feed(line)
        res = stats.result(10)
        self.assertEqual(res['instructions'], 4)
        self.assertEqual(res['store_lines'], 1)
        self.assertEqual(res['calls_vjm'], 1)
        self.assertEqual(res['calls_uj'], 2)
        self.assertEqual(res['calls_resolved'], 3)
        self.assertEqual(stats.insn_by_page[1], 3)
        self.assertEqual(stats.insn_by_page[0], 1)
        self.assertIn((1, 0), stats.edges)
        self.assertIn((1, 30), stats.edges)
        self.assertIn(0o1322,
                      stats.targets_by_page[1])
        self.assertIn(1, stats.callers_by_page[0])

    def test_text_and_json_output(self):
        stats = mct.TraceStats()
        stats.feed('02000: vjm 1322(16) (=0) '
                   'acc=0 r[16]=0')
        res = stats.result(1)
        text = mct.render_text(res, 'synthetic.err')
        self.assertIn('MODULE CALL TRACE', text)
        self.assertIn('TOP PAGE EDGES', text)
        self.assertIn('01', text)


@unittest.skipUnless(
    os.path.exists(TRACE),
    'large trace %s is not present' % TRACE)
class TestOptionalIntegration(unittest.TestCase):
    def test_real_trace_streams_once(self):
        stats = mct.TraceStats()
        with open(TRACE, 'r', encoding='utf-8',
                  errors='replace') as fh:
            for line in fh:
                stats.feed(line)
        self.assertGreater(stats.instructions, 1000000)
        self.assertGreater(stats.store_lines, 0)
        total = (stats.instructions + stats.store_lines +
                 stats.other_lines)
        self.assertEqual(total, stats.lines)
        res = stats.result(5)
        self.assertGreater(res['calls_resolved'], 0)
        self.assertLessEqual(len(res['pages']), 5)


if __name__ == '__main__':
    unittest.main()
