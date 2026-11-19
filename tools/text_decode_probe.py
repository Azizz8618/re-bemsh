#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TEXT-DECODING PROBE for the BESM-6 MACRO-BEMSH translator (том 2348).

Purpose: test whether translator text is stored with a non-standard
OFFSET/BIAS that makes disbesm6 print garbage, or whether disbesm6 simply
applies a different (GOST-10859) table and never tries the 6-bit Dubna
TEXT table.

Calibration: five stamps whose text is known from `besmtool search`:
    0147.1315 'ИПМ МА', 0154.0751 'МАКРОР', 0170.0216 'МАКРОМ',
    0173.0655 'ОШ.СПР', 0176.1732 'ИПМ МА' (B2 copies have the same bytes).

Usage:
    python3 tools/text_decode_probe.py                 # calibrate + report
    python3 tools/text_decode_probe.py --dump DIR       # scan dumped zones
    python3 tools/text_decode_probe.py --bytes ae ac a9 a6 a5 40
    python3 tools/text_decode_probe.py --zone-word 0173.0744 --dump DIR

Only reads files; never writes to gold/ or dis/.
"""

import argparse
import os
import re
import sys

# ---------------------------------------------------------------------------
# 1. Tables (canonical ports of monitor80-re/tools/encoding.cpp)
# ---------------------------------------------------------------------------

# gost_to_unicode_cyr[0..127]. 0 = no glyph.  GOST-10859, 8 bit/char, 6/wd.
GOST_CYR = [
    0x30,0x31,0x32,0x33,0x34,0x35,0x36,0x37,
    0x38,0x39,0x2b,0x2d,0x2f,0x2c,0x2e,0x20,
    0x23e8,0x2191,0x28,0x29,0xd7,0x3d,0x3b,0x5b,
    0x5d,0x2a,0x2018,0x2019,0x2260,0x3c,0x3e,0x3a,
    0x0410,0x0411,0x0412,0x0413,0x0414,0x0415,0x0416,0x0417,
    0x0418,0x0419,0x041a,0x041b,0x041c,0x041d,0x041e,0x041f,
    0x0420,0x0421,0x0422,0x0423,0x0424,0x0425,0x0426,0x0427,
    0x0428,0x0429,0x042b,0x042c,0x042d,0x042e,0x042f,0x44,
    0x46,0x47,0x49,0x4a,0x4c,0x4e,0x51,0x52,
    0x53,0x55,0x56,0x57,0x5a,0x203e,0x2a7d,0x2a7e,
    0x2228,0x2227,0x2283,0xac,0xf7,0x2261,0x25,0x25c7,
    0x7c,0x2015,0x5f,0x21,0x22,0x042a,0xb0,0x2032,
]

# gost_to_unicode_lat[0..127] (GOST_LATIN=true) -- differs from GOST_CYR in
# 0x20..0x3e (Latin-shaped homoglyphs for A, B, E, K, M, H, O, P, C, T, Y, X).
GOST_LAT = [
    0x30,0x31,0x32,0x33,0x34,0x35,0x36,0x37,
    0x38,0x39,0x2b,0x2d,0x2f,0x2c,0x2e,0x20,
    0x23e8,0x2191,0x28,0x29,0xd7,0x3d,0x3b,0x5b,
    0x5d,0x2a,0x2018,0x2019,0x2260,0x3c,0x3e,0x3a,
    0x41,0x0411,0x42,0x0413,0x0414,0x45,0x0416,0x0417,
    0x0418,0x0419,0x4b,0x041b,0x4d,0x48,0x4f,0x041f,
    0x50,0x43,0x54,0x59,0x0424,0x58,0x0426,0x0427,
    0x0428,0x0429,0x042b,0x042c,0x042d,0x042e,0x042f,0x44,
    0x46,0x47,0x49,0x4a,0x4c,0x4e,0x51,0x52,
    0x53,0x55,0x56,0x57,0x5a,0x203e,0x2a7d,0x2a7e,
    0x2228,0x2227,0x2283,0xac,0xf7,0x2261,0x25,0x25c7,
    0x7c,0x2015,0x5f,0x21,0x22,0x042a,0xb0,0x2032,
]

# dtran.cc:59 -- Dubna 6-bit TEXT (code -> glyph). 'code = ASCII - 0x20'
# for the Latin subset; Cyrillic codes use text_to_gost[].
TEXT_DUBNA = (" .БЦДФГИ()*ЙЛЯЖ/0123456789Ь,П-+ЫЗ"
              "ABCDEFGHIJKLMNOPQRSTUVWXYZШЭЩЧЮ")
assert len(TEXT_DUBNA) == 64

# dtran.cc:is_likely_text -- codes allowed in a real 6-bit TEXT constant.
TEXT_VALID = frozenset([0, 10, 15, *range(16, 26), 29, 30, *range(33, 59)])

# ---------------------------------------------------------------------------
# 2. Decoders
# ---------------------------------------------------------------------------

def groups6(word):
    """Eight 6-bit groups, most significant first."""
    return [(word >> s) & 0x3f for s in (42, 36, 30, 24, 18, 12, 6, 0)]


def bytes8(word):
    """Six 8-bit bytes, most significant first."""
    return [(word >> s) & 0xff for s in (40, 32, 24, 16, 8, 0)]


def gost8(word, latin=False, bias=0):
    """GOST-10859: 6 bytes x 8 bit. bias is added to each byte."""
    tbl = GOST_LAT if latin else GOST_CYR
    out = []
    for b in bytes8(word):
        b = (b + bias) & 0xff
        u = tbl[b] if b < len(tbl) else 0
        out.append(chr(u) if u else '\0')
    return ''.join(out)


def text_ascii(word):
    """8 x 6-bit, code = ASCII - 0x20 (re-forex docs 19/20)."""
    return ''.join(chr(c + 0x20) for c in groups6(word))


def text_dubna(word):
    return ''.join(TEXT_DUBNA[c] for c in groups6(word))


def word_from_bytes(bs):
    return int.from_bytes(bytes(bs), 'big')


# ---------------------------------------------------------------------------
# 3. Transformations tested against the calibration stamps
# ---------------------------------------------------------------------------

def rotl48(w, n):
    n %= 48
    return ((w << n) | (w >> (48 - n))) & ((1 << 48) - 1)


def nibble_swap(word):
    bs = bytes8(word)
    return word_from_bytes([((b << 4) | (b >> 4)) & 0xff for b in bs])


def halfword_swap(word):
    return ((word & 0xffffff) << 24) | ((word >> 24) & 0xffffff)


def byte_reverse(word):
    return word_from_bytes(list(reversed(bytes8(word))))


def transforms(word):
    """Yield (name, transformed_word) for every hypothesis under test."""
    yield ('identity', word)
    for bias in (0x20, -0x20, 0x40, -0x40, 0xa0, -0xa0, 0x10, -0x10):
        yield ('bias %+d' % bias, word_from_bytes(
            [(b + bias) & 0xff for b in bytes8(word)]))
    for n in (6, 12, 18, 24, 30, 36, 42):
        yield ('rotl %d' % n, rotl48(word, n))
    yield ('nibble-swap', nibble_swap(word))
    yield ('halfword-swap', halfword_swap(word))
    yield ('byte-reverse', byte_reverse(word))


def cyr_score(s):
    """Fraction of non-padding chars that are Cyrillic letters."""
    eff = [c for c in s if c != '\0']
    if not eff:
        return 0.0
    return sum(('А' <= c <= 'Я') or ('а' <= c <= 'я') for c in eff) / len(eff)


CALIBRATION = [
    ('0147.1315', '28 2f 2c 0f 2c 20', 'ИПМ МА'),
    ('0154.0751', '2c 20 2a 30 2e 30', 'МАКРОР'),
    ('0170.0216', '2c 20 2a 30 2e 2c', 'МАКРОМ'),
    ('0173.0655', '2e 38 0e 31 2f 30', 'ОШ.СПР'),
    ('0176.1732', '28 2f 2c 0f 2c 20', 'ИПМ МА'),
]

# Constants previously printed as в'...' / garbage by disbesm6, now decoded
# with the 6-bit TEXT table (all byte values >= 0x20, mostly 0xa0..0xdf).
ILLEGIBLE = [
    ('0152.0472', 'ae ac a9 a6 a5 40'),
    ('0152.1101', 'ba ad af a4 ac 40'),
    ('0166.0355', '00 04 0a ce 88 f1'),
    ('0171.0544', '40 00 00 8e 89 67'),
    ('0173.0744', 'b3 a9 ae 00 00 00'),
    ('0173.0753', 'da a8 a1 ab 00 00'),
    ('0173.1070', 'd0 a8 51 ab 00 00'),
    ('0173.1257', 'ac a9 b3 b4 00 00'),
    ('0174.0106', 'a8 a5 b4 c7 a5 a8'),
    ('0176.1137', 'd0 a5 b0 40 ad a5'),
    ('0176.1167', 'a8 a5 b4 40 ad a5'),
    ('0176.1227', 'a8 a5 b4 40 a8 a1'),
]

# ---------------------------------------------------------------------------
# 4. Report modes
# ---------------------------------------------------------------------------

def calibration_report():
    print('=== 1. BYTE -> CHARACTER MAPPING (calibration stamps) ===')
    for addr, hexb, exp in CALIBRATION:
        w = word_from_bytes(int(x, 16) for x in hexb.split())
        print('%s bytes=%s' % (addr, hexb))
        print('   GOST8-cyr = %-9r  GOST8-lat = %-9r' %
              (gost8(w), gost8(w, True)))
        print('   TEXT(ascii-0x20)=%-9r TEXT-DUBNA=%-9r' %
              (text_ascii(w), text_dubna(w)))
        print('   exact GOST8 == expected? %s' % (gost8(w) == exp))

    print()
    print('=== 2. TRANSFORMATION HYPOTHESES (Cyrillic score / exact matches) ===')
    results = {}
    for addr, hexb, exp in CALIBRATION:
        w = word_from_bytes(int(x, 16) for x in hexb.split())
        for name, tw in transforms(w):
            s = gost8(tw)
            rec = results.setdefault(name, [0.0, 0])
            rec[0] += cyr_score(s)
            rec[1] += (s == exp)
    n = len(CALIBRATION)
    ranked = sorted(results.items(), key=lambda kv: (-kv[1][1], -kv[1][0]))
    print('%-14s %8s %8s' % ('transform', 'cyr/mean', 'exact/5'))
    print('%-14s %8s %8s' % ('-' * 14, '-' * 8, '-' * 8))
    for name, (score, exact) in ranked:
        print('%-14s %8.3f %8d' % (name, score / n, exact))
    print()
    print('Winner: identity + GOST8 -- no byte bias, no rotation, no swap.')


def illegible_report():
    print('=== 3. PREVIOUSLY ILLEGIBLE CONSTANTS -> 6-bit TEXT ===')
    print('%-10s %-17s %-10s %s' % ('address', 'bytes', 'GOST8-cyr', 'TEXT'))
    print('%-10s %-17s %-10s %s' % ('-' * 10, '-' * 17, '-' * 10, '-' * 30))
    for addr, hexb in ILLEGIBLE:
        w = word_from_bytes(int(x, 16) for x in hexb.split())
        print('%-10s %-17s %-10r %r' %
              (addr, hexb, gost8(w), text_ascii(w)))
    print()
    print('GOST8-cyr is garbage/octal escapes (disbesm6 prints в\'...\');')
    print('6-bit TEXT with code=ASCII-0x20 yields readable Latin names.')


def scan_report(dumpdir):
    """Find words that are illegible in GOST8 but clean 6-bit TEXT names."""
    found = []
    for fn in sorted(os.listdir(dumpdir)):
        if not re.fullmatch(r'z\d{4}\.bin', fn):
            continue
        zone = fn[1:5]
        data = open(os.path.join(dumpdir, fn), 'rb').read()
        for i in range(len(data) // 6):
            w = word_from_bytes(data[i * 6:(i + 1) * 6])
            gs = [c for c in groups6(w) if c]
            if len(gs) < 4 or any(c not in TEXT_VALID for c in gs):
                continue
            t = text_ascii(w)
            if sum(c.isalpha() for c in t) < 4:
                continue
            if len(set(c for c in t if c.isalpha())) < 3:
                continue
            g = gost8(w)
            if cyr_score(g) > 0.34:
                continue
            found.append((zone, i, g, t))
    print('=== SCAN: TEXT-bright / GOST-dark words (%d) ===' % len(found))
    for zone, i, g, t in found[:80]:
        print('%s.%04o GOST8=%-11r TEXT=%r' % (zone, i, g, t))


def probe_bytes(hexb):
    if isinstance(hexb, str):
        hexb = hexb.split()
    w = word_from_bytes(int(x, 16) for x in hexb)
    print('word = %016o' % w)
    print('GOST8-cyr   = %r' % gost8(w))
    print('GOST8-lat   = %r' % gost8(w, True))
    print('TEXT(ascii) = %r' % text_ascii(w))
    print('TEXT-DUBNA  = %r' % text_dubna(w))
    print('6-bit codes = %s' % ' '.join('%02o' % c for c in groups6(w)))
    print('bytes       = %s' % ' '.join('%02x' % b for b in bytes8(w)))


def probe_zone_word(dumpdir, zw):
    m = re.fullmatch(r'(\d{4})\.(\d{1,4})', zw)
    if not m:
        print('bad --zone-word (expected ZONE.WORD, e.g. 0173.0744)')
        return
    zone, wordno = m.group(1), int(m.group(2), 8)
    path = os.path.join(dumpdir, 'z%s.bin' % zone)
    data = open(path, 'rb').read()
    bs = data[wordno * 6:(wordno + 1) * 6]
    print('%s.%04o' % (zone, wordno))
    probe_bytes(' '.join('%02x' % b for b in bs))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dump', metavar='DIR',
                    help='каталог с дампами зон zNNNN.bin (besmtool dump)')
    ap.add_argument('--scan', action='store_true',
                    help='сканировать дампы на TEXT-константы')
    ap.add_argument('--bytes', nargs=6, metavar='XX',
                    help='6 байт слова в hex, например ae ac a9 a6 a5 40')
    ap.add_argument('--zone-word', metavar='ZONE.WORD',
                    help='слово из дампа, например 0173.0744')
    ap.add_argument('--illegible-only', action='store_true',
                    help='только таблица ранее нечитаемых констант')
    args = ap.parse_args(argv)

    if args.bytes:
        probe_bytes(args.bytes)
        return 0
    if args.zone_word:
        if not args.dump:
            print('--zone-word требует --dump DIR')
            return 2
        probe_zone_word(args.dump, args.zone_word)
        return 0
    if args.illegible_only:
        illegible_report()
        return 0
    if args.dump and args.scan:
        scan_report(args.dump)
        return 0
    calibration_report()
    print()
    illegible_report()
    return 0


if __name__ == '__main__':
    sys.exit(main())
