"""FAT32 reconstruction.

The geometry (cluster size, start of the data area, FAT location) is taken from a surviving
boot sector when there is one and otherwise *derived from the data itself*: every
sub-directory starts with a "." entry that stores its own cluster number, so a handful of
directories pins down both the cluster size and the offset of cluster 2.
"""

from __future__ import annotations

import struct
from array import array
from collections import Counter

from .model import ATTR_DIRECTORY, Node, Volume, dos_to_filetime

EOC = 0x0FFFFFF8
CLUSTER_SIZES = [512 << k for k in range(8)]          # 512 B .. 64 KB
OEM_CODEPAGE = "cp437"


def _oem_codepage():
    try:
        import ctypes
        return "cp%d" % ctypes.windll.kernel32.GetOEMCP()
    except Exception:
        return OEM_CODEPAGE


class _Geometry:
    def __init__(self, cluster_size, data_start, fat_off=None, fat_len=0, root=2, vol_start=None, vol_size=None):
        self.cs, self.data, self.fat_off, self.fat_len = cluster_size, data_start, fat_off, fat_len
        self.root, self.vol_start, self.vol_size = root, vol_start, vol_size


def _from_boot_sectors(src, offsets):
    out = []
    for off in offsets:
        b = src.read(off, 512)
        bps, spc, reserved, nfats = struct.unpack("<HBHB", b[11:17])
        fatsz, root = struct.unpack("<I", b[36:40])[0], struct.unpack("<I", b[44:48])[0]
        total = struct.unpack("<I", b[32:36])[0]
        if bps not in (512, 1024, 2048, 4096) or spc == 0 or spc & (spc - 1) or not fatsz or nfats not in (1, 2):
            continue
        for vs in (off, off - 6 * bps):               # the hit may be the backup copy (sector 6)
            if vs < 0:
                continue
            fat_off = vs + reserved * bps
            sig = src.read(fat_off, 4)
            if len(sig) == 4 and sig[0] in (0xF8, 0xF0) and sig[1:3] == b"\xff\xff":
                out.append(_Geometry(bps * spc, fat_off + nfats * fatsz * bps, fat_off, fatsz * bps,
                                     root if root >= 2 else 2, vs, total * bps))
                break
    return out


def _from_directories(src, dir_offsets):
    """Vote for (cluster size, data start) using the self-cluster stored in each "." entry."""
    votes = Counter()
    for off in dir_offsets:
        e = src.read(off, 32)
        c = struct.unpack("<H", e[20:22])[0] << 16 | struct.unpack("<H", e[26:28])[0]
        if c < 2:
            continue
        for cs in CLUSTER_SIZES:
            d = off - (c - 2) * cs
            if d >= 0 and d % 512 == 0:
                votes[(cs, d)] += 1
    if not votes:
        return []
    best = votes.most_common(1)[0][1]
    return [_Geometry(cs, d) for (cs, d), n in votes.items() if n >= 3 and n * 5 >= best]


def _locate_fat(src, g):
    """Find the FAT copies in front of the data area (they end exactly where the data starts)."""
    need = ((src.size - g.data) // g.cs + 2) * 4
    lo = max(0, g.data - 2 * need - (16 << 20))
    hits, pos = [], lo - lo % 512
    while pos < g.data:
        buf = src.read_raw(pos, min(8 << 20, g.data - pos))
        if not buf:
            break
        i = buf.find(b"\xff\xff", 1)
        while i != -1:
            if (i - 1) % 512 == 0 and buf[i - 1] in (0xF8, 0xF0) and i + 2 < len(buf) and buf[i + 2] in (0x0F, 0xFF):
                hits.append(pos + i - 1)
            i = buf.find(b"\xff\xff", i + 1)
        pos += len(buf)
    for a in hits:                                    # two intact copies: FAT1, FAT2, data
        for b in hits:
            if b > a and g.data - b == b - a:
                g.fat_off, g.fat_len = a, b - a
                return
    if hits:                                          # only one signature survived
        a = hits[-1]
        g.fat_off, g.fat_len = a, g.data - a


def _lfn_checksum(short):
    s = 0
    for ch in short:
        s = (((s >> 1) | ((s & 1) << 7)) + ch) & 0xFF
    return s


class _Fat32:
    def __init__(self, src, g):
        self.src, self.g = src, g
        self.max_cluster = (min(src.size, (g.vol_start or 0) + g.vol_size if g.vol_size else src.size) - g.data) // g.cs + 2
        self.fat = None
        if g.fat_off is not None and g.fat_len >= 8:
            raw = src.read_raw(g.fat_off, min(g.fat_len, self.max_cluster * 4 + 4096) // 4 * 4)
            self.fat = array("I")
            self.fat.frombytes(raw)
        self.codepage = _oem_codepage()
        self.visited = set()
        self.deferred = []       # deleted directory entries: (cluster, node, parent, parent_cluster)
        self.label = ""

    def parent_of(self, c):
        e = self.src.read(self.offset(c) + 32, 32)
        return struct.unpack("<H", e[20:22])[0] << 16 | struct.unpack("<H", e[26:28])[0]

    def run_deferred(self):
        """Re-attach deleted directories whose clusters still hold their old content."""
        while self.deferred:
            cluster, node, parent, pfirst = self.deferred.pop()
            if not 2 <= cluster < self.max_cluster or cluster in self.visited or not self.is_dir_cluster(cluster):
                continue
            if self.parent_of(cluster) not in (pfirst, 0 if pfirst == self.g.root else pfirst):
                continue
            self.parse(cluster, node, False, True)
            if node.children:
                parent.children.append(node)

    def nxt(self, c):
        return self.fat[c] & 0x0FFFFFFF if self.fat is not None and c < len(self.fat) else 0

    def offset(self, c):
        return self.g.data + (c - 2) * self.g.cs

    def chain(self, first, need=None):
        """Follow the FAT. Returns (clusters, ok)."""
        out, seen, c = [], set(), first
        while 2 <= c < self.max_cluster and c not in seen:
            out.append(c)
            seen.add(c)
            if need is not None and len(out) >= need:
                return out, self.nxt(c) >= EOC
            n = self.nxt(c)
            if n >= EOC:
                return out, need is None
            c = n
        return out, False

    def clusters_for(self, first, size, node):
        need = -(-size // self.g.cs)
        if need == 0:
            return []
        if not 2 <= first < self.max_cluster:
            node.flags.append("BAD_START_CLUSTER")
            return []
        if self.nxt(first) == 0:                      # FAT entry is free: deleted file or wiped FAT
            if need > 1:
                node.flags.append("CHAIN_GUESSED")
            return list(range(first, min(first + need, self.max_cluster)))
        cl, ok = self.chain(first, need)
        if not ok:
            node.flags.append("CHAIN_BROKEN")
            last = cl[-1] if cl else first - 1
            cl += list(range(last + 1, min(last + 1 + need - len(cl), self.max_cluster)))
        return cl

    def extents(self, clusters, size):
        out, i, left = [], 0, size
        while i < len(clusters) and left > 0:
            j = i
            while j + 1 < len(clusters) and clusters[j + 1] == clusters[j] + 1:
                j += 1
            n = min((j - i + 1) * self.g.cs, left)
            out.append((self.offset(clusters[i]), n))
            left -= n
            i = j + 1
        return out

    def read_dir(self, first):
        if self.nxt(first) == 0:
            cl = [first]
        else:
            cl, _ = self.chain(first)
        return b"".join(self.src.read(self.offset(c), self.g.cs) for c in cl[:65536])

    def is_dir_cluster(self, c):
        e = self.src.read(self.offset(c), 32)
        return len(e) == 32 and e[:11] == b".          " and (
            struct.unpack("<H", e[20:22])[0] << 16 | struct.unpack("<H", e[26:28])[0]) == c

    def parse(self, first, parent, live, deleted_branch=False):
        """Read one directory and attach its entries to ``parent`` (recursively)."""
        if first in self.visited:
            return
        self.visited.add(first)
        raw = self.read_dir(first)
        lfn = []
        for o in range(0, len(raw) - 31, 32):
            e = raw[o:o + 32]
            if e[0] == 0:
                break
            attr = e[11]
            if attr & 0x3F == 0x0F:
                lfn.append(e)
                continue
            deleted = e[0] == 0xE5
            short = e[:11]
            pieces, lfn = lfn, []
            if attr & 0x08:
                if not deleted and not self.label and first == self.g.root:
                    self.label = short.decode(self.codepage, "replace").strip()
                continue
            if attr & 0xC0 or any(ch < 0x20 for ch in short[1:]) or (e[0] < 0x20 and e[0] != 0x05):
                continue                                # not a plausible entry
            name = None
            if pieces:
                good = deleted or all(p[13] == _lfn_checksum(short) for p in pieces)
                if good:
                    u = b"".join(p[1:11] + p[14:26] + p[28:32] for p in reversed(pieces))
                    name = u.decode("utf-16-le", "replace").split("\0")[0].rstrip("￿")
            if not name:
                first_ch = b"\xe5" if e[0] == 0x05 else (b"_" if deleted else short[:1])
                base = (first_ch + short[1:8]).decode(self.codepage, "replace").rstrip()
                ext = short[8:11].decode(self.codepage, "replace").rstrip()
                if e[12] & 0x08:
                    base = base.lower()
                if e[12] & 0x10:
                    ext = ext.lower()
                name = base + ("." + ext if ext else "")
            if name in (".", "..") or not name:
                continue
            cluster = struct.unpack("<H", e[20:22])[0] << 16 | struct.unpack("<H", e[26:28])[0]
            size = struct.unpack("<I", e[28:32])[0]
            is_dir = bool(attr & ATTR_DIRECTORY)
            node = Node(name, is_dir, 0 if is_dir else size)
            node.attrs = attr & 0x07
            node.deleted = deleted or deleted_branch
            node.live = live and not node.deleted
            node.ident = cluster
            node.ctime = dos_to_filetime(struct.unpack("<H", e[16:18])[0], struct.unpack("<H", e[14:16])[0], e[13])
            node.mtime = dos_to_filetime(struct.unpack("<H", e[24:26])[0], struct.unpack("<H", e[22:24])[0])
            node.atime = dos_to_filetime(struct.unpack("<H", e[18:20])[0], 0)
            if is_dir:
                if deleted:
                    # Handled after the live tree, so a reused cluster is never taken away
                    # from the directory that owns it now.
                    self.deferred.append((cluster, node, parent, first))
                    continue
                if 2 <= cluster < self.max_cluster and self.is_dir_cluster(cluster):
                    self.parse(cluster, node, live, node.deleted)
                else:
                    node.flags.append("DIRECTORY_CONTENT_LOST")
            else:
                node.extents = self.extents(self.clusters_for(cluster, size, node), size)
            parent.children.append(node)


def find_volumes(src, scan, log=lambda m: None):
    geos, seen = [], set()
    for g in _from_boot_sectors(src, scan.boot["FAT32"]) + _from_directories(src, scan.fat_dirs):
        if (g.cs, g.data) not in seen:
            seen.add((g.cs, g.data))
            geos.append(g)
    volumes = []
    for g in geos:
        if g.fat_off is None:
            _locate_fat(src, g)
        fs = _Fat32(src, g)
        vol = Volume("FAT32", g.vol_start if g.vol_start is not None else (g.fat_off or g.data),
                     g.vol_size or src.size - g.data, g.cs)
        if fs.fat is None:
            vol.notes.append("FAT_NOT_FOUND")
        elif not any(fs.fat[2:min(len(fs.fat), 200000)]):
            vol.notes.append("FAT_EMPTY")
        # "live" only if this is the filesystem the boot sector at the volume start describes now
        current = (fs.fat is not None and g.vol_start is not None
                   and src.read(g.vol_start + 0x52, 8) == b"FAT32   ")
        fs.parse(g.root, vol.root, live=current)
        fs.run_deferred()
        # directories found by the scan that the tree walk did not reach
        own = {}
        for off in scan.fat_dirs:
            if off >= g.data and (off - g.data) % g.cs == 0:
                c = (off - g.data) // g.cs + 2
                e = src.read(off + 32, 32)
                if fs.is_dir_cluster(c):
                    own[c] = struct.unpack("<H", e[20:22])[0] << 16 | struct.unpack("<H", e[26:28])[0]
        orphans = [c for c in sorted(own) if c not in fs.visited]
        orphan_set = set(orphans)
        for c in [c for c in orphans if own[c] not in orphan_set] + orphans:
            if c in fs.visited:
                continue
            node = Node("dir_cluster_%d" % c, True)
            node.ident = c
            fs.parse(c, node, live=False)
            fs.run_deferred()
            vol.orphans.children.append(node)
        vol.label = fs.label
        vol.fat_info = (g.fat_off, g.fat_len, g.data)
        log("FAT32: cluster=%d data@%d fat@%s -> %d files, %d dirs" % ((g.cs, g.data, g.fat_off) + vol.count()))
        volumes.append(vol)
    return volumes
