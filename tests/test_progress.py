"""Progress of the "rebuilding folder structure" phase, on a small NTFS image built in memory.

    python tests\\test_progress.py

No hardware or administrator rights are needed.  The image holds a boot sector and an MFT of
a few thousand records (folders and small files, some deleted), enough for the counters to tick.
"""

from __future__ import annotations

import os
import shutil
import struct
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recoverytool.engine import ANALYZE_STEPS, Engine, Options  # noqa: E402
from recoverytool.source import Source  # noqa: E402

CS, MFT_LCN = 4096, 4
DIRS, FILES = 300, 6000


def record(number, name, parent, is_dir=False, in_use=True, data=b""):
    buf = bytearray(1024)
    buf[0:4] = b"FILE"
    struct.pack_into("<HHQHH", buf, 4, 48, 3, 0, 1, 1)        # usa offset/count, lsn, seq, links
    struct.pack_into("<HH", buf, 20, 56, (1 if in_use else 0) | (2 if is_dir else 0))
    struct.pack_into("<I", buf, 28, 1024)
    struct.pack_into("<I", buf, 44, number)
    buf[48:50] = b"\x01\x00"                                   # update sequence number
    p = 56
    enc = name.encode("utf-16-le")
    body = struct.pack("<Q", parent | (1 << 48)) + struct.pack("<4Q", *(132000000000000000,) * 4)
    body += struct.pack("<QQII", 0, len(data), 0x20, 0) + bytes([len(name), 1]) + enc
    for atype, content in ((0x30, body), (0x80, data)):
        if atype == 0x80 and is_dir:
            continue
        alen = (24 + len(content) + 7) & ~7
        struct.pack_into("<IIBBHHHIH", buf, p, atype, alen, 0, 0, 0, 0, 0, len(content), 24)
        buf[p + 24:p + 24 + len(content)] = content
        p += alen
    struct.pack_into("<I", buf, p, 0xFFFFFFFF)
    struct.pack_into("<I", buf, 24, p + 8)
    for end in (512, 1024):                                    # sector tails carry the USN
        buf[end - 2:end] = b"\x01\x00"
    return bytes(buf)


def build_image(path):
    recs = [record(0, "$MFT", 5), record(5, ".", 5, is_dir=True)]
    for d in range(DIRS):
        recs.append(record(24 + d, "dir%03d" % d, 5, is_dir=True, in_use=d % 7 != 0))
    for f in range(FILES):
        recs.append(record(24 + DIRS + f, "file%05d.txt" % f, 24 + f % DIRS, in_use=f % 3 != 0,
                           data=b"x" * (f % 200)))
    numbers = [0, 5] + list(range(24, 24 + DIRS + FILES))
    size = MFT_LCN * CS + (max(numbers) + 1) * 1024 + (1 << 20)
    img = bytearray(size)
    boot = bytearray(512)
    boot[3:11] = b"NTFS    "
    struct.pack_into("<HB", boot, 11, 512, CS // 512)
    struct.pack_into("<QQ", boot, 40, size // 512, MFT_LCN)
    boot[510:512] = b"\x55\xaa"
    img[0:512] = boot
    for n, r in zip(numbers, recs):
        off = MFT_LCN * CS + n * 1024
        img[off:off + 1024] = r
    with open(path, "wb") as f:
        f.write(img)


def main():
    tmp = tempfile.mkdtemp(prefix="rt-progress-")
    try:
        image = os.path.join(tmp, "ntfs.img")
        build_image(image)
        events = []
        src = Source(image)
        eng = Engine(src, os.path.join(tmp, "out"), Options(), lambda kind, **kw: events.append((kind, kw)),
                     threading.Event())
        eng.analyze()
        src.close()

        files, dirs = eng.volumes[0].count() if eng.volumes else (0, 0)
        assert files == FILES and dirs == DIRS, (files, dirs)

        steps = [kw for kind, kw in events if kind == "progress" and kw.get("unit") == "records"]
        assert steps, "no progress while rebuilding the folder structure"
        by_stage = {}
        for kw in steps:
            by_stage.setdefault(kw["stage"], []).append(kw)
        for stage in ("st_records", "st_plan", "st_check"):
            seq = by_stage.get(stage)
            assert seq, "no progress for " + stage
            assert seq[0]["done"] == 0, (stage, seq[0])
            for kw in seq:
                assert 0 <= kw["done"] <= kw["total"], (stage, kw)
            dones = [kw["done"] for kw in seq]
            assert dones == sorted(dones), (stage, dones)
            assert seq[-1]["done"] == seq[-1]["total"], (stage, seq[-1])
            assert ("/%d" % ANALYZE_STEPS) in seq[0]["text"], seq[0]["text"]
        # every record is read once and every kept record linked twice: the bar ends at its total
        recs = by_stage["st_records"][-1]
        assert recs["total"] == 3 * (2 + DIRS + FILES), recs
        print("progress tests passed: %d records, %d updates" % (2 + DIRS + FILES, len(steps)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
