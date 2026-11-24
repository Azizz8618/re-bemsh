#!/usr/bin/env python3
"""verify.pl-style sector comparison for compiled BEMSH modules.

Method taken from re-dispak/verify.pl:
  * module is compiled with 1-1 and written to PERS0 (tape 43),
  * silver zone is dumped from the PERS0 volume,
  * gold and silver are compared sector by sector with byte offset.

This tool does NOT compare translator core bytes in 0-0 mode; it
compares OBJECT MODULES after compilation. Relocation bits emitted
by external labels are part of the object and are resolved later
by the linker, so they are not an error at this stage.

Usage:
  python3 tools/v78_verify_module.py MODULE.be --dest 0100 --len 2 \
      --gold-dir /path/to/gold --gold-disk 2248 --work /var/tmp/v78-verify
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BESM6_SHARE = '/usr/local/share/besm6'
SECTOR = 1536
ZONE = 6144


def guard(path):
    real = os.path.realpath(path)
    share = os.path.realpath(BESM6_SHARE)
    if real == share or real.startswith(share + os.sep):
        raise RuntimeError('refuse write to reference images: ' + path)
    return path


def asm_job(src, dest, length, mode='МОД'):
    """Build the same job shape as re-dispak/asm.pl."""
    name = None
    for line in open(src, encoding='utf-8', errors='replace'):
        p = line.split()
        if len(p) >= 2 and p[1].lower() in ('старт', 'start', 'ctapt'):
            name = p[0]
            break
    if not name:
        raise RuntimeError('no START label in ' + src)
    head = """шифр 419999^
трак 64^
лент 30(2048-6200)^
лент 42(2099)^
лент 43(2222-ЗП)^
ацп 40^
росп 0^
врем 240^
лист 0-37^
вход 4000^
е
в 4000
к 00 010 4003
к 15 24 04000
к 00 066 0001 00 000 0100
с 3000 67
в 14000
а1
ВВД$$$^
"""
    lines = []
    for line in open(src, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        # asm.pl strips everything after a spaced comma
        idx = line.find('  ,')
        if idx >= 0:
            line = line[:idx]
        lines.append(line if line.strip() else '*')
    tail = """
КВЧ$$$^
ТРН$$$^
ЧТКОМП420070^
1-1^
БТМАЛФ^
ЗОН%s43%s 00%d^
КНЦ$$$^
_$ЕКОНЕЦ
""" % (mode, dest, length)
    return head + '\n'.join(l + '^' for l in lines) + tail


def run(cmd, cwd, env):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def compare(gold, silver):
    """Return list of differing sectors and total differing bytes."""
    sectors = []
    total = 0
    with open(gold, 'rb') as g, open(silver, 'rb') as s:
        gd = g.read()
        sd = s.read()
    for off in range(0, min(len(gd), len(sd)), SECTOR):
        a = gd[off:off + SECTOR]
        b = sd[off:off + SECTOR]
        n = sum(1 for x, y in zip(a, b) if x != y)
        if n:
            sectors.append((off // SECTOR, n))
            total += n
    return sectors, total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('module')
    ap.add_argument('--dest', required=True, help='PERS0 logical zone (octal)')
    ap.add_argument('--len', dest='length', type=int, default=1)
    ap.add_argument('--gold-dir', required=True)
    ap.add_argument('--gold-disk', default='2248')
    ap.add_argument('--work', default='/var/tmp/v78-verify')
    ap.add_argument('--format', choices=('json', 'text'), default='text')
    args = ap.parse_args()

    work = args.work
    os.makedirs(work, exist_ok=True)
    images = os.path.join(work, 'images')
    os.makedirs(images, exist_ok=True)
    for vol in ('2048', '2053', '2099', '2222', '2248'):
        src = os.path.join(BESM6_SHARE, vol)
        dst = os.path.join(images, vol)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
    env = dict(os.environ, BESM6_PATH=images + ':' + BESM6_SHARE)
    job = os.path.join(work, 'module.b6')
    open(job, 'w', encoding='utf-8').write(asm_job(args.module, args.dest,
                                                    args.length))
    rc, out = run(['dispak', '-l', job], work, env)
    if rc != 0:
        print('COMPILE FAIL', out[-500:], file=sys.stderr)
        return 1
    silver = os.path.join(work, 'S%s-L%d' % (args.dest, args.length))
    cmd = ['besmtool', 'dump', '2222', '--start=0%s' % args.dest,
           '--length=%d' % args.length, '--to-file=' + silver]
    rc, out = run(cmd, work, env)
    if rc != 0:
        print('DUMP FAIL', out[-500:], file=sys.stderr)
        return 1
    gold = os.path.join(args.gold_dir,
                        'G%s-L%d' % (args.dest, args.length))
    if not os.path.isfile(gold):
        cmd = ['besmtool', 'dump', args.gold_disk,
               '--start=0%s' % args.dest, '--length=%d' % args.length,
               '--to-file=' + gold]
        rc, out = run(cmd, work, env)
        if rc != 0:
            print('GOLD FAIL', out[-500:], file=sys.stderr)
            return 1
    sectors, total = compare(gold, silver)
    result = {'module': args.module, 'dest': args.dest,
              'length': args.length, 'differing_sectors': sectors,
              'differing_bytes': total, 'match': total == 0}
    if args.format == 'json':
        import json
        print(json.dumps(result, ensure_ascii=False))
    else:
        print('МОДУЛЬ', args.module, 'зона', args.dest)
        print('секторов с отличиями:', len(sectors), 'байт:', total)
        for sec, n in sectors[:10]:
            print('  сектор', sec, 'отличий', n)
    return 0 if total == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
