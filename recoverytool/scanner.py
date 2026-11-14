"""Single sequential pass over the whole source that records where filesystem metadata lives.

Nothing is interpreted here; the pass only collects offsets of
  * boot sectors (NTFS / exFAT / FAT32, primary and backup copies),
  * FAT sub-directory clusters (they start with the "." and ".." entries),
  * NTFS MFT file records,
  * exFAT directory entry sets (in use and deleted).
The filesystem modules turn these into trees afterwards, which is what makes recovery possible
after a format, when the partition table and boot sector no longer describe the old data.
"""

from __future__ import annotations

import re
from array import array

from .model import Cancelled

CHUNK = 16 * 1024 * 1024

# File entry (0x85 / deleted 0x05) + stream extension (0xC0 / 0x40) + first name entry (0xC1 / 0x41)
# A lookahead is used so that a false hit can never hide a real set that starts inside it, and
# the literal first byte lets the regex engine skip ahead quickly.
_EXFAT_SETS = (re.compile(rb"\x85(?=[\x02-\x12].{30}\xc0.{31}\xc1)", re.S),
               re.compile(rb"\x05(?=[\x02-\x12].{30}\x40.{31}\x41)", re.S))
_DOT = b".          "
_DOTDOT = b"..         "


class ScanResult:
    def __init__(self):
        self.boot = {"NTFS": [], "exFAT": [], "FAT32": []}
        self.fat_dirs = array("Q")
        self.mft = array("Q")
        self.exfat_sets = array("Q")
        self.nonzero_bytes = 0


def _aligned(buf, pat, align, rel=0):
    i = buf.find(pat)
    while i != -1:
        if (i - rel) % align == 0 and i >= rel:
            yield i - rel
        i = buf.find(pat, i + 1)


def scan(src, progress=None, cancel=None):
    res = ScanResult()
    off, size = 0, src.size
    while off < size:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        buf = src.read_raw(off, min(CHUNK, size - off))
        if not buf:
            break
        if buf.count(0) != len(buf):
            res.nonzero_bytes += len(buf)
            for i in _aligned(buf, b"FILE0\x00", 512):
                res.mft.append(off + i)
            for i in _aligned(buf, _DOT, 512):
                if buf[i + 11] & 0x10 and buf[i + 32:i + 43] == _DOTDOT and buf[i + 43] & 0x10:
                    res.fat_dirs.append(off + i)
            for i in _aligned(buf, b"NTFS    ", 512, 3):
                if buf[i + 510:i + 512] == b"\x55\xaa":
                    res.boot["NTFS"].append(off + i)
            for i in _aligned(buf, b"EXFAT   ", 512, 3):
                if buf[i + 510:i + 512] == b"\x55\xaa":
                    res.boot["exFAT"].append(off + i)
            for i in _aligned(buf, b"FAT32   ", 512, 0x52):
                if buf[i + 510:i + 512] == b"\x55\xaa":
                    res.boot["FAT32"].append(off + i)
            found = [m.start() for rx in _EXFAT_SETS for m in rx.finditer(buf) if m.start() % 32 == 0]
            for i in sorted(found):
                res.exfat_sets.append(off + i)
        off += len(buf)
        if progress:
            progress(off, size)
    return res
