"""Shared data model used by every filesystem parser and by the extractor."""

from __future__ import annotations

import time
from bisect import bisect_right


class Cancelled(Exception):
    """Raised inside the worker when the user cancels the operation."""


# Final per-file statuses written to the report.
OK = "OK"
REPAIRED = "REPAIRED"                # damaged blocks refilled from a byte-verified twin copy
FILLED_FROM_TWIN = "FILLED_FROM_TWIN"  # fully overwritten; replaced by same name+size+time copy
UNCERTAIN = "UNCERTAIN"              # recovered, but integrity could not be proven
DAMAGED = "DAMAGED"                  # evidence of corruption
UNSUPPORTED = "UNSUPPORTED"
SKIPPED = "SKIPPED"

# Windows-compatible attribute bits (identical on FAT, exFAT and NTFS).
ATTR_READONLY, ATTR_HIDDEN, ATTR_SYSTEM, ATTR_DIRECTORY = 0x01, 0x02, 0x04, 0x10

_EPOCH_DIFF = 116444736000000000  # 1601-01-01 -> 1970-01-01 in 100 ns units


class Node:
    """A recovered file or directory.

    ``extents`` is a list of ``(disk_offset | None, length)`` byte ranges; ``None`` means a
    sparse/zero range.  Times are Windows FILETIME integers (UTC) or ``None``.
    """

    __slots__ = ("name", "is_dir", "size", "children", "ctime", "mtime", "atime", "attrs",
                 "deleted", "live", "extents", "resident", "flags", "ident")

    def __init__(self, name, is_dir=False, size=0):
        self.name = name
        self.is_dir = is_dir
        self.size = size
        self.children = [] if is_dir else None
        self.ctime = self.mtime = self.atime = None
        self.attrs = 0
        self.deleted = False     # entry was marked deleted in the filesystem
        self.live = False        # belongs to the *current* intact filesystem
        self.extents = []
        self.resident = None     # bytes stored inside the metadata record (NTFS)
        self.flags = []          # parser remarks, e.g. "CHAIN_GUESSED"
        self.ident = None        # cluster / record number, for diagnostics


class Volume:
    """One reconstructed filesystem found on the source."""

    def __init__(self, fs, start, size, cluster_size, label=""):
        self.fs = fs
        self.start = start
        self.size = size
        self.cluster_size = cluster_size
        self.label = label
        self.root = Node("", True)
        self.orphans = Node("", True)   # directories whose parent could not be located
        self.notes = []

    def count(self):
        files = dirs = 0
        stack = [self.root, self.orphans]
        seen = set()
        while stack:
            n = stack.pop()
            if id(n) in seen:
                continue
            seen.add(id(n))
            for c in n.children:
                if c.is_dir:
                    dirs += 1
                    stack.append(c)
                else:
                    files += 1
        return files, dirs


class Intervals:
    """Sorted, merged set of half-open byte ranges with fast overlap queries."""

    def __init__(self, ranges=()):
        merged = []
        for s, e in sorted(r for r in ranges if r[1] > r[0]):
            if merged and s <= merged[-1][1]:
                if e > merged[-1][1]:
                    merged[-1][1] = e
            else:
                merged.append([s, e])
        self.starts = [m[0] for m in merged]
        self.ends = [m[1] for m in merged]

    def __bool__(self):
        return bool(self.starts)

    def total(self):
        return sum(e - s for s, e in zip(self.starts, self.ends))

    def overlaps(self, start, length):
        """Return the parts of [start, start+length) covered by this set."""
        out, end = [], start + length
        i = max(bisect_right(self.starts, start) - 1, 0)
        while i < len(self.starts) and self.starts[i] < end:
            s, e = max(self.starts[i], start), min(self.ends[i], end)
            if e > s:
                out.append((s, e))
            i += 1
        return out


def unix_to_filetime(ts):
    return int(ts * 10000000) + _EPOCH_DIFF


def dos_to_filetime(date, tm, tenths=0, utc_offset_quarters=None):
    """Convert FAT/exFAT date+time (+10 ms units) to FILETIME.

    Without an explicit UTC offset the value is interpreted as local time, as Windows does.
    """
    try:
        y, mo, d = 1980 + (date >> 9), (date >> 5) & 15, date & 31
        h, mi, s = tm >> 11, (tm >> 5) & 63, (tm & 31) * 2
        if not (1 <= mo <= 12 and 1 <= d <= 31 and h < 24 and mi < 60 and s < 60):
            return None
        s += tenths // 100
        frac = (tenths % 100) * 100000
        if utc_offset_quarters is None:
            ts = time.mktime((y, mo, d, h, mi, s, 0, 0, -1))
        else:
            import calendar
            ts = calendar.timegm((y, mo, d, h, mi, s, 0, 0, 0)) - utc_offset_quarters * 900
        return unix_to_filetime(ts) + frac
    except (OverflowError, ValueError, OSError):
        return None


def filetime_to_text(ft):
    if not ft:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime((ft - _EPOCH_DIFF) / 10000000))
    except (OverflowError, ValueError, OSError):
        return ""


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
