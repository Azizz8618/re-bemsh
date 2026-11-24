#!/usr/bin/env python3
"""Own link+verify scenario modeled on re-dispak asm.pl/rvs.pl/verify.pl.

Flow:
  1. compile each .be with 1-1 into a PERS0 source zone (43SRC)
  2. link all modules with a generated rvs-style job (43OUT)
  3. dump linked zones from PERS0 and compare SECTOR BY SECTOR with
     gold disk zones (the same cmp -i 1536 -n 1536 logic as verify.pl)

No external module corpus is used: every module comes from our own
bemsh/*.be sources.

Usage:
  python3 tools/v78_link_verify.py compile --zones 0137,0147 --work DIR
  python3 tools/v78_link_verify.py link --zones 0137,0147 --work DIR
  python3 tools/v78_link_verify.py verify --zones 0137,0147 --work DIR
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARE = '/usr/local/share/besm6'
SRC_BASE = 0o4000   # our PERS0 source zones
OUT_BASE = 0o5000   # our PERS0 linked zones
ZONE = 6144
SECTOR = 1536


def guard(path):
    real = os.path.realpath(path)
    share = os.path.realpath(SHARE)
    if real == share or real.startswith(share + os.sep):
        raise RuntimeError('refuse write to reference images: ' + path)
    return path


def zone_info(zone):
    """Return (be path, module name, START value) for a B zone."""
    path = os.path.join(ROOT, 'bemsh', 'MBE-Z%s.be' % zone)
    if not os.path.isfile(path):
        path = os.path.join(ROOT, 'bemsh', 'MBE-Z%s-L1.be' % zone)
    name = None
    start = None
    for line in open(path, encoding='utf-8', errors='replace'):
        p = line.split()
        if len(p) >= 3 and p[1].lower() == 'старт':
            name = p[0]
            start = p[2].strip("'")
            break
    if not name or not start:
        raise RuntimeError('no START in ' + path)
    return path, name, start


def prepare(work):
    images = os.path.join(work, 'images')
    os.makedirs(images, exist_ok=True)
    for vol in ('2048', '2053', '2099', '2113', '2222', '2248'):
        dst = os.path.join(images, vol)
        if not os.path.exists(dst):
            shutil.copy2(os.path.join(SHARE, vol), dst)
    return dict(os.environ, BESM6_PATH=images + ':' + SHARE)


def compile_job(path, dest, name, start, drop_external=False):
    """asm.pl-style job with 1-1 and ЗОНМОД."""
    lines = []
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        if line.lstrip().startswith('*'):
            continue
        if 'ВНЕШН' in line and (drop_external or
                not re.search(r'Z\d{4}\.', line)):
            continue
        idx = line.find('  ,')
        if idx >= 0:
            line = line[:idx]
        lines.append(line)
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
    tail = """
КВЧ$$$^
ТРН$$$^
ЧТКОМП420070^
ЗОНМОД433900  0001^
1-1^
БТМАЛФ^
ЗОНМОД43%04o 0001^
КНЦ$$$^
_$ЕКОНЕЦ
""" % dest
    return head + '\n'.join(l + '^' for l in lines) + tail


def link_job(modules):
    """rvs.pl-style linker job for our own modules."""
    body = []
    for zone, name, start, src, out in modules:
        body.append('мдл   %s43%04o^наз   %06s^зонгп 43%04o 0001^'
                    % (name.ljust(6), src, start.zfill(6), out))
    return """шифр 419999^
лен 67(2248)42(2113)^
лен 43(2222-зп)^
росп 0^
вход 1000^
е
в 1000
к 00 070 1003
к 00 070 1004
к 00 30 70000
с 0010 3400 0067 0105
с 0010 3500 0067 0106
в 2000
а1
%s
конец ^
_$
еконец
""" % '\n'.join(body)


def run(cmd, work, env):
    p = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def compare(gold, silver):
    sectors = []
    total = 0
    gd = open(gold, 'rb').read()
    sd = open(silver, 'rb').read()
    for off in range(0, min(len(gd), len(sd)), SECTOR):
        n = sum(1 for a, b in zip(gd[off:off + SECTOR],
                                  sd[off:off + SECTOR]) if a != b)
        if n:
            sectors.append((off // SECTOR, n))
            total += n
    return sectors, total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage', choices=('compile', 'link', 'verify'))
    ap.add_argument('--zones', required=True)
    ap.add_argument('--work', default='/var/tmp/v78-link')
    ap.add_argument('--format', choices=('json', 'text'), default='text')
    ap.add_argument('--drop-external', action='store_true')
    args = ap.parse_args()
    zones = args.zones.split(',')
    work = args.work
    os.makedirs(work, exist_ok=True)
    env = prepare(work)
    manifest = os.path.join(work, 'manifest.json')

    if args.stage == 'compile':
        mods = []
        for i, zone in enumerate(zones):
            path, name, start = zone_info(zone)
            src = SRC_BASE + 2 * i
            job = os.path.join(work, 'c%s.b6' % zone)
            open(job, 'w', encoding='utf-8').write(
                compile_job(path, src, name, start, args.drop_external))
            rc, out = run(['dispak', '-l', job], work, env)
            mods.append({'zone': zone, 'name': name, 'start': start,
                         'src': '%04o' % src, 'out': '%04o' % int(zone, 8),
                         'compile_rc': rc})
            if rc:
                print('COMPILE FAIL', zone, out[-200:], file=sys.stderr)
        open(manifest, 'w').write(json.dumps(mods, indent=2))
        print('compiled', len(mods), 'zones')
        return 0

    mods = json.load(open(manifest))
    if args.stage == 'link':
        job = os.path.join(work, 'link.b6')
        open(job, 'w', encoding='utf-8').write(link_job([
            (m['zone'], m['name'], m['start'], int(m['src'], 8),
             int(m['out'], 8)) for m in mods]))
        rc, out = run(['dispak', '-s', job], work, env)
        open(os.path.join(work, 'link.log'), 'w').write(out)
        print('link rc', rc)
        for line in out.splitlines():
            if 'ЗОНГП' in line or 'ОШ' in line:
                print(line[:120])
        return rc

    result = []
    for m in mods:
        silver = os.path.join(work, 'S%s' % m['out'])
        cmd = ['besmtool', 'dump', '2222', '--start=0' + m['out'],
               '--length=1', '--to-file=' + silver]
        run(cmd, work, env)
        gold = os.path.join(ROOT, 'gold', 'MBE-Z%s-L1.bin' % m['zone'])
        if not os.path.isfile(silver) or not os.path.isfile(gold):
            result.append((m['zone'], -1, 0))
            continue
        sectors, total = compare(gold, silver)
        result.append((m['zone'], len(sectors), total))
    if args.format == 'json':
        print(json.dumps(result))
    else:
        for zone, ns, nb in result:
            print('зона %s: секторов %d, байт %d' % (zone, ns, nb))
    return 0


if __name__ == '__main__':
    sys.exit(main())
