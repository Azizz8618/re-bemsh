#!/usr/bin/env python3
"""Replace local numeric operands that point to code labels.

Read-only analysis by default; --apply edits .be files on COPIES
only and verifies each zone with rebuild-zone.sh. Inputs are the
JSON outputs of tools/v78_label_index.py and v78_offset_resolve.py.

Usage:
  python3 tools/v78_replace_offsets.py --file bemsh/ASM-Z0055.be
      --labels LABELS.json --offsets OFFSETS.json --mode ASM --zone 0055
  python3 tools/v78_replace_offsets.py ... --apply --backup DIR
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REBUILD = os.path.join(ROOT, 'tools', 'rebuild-zone.sh')
RE_START = re.compile(r'^([A-Z0-9]{5,6})\s+СТАРТ\b')


def load(path):
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else data.get('records', [])


def start_label(lines):
    for line in lines:
        m = RE_START.match(line)
        if m:
            return m.group(1)
    return None


def plan_edits(lines, labels, offsets, target, ham_fix=0):
    """Return (new_lines, edits) without changing the original."""
    index = {r['label']: r for r in labels}
    out = list(lines)
    edits = []
    by_line = {}
    for r in offsets:
        if r.get('file') != target:
            continue
        if r.get('mnemonic') == 'ЭКВ':
            continue
        if r.get('scope') != 'local':
            continue
        lab = index.get(r.get('target_label'))
        if not lab or lab.get('kind') != 'code':
            continue
        raw = r.get('operand_raw', '')
        # only a bare decimal number, optionally with (Mn) / (13) suffix
        m = re.match(r'^(\d{1,5})\s*(\([^)]*\))?\s*$', raw.strip())
        if not m:
            continue
        num = int(m.group(1))
        suffix = m.group(2) or ''
        # decimal operand must equal the octal label offset
        if num != int(lab['offset'], 8):
            continue
        lineno = r['line'] - 1
        if not 0 <= lineno < len(out):
            continue
        old_line = out[lineno]
        if 'ЭКВ' in old_line or '-З' in old_line:
            continue
        pattern = r'(\b)' + re.escape(m.group(1)) + r'(\b)'
        if not re.search(pattern, old_line):
            continue
        tail = ('+%d' % ham_fix) if ham_fix else ''
        new_line = re.sub(pattern, lab['label'] + '-З' + tail, old_line, count=1)
        edits.append({'line': r['line'], 'old': old_line.rstrip(),
                      'new': new_line.rstrip(), 'label': lab['label']})
        out[lineno] = new_line
        by_line[r['line']] = True
    base = start_label(out)
    if edits and base:
        has_base = any(re.match(r'^З\s+ЭКВ\b', l) for l in out)
        if not has_base:
            pos = next(i for i, l in enumerate(out) if RE_START.match(l)) + 1
            out.insert(pos, 'З       ЭКВ %s' % base)
    return out, edits


def rebuild(zone, mode):
    cmd = ['bash', REBUILD, zone]
    if mode != 'B':
        cmd.append(mode)
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--labels', required=True)
    ap.add_argument('--offsets', required=True)
    ap.add_argument('--file', required=True)
    ap.add_argument('--zone', required=True)
    ap.add_argument('--mode', default='B', choices=('B', 'MBE2', 'ASM'))
    ap.add_argument('--backup', default='/var/tmp/v78-replace-backup')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--ham-fix', default='0', help="decimal add after -З, e.g. 1 for HAM zones")
    args = ap.parse_args()

    path = os.path.join(ROOT, args.file)
    lines = open(path, encoding='utf-8').read().splitlines()
    new, edits = plan_edits(lines, load(args.labels), load(args.offsets),
                            args.file, int(args.ham_fix))
    print('candidate edits:', len(edits))
    for e in edits[:20]:
        print('  %d  %s  ->  %s' % (e['line'], e['old'][:48], e['new'][:48]))
    if not args.apply or not edits:
        return 0

    os.makedirs(args.backup, exist_ok=True)
    backup = os.path.join(args.backup, os.path.basename(path))
    shutil.copy2(path, backup)
    open(path, 'w', encoding='utf-8').write('\n'.join(new) + '\n')
    rc, out = rebuild(args.zone, args.mode)
    if rc != 0:
        shutil.copy2(backup, path)
        print('REBUILD FAIL, reverted:', args.file)
        print(out[-800:])
        return 1
    print('REBUILD OK:', args.file)
    return 0


if __name__ == '__main__':
    sys.exit(main())
