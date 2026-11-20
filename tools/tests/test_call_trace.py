"""Unit tests for the parser embedded in tools/call_trace.sh.

The parser is extracted with --emit-parser so that the tests exercise
exactly the code the trace script runs.  No image or dispak run is needed.
"""

import os
import subprocess
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SCRIPT = os.path.join(REPO, 'tools', 'call_trace.sh')


def load_parser():
    proc = subprocess.run(['bash', SCRIPT, '--emit-parser'],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, check=True)
    ns = {}
    exec(proc.stdout, ns)
    return ns


P = load_parser()


class TestParseLine(unittest.TestCase):
    def test_call_with_register(self):
        rec = P['parse_line'](
            '03470: vjm 77316(16)        (=0000660100360114) '
            'acc=0000000000000000 r[16]=03470')
        self.assertEqual(rec['addr'], 0o3470)
        self.assertEqual(rec['mnemonic'], 'vjm')
        self.assertEqual(rec['operand'], '77316(16)')
        self.assertEqual(rec['number'], 0o77316)
        self.assertEqual(rec['reg'], 0o16)  # register numbers are octal
        self.assertEqual(rec['reg_value'], 0o3470)

    def test_store_line_is_ignored(self):
        self.assertIsNone(P['parse_line'](
            '       165465: store 2031463100000000'))
        self.assertIsNone(P['parse_line'](''))
        self.assertIsNone(P['parse_line']('some listing text'))

    def test_register_only_and_negative_operand(self):
        rec = P['parse_line']('02410: uj  (12)  (=1410) acc=0 r[12]=30550')
        self.assertEqual(rec['operand'], '(12)')
        self.assertIsNone(rec['number'])
        self.assertEqual(rec['reg'], 0o12)
        self.assertEqual(P['operand_number']('-73(15)'), -0o73)
        self.assertIsNone(P['operand_number']('(15)'))


class TestSequence(unittest.TestCase):
    def test_next_executed_address(self):
        lines = [
            '03470: vjm 77316(16)  (=0) acc=0 r[16]=03470',
            '77316: vlm 77320(2)   (=0) acc=0 r[2]=77772',
            '       165465: store 0',
            '77320: atx 1         (=0) acc=0',
        ]
        seq = P['build_sequence'](lines)
        self.assertEqual(len(seq), 3)
        self.assertEqual(seq[0]['next_addr'], 0o77316)
        self.assertEqual(seq[1]['next_addr'], 0o77320)
        self.assertIsNone(seq[2]['next_addr'])

    def test_find_calls_and_target_filter(self):
        lines = [
            '02016: vjm 2070(5)   (=0) acc=0 r[5]=74037',
            '02070: atx 2005      (=0) acc=0',
            '04154: vjm 77316(16) (=0) acc=0 r[16]=03726',
            '77316: vlm 77320(2)  (=0) acc=0 r[2]=77772',
        ]
        seq = P['build_sequence'](lines)
        calls = P['find_calls'](seq)
        self.assertEqual(len(calls), 2)
        self.assertEqual([c['number'] for c in calls], [0o2070, 0o77316])
        self.assertEqual(len(P['find_calls'](seq, {0o77316})), 1)
        self.assertEqual([c['next_addr'] for c in calls], [0o2070, 0o77316])

    def test_mnemonic_mapping(self):
        m = P['CALL_MNEMONICS']
        self.assertEqual(m['uj'], 'ПБ')
        self.assertEqual(m['vjm'], 'ПВ')
        self.assertEqual(m['vzm'], 'ПИО')
        self.assertEqual(m['v1m'], 'ПИНО')


class TestSnapshotMap(unittest.TestCase):
    MAP = '''
=== snap-z02000.raw (/tmp/ram-snap/snap-z02000.raw) ===
| snap-z02000.raw | 00 | 00000 | MBE-0147 | 992 | MBE2-0547 | 519 | HIGH |
| snap-z02000.raw | 01 | 02000 | MBE-0154 | 1024 | MBE2-0554 | 465 | EXACT |
| snap-z02000.raw | 37 | 76000 | MBE-0157 | 1024 | MBE2-0557 | 597 | EXACT |
=== snap-z70000.raw (/tmp/ram-snap/snap-z70000.raw) ===
| snap-z70000.raw | 37 | 76000 | MBE-0152 | 1024 | MBE2-0552 | 1024 | EXACT |
'''

    def test_zone_attribution(self):
        sm = P['SnapshotMap'].from_text(self.MAP)
        z = sm.zones_for_addr(0o77316)
        self.assertEqual(set(x[1] for x in z), {'0157', '0152'})
        self.assertIn('0157', sm.classify(0o77316))

    def test_unknown_page(self):
        sm = P['SnapshotMap'].from_text(self.MAP)
        self.assertIn('NO RESIDENT ZONE', sm.classify(0o34562))


if __name__ == '__main__':
    unittest.main()
