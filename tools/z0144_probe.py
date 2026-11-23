#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only GOST text probe for BESM-6 zone 0144 dumps.

Decodes every 6-byte word with the project decoder
(tools/text_decode_all.py, imported read-only) and groups
contiguous GOST text words into messages. No emulator, no
image access, no writes. Any 6-byte-per-word path works.

Usage:
    python3 tools/z0144_probe.py gold/MBE-Z0144-L1.bin
    python3 tools/z0144_probe.py FILE --format json
    python3 tools/z0144_probe.py FILE --check

Exit codes: 0 ok/check, 1 check failed, 2 input error.
The --check invariant: size 6144 bytes, 7 anchors from
docs/SEMANTIC/Z0144.md section 2, each anchor covered by
a message or a start within 0o10 octal words.
See analysis/Z0144-TEXTS.md for the decoding evidence.
"""

import argparse
import json
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import text_decode_all as TD  # noqa: E402

WORD_BYTES = 6
ZONE_SIZE = 6144
ZONE_ID = '0144'
# Documented memory-map anchors (octal), Z0144.md section 2.
ANCHOR_ADDRS = ('0275', '0310', '0543',
                '1211', '1224', '1434', '1765')
ANCHOR_WINDOW = 0o10

DIGITS = frozenset('0123456789')
CLEAN = TD.CYR_UP | DIGITS | TD.PUNCT | frozenset(' =\0<>')

# Keyword heuristic only: the authoritative classification
# is in analysis/Z0144-TEXTS.md. Prefix wins over substring.
KIND_RULES = (
    ('error', ('ОШИБКА', 'ШИБКА:', 'НЕВЕР', 'ОШ ',
               'ОШ.', 'НЕТ', 'ПРОГРА')),
    ('diagnostic', ('***', 'АДРЕС', 'ДЛ МДЛ',
                    '> ДОП.', 'ЗОНГП=', 'СВ.З')),
    ('status', ('ЗАМ', 'ПЕЧ', 'КОНЕЦ', 'НАЗ', 'ПФГП')),
    ('name', ('ВНЕШ', 'МДЛ', 'ИКОП',
              'АМИН', 'АМАКС', 'АСВОБ')),
    ('table', ('ПРПЛН', 'СВОБ', 'Р В С', 'ПОВТОР')),
)


def addr(idx):
    """Physical word address as a string in the zone."""
    return '%s.%04o' % (ZONE_ID, idx)


def hexbytes(word):
    return ''.join('%02x' % b for b in TD.bytes8(word))


def interspersed(text):
    """True when a digit has a Cyrillic letter to its right.

    Such words are numeric masks (F00900, M2B900), not text.
    """
    seen = False
    for char in text:
        if char in DIGITS:
            seen = True
        elif TD.is_cyr(char) and seen:
            return True
    return False


def is_text_word(word):
    """One GOST text word, seed of a message."""
    text = TD.decode_gost(word)
    if '\0' in text or any(c not in CLEAN for c in text):
        return False
    if interspersed(text):
        return False
    if sum(TD.is_cyr(c) for c in text) < 2:
        return False
    ok, _ = TD.gost_word_ok(text)
    if ok:
        return True
    if TD.gost_continuation_ok(text):
        if ' ' in text or any(c in TD.PUNCT for c in text):
            return True
    core = text.rstrip('0123456789')
    if len(core) < 2:
        return False
    return all(TD.is_cyr(c) for c in core)


def is_extension(word):
    """Tail word glued to the previous seed, e.g. a date."""
    text = TD.decode_gost(word)
    if '\0' in text or any(c not in CLEAN for c in text):
        return False
    if interspersed(text) or text.strip().isdigit():
        return False
    if not TD.gost_continuation_ok(text):
        return False
    return (any(TD.is_cyr(c) for c in text) or
            any(c in TD.PUNCT for c in text))


def find_messages(words):
    """Group adjacent text words into messages.

    Returns a list of dicts with 0-based word indexes.
    """
    out = []
    idx = 0
    total = len(words)
    while idx < total:
        if not is_text_word(words[idx]):
            idx += 1
            continue
        end = idx + 1
        while end < total:
            if (is_text_word(words[end]) or
                    is_extension(words[end])):
                end += 1
            else:
                break
        pieces = [TD.decode_gost(words[k]).rstrip()
                  for k in range(idx, end)]
        joined = ' '.join(pieces)
        text = re.sub(r'\s+', ' ', joined).strip()
        out.append({
            'start_idx': idx, 'end_idx': end - 1,
            'span': end - idx, 'text': text,
        })
        idx = end
    return out


def classify(text):
    """Coarse keyword class of one decoded message."""
    upper = text.upper().strip()
    for kind, keys in KIND_RULES:
        for key in keys:
            if upper.startswith(key) or key in upper:
                return kind
    return 'unknown'


def read_words(path):
    """Read dump as 48-bit words. Raises ValueError."""
    if not os.path.isfile(path):
        raise ValueError('not a file: %s' % path)
    with open(path, 'rb') as handle:
        data = handle.read()
    if len(data) % WORD_BYTES:
        raise ValueError('size not a multiple of %d: %d' %
                         (WORD_BYTES, len(data)))
    return [TD.word_from_bytes(data[i:i + WORD_BYTES])
            for i in range(0, len(data), WORD_BYTES)]


def build_report(path, do_check=False):
    """Decode one file and assemble the report dict."""
    words = read_words(path)
    raw = find_messages(words)
    messages = []
    for msg in raw:
        lo, hi = msg['start_idx'], msg['end_idx']
        messages.append({
            'start': addr(lo), 'end': addr(hi),
            'span': msg['span'], 'text': msg['text'],
            'kind': classify(msg['text']),
            'words': [{
                'addr': addr(k), 'hex': hexbytes(words[k]),
                'gost': TD.decode_gost(words[k]),
            } for k in range(lo, hi + 1)],
        })
    report = {
        'path': path, 'zone': ZONE_ID,
        'size_bytes': len(words) * WORD_BYTES,
        'word_count': len(words),
        'message_count': len(messages),
        'gost_word_count': sum(
            is_text_word(w) for w in words),
        'addresses': [m['start'] for m in messages],
        'messages': messages,
        'check': check_report(
            messages, len(words) * WORD_BYTES
        ) if do_check else None,
    }
    return report


def check_report(messages, size):
    """Validate size and 7 documented anchor regions."""
    starts = [int(m['start'].split('.')[1], 8)
              for m in messages]
    spans = [(int(m['start'].split('.')[1], 8),
              int(m['end'].split('.')[1], 8))
             for m in messages]
    failures = []
    size_ok = size == ZONE_SIZE
    if not size_ok:
        failures.append('size %d != %d' % (size, ZONE_SIZE))
    count_ok = len(ANCHOR_ADDRS) == 7
    if not count_ok:
        failures.append('anchor count %d != 7' %
                        len(ANCHOR_ADDRS))
    anchors = []
    for octs in ANCHOR_ADDRS:
        a = int(octs, 8)
        covered = any(lo <= a <= hi for lo, hi in spans)
        near = any(a <= s < a + ANCHOR_WINDOW
                   for s in starts)
        ok = covered or near
        if not ok:
            failures.append('anchor %s not found' % octs)
        anchors.append({
            'addr': addr(a), 'covered': covered,
            'near_start': near, 'ok': ok,
        })
    return {
        'ok': not failures, 'size_ok': size_ok,
        'anchor_count': len(ANCHOR_ADDRS),
        'anchor_count_ok': count_ok,
        'anchors': anchors, 'failures': failures,
    }


def render_text(report):
    """Human-readable summary with counts and addresses."""
    lines = [
        'zone: %s' % report['zone'],
        'path: %s' % report['path'],
        'size: %d bytes, %d words' % (report['size_bytes'],
                                      report['word_count']),
        'GOST text words: %d' % report['gost_word_count'],
        'messages: %d' % report['message_count'],
        'addresses: %s' % ' '.join(report['addresses']),
        '',
    ]
    for msg in report['messages']:
        lines.append('%s-%s [%s] %s' % (
            msg['start'], msg['end'],
            msg['kind'], msg['text']))
    check = report['check']
    if check is not None:
        lines.append('')
        lines.append('check: %s' % ('PASS' if check['ok']
                                    else 'FAIL'))
        for failure in check['failures']:
            lines.append('  ! %s' % failure)
    return '\n'.join(lines) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Decode GOST text in a BESM-6 dump.')
    ap.add_argument('bin', metavar='FILE',
                    help='input dump, 6 bytes/word')
    ap.add_argument('--format', choices=('json', 'text'),
                    default='text', help='output format')
    ap.add_argument('--check', action='store_true',
                    help='validate size and 7 anchors')
    args = ap.parse_args(argv)
    try:
        report = build_report(args.bin, args.check)
    except (OSError, ValueError) as exc:
        sys.stderr.write('z0144_probe: %s\n' % exc)
        return 2
    if args.format == 'json':
        print(json.dumps(report, ensure_ascii=False,
                         indent=2))
    else:
        sys.stdout.write(render_text(report))
    if args.check and not report['check']['ok']:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
