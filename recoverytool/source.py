"""Read-only access to a physical disk or an image file.

The source is opened for reading only; nothing in this project ever writes to it.
Unreadable areas are returned as zeros and counted, so a failing disk does not abort a run.
"""

from __future__ import annotations

import os
from collections import OrderedDict

BLOCK = 1 << 20          # cache granularity
CACHE_BLOCKS = 32


class SourceLost(Exception):
    """The disk was unplugged or no longer answers."""


class Source:
    _failures = 0

    def __init__(self, path, size=None, sector=512, label=None):
        self.path = path
        self.is_device = path.startswith("\\\\.\\")
        self.sector = sector or 512
        self._f = open(path, "rb", buffering=0)
        self.size = size if size else os.path.getsize(path)
        self.label = label or path
        self.bad_bytes = 0
        self._cache = OrderedDict()

    def close(self):
        try:
            self._f.close()
        except OSError:
            pass

    # -- low level -------------------------------------------------------------------------
    def _read_exact(self, off, n):
        self._f.seek(off)
        chunks, got = [], 0
        while got < n:
            b = self._f.read(n - got)
            if not b:
                break
            chunks.append(b)
            got += len(b)
        data = b"".join(chunks)
        if len(data) != n:
            raise OSError("short read at %d" % off)
        return data

    def _read_aligned(self, off, n):
        """Read a sector-aligned range; unreadable parts come back as zeros and are counted.

        A failed read is retried in 64 KB blocks and then sector by sector.  After a few
        consecutive bad sectors the rest of that block is given up, because every failed read on
        a dying disk can take seconds.  If the device itself has gone away, SourceLost is raised
        instead of silently "reading" zeros to the end.
        """
        try:
            data = self._read_exact(off, n)
            self._failures = 0
            return data
        except OSError:
            pass
        out = bytearray(n)
        block = max(self.sector, 65536 // self.sector * self.sector)
        for pos in range(0, n, block):
            m = min(block, n - pos)
            try:
                out[pos:pos + m] = self._read_exact(off + pos, m)
                self._failures = 0
                continue
            except OSError:
                pass
            streak = 0
            for s in range(0, m, self.sector):
                k = min(self.sector, m - s)
                if streak >= 4:                         # give up on the rest of this block
                    self.bad_bytes += m - s
                    break
                try:
                    out[pos + s:pos + s + k] = self._read_exact(off + pos + s, k)
                    streak = 0
                except OSError:
                    streak += 1
                    self.bad_bytes += k
            self._failures += 1
            if self._failures >= 8:
                self._probe()
        return bytes(out)

    def _probe(self):
        """Many failures in a row: is the device still there at all?"""
        self._failures = 0
        for probe_off in (0, self.sector * 2048):
            try:
                self._read_exact(probe_off, self.sector)
                return
            except OSError:
                continue
        raise SourceLost("the source device stopped responding")

    def read_raw(self, off, n):
        """Uncached read of an arbitrary range (clipped to the source size)."""
        if off >= self.size or n <= 0:
            return b""
        n = min(n, self.size - off)
        s = self.sector
        a = off - off % s
        b = min(-(-(off + n) // s) * s, -(-self.size // s) * s)
        if not self.is_device:
            b = min(b, self.size)
        data = self._read_aligned(a, b - a)
        return data[off - a:off - a + n]

    # -- cached -----------------------------------------------------------------------------
    def read(self, off, n):
        """Cached read, intended for the many small metadata reads done after the scan."""
        if off < 0 or off >= self.size or n <= 0:
            return b""
        n = min(n, self.size - off)
        if n > 4 * BLOCK:
            return self.read_raw(off, n)
        out = []
        pos, end = off, off + n
        while pos < end:
            bi = pos // BLOCK
            blk = self._cache.get(bi)
            if blk is None:
                blk = self.read_raw(bi * BLOCK, BLOCK)
                self._cache[bi] = blk
                if len(self._cache) > CACHE_BLOCKS:
                    self._cache.popitem(last=False)
            else:
                self._cache.move_to_end(bi)
            o = pos - bi * BLOCK
            take = min(end - pos, BLOCK - o)
            out.append(blk[o:o + take])
            pos += take
        return b"".join(out) if len(out) != 1 else out[0]
