#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сравнение зон 0137-0177 томов 2048 / 2148 / 2248.

Только чтение эталонов: besmtool dump --to-file пишет дампы
в уникальный temp-каталог. guard_output() запрещает любую
запись внутрь каталога образов, включая /usr/local/share.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

DEFAULT_ROOT = '/usr/local/share/besm6'
DEFAULT_DISKS = ('2048', '2148', '2248')
ZONE_FIRST = '0137'
ZONE_LAST = '0177'
ZONE_LOADER_LAST = '0143'
ZONE_BYTES = 6144
MD5_2048 = '2f503f5b8f8fb6ad12632fed6f8cf17f'
MD5_2148 = '90434226c98df1c40bbb8d76e1560613'

# Слова переадресации процитированы из analysis/reloc.md и
# docs/SEMANTIC/Z0142.md. Это подсказки, не команды.
RELOC_WORDS = (
    "выпр '70707'(М17)",
    "зп '70000'",
    'мода',
    'пб (М3)',
    "'36436'",
)

EXIT_REFUSE = 3


class GuardError(Exception):
    """Попытка записи в каталог эталонных образов."""


def zone_dec(zone):
    """Ведущий 0: восьмеричное, иначе десятичное."""
    s = str(zone).strip()
    return int(s, 8) if s.startswith('0') else int(s, 10)


def zone_oct(z):
    """Dec-зона в 4-значной восьмеричной записи."""
    return format(z, '04o')


def zone_list(first, last):
    """Список dec-зон в диапазоне включительно."""
    a, b = zone_dec(first), zone_dec(last)
    if a > b:
        raise ValueError('bad zone range')
    return list(range(a, b + 1))


def md5_concat(blobs):
    """md5 побайтовой склейки блоков зон."""
    h = hashlib.md5()
    for blob in blobs:
        h.update(blob)
    return h.hexdigest()


def diff_bytes(a, b):
    """Число отличающихся байтов, включая разницу длин."""
    return (sum(x != y for x, y in zip(a, b))
            + abs(len(a) - len(b)))


def is_loader(z):
    """Зона относится к загрузчику 0137-0143."""
    lo = zone_dec(ZONE_FIRST)
    hi = zone_dec(ZONE_LOADER_LAST)
    return lo <= z <= hi


def diff_map(zones_a, zones_b):
    """Отличающиеся зоны: dec-зона и число байтов."""
    out = {}
    for z in sorted(set(zones_a) | set(zones_b)):
        a = zones_a.get(z, b'')
        b = zones_b.get(z, b'')
        n = diff_bytes(a, b)
        if n:
            out[z] = n
    return out


def reloc_hits(text):
    """Какие слова переадресации есть в тексте."""
    return {w: w in text for w in RELOC_WORDS}


def guard_output(path, root=DEFAULT_ROOT):
    """REFUSE, если путь записи внутри каталога образов."""
    if path is None:
        return True
    p = os.path.realpath(os.path.expanduser(str(path)))
    bases = (os.path.realpath(root),
             os.path.realpath('/usr/local/share'))
    for base in bases:
        if p == base or p.startswith(base + os.sep):
            raise GuardError('REFUSE: output inside %s: %s'
                             % (base, path))
    return True


def dump_command(besmtool, disk, z, path):
    """Команда besmtool dump одной зоны."""
    return [besmtool, 'dump', str(disk),
            '--start=' + zone_oct(z), '--length=1',
            '--to-file=' + path]


def dump_zones(disk, zones, root, besmtool, workdir):
    """Слить зоны диска в workdir: dec-зона и bytes."""
    out = {}
    env = dict(os.environ)
    env['BESM6_PATH'] = root
    for z in zones:
        name = '%s-z%s.bin' % (disk, zone_oct(z))
        path = os.path.join(workdir, name)
        cmd = dump_command(besmtool, disk, z, path)
        r = subprocess.run(
            cmd, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        if r.returncode != 0:
            err = r.stderr.decode('utf-8', 'replace')
            msg = err.strip()
            raise RuntimeError('dump failed: %s %s: %s'
                               % (disk, zone_oct(z), msg))
        with open(path, 'rb') as fh:
            data = fh.read()
        if len(data) != ZONE_BYTES:
            n = len(data)
            raise RuntimeError('bad zone size: %d' % n)
        out[z] = data
    return out


def build_report(dumps, first=ZONE_FIRST, last=ZONE_LAST,
                 baseline='2048'):
    """Отчёт: список зон, md5 склейки и diff к baseline."""
    zones = zone_list(first, last)
    report = {
        'zones': [zone_oct(z) for z in zones],
        'zone_bytes': ZONE_BYTES,
        'concat_bytes': len(zones) * ZONE_BYTES,
        'baseline': baseline,
        'disks': {},
        'diffs': {},
    }
    for disk in sorted(dumps):
        data = dumps[disk]
        missing = [z for z in zones if z not in data]
        if missing:
            raise RuntimeError('missing zones on %s: %s'
                               % (disk, missing))
        blob = b''.join(data[z] for z in zones)
        report['disks'][disk] = {
            'md5_concat': md5_concat([blob]),
            'zone_md5': {
                zone_oct(z): hashlib.md5(
                    data[z]).hexdigest()
                for z in zones
            },
        }
    if baseline in dumps:
        for disk in sorted(dumps):
            if disk == baseline:
                continue
            dm = diff_map(dumps[baseline], dumps[disk])
            report['diffs'][disk] = {
                zone_oct(z): n
                for z, n in sorted(dm.items())
            }
    return report


def format_text(report):
    """Текстовый отчёт, строки не длиннее 60 колонок."""
    z = report['zones']
    lines = ['zones: %s..%s, %d x %d bytes'
             % (z[0], z[-1], len(z), report['zone_bytes'])]
    for disk, info in report['disks'].items():
        lines.append('%s md5 concat: %s'
                     % (disk, info['md5_concat']))
    for disk, diffs in report['diffs'].items():
        if not diffs:
            lines.append('%s vs %s: identical'
                         % (disk, report['baseline']))
            continue
        for zone, n in diffs.items():
            tag = ('loader' if is_loader(zone_dec(zone))
                   else 'kernel')
            lines.append('%s vs %s: %s %s %d bytes'
                         % (disk, report['baseline'],
                            zone, tag, n))
    return '\n'.join(lines) + '\n'


def parse_args(argv):
    """Разбор аргументов CLI."""
    p = argparse.ArgumentParser(
        description='diff зон 0137-0177: 2048/2148/2248')
    p.add_argument('--root', default=DEFAULT_ROOT,
                   help='каталог образов, только чтение')
    p.add_argument('--disks', nargs='+',
                   default=list(DEFAULT_DISKS))
    p.add_argument('--first', default=ZONE_FIRST)
    p.add_argument('--last', default=ZONE_LAST)
    p.add_argument('--baseline', default='2048')
    tool = shutil.which('besmtool') or 'besmtool'
    p.add_argument('--besmtool', default=tool)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--format', choices=('json', 'text'),
                   default='text')
    p.add_argument('--output', default=None,
                   help='файл отчёта вне каталога образов')
    return p.parse_args(argv)


def main(argv=None):
    """Входная точка: guard, дампы во temp, отчёт."""
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    try:
        guard_output(args.output, args.root)
    except GuardError as e:
        print(e, file=sys.stderr)
        return EXIT_REFUSE
    zones = zone_list(args.first, args.last)
    if args.dry_run:
        plan = []
        for disk in args.disks:
            for z in zones:
                path = os.path.join(
                    '<TEMP>',
                    '%s-z%s.bin' % (disk, zone_oct(z)))
                plan.append(' '.join(dump_command(
                    args.besmtool, disk, z, path)))
        if args.format == 'json':
            print(json.dumps({'dry_run': True,
                              'commands': plan},
                             ensure_ascii=False, indent=2))
        else:
            print('\n'.join(plan))
        return 0
    try:
        with tempfile.TemporaryDirectory(
                prefix='loader-reloc-') as workdir:
            guard_output(workdir, args.root)
            dumps = {}
            for disk in args.disks:
                dumps[disk] = dump_zones(
                    disk, zones, args.root,
                    args.besmtool, workdir)
            report = build_report(
                dumps, args.first, args.last, args.baseline)
    except GuardError as e:
        print(e, file=sys.stderr)
        return EXIT_REFUSE
    if args.format == 'json':
        text = json.dumps(report, ensure_ascii=False,
                          indent=2)
    else:
        text = format_text(report)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as fh:
            fh.write(text + '\n')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
