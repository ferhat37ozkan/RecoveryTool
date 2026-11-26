"""Duplicate Finder: only byte-identical files are grouped, and groups are announced as they are found.

    python tests\\test_dupes.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from benchwise.tools import dupes  # noqa: E402


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def test_groups():
    base = tempfile.mkdtemp(prefix="bw-dupes-")
    try:
        big = b"x" * 200000
        for sub in ("a", "b", os.path.join("c", "d")):
            write(os.path.join(base, sub, "report.pdf"), big)
            write(os.path.join(base, sub, "small.xml"), b"s" * 2000)
        write(os.path.join(base, "same-size-other.pdf"), b"y" * 200000)            # same size, other content
        write(os.path.join(base, "same-head.pdf"), b"x" * 100000 + b"z" * 100000)   # same first 64 KB
        write(os.path.join(base, "tiny.txt"), b"s" * 10)                           # below the minimum
        events = []
        groups = dupes.scan(base, 1000, lambda *a: None, lambda key, files: events.append((key, len(files))))
        sizes = sorted((v[0][1], len(v)) for v in groups.values())
        assert sizes == [(2000, 3), (200000, 3)], sizes
        assert sorted(n for _, n in events) == [2, 2, 3, 3]     # told at the 2nd copy, again at the 3rd
        stopped = dupes.scan(base, 1000, lambda *a: None, job={"stop": True})
        assert stopped == {}
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    test_groups()
    print("dupes tests passed")
