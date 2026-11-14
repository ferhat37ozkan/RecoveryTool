"""exFAT reconstruction.

Works from the individual directory entry sets found by the scan rather than from a tree walk,
so files are still found when the root directory and the allocation tables were reset by a
format.  Each set is placed in its directory by the cluster it physically lives in.
"""

from __future__ import annotations

import struct
from array import array
from collections import Counter

from .model import ATTR_DIRECTORY, Node, Volume, dos_to_filetime
from .signatures import magic_matches


class _Geometry:
    def __init__(self, cs, heap, vol_start=None, fat_off=None, clusters=None, root=None, sector=512):
        self.cs, self.heap, self.vol_start, self.fat_off = cs, heap, vol_start, fat_off
        self.clusters, self.root, self.sector = clusters, root, sector


def _checksum(data):
    c = 0
    for i, b in enumerate(data):
        if i in (2, 3):
            continue
        c = (((c << 15) | (c >> 1)) + b) & 0xFFFF
    return c


def _timestamp(ts, ms10, tz):
    off = None
    if tz & 0x80:
        off = tz & 0x7F
        if off >= 0x40:
            off -= 0x80
    return dos_to_filetime(ts >> 16, ts & 0xFFFF, ms10, off)


def _parse_set(src, off):
    """Decode one entry set. Returns a dict or None if it is not plausible."""
    head = src.read(off, 64)
    if len(head) < 64:
        return None
    count = head[1]
    raw = src.read(off, 32 * (count + 1))
    if len(raw) < 32 * (count + 1) or count < 2:
        return None
    deleted = raw[0] == 0x05
    want = 0x41 if deleted else 0xC1
    if raw[32] != (0x40 if deleted else 0xC0) or any(raw[32 * i] != want for i in range(2, count + 1)):
        return None
    if not deleted and _checksum(raw) != struct.unpack("<H", raw[2:4])[0]:
        return None
    name_len = raw[35]
    if not 1 <= name_len <= 15 * (count - 1):
        return None
    name = b"".join(raw[32 * i + 2:32 * i + 32] for i in range(2, count + 1)).decode("utf-16-le", "replace")[:name_len]
    if "\0" in name or any(ord(ch) < 0x20 for ch in name):
        return None
    valid, first, length = struct.unpack("<Q", raw[40:48])[0], struct.unpack("<I", raw[52:56])[0], struct.unpack("<Q", raw[56:64])[0]
    if valid > length or length > src.size:
        return None
    attrs = struct.unpack("<H", raw[4:6])[0]
    c, m, a = struct.unpack("<III", raw[8:20])
    return dict(off=off, deleted=deleted, name=name, attrs=attrs, first=first, length=length, valid=valid,
                contiguous=bool(raw[33] & 2), ctime=_timestamp(c, raw[20], raw[22]),
                mtime=_timestamp(m, raw[21], raw[23]), atime=_timestamp(a, 0, raw[24]))


def _from_boot_sectors(src, offsets, sets):
    out = []
    probe = [s["off"] for s in sets[:2000]]
    for off in offsets:
        b = src.read(off, 512)
        fat_off, fat_len, heap_off, clusters, root = struct.unpack("<IIIII", b[80:100])
        bps_shift, spc_shift = b[108], b[109]
        if not (9 <= bps_shift <= 12 and spc_shift <= 25 and heap_off and clusters):
            continue
        bps = 1 << bps_shift
        cs = bps << spc_shift
        best = None
        for vs in (off, off - 12 * bps):              # the hit may be the backup boot region
            if vs < 0:
                continue
            heap = vs + heap_off * bps
            score = sum(1 for x in probe if heap <= x < heap + clusters * cs)
            first = src.read(heap + (root - 2) * cs, 1)
            score += 5 if first and first[0] in (0x81, 0x82, 0x83, 0x03, 0x85, 0x05) else 0
            if best is None or score > best[0]:
                best = (score, vs, heap)
        if best:
            out.append(_Geometry(cs, best[2], best[1], best[1] + fat_off * bps, clusters, root, bps))
    return out


def _infer(src, sets):
    """No boot sector: derive (cluster size, heap offset) from the data.

    The first entry set of a sub-directory sits at the start of the cluster its parent's entry
    points to, which gives candidate geometries by voting.  Neighbouring directories make
    off-by-one-cluster candidates score almost as well, so the candidates are then ranked by how
    many files with a known signature really start where that geometry says they do.
    """
    dirs = [s["first"] for s in sets if s["attrs"] & ATTR_DIRECTORY and not s["deleted"] and s["first"] >= 2]
    tops = sorted({s["off"] for s in sets if s["off"] % 512 == 0})
    if len(dirs) < 2 or len(tops) < 2:
        return []
    step_d, step_t = max(1, len(dirs) // 400), max(1, len(tops) // 400)
    votes = Counter()
    for n in dirs[::step_d]:
        for x in tops[::step_t]:
            for k in range(17):
                cs = 512 << k
                h = x - (n - 2) * cs
                if h >= 0:
                    votes[(cs, h)] += 1
    files = [s for s in sets if not s["attrs"] & ATTR_DIRECTORY and not s["deleted"] and s["length"] >= 16
             and magic_matches(s["name"], b"\0" * 16) is False]          # i.e. the type has a signature
    files = files[::max(1, len(files) // 300)]
    top_set = set(tops)
    best, best_score, second = None, 0, 0
    for (cs, h), n in votes.most_common(8):
        if n < 2:
            break
        score = sum(1 for d in dirs[::step_d] if h + (d - 2) * cs in top_set)
        score += 3 * sum(1 for f in files if magic_matches(f["name"], src.read(h + (f["first"] - 2) * cs, 16)))
        if score > best_score:
            best, best_score, second = (cs, h), score, best_score
        elif score > second:
            second = score
    if best is None or best_score < 3 or second * 4 > best_score * 3:
        return []
    return [_Geometry(best[0], best[1])]


def find_volumes(src, scan, log=lambda m: None):
    sets = []
    for off in scan.exfat_sets:
        s = _parse_set(src, off)
        if s:
            sets.append(s)
    if not sets:
        return []
    geos, seen = [], set()
    for g in _from_boot_sectors(src, scan.boot["exFAT"], sets) + _infer(src, sets):
        if (g.cs, g.heap) not in seen:
            seen.add((g.cs, g.heap))
            geos.append(g)
    volumes = []
    for g in geos:
        vol = _build(src, g, sets)
        if vol.count() != (0, 0):
            log("exFAT: cluster=%d heap@%d -> %d files, %d dirs" % ((g.cs, g.heap) + vol.count()))
            volumes.append(vol)
    return volumes


def _build(src, g, all_sets):
    end = g.heap + g.clusters * g.cs if g.clusters else src.size
    max_cluster = (min(end, src.size) - g.heap) // g.cs + 2
    sets = [s for s in all_sets if g.heap <= s["off"] < end]
    vol = Volume("exFAT", g.vol_start if g.vol_start is not None else g.heap, end - (g.vol_start or g.heap), g.cs)
    vol.exfat_info = (g.heap, g.cs, g.root, g.vol_start)

    fat = None
    if g.fat_off is not None:
        fat = array("I")
        fat.frombytes(src.read_raw(g.fat_off, (max_cluster + 1) * 4 // 4 * 4))
    else:
        vol.notes.append("FAT_NOT_FOUND")

    def cluster_list(first, length, contiguous, node=None):
        need = max(1, -(-length // g.cs))
        if not 2 <= first < max_cluster:
            if node is not None:
                node.flags.append("BAD_START_CLUSTER")
            return []
        if contiguous or fat is None or first >= len(fat) or fat[first] == 0:
            if node is not None and not contiguous and need > 1:
                node.flags.append("CHAIN_GUESSED")
            return list(range(first, min(first + need, max_cluster)))
        out, c, seen = [], first, set()
        while 2 <= c < max_cluster and c not in seen and len(out) < need:
            out.append(c)
            seen.add(c)
            c = fat[c] if c < len(fat) else 0
        if len(out) < need:
            if node is not None:
                node.flags.append("CHAIN_BROKEN")
            last = out[-1]
            out += list(range(last + 1, min(last + 1 + need - len(out), max_cluster)))
        return out

    # 1) one node per set
    nodes = []
    for s in sets:
        is_dir = bool(s["attrs"] & ATTR_DIRECTORY)
        n = Node(s["name"], is_dir, 0 if is_dir else s["length"])
        n.attrs, n.deleted, n.ident = s["attrs"] & 0x07, s["deleted"], s["first"]
        n.ctime, n.mtime, n.atime = s["ctime"], s["mtime"], s["atime"]
        nodes.append(n)

    # 2) which directory owns each cluster
    owner = {}
    if g.root:
        chain = [g.root]
        if fat is not None:
            c, seen = g.root, set()
            chain = []
            while 2 <= c < max_cluster and c not in seen and len(chain) < 1 << 16:
                chain.append(c)
                seen.add(c)
                c = fat[c] if c < len(fat) else 0
        for c in chain:
            owner[c] = vol.root
    for live_pass in (True, False):                    # live directories win over deleted ones
        for s, n in zip(sets, nodes):
            if n.is_dir and (not s["deleted"]) == live_pass and s["first"] >= 2:
                for c in cluster_list(s["first"], s["length"], s["contiguous"]):
                    owner.setdefault(c, n)

    # 3) attach every set to the directory whose cluster it sits in
    placeholders = {}
    for s, n in zip(sets, nodes):
        c = (s["off"] - g.heap) // g.cs + 2
        parent = owner.get(c)
        if parent is None or parent is n:
            parent = placeholders.get(c)
            if parent is None:
                parent = placeholders[c] = Node("dir_cluster_%d" % c, True)
                parent.ident = c
                vol.orphans.children.append(parent)
        parent.children.append(n)
        if not n.is_dir:
            cl = cluster_list(s["first"], s["length"], s["contiguous"], n) if s["length"] else []
            left_valid, left = s["valid"], s["length"]
            i = 0
            while i < len(cl) and left > 0:
                j = i
                while j + 1 < len(cl) and cl[j + 1] == cl[j] + 1:
                    j += 1
                size = min((j - i + 1) * g.cs, left)
                real = min(size, left_valid)
                if real:
                    n.extents.append((g.heap + (cl[i] - 2) * g.cs, real))
                if size > real:
                    n.extents.append((None, size - real))   # beyond the valid data length
                left, left_valid = left - size, left_valid - real
                i = j + 1

    # 4) "live" = not deleted and reachable from the current root
    def mark(node, seen):
        for ch in node.children:
            if not ch.deleted and id(ch) not in seen:
                seen.add(id(ch))
                ch.live = True
                if ch.is_dir:
                    mark(ch, seen)
    if g.root and fat is not None and src.read(g.vol_start + 3, 8) == b"EXFAT   ":
        mark(vol.root, set())

    def spread_deleted(node, flag, seen):
        for ch in node.children:
            if id(ch) in seen:
                continue
            seen.add(id(ch))
            ch.deleted = ch.deleted or flag
            if ch.is_dir:
                spread_deleted(ch, ch.deleted, seen)
    spread_deleted(vol.root, False, set())
    spread_deleted(vol.orphans, False, set())
    return vol
