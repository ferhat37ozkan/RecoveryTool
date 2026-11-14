"""Developer aid: show what the scanner and the filesystem parsers see in an image.

    python tests\\inspect_image.py disk.img
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recoverytool import allocation, exfat, fat32, ntfs, scanner  # noqa: E402
from recoverytool.model import human_size  # noqa: E402
from recoverytool.source import Source  # noqa: E402


def main():
    src = Source(sys.argv[1])
    res = scanner.scan(src)
    print("size %s, non-zero %s" % (human_size(src.size), human_size(res.nonzero_bytes)))
    print("boot sectors:", {k: list(v) for k, v in res.boot.items()})
    print("MFT records: %d   FAT dirs: %d   exFAT sets: %d" % (len(res.mft), len(res.fat_dirs), len(res.exfat_sets)))
    print("partition starts:", allocation.partition_starts(src))
    alloc = allocation.current_allocation(src, print)
    print("currently allocated:", human_size(alloc.total()))
    vols = fat32.find_volumes(src, res, print) + exfat.find_volumes(src, res, print) + ntfs.find_volumes(src, res, print)
    for v in vols:
        print("\n%s volume at %d, cluster %d, notes %s" % (v.fs, v.start, v.cluster_size, v.notes))
        stats = {}

        def walk(node, where, seen):
            for ch in node.children:
                if id(ch) in seen:
                    continue
                seen.add(id(ch))
                if ch.is_dir:
                    walk(ch, where, seen)
                else:
                    key = (where, "live" if ch.live else "deleted" if ch.deleted else "lost", ",".join(ch.flags))
                    stats[key] = stats.get(key, 0) + 1

        seen = set()
        walk(v.root, "tree", seen)
        walk(v.orphans, "orphans", seen)
        for k, n in sorted(stats.items()):
            print("   %5d  %s" % (n, k))


if __name__ == "__main__":
    main()
