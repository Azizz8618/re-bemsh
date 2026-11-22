#!/usr/bin/env python3
"""Извлечение prword-дампов из текста dispak (разовый скрипт агента
/tmp/.private/azizz/phaseB/extract_dumps.py). Только чтение текста.
"""
import re
import sys

_AOX_LINE = re.compile(r"^\s*\d{5}: ")
_WORD = re.compile(r"[0-7]{4}")


def extract_dump(text):
    """Вернуть список prword-строк (4 поля по 4 восьмеричные цифры)
    после первого строкового признака `aox` (до 8 слов).
    """
    out = []
    in_dump = False
    for l in text.splitlines():
        if not in_dump and _AOX_LINE.match(l) and re.search(r"\baox\b", l):
            in_dump = True
            continue
        if in_dump:
            if l.startswith("- "):
                l = l[2:]
            parts = l.split()
            if (len(parts) == 4
                    and all(re.fullmatch(r"[0-7]{4}", p) for p in parts)):
                out.append(" ".join(parts))
                if len(out) >= 8:
                    break
            elif out:
                break
    return out


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: phaseb_dump_extract.py FILE...", file=sys.stderr)
        return 2
    for path in args:
        with open(path, encoding="utf-8", errors="replace") as f:
            for w in extract_dump(f.read()):
                print(w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
