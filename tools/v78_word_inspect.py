#!/usr/bin/env python3
"""Read-only inspector for 48-bit BESM words.

Given a word (octal or 0x-hex) or a word inside a gold zone
dump, print its six bytes, all four project decodings with a
quality estimate, and the GOST->BESM table formula.

Optional disk search scans the four reference volumes for the
same six-byte pattern and reports zone.word hits. Reference
files are opened READ-ONLY; the guard refuses any write path.

Usage:
  python3 tools/v78_word_inspect.py 01400744203630417
  python3 tools/v78_word_inspect.py 0x1400744203630417
  python3 tools/v78_word_inspect.py --zone 0144 --word 0571
  python3 tools/v78_word_inspect.py --zone 0152 --word 0317 \
      --search --format json
  python3 tools/v78_word_inspect.py --check
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import text_decode_all as TD  # noqa: E402

DEFAULT_IMAGES = ('2048', '2148', '2248', '2348')
IMAGE_DIR = '/usr/local/share/besm6'
ZONE_BYTES = 6144
WORD_BYTES = 6
MAX_HITS = 12


class GuardError(Exception):
    """Raised on any attempt to write to a reference directory."""


def guard(path):
    """Refuse paths under the read-only image directory."""
    real = os.path.realpath(path)
    image = os.path.realpath(IMAGE_DIR)
    if real == image or real.startswith(image + os.sep):
        raise GuardError('write refused: ' + path)
    return path


def parse_word(text):
    """Parse an octal (16 digits) or 0x-hex 48-bit word."""
    s = str(text).strip().replace(' ', '')
    if s.lower().startswith('0x'):
        value = int(s[2:], 16)
    else:
        if not re.fullmatch(r'[0-7]{1,16}', s):
            raise ValueError('bad octal word: ' + text)
        value = int(s, 8)
    if not 0 <= value < (1 << 48):
        raise ValueError('word out of 48-bit range')
    return value


def word_at(zone, offset, root=ROOT):
    """Read one 48-bit word from a gold zone dump."""
    path = os.path.join(root, 'gold', 'MBE-Z%04o-L1.bin' % zone)
    guard(path)
    with open(path, 'rb') as handle:
        handle.seek(offset * WORD_BYTES)
        raw = handle.read(WORD_BYTES)
    if len(raw) != WORD_BYTES:
        raise ValueError('short read at zone %04o word %04o' % (zone, offset))
    return int.from_bytes(raw, 'big')


def byte_rows(word):
    """Six rows: index, byte, GOST code, BESM byte, TAB formula."""
    rows = []
    for i, b in enumerate(TD.bytes8(word)):
        formula = 'TAB[%03o&077]' % b if b else 'TAB[000]'
        rows.append({'i': i, 'hex': '0x%02x' % b, 'oct': '%03o' % b,
                     'formula': formula})
    return rows


def quality(text, enc):
    """Score a decoding; no claim is made for low scores."""
    hits = TD.known_word_hits(text) if enc in ('GOST', 'ITM', 'KOI7') else []
    dig = TD.digraph_ratio(text)
    if '\0' in text:
        return 'НЕТ_ГЛИФА', 0, dig
    if enc == 'TEXT':
        return 'СЛАБО', len(hits), dig
    if hits and dig >= 0.25:
        return 'ВЕРОЯТНО', len(hits), dig
    if hits or dig >= 0.2:
        return 'ВОЗМОЖНО', len(hits), dig
    return 'СЛАБО', len(hits), dig


def decode(word):
    out = {}
    for enc, text in TD.decode_all(word).items():
        verdict, hits, dig = quality(text, enc)
        out[enc] = {'text': text, 'verdict': verdict,
                    'known_hits': hits, 'digraph': round(dig, 3)}
    return out


def search_image(path, raw):
    """Find the 6-byte pattern in one volume image (READ-ONLY)."""
    hits = []
    with open(path, 'rb') as handle:
        data = handle.read()
    for order, pat in (('прямой', raw), ('обратный', raw[::-1])):
        start = 0
        while len(hits) < MAX_HITS:
            pos = data.find(pat, start)
            if pos < 0:
                break
            zone = pos // ZONE_BYTES
            word = (pos % ZONE_BYTES) // WORD_BYTES
            hits.append({'zone': '%04o' % zone, 'word': '%04o' % word,
                         'byte': pos, 'order': order})
            start = pos + 1
    return hits


def search_all(word, image_dir=IMAGE_DIR, volumes=DEFAULT_IMAGES):
    raw = word.to_bytes(WORD_BYTES, 'big')
    out = {}
    for vol in volumes:
        path = os.path.join(image_dir, vol)
        if os.path.isfile(path):
            out[vol] = search_image(path, raw)
    return out


def check():
    """Validate the decoder against known constants."""
    errors = []
    cases = [
        (0x400000000000, 0x40, 'space'),
        (0x010000000000, 0x01, 'marker'),
        (0xbe0000000000, 0xbe, 'end marker'),
        (0xbf0000000000, 0xbf, 'underline'),
    ]
    for word, byte, name in cases:
        got = TD.bytes8(word)[0]
        if got != byte:
            errors.append('%s: %02x != %02x' % (name, got, byte))
    if TD.decode_text(0) != '        ':
        errors.append('TEXT eight zero groups')
    if word_at(0o152, 0o317) != 0x400000000000:
        errors.append('gold 0152 word 0317 is not 0x40')
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('word', nargs='?', help='octal or 0x-hex 48-bit word')
    ap.add_argument('--zone', help='read from gold zone (octal)')
    ap.add_argument('--word', dest='zone_word', help='word offset in zone (octal)')
    ap.add_argument('--search', action='store_true',
                    help='scan all reference volumes for the byte pattern')
    ap.add_argument('--no-search', action='store_true',
                    help='explicitly skip disk search (default)')
    ap.add_argument('--format', choices=('json', 'text'), default='text')
    ap.add_argument('--check', action='store_true', help='validate decoders')
    args = ap.parse_args(argv)

    try:
        if args.check:
            errors = check()
            print('ПРОВЕРКА: ' + ('OK' if not errors else 'FAIL'))
            for e in errors:
                print('  ' + e)
            return 0 if not errors else 1
        if args.zone:
            if not args.zone_word:
                ap.error('--zone requires --word')
            word = word_at(int(args.zone, 8), int(args.zone_word, 8))
        elif args.word:
            word = parse_word(args.word)
        else:
            ap.error('give WORD or --zone/--word')
        result = {'oct': '%016o' % word, 'hex': '0x%012x' % word,
                  'bytes': byte_rows(word), 'decode': decode(word)}
        if args.search and not args.no_search:
            result['search'] = search_all(word)
        if args.format == 'json':
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print('СЛОВО %s  %s' % (result['oct'], result['hex']))
            for row in result['bytes']:
                print('  б%s %s %s %s' % (row['i'], row['hex'],
                                          row['oct'], row['formula']))
            for enc, info in result['decode'].items():
                print('%-5s %-10s %s' % (enc, info['verdict'],
                                         repr(info['text'])))
            if 'search' in result:
                print('ЗОНЫ ФИЗИЧЕСКИЕ (файловые), не каталожные;')
                print('для каталожных адресов использовать besmtool.')
                for vol, hits in result['search'].items():
                    print('том %s: %d попаданий' % (vol, len(hits)))
                    for h in hits[:5]:
                        print('  %s.%s' % (h['zone'], h['word']))
        return 0
    except (GuardError, ValueError, OSError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
