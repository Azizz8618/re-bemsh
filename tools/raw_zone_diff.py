#!/usr/bin/env python3
"""Пословный diff восстановленной raw-зоны против gold.

Промотировано из /tmp/.private/azizz/raw-work/diffwords.py.
Только чтение файлов; запись в репозиторий не ведется.
"""
import sys


def load_words(path):
    """Читать raw-зону как список по 6 байтовых слов."""
    with open(path, 'rb') as f:
        data = f.read()
    return [data[6 * i:6 * i + 6] for i in range(len(data) // 6)]


def diff_words(gold, silver):
    """Вернуть [(index, gold_word, silver_word)] для отличающихся слов."""
    diffs = []
    for w in range(len(gold)):
        g = gold[w]
        s = silver[w] if w < len(silver) else None
        if g != s:
            diffs.append((w, g, s))
    return diffs


def diff_zones(gold_path, silver_path):
    """Вернуть diff двух файлов raw-зон (пути к .bin)."""
    return diff_words(load_words(gold_path), load_words(silver_path))


def _fmt(word):
    if word is None:
        return "-"
    return "%016o" % int.from_bytes(word, 'big')


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: raw_zone_diff.py GOLD.bin SILVER.bin",
              file=sys.stderr)
        return 2
    gold = load_words(args[0])
    silver = load_words(args[1])
    diffs = diff_words(gold, silver)
    print("words: gold=%d silver=%d" % (len(gold), len(silver)))
    print("%d words differ" % len(diffs))
    for w, g, s in diffs:
        print("w%04o: gold=%s silver=%s" % (w, _fmt(g), _fmt(s)))
    return 1 if diffs else 0


if __name__ == '__main__':
    sys.exit(main())
