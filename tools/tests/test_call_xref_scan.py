#!/usr/bin/env python3
"""Тесты tools/call_xref_scan.py (только stdlib, unittest)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import call_xref_scan as cx  # noqa: E402

ROOT = str(Path(__file__).resolve().parents[2])

TAB = '\t'
HEAD = ('          File: fake\n'
        '         Type: Binary\n'
        '         Code: 6144 (02000) words\n'
        '      Address: 0\n'
        '\n')


def write_tree(files):
    """Создать временный корень с минимальными входными файлами."""
    tmp = tempfile.TemporaryDirectory()
    base = tmp.name
    for rel, content in files.items():
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(content)
    return tmp, base


def listing(*rows):
    """Собрать текст листинга из строк ''address-field<TAB>...''."""
    return HEAD + '\n'.join(rows) + '\n'


class TestNarrowedInstructionSet(unittest.TestCase):
    def test_only_four_call_mnemonics(self):
        self.assertEqual(cx.CALL_MNEMONICS,
                         frozenset(('пб', 'пв', 'пио', 'пино', 'пио36')))
        for dropped in ('по', 'пе', 'цикл', 'выпр', 'нтж', 'пво', 'вжм'):
            self.assertNotIn(dropped, cx.CALL_MNEMONICS)

    def test_pio_and_pio36_counted_but_po_pe_dropped(self):
        rows = (
            '    0 00 36 34562 ' + TAB + TAB + 'пио' + TAB + "'34562'\n",
            '    1 00 36 34563 ' + TAB + TAB + 'пио36' + TAB +
            "'34563'\n",
            '    2 00 36 34564 ' + TAB + TAB + 'пино' + TAB +
            "'34564'\n",
            '    3 00 26 34565 ' + TAB + TAB + 'по' + TAB + "'34565'\n",
            '    4 00 27 34566 ' + TAB + TAB + 'пе' + TAB + "'34566'\n",
            '    5 00 37 34567 ' + TAB + TAB + 'цикл' + TAB +
            "'34567'\n",
        )
        tmp, base = write_tree({
            'dis-forced/Z0140.asm': listing(*rows),
            'sym/GLOBAL.tab': '',
            'analysis/MEMORY-MAP.md': '',
        })
        try:
            raw, _, _, _ = cx.scan_listings(base)
            self.assertEqual([r['mnem'] for r in raw],
                             ['пио', 'пио36', 'пино'])
            self.assertEqual([r['value'] for r in raw],
                             ['34562', '34563', '34564'])
        finally:
            tmp.cleanup()

    def test_second_half_inherits_address_and_local_is_excluded(self):
        rows = (
            '    7 00 30 02000 ' + TAB + TAB + 'пб' + TAB + "'2000'\n",
            '      16 31 77316 ' + TAB + TAB + 'пв' + TAB +
            "'77316'(М16)\n",
            '   10 00 30 01400 ' + TAB + TAB + 'пб' + TAB + "'1400'\n",
        )
        tmp, base = write_tree({'dis-forced/Z0155.asm': listing(*rows)})
        try:
            raw, _, _, _ = cx.scan_listings(base)
            self.assertEqual(len(raw), 2)
            self.assertEqual([r['addr'] for r in raw], [7, 7])
            self.assertEqual([r['mod'] for r in raw], ['-', 'М16'])
        finally:
            tmp.cleanup()


class TestDedupAndClassification(unittest.TestCase):
    def test_overlap_of_two_listings_deduplicated(self):
        rows = ('   20 00 30 41140 ' + TAB + TAB + 'пб' + TAB +
                "'41140'\n",)
        tmp, base = write_tree({
            'dis-forced/Z0142.asm': listing(*rows),
            'dis/MBE-Z0142-L1.asm': listing(*rows),
        })
        try:
            raw, meta, _, _ = cx.scan_listings(base)
            self.assertEqual(len(meta), 2)
            self.assertEqual(len(raw), 2)
            dedup = cx.dedup(raw)
            self.assertEqual(len(dedup), 1)
            self.assertEqual(dedup[0]['raw_count'], 2)
            self.assertEqual(dedup[0]['file'], 'Z0142.asm')
        finally:
            tmp.cleanup()

    def test_known_symbol_page_and_unresolved(self):
        tmp, base = write_tree({
            'sym/GLOBAL.tab': '02000 2 MAC_EDITOR_LOAD\n'
                              '70000 0 SYSCALL_GATE\n',
            'analysis/MEMORY-MAP.md':
                '| Диск. зона | Адрес ОП | Страница | Точных |\n'
                '|---|---|---|---|\n'
                '| 0157 | `76000₈` | 37 | 1024 |\n',
        })
        try:
            symbols = cx.load_symbols(base)
            pages = cx.load_pages(base)
            self.assertEqual(symbols[0o2000][0], 'MAC_EDITOR_LOAD')
            self.assertEqual(pages['37'][0][0], '0157')
            self.assertEqual(cx.page_of(0o77316), '37')
            self.assertEqual(cx.page_of(0o2070), '01')
            ref = {'zone': '0155', 'mnem': 'пв', 'value': '77316',
                   'value_int': 0o77316, 'file': 'Z0155.asm', 'line': 12,
                   'addr': 12}
            self.assertEqual(cx.classify(ref, symbols, pages, set(), {})[0],
                             cx.CLASS_PAGE)
            ref['value'] = '2000'
            ref['value_int'] = 0o2000
            self.assertEqual(cx.classify(ref, symbols, pages, set(), {})[0],
                             cx.CLASS_KNOWN)
            ref['value'] = '34562'
            ref['value_int'] = 0o34562
            self.assertEqual(cx.classify(ref, symbols, pages, set(), {})[0],
                             cx.CLASS_UNKNOWN)
        finally:
            tmp.cleanup()

    def test_repeated_word_is_an_address_not_a_data_pattern(self):
        rows = []
        for addr in (74, 75, 76):
            rows.append('%5s 00 30 27615 ' % addr + TAB + TAB + 'пб' +
                        TAB + "'27615'\n")
            rows.append('      00 30 27615 ' + TAB + TAB + 'пб' + TAB +
                        "'27615'\n")
        tmp, base = write_tree({'dis-forced/Z0162.asm': listing(*rows)})
        try:
            raw, _, dup, _ = cx.scan_listings(base)
            fills = cx.fill_addresses(dup)
            # адреса в листинге восьмеричные: 74к8 = 60, 75к8 = 61.
            self.assertEqual(fills,
                             set((('0162', 'пб', '27615', a)
                                  for a in (0o74, 0o75, 0o76))))
            dedup = cx.dedup(raw)
            self.assertEqual(len(dedup), 3)
            for r in dedup:
                cls = cx.classify(r, {}, {}, fills, {})[0]
                self.assertNotEqual(cls, cx.CLASS_FP)
                self.assertEqual(cls, cx.CLASS_UNKNOWN)
        finally:
            tmp.cleanup()


class TestRealData(unittest.TestCase):
    def test_compact_names_are_short_and_unique(self):
        data = cx.build(ROOT)
        compacts = [t['compact'] for t in data['top']]
        self.assertTrue(all(len(c) <= 6 for c in compacts))
        self.assertEqual(len(compacts), len(set(compacts)))
        self.assertTrue(all(c.startswith('X') for c in compacts))

    def test_real_data_counts_match_report(self):
        s = cx.build(ROOT)['stats']
        self.assertEqual(s['listings'], 56)
        self.assertEqual(s['raw_refs'], 4196)
        self.assertEqual(s['dedup_refs'], 4071)
        self.assertEqual(s['groups'], 1987)
        self.assertEqual(s['targets'], 1449)
        self.assertEqual(s['by_mnem']['пио36'], 345)
        self.assertEqual(s['by_class_refs'], {
            'ZONE_PAGE': 3004, 'UNKNOWN_ABSOLUTE_ADDRESS': 1048,
            'KNOWN_SYMBOLS': 19})
        self.assertEqual(s['by_class_refs'].get('FALSE_POSITIVE', 0), 0)

    def test_07417_is_page_address_not_data(self):
        data = cx.build(ROOT)
        target = next(t for t in data['top'] if t['value'] == '7417')
        self.assertEqual(target['class'], cx.CLASS_PAGE)
        self.assertEqual(target['count'], 138)
        self.assertEqual(cx.page_of(0o7417), '03')
        self.assertIn('7417', cx.ADDRESS_RESEARCH)
        md = cx.render_markdown(data, ROOT)
        self.assertIn('MEMORY-MAP.md:111', md)
        self.assertIn('не данные', md)

    def test_markdown_has_all_sections(self):
        data = cx.build(ROOT)
        md = cx.render_markdown(data, ROOT)
        for header in ('## 1. Методика', '## 2. Правила классификации',
                       '## 3. Статистика', '## 4. Топ-50',
                       '## 5. Проверка подозрительных адресов',
                       '## 6. Приложение', '## 7. Честные оговорки'):
            self.assertIn(header, md)
        self.assertIn('пио36', md)
        self.assertNotIn('| `по` |', md)
        self.assertNotIn('| `пе` |', md)


if __name__ == '__main__':
    unittest.main()
