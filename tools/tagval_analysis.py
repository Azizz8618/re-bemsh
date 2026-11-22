#!/usr/bin/env python3
"""Разбор prword-слов на половины [TAG(24)|VAL(24)].

Промотировано из /tmp/.private/azizz/phaseB/analyze_tagval.py.
Гипотеза [TAG|VAL] не подтверждена
(MACRO-TABLE-FORMAT-VERIFIED.md, sec.10.3), но пословный разбор
половин слов из дампов остается рабочим инструментом анализа.
"""
import sys


def split_tagval(word):
    """Вернуть (tag, val): первые и последние 8 восьмеричных цифр word."""
    s = ("%016o" % word) if isinstance(word, int) else str(word)
    if len(s) != 16:
        raise ValueError("expected 16 octal digits, got %d: %r"
                         % (len(s), word))
    return s[:8], s[8:]


def analyze(words):
    """Вернуть [(word, tag, val), ...] для каждого слова."""
    return [(w,) + split_tagval(w) for w in words]


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    words = args if args else [l.strip() for l in sys.stdin
                               if l.strip()]
    for word, tag, val in analyze(words):
        print("word=%s TAG=%s VAL=%s" % (word, tag, val))
    return 0


if __name__ == '__main__':
    sys.exit(main())
