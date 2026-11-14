"""What is on the source *now*: the current partitions and the space they occupy.

After a format - or after an image was written over a disk by mistake - something new sits on
top of part of the old data.  Old files that overlap it cannot be intact, and deleted files
whose space has been reused are damaged as well.  This module answers three questions:

* ``partitions(src)``          which partitions does the current partition table describe?
* ``accessible_starts(src)``   which of them hold a filesystem that can simply be opened?
* ``current_allocation(src)``  which byte ranges are certainly occupied by current data, and
                               which ranges belong to something we cannot look inside?
"""

from __future__ import annotations

import struct
from array import array

from . import ntfs
from .model import Intervals


def partitions(src):
    """Return [(start, size)] in bytes for every MBR/GPT partition. Offset 0 is not included."""
    out = []
    s = src.sector
    mbr = src.read(0, 512)
    if len(mbr) < 512 or mbr[510:512] != b"\x55\xaa":
        return out
    gpt = False
    for i in range(4):
        e = mbr[446 + 16 * i:462 + 16 * i]
        ptype, lba, count = e[4], struct.unpack("<I", e[8:12])[0], struct.unpack("<I", e[12:16])[0]
        if ptype == 0xEE:
            gpt = True
        elif ptype in (0x05, 0x0F) and lba:                   # extended: walk the logical chain
            base = nxt = lba
            for _ in range(64):
                ebr = src.read(nxt * s, 512)
                if len(ebr) < 512 or ebr[510:512] != b"\x55\xaa":
                    break
                l1, c1 = struct.unpack("<II", ebr[454:462])
                if ebr[450] and l1:
                    out.append(((nxt + l1) * s, c1 * s))
                l2 = struct.unpack("<I", ebr[470:474])[0]
                if not ebr[466] or not l2:
                    break
                nxt = base + l2
        elif ptype and count:
            out.append((lba * s, count * s))
    if gpt:
        hdr = src.read(s, 92)
        if hdr[:8] == b"EFI PART":
            lba, count, esize = struct.unpack("<QII", hdr[72:88])
            if 128 <= esize <= 512:
                table = src.read(lba * s, min(count, 256) * esize)
                for i in range(min(count, 256)):
                    e = table[i * esize:(i + 1) * esize]
                    if len(e) >= 48 and any(e[:16]):
                        first, last = struct.unpack("<QQ", e[32:48])
                        if last >= first:
                            out.append((first * s, (last - first + 1) * s))
    return sorted(p for p in set(out) if 0 <= p[0] < src.size)


def partition_starts(src):
    """Offsets where a current filesystem may begin: offset 0 plus every partition."""
    return sorted({0} | {p[0] for p in partitions(src)})


def boot_kind(src, start):
    """Which filesystem does the boot sector at ``start`` announce? None if not one we read."""
    b = src.read(start, 512)
    if len(b) < 512 or b[510:512] != b"\x55\xaa":
        return None
    if b[3:11] == b"NTFS    ":
        return "NTFS"
    if b[3:11] == b"EXFAT   ":
        return "exFAT"
    if b[0x52:0x5A] == b"FAT32   ":
        return "FAT32"
    return None


def accessible_starts(src):
    """Volumes the current partition table points at and whose boot sector is valid.

    Only files of such a volume count as "still accessible normally".  A healthy filesystem
    that is no longer listed in the partition table - a lost partition - is not accessible, and
    its files have to be recovered like any other lost data.
    """
    return {start for start in partition_starts(src) if boot_kind(src, start)}


def _ntfs(src, start, b):
    bps, spc = struct.unpack("<H", b[11:13])[0], b[13]
    total, mft_lcn = struct.unpack("<QQ", b[40:56])
    if bps not in (512, 1024, 2048, 4096) or not total:
        return []
    cs = bps * spc if spc < 0x80 else bps << (256 - spc)
    r = ntfs.parse_record(src, start + mft_lcn * cs + 6 * 1024)        # $Bitmap
    if not r or r.name != "$Bitmap" or not r.data:
        return [(start, start + 16 * bps)]
    bitmap, left = bytearray(), r.size
    for _, runs in sorted(r.data):
        for lcn, n in runs:
            if lcn is None or left <= 0:
                continue
            chunk = src.read_raw(start + lcn * cs, min(n * cs, left))
            bitmap += chunk
            left -= len(chunk)
    return _bits_to_ranges(bitmap, start, cs)


def _bits_to_ranges(bitmap, base, unit, first_index=0):
    """Turn set bits into merged (start, end) byte ranges."""
    out, run_start, n = [], None, len(bitmap) * 8
    i = 0
    while i < n:
        byte = bitmap[i >> 3]
        if byte == 0 and i & 7 == 0:
            if run_start is not None:
                out.append((base + (run_start + first_index) * unit, base + (i + first_index) * unit))
                run_start = None
            i += 8
            continue
        if byte == 0xFF and i & 7 == 0:
            if run_start is None:
                run_start = i
            i += 8
            continue
        if byte >> (i & 7) & 1:
            if run_start is None:
                run_start = i
        elif run_start is not None:
            out.append((base + (run_start + first_index) * unit, base + (i + first_index) * unit))
            run_start = None
        i += 1
    if run_start is not None:
        out.append((base + (run_start + first_index) * unit, base + (n + first_index) * unit))
    return out


def _fat32(src, start, b):
    bps, spc, reserved, nfats = struct.unpack("<HBHB", b[11:17])
    fatsz = struct.unpack("<I", b[36:40])[0]
    if bps not in (512, 1024, 2048, 4096) or not spc or not fatsz:
        return []
    cs, fat_off = bps * spc, start + reserved * bps
    data = fat_off + nfats * fatsz * bps
    fat = array("I")
    fat.frombytes(src.read_raw(fat_off, fatsz * bps // 4 * 4))
    out, run = [(start, data)], None
    for c in range(2, len(fat)):
        if fat[c] & 0x0FFFFFFF:
            if run is None:
                run = c
        elif run is not None:
            out.append((data + (run - 2) * cs, data + (c - 2) * cs))
            run = None
    if run is not None:
        out.append((data + (run - 2) * cs, data + (len(fat) - 2) * cs))
    return out


def _exfat(src, start, b):
    fat_off, fat_len, heap_off, clusters, root = struct.unpack("<IIIII", b[80:100])
    if not (9 <= b[108] <= 12) or not heap_off:
        return []
    bps = 1 << b[108]
    cs = bps << b[109]
    heap = start + heap_off * bps
    out = [(start, heap)]
    rootdir = src.read(heap + (root - 2) * cs, min(cs, 1 << 16))
    for o in range(0, len(rootdir) - 31, 32):
        if rootdir[o] == 0x81:                                # allocation bitmap entry
            first, length = struct.unpack("<I", rootdir[o + 20:o + 24])[0], struct.unpack("<Q", rootdir[o + 24:o + 32])[0]
            bitmap = src.read_raw(heap + (first - 2) * cs, min(length, (clusters + 7) // 8))
            out += _bits_to_ranges(bitmap, heap, cs)
            break
        if rootdir[o] == 0:
            break
    return out


def _iso9660_end(src):
    """Size of an ISO 9660 image written to the start of the source (0 if there is none).

    Writing a Linux or Windows installer image "raw" to a disk puts an ISO filesystem at offset
    0.  Its primary volume descriptor says how many bytes the image covers; all of that was
    overwritten.
    """
    pvd = src.read(0x8000, 2048)
    if len(pvd) < 2048 or pvd[0] != 1 or pvd[1:6] != b"CD001":
        return 0
    blocks = struct.unpack("<I", pvd[80:84])[0]
    block_size = struct.unpack("<H", pvd[128:130])[0]
    if block_size not in (512, 1024, 2048, 4096):
        return 0
    return min(blocks * block_size, src.size)


def current_allocation(src, log=lambda m: None):
    """Return ``(occupied, unknown)`` as two Intervals.

    ``occupied``  byte ranges that current data certainly sits on.
    ``unknown``   current partitions holding something this tool cannot read (ext4, a boot
                  partition of an installer image, ...).  Old data under them may or may not
                  have been overwritten.
    """
    occupied, unknown = [], []
    iso_end = _iso9660_end(src)
    if iso_end:
        occupied.append((0, iso_end))
        log("ISO 9660 image at the start of the source covers %d bytes" % iso_end)
    known = {}
    for start in partition_starts(src):
        b = src.read(start, 512)
        kind = boot_kind(src, start)
        if not kind:
            continue
        try:
            part = {"NTFS": _ntfs, "exFAT": _exfat, "FAT32": _fat32}[kind](src, start, b)
        except Exception as ex:                               # a damaged current FS must not stop recovery
            log("allocation map failed at %d: %s" % (start, ex))
            continue
        known[start] = True
        log("current %s filesystem at %d occupies %d ranges" % (kind, start, len(part)))
        occupied += part
    for start, size in partitions(src):
        if start in known or start + size <= iso_end:
            continue
        kind = foreign_kind(src, start)
        if not kind:
            continue      # empty, or the damaged remains of the very filesystem being recovered
        unknown.append((max(start, iso_end), min(start + size, src.size)))
        log("%s partition at %d (%d bytes) cannot be inspected" % (kind, start, size))
    return Intervals(occupied), Intervals(unknown)


def foreign_kind(src, start):
    """Positively identify a filesystem this tool does not read. None if it is not one of them.

    A partition is only treated as "something else lives here now" when that something is
    recognised.  A partition with a broken boot sector must not land here: it is usually the
    damaged filesystem the user wants back, not new data on top of it.
    """
    head = src.read(start, 4608)
    if len(head) < 4608:
        return None
    if head[1080:1082] == b"\x53\xef":
        return "ext2/3/4"
    if head[:4] == b"XFSB":
        return "XFS"
    if head[1024:1026] in (b"H+", b"HX"):
        return "HFS+"
    if head[32:36] == b"NXSB":
        return "APFS"
    if head[:6] == b"LUKS\xba\xbe":
        return "LUKS"
    if head[4086:4096] in (b"SWAPSPACE2", b"SWAP-SPACE"):
        return "Linux swap"
    if head[510:512] == b"\x55\xaa" and head[0x36:0x3B] in (b"FAT12", b"FAT16"):
        return "FAT12/16"
    if src.read(start + 0x10040, 8) == b"_BHRfS_M":
        return "btrfs"
    if src.read(start + 0x8001, 5) == b"CD001":
        return "ISO 9660"
    return None
