#!/usr/bin/env python3
"""Model the HOST-side text packing in dispak vsinput.c.

Only the A0/A1 continuous-text branch (vsinput.c:479-522) is
modelled. It proves one thing: the host never splits a line
into LABEL / OPCODE / OPERAND / COMMENT. Characters are
packed six per 48-bit word, newlines are dropped, and every
space is kept verbatim.

The 12x80 punch-image branch (vsinput.c:523-684) is modelled
only far enough to show that chad() maps hole positions to
bits. Its column count is used for error text, not for
language fields.

Usage:
    python3 tools/host_line_probe.py FILE...
    python3 tools/host_line_probe.py FILE... --json
    python3 tools/host_line_probe.py --check

See analysis/HOST-LINE-SPLIT.md.
"""
import argparse
import json
import sys

BPW = 6                 # BESM-6 bytes per word, defs.h BPW
SPACE = 0o17            # GOST_SPACE, gost10859.h:29
OVERLINE = 0o115        # GOST_OVERLINE, gost10859.h:91
DIAMOND = 0o127         # GOST_DIAMOND, gost10859.h:101
UNDERLINE = 0o132       # GOST_UNDERLINE, gost10859.h:104

GOST = {}
for _i, _c in enumerate('0123456789'):
    GOST[_c] = _i
GOST.update({
    ' ': SPACE, '\t': SPACE, '.': 0o16, ',': 0o15,
    ';': 0o26, '(': 0o22, ')': 0o23, "'": 0o33,
    '$': DIAMOND, '_': UNDERLINE, '^': OVERLINE,
    '↑': OVERLINE, '+': 0o12, '-': 0o13, '=': 0o25,
    ':': 0o37, '!': 0o133, '/': 0o14, '*': 0o31,
    '#': 0o34, '<': 0o35, '>': 0o36, '"': 0o134,
    '\n': 10, '\r': 13,
})
_CYR = 'АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЫЬЭЮЯ'
for _i, _c in enumerate(_CYR):
    GOST[_c] = 0o40 + _i
GOST.update({c.lower(): v for c, v in list(GOST.items())
             if c in _CYR})
_LAT = {
    'A': 0o40, 'B': 0o42, 'C': 0o61, 'D': 0o77,
    'E': 0o45, 'F': 0o100, 'G': 0o101, 'H': 0o55,
    'I': 0o102, 'J': 0o103, 'K': 0o52, 'L': 0o104,
    'M': 0o54, 'N': 0o105, 'O': 0o56, 'P': 0o60,
    'Q': 0o106, 'R': 0o107, 'S': 0o110, 'T': 0o62,
    'U': 0o111, 'V': 0o112, 'W': 0o113, 'X': 0o65,
    'Y': 0o114, 'Z': 0o124,
}
GOST.update(_LAT)
GOST.update({c.lower(): v for c, v in _LAT.items()})


def to_gost(text):
    """Map characters to GOST bytes; reject anything unknown."""
    out = []
    for ch in text:
        if ch not in GOST:
            raise ValueError('no GOST byte for %r' % ch)
        out.append(GOST[ch])
    return out


def pack_text(text, mode='gost'):
    """Pack continuous text into six-byte words, like vsinput.c:483-520.

    Newlines are skipped. The last partial word is right padded.
    mode 'gost' is A1 (raw bytes); mode 'itm' is A0, where the
    host applies gost_to_itm. The ITM table is not duplicated
    here, so 'itm' raises NotImplementedError.
    """
    if mode == 'itm':
        raise NotImplementedError('A0 ITM table lives in encoding.c')
    if mode != 'gost':
        raise ValueError('mode must be gost or itm')
    data = [b for b in to_gost(text) if b not in (10, 13)]
    words = []
    for i in range(0, len(data), BPW):
        part = data[i:i + BPW]
        words.append(bytes(part + [0] * (BPW - len(part))))
    return words


def nonspace_stream(words):
    """Concatenate word bytes, drop ITM/GOST space bytes.

    Used to show that two decks differing only in spacing have
    the same token stream on the host.
    """
    return bytes(b for w in words for b in w
                 if b not in (SPACE, 0))


def host_fields(line):
    """Return the host's field split. Always None.

    vsinput.c has no branch that produces label, opcode,
    operand or comment fields. The guest translator does that.
    """
    return None


def chad(word, bit, val):
    """Model chad() at vsinput.c:643-662.

    One bit of a 12x80 punch image. val 'O' is a hole, '.'
    is no hole. Returns (word_index, new_word, line, symbol).
    line is 1..12 and symbol is 1..10, used only by inperr().
    """
    index = bit // 40
    if val == 'O':
        new = ((word << 1) | 1) & 0xffffffffff
    elif val == '.':
        new = (word << 1) & 0xffffffffff
    else:
        raise ValueError('bad punch value %r' % val)
    return index, new, bit // 80 + 1, (bit % 80) // 8 + 1


def prettycard(rows):
    """Model prettycard() at vsinput.c:665-684 (12 rows x 80)."""
    if len(rows) != 12 or any(len(r) != 80 for r in rows):
        raise ValueError('expected 12 rows of 80 columns')
    words = [0] * 24
    for bit in range(12 * 80):
        val = rows[bit // 80][bit % 80]
        index, new, _line, _sym = chad(words[bit // 40], bit, val)
        words[index] = new
    return words


def markers_in_text(text):
    """Report guest dispatcher markers as plain host characters."""
    bytes_ = to_gost(text)
    return {
        'vvd': text.count('ВВД'),
        'kvch': text.count('КВЧ'),
        'diamond_count': bytes_.count(DIAMOND),
        'overlay_count': bytes_.count(OVERLINE),
        'host_action': 'none (packed as text words)',
    }


def check():
    """Self-check the host invariants. Return list of failures."""
    bad = []
    a = 'ПРОГ\tСТАРТ\t512' + '\n'
    b = 'ПРОГ         СТАРТ         512' + '\n'
    wa, wb = pack_text(a), pack_text(b)
    if any(len(w) != BPW for w in wa + wb):
        bad.append('word width is not six bytes')
    if nonspace_stream(wa) != nonspace_stream(wb):
        bad.append('spacing-only change altered the token stream')
    if wa == wb:
        bad.append('spacing-only change did not alter the words')
    if host_fields(a) is not None:
        bad.append('host_fields must always return None')
    words = prettycard(['.' * 80] * 12)
    if words != [0] * 24:
        bad.append('an unpunched card must give 24 zero words')
    one = prettycard(['O' + '.' * 79] + ['.' * 80] * 11)
    if one[0] != 1 << 39:
        bad.append('first hole must land in bit 39 of word 0')
    m = markers_in_text('ВВД$$$' + '\n' + 'КВЧ$$$')
    if m['diamond_count'] != 6:
        bad.append('six dollar signs must give six diamonds')
    if m['host_action'] != 'none (packed as text words)':
        bad.append('host must not act on dispatcher markers')
    return bad


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('files', nargs='*')
    p.add_argument('--mode', choices=('gost', 'itm'), default='gost')
    p.add_argument('--json', action='store_true')
    p.add_argument('--check', action='store_true')
    a = p.parse_args(argv)
    if a.check:
        bad = check()
        for line in bad:
            print('FAIL:', line)
        if not bad:
            print('PASS: host pack has no field split')
        return 1 if bad else 0
    if not a.files:
        p.error('give FILE... or --check')
    out = []
    for name in a.files:
        with open(name, 'r', encoding='utf-8-sig') as f:
            text = f.read()
        words = pack_text(text, a.mode)
        out.append({
            'file': name,
            'words': len(words),
            'space_bytes': sum(w.count(SPACE) for w in words),
            'octal_words': [' '.join('%02o' % b for b in w)
                            for w in words],
            'host_fields': host_fields(text),
            'markers': markers_in_text(text),
        })
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for r in out:
            print('%s: words=%d spaces=%d fields=%s'
                  % (r['file'], r['words'], r['space_bytes'],
                     r['host_fields']))
            for w in r['octal_words']:
                print('   ', w)
    return 0


if __name__ == '__main__':
    sys.exit(main())
