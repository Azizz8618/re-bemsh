#!/usr/bin/env python3
"""Controlled dispak runner for the ВЕР.06/78 deck corpus.

Runs dispak on COPIES of the reference volumes. Stdout is a
listing file. Stderr is streamed line by line into a bounded
JSONL event file. The full trace is never stored.

Exit codes: 0 ok, 1 --check violation, 2 input or CLI error,
3 guard violation (write attempt or changed image).

Usage:
  python3 tools/v78_runner.py DECK.b6 [DECK.b6 ...]
  python3 tools/v78_runner.py DECK.b6 --format json
  python3 tools/v78_runner.py DECK.b6 --check --out DIR
  python3 tools/v78_runner.py --help

See analysis/V78-RUNNER.md.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REF_DIR = '/usr/local/share/besm6'
SCRATCH_ROOT = '/var/tmp/v78-runner'
DISPAK = ('/home/azizz/Yandex.Disk/dispak/'
          'build/dispak/dispak')
VOLUMES = ('2048', '2053', '2099', '2248')
PROTECTED = ('/usr/local/share/besm6', '~/.besm6')
PC_LIMIT = 0o200000
CHUNK = 1 << 20
HEAD_N = 8
VIOLATION_N = 30
SCHEMA = 1

PHASES = ('BOOT', 'RLOAD', 'RLE', 'INPUT',
          'EDITOR', 'MACHINE', 'LISTING', 'UNKNOWN')
EVENT_KEYS = ('n', 'kind', 'pc', 'mn',
              'operand', 'acc', 'phase')

# Proven patterns from tools/v78_token_diff.py. A store line
# is a memory write, a DD line is I/O, neither is a PC.
RE_EXEC = re.compile(r'^([0-7]{5}):\s+(\S+)(.*)$')
RE_STORE = re.compile(r'^\s*([0-7]{5,6}):\s+store\b(.*)$',
                      re.I)
RE_DD = re.compile(r'^\s*DD\b(.*)$')
RE_DD_PC = re.compile(r'\bpc=([0-7]{1,6})L?(?![0-7])')
RE_PC_FIELD = re.compile(r'\bpc=(\S+)')
RE_MALFORMED = re.compile(r'^\s*[0-7]{4,6}:\s*$')
RE_ACC = re.compile(r'\bacc=(\S+)')

# Anchors from docs/PLAN-TEST-CORPUS.md, section 3.5.
# The address 02000 is shared: xta enters the editor,
# ntr enters the machine. Hence the optional mnemonic.
DEFAULT_ANCHORS = (
    ('00110', None, 'RLOAD'),
    ('076600', None, 'RLE'),
    ('076000', None, 'INPUT'),
    ('02000', 'xta', 'EDITOR'),
    ('02000', 'ntr', 'MACHINE'),
    ('04201', None, 'LISTING'),
)


class GuardError(Exception):
    """Write to a reference image was refused."""


class Anchor:
    """One ordered phase transition."""

    __slots__ = ('pc', 'mn', 'phase')

    def __init__(self, pc, phase, mn=None):
        self.pc = int(pc, 8)
        self.mn = mn
        self.phase = phase

    def matches(self, pc, mn):
        """True if this instruction triggers the anchor."""
        return self.pc == pc and (
            self.mn is None or self.mn == mn)


class PhaseMap:
    """Monotonic state machine over ordered anchors."""

    def __init__(self, anchors, initial='BOOT'):
        self.anchors = list(anchors)
        self.initial = initial
        self.cursor = 0
        self.current = initial

    def update(self, pc, mn):
        """Advance on a matching anchor, return phase."""
        for idx in range(self.cursor, len(self.anchors)):
            if self.anchors[idx].matches(pc, mn):
                self.current = self.anchors[idx].phase
                self.cursor = idx + 1
                break
        return self.current

    def clone(self):
        """Fresh state, same anchor rules."""
        return PhaseMap(self.anchors, self.initial)


def default_phase_map():
    """Build the plan's default phase map."""
    anchors = [Anchor(pc, phase, mn)
               for pc, mn, phase in DEFAULT_ANCHORS]
    return PhaseMap(anchors)


def load_phase_map(path):
    """Load a JSON phase map from disk."""
    with open(path, encoding='utf-8') as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError('phase map must be a JSON object')
    if 'anchors' in raw:
        items = raw['anchors']
        initial = raw.get('initial', 'BOOT')
    else:
        items = [{'pc': key, 'phase': value}
                 for key, value in raw.items()]
        initial = 'BOOT'
    if not isinstance(items, list):
        raise ValueError('anchors must be a list')
    if not re.fullmatch(r'[A-Z][A-Z0-9_]*', initial):
        raise ValueError('bad initial phase: %s' % initial)
    anchors = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('anchor must be an object')
        pc = str(item.get('pc', ''))
        phase = str(item.get('phase', ''))
        mn = item.get('mn')
        if not re.fullmatch(r'[0-7]{1,6}', pc):
            raise ValueError('bad anchor pc: %s' % pc)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', phase):
            raise ValueError('bad anchor phase: %s' % phase)
        if mn is not None:
            mn = str(mn)
            if not re.fullmatch(r'[A-Za-z0-9*+\-]+', mn):
                raise ValueError('bad anchor mn: %s' % mn)
        anchors.append(Anchor(pc, phase, mn))
    return PhaseMap(anchors, initial)


def protected_dirs(ref_dir):
    """All directories that must stay read-only."""
    found = [os.path.abspath(os.path.expanduser(p))
             for p in PROTECTED]
    found.append(os.path.abspath(ref_dir))
    return tuple(dict.fromkeys(found))


def is_protected(path, dirs):
    """True if path is inside a protected directory."""
    real = os.path.abspath(os.path.expanduser(path))
    for item in dirs:
        if real == item or real.startswith(item + os.sep):
            return True
    return False


def guard_writable(path, dirs):
    """Refuse a write target under a protected dir."""
    if is_protected(path, dirs):
        raise GuardError('не пишем в эталон: %s' % path)


def md5_file(path):
    """Stream a file through md5, never load it whole."""
    digest = hashlib.md5()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def octstr(value, digits=5):
    """Octal string, zero padded to at least digits."""
    if value is None:
        return None
    return ('%%0%do' % digits) % value


def split_acc(tail):
    """Split an instruction tail into operand and acc."""
    match = RE_ACC.search(tail)
    if match is None:
        return tail.strip(), None
    return tail[:match.start()].strip(), match.group(1)


def classify(text):
    """Return kind, pc, mn, operand, acc of one line."""
    match = RE_DD.match(text)
    if match:
        found = RE_DD_PC.search(text)
        pc = int(found.group(1), 8) if found else None
        tail = RE_PC_FIELD.sub('', match.group(1),
                               count=1).strip()
        return ('dd', pc, None, tail or None, None)
    match = RE_EXEC.match(text)
    if match:
        pc = int(match.group(1), 8)
        mn = match.group(2)
        if mn.lower() == 'store':
            return ('store', pc, 'store',
                    match.group(3).strip() or None, None)
        operand, acc = split_acc(match.group(3))
        return ('exec', pc, mn, operand or None, acc)
    match = RE_STORE.match(text)
    if match:
        return ('store', int(match.group(1), 8),
                'store', match.group(2).strip() or None,
                None)
    return ('other', None, None, None, None)


class StreamParser:
    """Bounded accumulators over a stream of trace lines."""

    def __init__(self, phase_map):
        self.pm = phase_map
        self.lines = 0
        self.kinds = Counter()
        self.phases = Counter()
        self.exec_phases = Counter()
        self.span = {}
        self.head = []
        self.phase_first = {}
        self.last = None
        self.violations = []
        self.violations_total = 0

    def add_violation(self, invariant, detail):
        """Count a violation, keep a bounded sample."""
        self.violations_total += 1
        if len(self.violations) < VIOLATION_N:
            self.violations.append({
                'invariant': invariant, 'detail': detail})

    def feed(self, text):
        """Consume one line, return an event or None."""
        self.lines += 1
        kind, pc, mn, operand, acc = classify(text)
        if kind == 'other':
            self.kinds['other'] += 1
            if RE_MALFORMED.match(text):
                self.add_violation(
                    'malformed_pc_line',
                    'line %d has no mnemonic' % self.lines)
            return None
        if kind == 'exec':
            phase = self.pm.update(pc, mn)
        else:
            phase = self.pm.current
        if pc is not None and not 0 <= pc < PC_LIMIT:
            self.add_violation(
                'pc_range', 'line %d %s pc=%s' % (
                    self.lines, kind, octstr(pc)))
        if (kind == 'dd' and pc is None and
                RE_PC_FIELD.search(text)):
            self.add_violation(
                'malformed_dd_pc',
                'line %d pc is not octal' % self.lines)
        event = {
            'n': self.lines, 'kind': kind,
            'pc': octstr(pc), 'mn': mn,
            'operand': operand, 'acc': acc,
            'phase': phase,
        }
        self.kinds[kind] += 1
        self.phases[phase] += 1
        if kind == 'exec':
            self.exec_phases[phase] += 1
        row = self.span.setdefault(
            phase, {'first': self.lines,
                    'last': self.lines})
        row['last'] = self.lines
        if phase not in self.phase_first:
            self.phase_first[phase] = event
        if len(self.head) < HEAD_N:
            self.head.append(event)
        self.last = event
        return event


def normalize(raw):
    """Decode one stderr line and drop its line ending."""
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', 'replace')
    return raw.lstrip('\ufeff').rstrip('\r\n')


def run_one(deck, out_dir=None, phase_map=None, dispak=None,
            ref_dir=None, volumes=None, scratch_root=None):
    """Run one deck on copies, return its report."""
    deck = os.path.abspath(deck)
    if not deck.lower().endswith('.b6'):
        raise ValueError('deck must end with .b6: %s' %
                         deck)
    if not os.path.isfile(deck):
        raise ValueError('deck not found: %s' % deck)
    ref_dir = os.path.abspath(ref_dir or REF_DIR)
    scratch_root = os.path.abspath(
        scratch_root or SCRATCH_ROOT)
    dirs = protected_dirs(ref_dir)
    if is_protected(scratch_root, dirs):
        raise GuardError(' scratch под эталоном: %s' %
                         scratch_root)
    stem = Path(deck).stem
    target = os.path.join(out_dir or scratch_root, stem)
    guard_writable(target, dirs)
    os.makedirs(scratch_root, exist_ok=True)
    os.makedirs(target, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix='run-',
                               dir=scratch_root)
    binary = dispak or DISPAK
    names = tuple(volumes or VOLUMES)
    listing_path = os.path.join(target, 'listing.txt')
    events_path = os.path.join(target, 'events.jsonl')
    manifest_path = os.path.join(target, 'manifest.json')
    images = []
    try:
        for name in names:
            source = os.path.join(ref_dir, name)
            if not os.path.isfile(source):
                raise ValueError('нет тома: %s' % source)
            images.append({'name': name,
                           'before': md5_file(source),
                           'after': None, 'same': None})
            shutil.copyfile(source,
                            os.path.join(scratch, name))
        deck_copy = os.path.join(scratch,
                                 os.path.basename(deck))
        shutil.copyfile(deck, deck_copy)
        env = os.environ.copy()
        env['BESM6_PATH'] = os.pathsep.join(
            [scratch, ref_dir])
        pm = (phase_map.clone() if phase_map
              else default_phase_map())
        parser = StreamParser(pm)
        command = [binary, '-l', '-tt', deck_copy]
        with open(listing_path, 'wb') as listing, \
                open(events_path, 'w', encoding='utf-8') \
                as events:
            proc = subprocess.Popen(
                command, stdin=subprocess.DEVNULL,
                stdout=listing, stderr=subprocess.PIPE,
                env=env)
            for raw in proc.stderr:
                event = parser.feed(normalize(raw))
                if event is not None:
                    events.write(
                        json.dumps(
                            event,
                            ensure_ascii=False) + '\n')
            proc.stderr.close()
            status = proc.wait()
        for row in images:
            row['after'] = md5_file(
                os.path.join(ref_dir, row['name']))
            row['same'] = row['after'] == row['before']
        if status != 0:
            raise ValueError(
                'dispak exit=%d (trace: %s)' % (
                    status, events_path))
        manifest = {
            'schema': SCHEMA,
            'event_keys': list(EVENT_KEYS),
            'deck': deck,
            'deck_copy': os.path.basename(deck_copy),
            'dispak': binary,
            'besm6_path': env['BESM6_PATH'],
            'scratch': scratch,
            'images': images,
            'listing': listing_path,
            'events': events_path,
            'lines': parser.lines,
            'counts': {
                'kind': dict(sorted(parser.kinds.items())),
                'phase': dict(sorted(
                    parser.phases.items())),
                'exec_phase': dict(sorted(
                    parser.exec_phases.items())),
            },
            'phase_span': {key: parser.span[key]
                           for key in sorted(parser.span)},
            'phase_first': {key: parser.phase_first[key]
                            for key in
                            sorted(parser.phase_first)},
            'head': parser.head,
            'last_event': parser.last,
            'parse': {
                'violations_total': parser.violations_total,
                'violations': parser.violations,
            },
        }
        with open(manifest_path, 'w',
                  encoding='utf-8') as h:
            json.dump(manifest, h, ensure_ascii=False,
                      sort_keys=True, indent=2)
            h.write('\n')
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    changed = [row['name'] for row in images
               if not row['same']]
    if changed:
        raise GuardError('образ изменился: %s' %
                         ','.join(changed))
    return {'deck': deck, 'listing': listing_path,
            'events': events_path,
            'manifest': manifest_path, 'data': manifest}


def walk_numbers(value, path=''):
    """Yield integer fields with their paths."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk_numbers(
                item, path + '/' + key)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            yield from walk_numbers(
                item, '%s/%d' % (path, idx))
    elif isinstance(value, int) and not isinstance(
            value, bool):
        yield path, value


def check(report):
    """Validate manifest invariants for --check."""
    data = report['data']
    items = list(data['parse']['violations'])
    total = data['parse']['violations_total']

    def add(invariant, detail):
        nonlocal total
        total += 1
        if len(items) < VIOLATION_N:
            items.append({'invariant': invariant,
                          'detail': detail})

    for row in data['images']:
        if not row['same']:
            add('image_changed', 'том %s' % row['name'])
    numeric = list(walk_numbers(data))
    for path, value in numeric:
        if value < 0:
            add('no_negative_counts',
                '%s = %d' % (path, value))
    for event in data['head']:
        if tuple(event) != EVENT_KEYS:
            add('bad_event_schema', 'n=%d' % event['n'])
    return {
        'ok': total == 0,
        'checked': len(numeric) + len(data['head']),
        'violations_total': total,
        'violations': items,
    }


def sample(text, limit=48):
    """Shorten a path for a report row."""
    text = str(text)
    if len(text) > limit:
        return '...' + text[-limit + 3:]
    return text


def format_text(payload, checked=None):
    """Human-readable summary under 60 columns."""
    out = ['V78 RUNNER']
    for report in payload['runs']:
        data = report['data']
        out.append('колода: %s' % sample(report['deck']))
        out.append('  строк трассы: %d' % data['lines'])
        counts = data['counts']['kind']
        out.append('  exec/store/dd: %d/%d/%d' % (
            counts.get('exec', 0), counts.get('store', 0),
            counts.get('dd', 0)))
        out.append('  фазы: %s' % ' '.join(
            '%s=%d' % (key, value)
            for key, value in
            data['counts']['phase'].items()))
        first = data['head'][0] if data['head'] else None
        if first is None:
            out.append('  первое событие: нет')
        else:
            out.append('  первое: n=%d %s %s %s' % (
                first['n'], first['kind'], first['pc'],
                first['mn']))
        same = all(row['same'] for row in data['images'])
        out.append('  md5 эталонов: %s' % (
            'OK' if same else 'ИЗМЕНЁН'))
        out.append('  манифест: %s' % sample(
            report['manifest']))
    if checked is not None:
        ok = all(item['ok'] for item in checked)
        out.append('ПРОВЕРКА: %s' % (
            'OK' if ok else 'НАРУШЕНИЯ'))
        for item in checked:
            out.append('  нарушений: %d' %
                       item['violations_total'])
    return '\n'.join(out)


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            'Run dispak on deck COPIES; stream a bounded '
            'event fixture; no writes to the images.'))
    parser.add_argument(
        'decks', nargs='+', metavar='DECK.b6',
        help='one or more deck files')
    parser.add_argument(
        '--format', choices=('json', 'text'),
        default='text',
        help='output format (default: text)')
    parser.add_argument(
        '--check', action='store_true',
        help='validate invariants; exit 1 on violation')
    parser.add_argument(
        '--out', metavar='DIR',
        help='base directory for listing, events, manifest')
    parser.add_argument(
        '--phase-map', metavar='FILE',
        help='JSON file with ordered phase anchors')
    parser.add_argument(
        '--dispak', metavar='PATH',
        help='explicit path to the dispak binary')
    args = parser.parse_args(argv)
    try:
        phase_map = (load_phase_map(args.phase_map)
                     if args.phase_map
                     else default_phase_map())
        reports = [run_one(deck, args.out, phase_map,
                           args.dispak)
                   for deck in args.decks]
    except GuardError as exc:
        print('guard: %s' % exc, file=sys.stderr)
        return 3
    except (OSError, ValueError) as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2
    payload = {'runs': reports}
    checked = None
    if args.check:
        checked = [check(report) for report in reports]
        payload['check'] = checked
    if args.format == 'json':
        print(json.dumps(payload, ensure_ascii=False,
                         sort_keys=True, indent=2))
    else:
        print(format_text(payload, checked))
    if checked is not None and any(
            not item['ok'] for item in checked):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
