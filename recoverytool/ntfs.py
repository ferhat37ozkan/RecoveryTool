"""NTFS reconstruction from MFT file records.

Every file record found by the scan is decoded on its own (name, parent reference, timestamps,
data runs), then the tree is rebuilt from the parent references.  That works for deleted files,
for volumes whose boot sector is damaged and for quick-formatted volumes, where the old records
beyond the freshly written start of the new MFT are still intact.
"""

from __future__ import annotations

import struct
from bisect import bisect_left

from .model import Intervals, Node, Volume

ROOT_RECORD = 5
EXTEND_RECORD = 11
_NAMESPACE_RANK = {1: 0, 3: 1, 0: 2, 2: 3}      # Win32, Win32+DOS, POSIX, DOS


class _Geometry:
    def __init__(self, start, cs, size, mft_lcn):
        self.start, self.cs, self.size, self.mft_lcn = start, cs, size, mft_lcn


class _Record:
    __slots__ = ("off", "number", "seq", "in_use", "is_dir", "base", "name", "parent", "parent_seq",
                 "times", "attrs", "data", "resident", "size", "init", "data_flags")


def _runs(buf, pos):
    """Decode a run list into [(lcn | None, cluster_count)]."""
    out, lcn = [], 0
    while pos < len(buf) and buf[pos]:
        h = buf[pos]
        a, b = h & 15, h >> 4
        if a == 0 or a > 8 or b > 8 or pos + 1 + a + b > len(buf):
            break
        n = int.from_bytes(buf[pos + 1:pos + 1 + a], "little")
        if b:
            lcn += int.from_bytes(buf[pos + 1 + a:pos + 1 + a + b], "little", signed=True)
            out.append((lcn, n))
        else:
            out.append((None, n))                     # sparse
        pos += 1 + a + b
    return out


def parse_record(src, off):
    raw = src.read(off, 1024)
    if len(raw) < 1024 or raw[:4] != b"FILE":
        return None
    alloc = struct.unpack("<I", raw[28:32])[0]
    if alloc not in (1024, 2048, 4096):
        return None
    if alloc > 1024:
        raw = src.read(off, alloc)
        if len(raw) < alloc:
            return None
    buf = bytearray(raw)
    usa_off, usa_n = struct.unpack("<HH", buf[4:8])
    if usa_off + 2 * usa_n > alloc or usa_n < 2:
        return None
    usn = buf[usa_off:usa_off + 2]
    for i in range(1, usa_n):
        end = i * 512
        if end > alloc:
            break
        if buf[end - 2:end] != usn:
            return None                               # torn or partly overwritten record
        buf[end - 2:end] = buf[usa_off + 2 * i:usa_off + 2 * i + 2]

    r = _Record()
    r.off = off
    r.seq = struct.unpack("<H", buf[16:18])[0]
    flags = struct.unpack("<H", buf[22:24])[0]
    r.in_use, r.is_dir = bool(flags & 1), bool(flags & 2)
    r.base = struct.unpack("<Q", buf[32:40])[0] & 0xFFFFFFFFFFFF
    r.number = struct.unpack("<I", buf[44:48])[0]
    r.name = r.parent = r.parent_seq = r.times = r.resident = None
    r.attrs, r.data, r.size, r.init, r.data_flags = 0, [], 0, 0, 0
    rank = 99
    p = struct.unpack("<H", buf[20:22])[0]
    used = min(struct.unpack("<I", buf[24:28])[0], alloc)
    while p + 16 <= used:
        atype, alen = struct.unpack("<II", buf[p:p + 8])
        if atype == 0xFFFFFFFF or alen < 16 or p + alen > alloc:
            break
        nonres, name_len = buf[p + 8], buf[p + 9]
        if not nonres:
            clen, coff = struct.unpack("<IH", buf[p + 16:p + 22])
            body = bytes(buf[p + coff:p + coff + clen])
            if atype == 0x10 and len(body) >= 36:
                c, m, _, a = struct.unpack("<QQQQ", body[:32])
                r.times = (c, m, a)
                r.attrs = struct.unpack("<I", body[32:36])[0]
            elif atype == 0x30 and len(body) >= 66:
                ns = body[65]
                if _NAMESPACE_RANK.get(ns, 9) < rank:
                    rank = _NAMESPACE_RANK.get(ns, 9)
                    ref = struct.unpack("<Q", body[:8])[0]
                    r.parent, r.parent_seq = ref & 0xFFFFFFFFFFFF, ref >> 48
                    r.name = body[66:66 + 2 * body[64]].decode("utf-16-le", "replace")
                    if r.times is None:
                        c, m, _, a = struct.unpack("<QQQQ", body[8:40])
                        r.times = (c, m, a)
            elif atype == 0x80 and name_len == 0:
                r.resident, r.size, r.init = body, clen, clen
        elif atype == 0x80 and name_len == 0:
            start_vcn = struct.unpack("<Q", buf[p + 16:p + 24])[0]
            run_off = struct.unpack("<H", buf[p + 32:p + 34])[0]
            r.data.append((start_vcn, _runs(bytes(buf[p:p + alen]), run_off)))
            if start_vcn == 0:
                r.data_flags = struct.unpack("<H", buf[p + 12:p + 14])[0]
                r.size, r.init = struct.unpack("<Q", buf[p + 48:p + 56])[0], struct.unpack("<Q", buf[p + 56:p + 64])[0]
        p += alen
    return r


def _from_boot_sectors(src, offsets):
    out = []
    for off in offsets:
        b = src.read(off, 512)
        bps, spc = struct.unpack("<H", b[11:13])[0], b[13]
        total, mft_lcn = struct.unpack("<QQ", b[40:56])
        if bps not in (512, 1024, 2048, 4096) or not total or total * bps > src.size + (1 << 20):
            continue
        cs = bps * spc if spc < 0x80 else bps << (256 - spc)
        if cs < 512 or cs > (2 << 20):
            continue
        chosen = None
        for vs in (off, off - total * bps):            # primary copy, or the backup at the volume end
            if vs >= 0 and src.read(vs + mft_lcn * cs, 4) == b"FILE":
                chosen = vs
                break
        if chosen is None:
            chosen = off if off + total * bps <= src.size + (1 << 20) else off - total * bps
        if chosen >= 0:
            out.append(_Geometry(chosen, cs, total * bps, mft_lcn))
    return out


def _infer(src, scan):
    """No boot sector: locate the volume from the $MFT / $MFTMirr records themselves."""
    zeros = []
    for off in scan.mft:
        head = src.read(off, 48)
        if len(head) == 48 and struct.unpack("<I", head[44:48])[0] == 0:
            r = parse_record(src, off)
            if r and r.name == "$MFT" and r.data and r.data[0][1] and r.data[0][1][0][0] is not None:
                zeros.append(r)
        if len(zeros) >= 64:
            break
    out = []
    for r in zeros:
        lcn0 = r.data[0][1][0][0]
        mirr = parse_record(src, r.off + 1024)
        cs = None
        if mirr and mirr.name == "$MFTMirr" and mirr.data and mirr.data[0][1] and mirr.data[0][1][0][0] is not None:
            lcn1 = mirr.data[0][1][0][0]
            for other in zeros:
                if other is not r and lcn1 != lcn0 and (other.off - r.off) % (lcn1 - lcn0) == 0:
                    c = (other.off - r.off) // (lcn1 - lcn0)
                    if c in [512 << k for k in range(13)]:
                        cs = c
        if cs is None:
            cs = 4096
        start = r.off - lcn0 * cs
        if start >= 0:
            out.append(_Geometry(start, cs, src.size - start, lcn0))
    return out


def current_mft_extent(src, g):
    """Byte ranges of the MFT that the volume's boot sector points to (initialised part)."""
    r = parse_record(src, g.start + g.mft_lcn * g.cs)
    if not r or r.name != "$MFT" or not r.in_use or not r.data:
        return Intervals()
    ranges, left = [], r.init or r.size
    for _, runs in sorted(r.data):
        for lcn, n in runs:
            if lcn is not None and left > 0:
                ln = min(n * g.cs, left)
                ranges.append((g.start + lcn * g.cs, g.start + lcn * g.cs + ln))
                left -= ln
    return Intervals(ranges)


def find_volumes(src, scan, log=lambda m: None, cancel=None, progress=None):
    """``progress(done, total)``: records read and linked into folders, over all volumes."""
    geos, seen = [], set()
    for g in _from_boot_sectors(src, scan.boot["NTFS"]) or _infer(src, scan):
        if (g.start, g.cs) not in seen:
            seen.add((g.start, g.cs))
            geos.append(g)
    tick = _Ticker(progress, sum(bisect_left(scan.mft, g.start + g.size) - bisect_left(scan.mft, g.start)
                                 for g in geos))
    volumes = []
    for g in geos:
        vol = _build(src, scan, g, cancel, tick)
        tick._tell()
        log("NTFS: start@%d cluster=%d -> %d files, %d dirs" % ((g.start, g.cs) + vol.count()))
        volumes.append(vol)
    return volumes


class _Ticker:
    """One progress figure for reading the records of every volume and linking them into folders.

    Each record read is one unit, each kept record costs two more (making its node, finding its
    folder).  How many records are kept is only known volume by volume, so the remaining volumes
    are estimated at the ratio seen so far; the total settles as the work goes on.
    """

    def __init__(self, progress, total):
        self.progress, self.read_total = progress, total
        self.read = self.kept = self.read_done = self.linked = 0

    def total(self):
        ratio = self.kept / self.read_done if self.read_done else 1.0
        return self.read_total + 2 * (self.kept + int((self.read_total - self.read_done) * ratio))

    def _tell(self):
        if self.progress:
            self.progress(self.read + self.linked, max(self.total(), self.read + self.linked))

    def on_read(self):
        self.read += 1
        if self.read & 1023 == 0:
            self._tell()

    def volume_read(self, kept):
        """All records of one volume have been read; ``kept`` of them will be linked."""
        self.read_done, self.kept = self.read, self.kept + kept
        self._tell()

    def on_link(self):
        self.linked += 1
        if self.linked & 1023 == 0:
            self._tell()


def _build(src, scan, g, cancel, tick=None):
    tick = tick or _Ticker(None, 0)
    vol = Volume("NTFS", g.start, g.size, g.cs)
    # Records are "live" only if this volume is what the partition's boot sector describes now.
    boot = src.read(g.start, 512)
    is_current = boot[3:11] == b"NTFS    " and struct.unpack("<Q", boot[48:56])[0] == g.mft_lcn
    current = current_mft_extent(src, g) if is_current else Intervals()
    lo, hi = bisect_left(scan.mft, g.start), bisect_left(scan.mft, g.start + g.size)
    by_number, extensions = {}, []
    for i in range(lo, hi):
        if cancel is not None and i % 4096 == 0 and cancel.is_set():
            from .model import Cancelled
            raise Cancelled()
        r = parse_record(src, scan.mft[i])
        tick.on_read()
        if r is None:
            continue
        if r.base:
            extensions.append(r)
        elif r.name is not None:
            by_number.setdefault(r.number, []).append(r)
    for e in extensions:                               # $DATA continued in an extension record
        for base in by_number.get(e.base, ()):
            if e.data:
                base.data.extend(e.data)
                if not base.size and e.size:
                    base.size, base.init, base.data_flags = e.size, e.init, e.data_flags
            elif e.resident is not None and base.resident is None and not base.data:
                base.resident, base.size, base.init = e.resident, e.size, e.init

    system_dirs, grew = {EXTEND_RECORD}, True           # $Extend and everything below it
    while grew:
        grew = False
        for recs in by_number.values():
            for r in recs:
                if r.is_dir and r.parent in system_dirs and r.number not in system_dirs and r.number != ROOT_RECORD:
                    system_dirs.add(r.number)
                    grew = True

    tick.volume_read(sum(len(recs) for recs in by_number.values()))
    nodes = {}                                          # id(record) -> Node
    for recs in by_number.values():
        for r in recs:
            tick.on_link()
            if (r.number < 24 and r.number != ROOT_RECORD) or r.parent in system_dirs:
                continue
            if r.number == ROOT_RECORD:
                nodes[id(r)] = vol.root                 # every generation of the root maps to one root
                continue
            n = Node(r.name, r.is_dir, 0 if r.is_dir else r.size)
            n.ident = r.number
            n.deleted = not r.in_use
            n.live = r.in_use and bool(current.overlaps(r.off, 1))
            n.attrs = r.attrs & 0x07
            if r.times:
                n.ctime, n.mtime, n.atime = r.times
            if not r.is_dir:
                _fill_data(n, r, g, src.size)
            nodes[id(r)] = n

    placeholders = {}
    for recs in by_number.values():
        for r in recs:
            tick.on_link()
            n = nodes.get(id(r))
            if n is None or n is vol.root:
                continue
            cands = [c for c in by_number.get(r.parent, ()) if c.is_dir and id(c) in nodes and c is not r]
            parent = None
            for c in cands:                             # a deleted directory has its sequence bumped by one
                if c.seq == r.parent_seq or (not c.in_use and c.seq == r.parent_seq + 1):
                    parent = nodes[id(c)]
                    break
            if parent is None and cands:
                parent = nodes[id(cands[0])]
            if parent is None:
                parent = placeholders.get(r.parent)
                if parent is None:
                    parent = placeholders[r.parent] = Node("dir_record_%d" % r.parent, True)
                    parent.ident = r.parent
                    vol.orphans.children.append(parent)
            parent.children.append(n)

    def spread(node, deleted, seen):                    # everything below a deleted directory is deleted
        for ch in node.children:
            if id(ch) in seen:
                continue
            seen.add(id(ch))
            if deleted:
                ch.deleted, ch.live = True, False
            if ch.is_dir:
                spread(ch, ch.deleted, seen)
    import sys
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))
    spread(vol.root, False, set())
    spread(vol.orphans, False, set())
    for ph in placeholders.values():                    # orphans are never part of the live tree
        _unlive(ph)
    vol.ntfs_info = (g.start, g.cs, g.mft_lcn)
    return vol


def _unlive(node):
    stack, seen = [node], set()
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        n.live = False
        if n.is_dir:
            stack.extend(n.children)


def _fill_data(node, r, g, src_size):
    if r.resident is not None and not r.data:
        node.resident = r.resident
        node.size = len(r.resident)
        return
    if r.data_flags & 0x0001:
        node.flags.append("COMPRESSED")
        return
    if r.data_flags & 0x4000:
        node.flags.append("ENCRYPTED_EFS")
    # NTFS resets the valid-data length when a file is deleted; the runs still describe the data.
    left, left_init = r.size, (min(r.init, r.size) if r.in_use else r.size)
    expected_vcn = 0
    for start_vcn, runs in sorted(r.data, key=lambda d: d[0]):
        if start_vcn != expected_vcn:
            node.flags.append("RUNLIST_INCOMPLETE")
            break
        for lcn, n in runs:
            expected_vcn += n
            if left <= 0:
                continue
            size = min(n * g.cs, left)
            real = min(size, left_init) if lcn is not None else 0
            off = g.start + lcn * g.cs if lcn is not None else None
            if real and (off < 0 or off + real > src_size):
                node.flags.append("RUN_OUT_OF_RANGE")
                node.extents.append((None, size))
            else:
                if real:
                    node.extents.append((off, real))
                if size > real:
                    node.extents.append((None, size - real))
            left -= size
            left_init -= real if lcn is not None else min(size, left_init)
    if left > 0:
        if "RUNLIST_INCOMPLETE" not in node.flags:
            node.flags.append("RUNLIST_INCOMPLETE")
        node.extents.append((None, left))
