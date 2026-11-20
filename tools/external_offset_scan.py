#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan bemsh/*.be literal labels for external-offset candidates.

The reconstruction introduces literal EQU labels such as B211 ('11'),
AM10 ('10'), BR150 ('150').  A label value taken as a BESM-6 address
inside its own zone is usually small (0000-1777).  When such a value is
used as a CALL/branch target and no procedure entry exists at that
address in the same zone, the value is a candidate for an *offset into
another module*, not a plain local constant.

This scanner only collects evidence.  Every conclusion is a hypothesis:
the procedure catalogues in docs/PROCEDURES-*.md are themselves marked
ГИПОТЕЗА in the repository, so "no local entry" is weak evidence.

Usage
-----
    python3 tools/external_offset_scan.py
    python3 tools/external_offset_scan.py --labels labels.txt
    python3 tools/external_offset_scan.py --json > /tmp/offsets.json
    python3 tools/external_offset_scan.py --root /path/to/repo
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

# The 30 labels listed by the operator (MBE / ASM literal-label families).
DEFAULT_LABELS = """
AM10 AM137 AM147 AM1700 AM63
B211 B2112 B2113 B2115 B2116 B2117 B2120 B2140 B2141 B2142 B2144 B2151
B22 B22015 B222 B236 B2360 B24102 B26 B26338 B26622 B27
BR0014 BR016 BR1101 BR122 BR150
""".split()

# Mnemonics whose operand is a code target (CALL or branch).
# Sources: docs/PROCEDURES-B.md §1 (пв/пво/вжм = CALL,
# по/пе/цикл/пб/пио/пино/выпр = branch targets).
CALL_MNEMONICS = frozenset({'ПВ', 'ПВО', 'ВЖМ'})
BRANCH_MNEMONICS = frozenset({'ПО', 'ПЕ', 'ЦИКЛ', 'ПБ', 'ПИО', 'ПИНО', 'ВЫПР'})
TARGET_MNEMONICS = CALL_MNEMONICS | BRANCH_MNEMONICS

# Comment role markers written by tools/annotate_zone.py.  A label marked
# (переход)/(вызов) is *interpreted* by the reconstruction as a branch or
# call address even when the mnemonic itself is a data operation (e.g. ЗП).
TARGET_ROLE_RE = re.compile(r'\((переход|вызов)\)')

# A value fitting in one 1024-word zone is treated as "small".
SMALL_LIMIT_OCT = 0o1777

EQU_RE = re.compile(r"^\s*([A-ZА-ЯЁ][A-ZА-ЯЁ0-9_]*)\s+ЭКВ\s+'([0-7]+)'")
CODE_RE = re.compile(r'^\s+([A-ZА-ЯЁ]+)\s+(.*)$')
ZONE_RE = re.compile(r'Z(\d{4})')
TOKEN_RE = re.compile(r"[A-ZА-ЯЁ][A-ZА-ЯЁ0-9_]*|'[0-7]+'|\b[0-7]+\b")
REG_RE = re.compile(r'\(М(\d+)\)')
PROC_RE = re.compile(
    r'^\s*(\d{4}):(\d{4})-(\d{4})\s+size=\d+\s+\S+\s+(\S+)'
)


def zone_from_path(path):
    """Return the octal zone string encoded in a bemsh/*.be filename."""
    m = ZONE_RE.search(os.path.basename(path))
    return m.group(1) if m else ''


def parse_equ(line):
    """Parse 'AM10 ЭКВ \\'10\\'' -> ('AM10', '10'); else None."""
    m = EQU_RE.match(line.rstrip('\n'))
    if not m:
        return None
    return m.group(1), m.group(2)


def parse_code_line(line):
    """Parse an assembler code line into mnemonic / operand / comment."""
    s = line.rstrip('\n')
    if s.startswith('*') or not s.strip():
        return None
    m = CODE_RE.match(s)
    if not m:
        return None
    mnem, rest = m.group(1), m.group(2)
    if ',' in rest:
        operand, comment = rest.split(',', 1)
        comment = comment.strip()
    else:
        operand, comment = rest, ''
    return {'mnem': mnem, 'operand': operand.strip(), 'comment': comment}


def label_pattern(label):
    """Compiled word-boundary pattern so B211 never matches B2112."""
    return re.compile(
        r'(?<![A-ZА-ЯЁ0-9_])' + re.escape(label) + r'(?![A-ZА-ЯЁ0-9_])')


def label_in_operand(operand, label):
    """Word-boundary test so B211 never matches B2112."""
    return bool(label_pattern(label).search(operand))


def find_labels(operand, matchers):
    """Return every known label present in an operand, in one token pass."""
    found = []
    for tok in TOKEN_RE.findall(operand):
        if tok in matchers and tok not in found:
            found.append(tok)
    return found


def tokens_in_operand(operand):
    """All label-like / numeric tokens of an operand (for pair detection)."""
    return [t for t in TOKEN_RE.findall(operand)]


def role_of(comment):
    """Return the first (role) marker of a .be comment, or ''."""
    m = TARGET_ROLE_RE.search(comment)
    return m.group(1) if m else ''


def is_target_like(mnem, comment):
    """A usage is target-like if the mnemonic or comment denotes a jump."""
    return mnem in TARGET_MNEMONICS or bool(role_of(comment))


def load_procedure_entries(root):
    """Load known procedure starts from docs/PROCEDURES-*.md.

    Returns {zone: {addr4: set(status)}} where addr4 is zero-padded octal.
    Status ОСН/ВЛОЖ marks a procedure entry; ДАН marks a rejected target.
    """
    docs = os.path.join(root, 'docs')
    entries = collections.defaultdict(lambda: collections.defaultdict(set))
    for name in sorted(os.listdir(docs)):
        if not (name.startswith('PROCEDURES-') and name.endswith('.md')):
            continue
        path = os.path.join(docs, name)
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                m = PROC_RE.match(line)
                if not m:
                    continue
                zone, addr, _end, status = m.groups()
                entries[zone][addr].add(status)
    return {z: dict(a) for z, a in entries.items()}


def local_entry(proc_entries, zone, value_oct):
    """Return status set of a procedure entry at (zone, label value), else ().

    The EQU value is already an octal address string; pad it to 4 digits
    so '11' matches catalogue address '0011'.
    """
    try:
        addr = int(value_oct, 8)
    except ValueError:
        return ()
    if addr > 0o7777:
        return ()
    addr4 = format(addr, '04o')
    return tuple(sorted(proc_entries.get(zone, {}).get(addr4, ())))


def classify_usage(usage, proc_entries):
    """Attach per-usage verdict and local-entry evidence (in place)."""
    status = local_entry(
        proc_entries, usage['zone'], usage['value_oct']
    ) if usage['target_like'] else ()
    entry = [s for s in status if s in ('ОСН', 'ВЛОЖ')]
    if not usage['target_like']:
        usage['verdict'] = 'PLAIN_CONSTANT'
        usage['local_entry'] = []
    elif entry:
        usage['verdict'] = 'LOCAL_ADDR'
        usage['local_entry'] = entry
    else:
        usage['verdict'] = 'EXTERNAL_OFFSET_CANDIDATE'
        usage['local_entry'] = list(status)  # e.g. ДАН


VERDICT_PRIORITY = {
    'EXTERNAL_OFFSET_CANDIDATE': 3,
    'LOCAL_ADDR': 2,
    'PLAIN_CONSTANT': 1,
    'UNKNOWN': 0,
}


def summarize_verdict(usages):
    """Roll per-usage verdicts up into one label verdict."""
    if not usages:
        return 'UNKNOWN'
    return max(
        (u['verdict'] for u in usages),
        key=lambda v: VERDICT_PRIORITY[v],
    )


def _plain_small_tokens(operand):
    """Small numeric/label tokens that stand alone in an operand.

    Compound expressions such as '64+4' are ignored: the '64' there is a
    BESM addressing constant, not a candidate module address.
    """
    if '+' in operand or '-' in operand:
        return []
    base = operand.strip()
    rm = REG_RE.search(base)
    if rm:
        base = base[:rm.start()].strip()
    if re.fullmatch(r"'?[0-7]+'?", base):
        return [base.strip("'")]
    return []


def detect_pairs(file_lines, global_values, target_labels, matchers=None,
                 small_labels=None):
    """Detect the two pair patterns described by the operator.

    A) sequential : a target-label usage followed within 1-3 lines by
                    another small constant or a branch/call line
                    ("address in external module" + "module start").
    B) register   : a ПВ/ПБ with (Мn) whose register was loaded with a
                    small constant on a preceding line.  Either the
                    branch label or the loaded label may be one of the
                    labels under study; both are recorded in 'labels'.
    """
    if matchers is None:
        matchers = {lab: label_pattern(lab) for lab in global_values}
    if small_labels is None:
        small_labels = [lab for lab, v in global_values.items()
                        if _is_small(v)]
    pairs = []
    for idx, raw in enumerate(file_lines):
        parsed = parse_code_line(raw)
        if not parsed:
            continue
        mnem, operand = parsed['mnem'], parsed['operand']
        hits = find_labels(operand, matchers)
        hit = next((lab for lab in hits if lab in target_labels), None)
        if hit is not None:
            value_oct = global_values.get(hit, '')
            small = _is_small(value_oct)

            # A) look ahead 1-3 lines
            for j in range(idx + 1, min(idx + 4, len(file_lines))):
                nxt = parse_code_line(file_lines[j])
                if not nxt:
                    continue
                other_toks = _plain_small_tokens(nxt['operand'])
                branch = nxt['mnem'] in TARGET_MNEMONICS
                if other_toks or branch:
                    pairs.append({
                        'kind': 'sequential',
                        'labels': [hit],
                        'label': hit,
                        'value_oct': value_oct,
                        'line': idx + 1,
                        'other_line': j + 1,
                        'other_text': file_lines[j].rstrip('\n'),
                        'other_tokens': other_toks,
                        'other_mnem': nxt['mnem'],
                        'small': small,
                    })
                    break

        # B) look back 1-3 lines for a register load feeding ПВ/ПБ
        if mnem in ('ПВ', 'ПБ'):
            rm = REG_RE.search(operand)
            if rm:
                reg = 'М' + rm.group(1)
                branch_labs = hits
                for j in range(max(0, idx - 3), idx):
                    prev = parse_code_line(file_lines[j])
                    if not prev:
                        continue
                    pop = prev['operand']
                    if not re.search(re.escape(reg) + r'(?![0-9])', pop):
                        continue
                    load_labs = [
                        lab for lab in find_labels(pop, matchers)
                        if lab in small_labels
                    ]
                    if not load_labs:
                        continue
                    involved = list(dict.fromkeys(branch_labs + load_labs))
                    pairs.append({
                        'kind': 'register',
                        'labels': involved,
                        'label': next(
                            (lab for lab in involved if lab in target_labels),
                            load_labs[0]),
                        'value_oct': global_values[load_labs[0]],
                        'line': j + 1,
                        'other_line': idx + 1,
                        'other_text': file_lines[idx].rstrip('\n'),
                        'load_text': file_lines[j].rstrip('\n'),
                        'register': reg,
                        'branch_mnem': mnem,
                        'branch_operand': operand,
                        'branch_labels': branch_labs,
                        'load_labels': load_labs,
                    })
    return pairs


def _is_small(value_oct):
    try:
        return 0 <= int(value_oct, 8) <= SMALL_LIMIT_OCT
    except (ValueError, TypeError):
        return False


def scan(root, labels=None, proc_entries=None):
    """Scan all bemsh/*.be files and return a structured result dict."""
    labels = list(labels or DEFAULT_LABELS)
    if proc_entries is None:
        proc_entries = load_procedure_entries(root)

    definitions = collections.defaultdict(list)
    global_values = {}
    usages = collections.defaultdict(list)
    pair_rows = []

    bemsh = os.path.join(root, 'bemsh')
    files = []
    for name in sorted(os.listdir(bemsh)):
        if not name.endswith('.be'):
            continue
        path = os.path.join(bemsh, name)
        with open(path, encoding='utf-8') as fh:
            raw = fh.read().splitlines()
        zone = zone_from_path(name)
        files.append((name, zone, raw))

    # Pass 1: collect every EQU definition before matching usages, so a
    # label defined in a later zone is still visible to earlier files.
    for name, zone, raw in files:
        for lineno, line in enumerate(raw, 1):
            eq = parse_equ(line)
            if not eq:
                continue
            lab, val = eq
            definitions[lab].append({
                'label': lab, 'zone': zone, 'line': lineno,
                'file': name, 'value_oct': val,
                'value_dec': int(val, 8),
            })
            global_values.setdefault(lab, val)

    matchers = {lab: label_pattern(lab) for lab in global_values}
    target_matchers = {lab: matchers[lab] for lab in labels if lab in matchers}
    small_labels = [lab for lab, v in global_values.items()
                    if _is_small(v)]

    # Pass 2: usages and pair evidence.
    for name, zone, raw in files:
        for lineno, line in enumerate(raw, 1):
            if parse_equ(line):
                continue
            parsed = parse_code_line(line)
            if not parsed:
                continue
            for lab in find_labels(parsed['operand'], target_matchers):
                u = {
                    'label': lab,
                    'zone': zone,
                    'line': lineno,
                    'file': name,
                    'mnem': parsed['mnem'],
                    'operand': parsed['operand'],
                    'comment': parsed['comment'],
                    'role': role_of(parsed['comment']),
                    'text': line.rstrip('\n'),
                    'value_oct': global_values.get(lab, ''),
                    'target_by_mnem': parsed['mnem'] in TARGET_MNEMONICS,
                    'target_by_role': bool(role_of(parsed['comment'])),
                    'target_like': is_target_like(
                        parsed['mnem'], parsed['comment']),
                }
                classify_usage(u, proc_entries)
                usages[lab].append(u)
        pair_rows.extend(
            dict(p, file=name, zone=zone)
            for p in detect_pairs(raw, global_values, labels,
                                  matchers, small_labels)
        )

    def pairs_for(lab):
        return [p for p in pair_rows if lab in p.get('labels', [p['label']])]

    rows = []
    for lab in labels:
        us = usages.get(lab, [])
        mn = collections.Counter(u['mnem'] for u in us)
        near = collections.Counter()
        for p in pairs_for(lab):
            if p['kind'] == 'sequential':
                for t in p['other_tokens']:
                    near[t.strip("'")] += 1
                if p['other_mnem'] in TARGET_MNEMONICS:
                    near['<' + p['other_mnem'] + '>'] += 1
            else:
                near['reg:' + p.get('register', '')] += 1
        rows.append({
            'label': lab,
            'zones': sorted({d['zone'] for d in definitions.get(lab, [])}),
            'defs': definitions.get(lab, []),
            'value_oct': global_values.get(lab, ''),
            'usages': us,
            'mnemonics': dict(mn),
            'usage_count': len(us),
            'nearby_constants': dict(near),
            'pairs': pairs_for(lab),
            'verdict': summarize_verdict(us),
            'usage_verdicts': dict(collections.Counter(
                u['verdict'] for u in us)),
        })

    all_usage_verdicts = collections.Counter()
    external_basis = collections.Counter()
    for r in rows:
        for u in r['usages']:
            all_usage_verdicts[u['verdict']] += 1
            if u['verdict'] == 'EXTERNAL_OFFSET_CANDIDATE':
                if u['target_by_mnem']:
                    external_basis['mnemonic'] += 1
                elif u['target_by_role']:
                    external_basis['comment_role'] += 1
    return {
        'root': root,
        'labels': labels,
        'rows': rows,
        'pairs': pair_rows,
        'verdict_counts': dict(collections.Counter(r['verdict'] for r in rows)),
        'usage_verdict_counts': dict(all_usage_verdicts),
        'external_basis': dict(external_basis),
        'procedure_zones': len(proc_entries),
    }


def format_report(result, max_examples=3):
    """Render a compact human-readable report (text, UTF-8)."""
    out = []
    out.append('EXTERNAL OFFSET CANDIDATE SCAN')
    out.append('=' * 40)
    vc = result['verdict_counts']
    out.append('label verdicts: ' + ', '.join(
        '{}:{}'.format(k, vc.get(k, 0))
        for k in ('EXTERNAL_OFFSET_CANDIDATE', 'LOCAL_ADDR',
                  'PLAIN_CONSTANT', 'UNKNOWN')))
    uv = result.get('usage_verdict_counts', {})
    out.append('usage verdicts: ' + ', '.join(
        '{}:{}'.format(k, uv.get(k, 0))
        for k in ('EXTERNAL_OFFSET_CANDIDATE', 'LOCAL_ADDR',
                  'PLAIN_CONSTANT', 'UNKNOWN')))
    eb = result.get('external_basis', {})
    out.append('external basis: mnemonic:{} comment-role:{}'.format(
        eb.get('mnemonic', 0), eb.get('comment_role', 0)))
    out.append('')
    hdr = ('label | zones | value | defs | usages | nearby | verdict')
    out.append(hdr)
    out.append('-' * len(hdr))
    for r in result['rows']:
        zones = ','.join(r['zones'][:4]) + (
            '+{}'.format(len(r['zones']) - 4) if len(r['zones']) > 4 else '')
        d0 = r['defs'][0] if r['defs'] else {}
        dstr = '{}:{}'.format(d0.get('zone', '-'), d0.get('line', '-'))
        mns = ','.join('{}×{}'.format(k, v) for k, v in
                       sorted(r['mnemonics'].items(),
                              key=lambda kv: -kv[1])[:6])
        near = ','.join('{}:{}'.format(k, v) for k, v in
                        sorted(r['nearby_constants'].items(),
                               key=lambda kv: -kv[1])[:4])
        out.append('{} | {} | {} | {} | {} ({}) | {} | {}'.format(
            r['label'], zones, r['value_oct'], dstr,
            r['usage_count'], mns, near, r['verdict']))
    out.append('')
    out.append('PAIR EVIDENCE (first {} per label)'.format(max_examples))
    out.append('-' * 40)
    for r in result['rows']:
        ps = r['pairs'][:max_examples]
        if not ps:
            continue
        out.append('[{}] {}'.format(r['label'], r['verdict']))
        for p in ps:
            if p['kind'] == 'register':
                out.append('  {} {}:{} load {} -> {}:{} {}'.format(
                    p.get('register', ''), p['zone'], p['line'],
                    ','.join(p.get('load_labels', [])),
                    p['zone'], p['other_line'], p['other_text'][:46]))
            else:
                out.append('  {} {}:{} -> {}:{} {}'.format(
                    'SEQ', p['zone'], p['line'],
                    p['zone'], p['other_line'], p['other_text'][:52]))
    return '\n'.join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    ap.add_argument('--root', default=root,
                    help='repository root (default: parent of tools/)')
    ap.add_argument('--labels', default=None,
                    help='file with one label per line')
    ap.add_argument('--json', action='store_true',
                    help='emit structured JSON to stdout')
    args = ap.parse_args(argv)

    labels = DEFAULT_LABELS
    if args.labels:
        with open(args.labels, encoding='utf-8') as fh:
            labels = [w for line in fh for w in line.split()
                      if not line.lstrip().startswith('#')] or DEFAULT_LABELS

    result = scan(args.root, labels)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(format_report(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
