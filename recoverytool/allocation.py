"""What the *current* filesystems on the source occupy.

After a format the new filesystem writes its own metadata over part of the old data.  Old
files that overlap those areas cannot be intact, and deleted files whose space has been
reused are damaged as well.  This module returns the occupied byte ranges so the extractor can
tell exactly which files - and which bytes of them - are affected.
"""

from __future__ import annotations

import struct
from array import array

from . import ntfs
from .model import Intervals


def partition_starts(src):
    """Offsets where a current filesystem may begin: offset 0 plus every MBR/GPT partition."""
    starts = {0}
    s = src.sector
    mbr = src.read(0, 512)
    if len(mbr) == 512 and mbr[510:512] == b"\x55\xaa":
        gpt = False
        for i in range(4):
            e = mbr[446 + 16 * i:462 + 16 * i]
            ptype, lba = e[4], struct.unpack("<I", e[8:12])[0]
            if ptype == 0xEE:
                gpt = True
            elif ptype and lba:
                starts.add(lba * s)
                if ptype in (0x05, 0x0F):                     # extended: walk the logical chain
                    base = nxt = lba
                    for _ in range(64):
                        ebr = src.read(nxt * s, 512)
                        if len(ebr) < 512 or ebr[510:512] != b"\x55\xaa":
                            break
                        l1 = struct.unpack("<I", ebr[454:458])[0]
                        if ebr[450] and l1:
                            starts.add((nxt + l1) * s)
                        l2 = struct.unpack("<I", ebr[470:474])[0]
                        if not ebr[466] or not l2:
                            break
                        nxt = base + l2
        if gpt:
            hdr = src.read(s, 92)
            if hdr[:8] == b"EFI PART":
                lba, count, esize = struct.unpack("<QII", hdr[72:88])
                table = src.read(lba * s, min(count, 256) * esize)
                for i in range(min(count, 256)):
                    e = table[i * esize:(i + 1) * esize]
                    if len(e) >= 48 and any(e[:16]):
                        starts.add(struct.unpack("<Q", e[32:40])[0] * s)
    return sorted(x for x in starts if x < src.size)


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


def current_allocation(src, log=lambda m: None):
    ranges = []
    for start in partition_starts(src):
        b = src.read(start, 512)
        if len(b) < 512 or b[510:512] != b"\x55\xaa":
            continue
        try:
            if b[3:11] == b"NTFS    ":
                part = _ntfs(src, start, b)
            elif b[3:11] == b"EXFAT   ":
                part = _exfat(src, start, b)
            elif b[0x52:0x5A] == b"FAT32   ":
                part = _fat32(src, start, b)
            else:
                continue
        except Exception as ex:                               # a damaged current FS must not stop recovery
            log("allocation map failed at %d: %s" % (start, ex))
            continue
        log("current filesystem at %d occupies %d ranges" % (start, len(part)))
        ranges += part
    return Intervals(ranges)
