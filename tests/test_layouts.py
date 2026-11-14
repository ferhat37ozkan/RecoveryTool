"""Tests for partition handling. They work on files only and never touch a disk.

Part 1 needs nothing: partition tables are built in a temporary file.

Part 2 needs a disk image that contains at least one filesystem listed in its partition table
(for example an image of a USB stick).  Point RECOVERYTOOL_TEST_IMAGE at it; without the
variable part 2 is skipped.  The image is opened read-only and "damaged" only in memory, by
patching the bytes the reader returns:

  * the partition table is wiped       -> the volume is a lost partition, nothing may be skipped
  * a single partition is selected     -> same findings as on the whole disk
  * an ISO image "was written" over it -> every lost file under the image must be marked
  * the partition "became" ext4        -> files under it must be marked as possibly overwritten

    python tests\\test_layouts.py
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recoverytool import allocation  # noqa: E402
from recoverytool.engine import Engine, Options  # noqa: E402
from recoverytool.source import Source  # noqa: E402

MIB = 1 << 20


class Patched(Source):
    """A source whose content is altered in memory: {offset: bytes}."""

    patches = None

    def _read_exact(self, off, n):
        data = super()._read_exact(off, n)
        if self.patches:
            out = None
            for p_off, p_data in self.patches.items():
                p_off -= self.base
                if p_off < off + n and p_off + len(p_data) > off:
                    out = out or bytearray(data)
                    a, b = max(p_off, off), min(p_off + len(p_data), off + n)
                    out[a - off:b - off] = p_data[a - p_off:b - p_off]
            if out is not None:
                return bytes(out)
        return data


def mbr_entry(ptype, lba, count):
    return bytes([0, 0, 0, 0, ptype, 0, 0, 0]) + struct.pack("<II", lba, count)


def test_partition_tables():
    path = os.path.join(tempfile.gettempdir(), "rt_layout_test.bin")
    with open(path, "wb") as f:
        f.truncate(64 * MIB)
    try:
        # MBR: two primaries and an extended partition with one logical drive
        mbr = bytearray(512)
        mbr[446:462] = mbr_entry(0x07, 2048, 20480)
        mbr[462:478] = mbr_entry(0x0C, 22528, 20480)
        mbr[478:494] = mbr_entry(0x05, 43008, 40960)
        mbr[510:512] = b"\x55\xaa"
        ebr = bytearray(512)
        ebr[446:462] = mbr_entry(0x07, 2048, 10240)
        ebr[510:512] = b"\x55\xaa"
        src = Patched(path)
        src.patches = {0: bytes(mbr), 43008 * 512: bytes(ebr)}
        got = allocation.partitions(src)
        assert got == [(2048 * 512, 20480 * 512), (22528 * 512, 20480 * 512), (45056 * 512, 10240 * 512)], got
        assert allocation.accessible_starts(src) == set(), "no boot sectors yet"
        ntfs_boot = bytearray(512)
        ntfs_boot[3:11] = b"NTFS    "
        ntfs_boot[510:512] = b"\x55\xaa"
        src.patches[2048 * 512] = bytes(ntfs_boot)
        src._cache.clear()
        assert allocation.accessible_starts(src) == {2048 * 512}
        src.close()

        # GPT: protective MBR, header, two entries
        pmbr = bytearray(512)
        pmbr[446:462] = mbr_entry(0xEE, 1, 0xFFFFFFFF)
        pmbr[510:512] = b"\x55\xaa"
        hdr = bytearray(512)
        hdr[:8] = b"EFI PART"
        hdr[72:88] = struct.pack("<QII", 2, 128, 128)
        table = bytearray(128 * 128)
        for i, (first, last) in enumerate(((2048, 4095), (4096, 100000))):
            table[i * 128:i * 128 + 16] = bytes([i + 1]) * 16
            table[i * 128 + 32:i * 128 + 48] = struct.pack("<QQ", first, last)
        src = Patched(path)
        src.patches = {0: bytes(pmbr), 512: bytes(hdr), 1024: bytes(table)}
        got = allocation.partitions(src)
        assert got == [(2048 * 512, 2048 * 512), (4096 * 512, (100000 - 4096 + 1) * 512)], got

        # an ISO image written over the start
        pvd = bytearray(2048)
        pvd[0:6] = b"\x01CD001"
        pvd[80:84] = struct.pack("<I", 10000)
        pvd[128:130] = struct.pack("<H", 2048)
        src.patches[0x8000] = bytes(pvd)
        src._cache.clear()
        occupied, unknown = allocation.current_allocation(src)
        assert occupied.overlaps(0, 64 * MIB) == [(0, 10000 * 2048)], occupied.overlaps(0, 64 * MIB)

        # an ext4 superblock is recognised as something we cannot look into
        sb = bytearray(4608)
        sb[1080:1082] = b"\x53\xef"
        src.patches = {0: bytes(pmbr), 512: bytes(hdr), 1024: bytes(table), 4096 * 512: bytes(sb)}
        src._cache.clear()
        occupied, unknown = allocation.current_allocation(src)
        assert not occupied and unknown.overlaps(0, 64 * MIB) == [(4096 * 512, 100001 * 512)], unknown.overlaps(0, 64 * MIB)
        # ...but a partition with a merely broken boot sector is not
        src.patches = {0: bytes(pmbr), 512: bytes(hdr), 1024: bytes(table), 4096 * 512: os.urandom(512)}
        src._cache.clear()
        occupied, unknown = allocation.current_allocation(src)
        assert not occupied and not unknown
    finally:
        src.close()
        os.remove(path)
    print("partition table tests passed")


def analyze(src, accessible=None, **opts):
    dest = tempfile.mkdtemp(prefix="rt_layout_")
    try:
        eng = Engine(src, dest, Options(**opts), lambda kind, **kw: None, threading.Event(), accessible)
        eng.analyze()
        return eng
    finally:
        os.rmdir(dest)


def files(eng):
    return [i for i in eng.items if not i.node.is_dir]


def test_image(image):
    base = Source(image)
    parts = allocation.partitions(base)
    live_parts = [p for p in parts if allocation.boot_kind(base, p[0])]
    base.close()
    assert live_parts, "the test image needs a partition with a readable filesystem"
    start, size = live_parts[0]

    whole = analyze(Source(image))
    n_whole, skipped = len(files(whole)), whole.skipped_live
    print("whole image: %d files to recover, %d accessible files left out" % (n_whole, skipped))
    assert skipped > 0, "the image's current filesystem should have accessible files"

    # 1) lost partition: wipe the partition table
    src = Patched(image)
    src.patches = {446: bytes(64)}
    lost = analyze(src)
    print("partition table wiped: %d files, %d left out" % (len(files(lost)), lost.skipped_live))
    assert lost.skipped_live == 0, "files of a lost partition must not be treated as accessible"
    assert len(files(lost)) == n_whole + skipped

    # 2) only that partition is scanned
    part = analyze(Source(image, size=size, base=start), accessible={0})
    print("partition only: %d files, %d left out" % (len(files(part)), part.skipped_live))
    assert (len(files(part)), part.skipped_live) == (n_whole, skipped), "a partition scan must find the same files"
    assert sorted(i.node.size for i in files(part)) == sorted(i.node.size for i in files(whole))
    raw = analyze(Source(image, size=size, base=start), accessible=set())     # Windows shows it as RAW
    assert raw.skipped_live == 0 and len(files(raw)) == n_whole + skipped

    # 3) an ISO image of 2 GiB written over the start of the disk
    iso_bytes = 2048 * MIB
    pvd = bytearray(2048)
    pvd[0:6] = b"\x01CD001"
    pvd[80:84] = struct.pack("<I", iso_bytes // 2048)
    pvd[128:130] = struct.pack("<H", 2048)
    src = Patched(image)
    src.patches = {0x8000: bytes(pvd)}
    iso = analyze(src)
    under = marked = 0
    for it in files(iso):
        if it.node.live:
            continue
        hit = any(off is not None and off < iso_bytes for off, ln in it.node.extents)
        flagged = any(n.startswith("OVERWRITTEN") for n in it.notes)
        under += hit
        marked += flagged
        assert not hit or flagged, "a file under the written image was not marked: %s" % it.rel[-1]
    print("ISO over the first 2 GiB: %d files under it, %d marked overwritten" % (under, marked))
    assert under > 0

    # 4) the partition now holds ext4
    sb = bytearray(4608)
    sb[1080:1082] = b"\x53\xef"
    src = Patched(image)
    src.patches = {start: bytes(sb)}
    ext = analyze(src)
    maybe = sum(1 for it in files(ext) if any(n.startswith("MAYBE_OVERWRITTEN") for n in it.notes))
    print("partition turned into ext4: %d files marked as possibly overwritten" % maybe)
    assert maybe > 0 and ext.skipped_live == 0
    print("image layout tests passed")


if __name__ == "__main__":
    test_partition_tables()
    image = os.environ.get("RECOVERYTOOL_TEST_IMAGE")
    if image:
        test_image(image)
    else:
        print("RECOVERYTOOL_TEST_IMAGE not set: image tests skipped")
