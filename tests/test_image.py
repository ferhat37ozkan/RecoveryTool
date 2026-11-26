"""Image & Clone: the VHD footer and the partition table put in front of a partition image.

    python tests\\test_image.py
"""

from __future__ import annotations

import os
import struct
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from benchwise.tools import image  # noqa: E402


def test_geometry():
    assert image.chs(1 << 30) == (2080, 16, 63)            # what Windows / Hyper-V give a 1 GiB VHD
    assert image.chs(127 << 30)[1:] == (16, 255)


def test_footer():
    size = 64 << 20
    f = image.vhd_footer(size, when=946684800 + 100, uid=uuid.UUID(int=1))
    assert len(f) == 512 and f[:8] == b"conectix"
    assert struct.unpack_from(">I", f, 24)[0] == 100                       # timestamp
    assert struct.unpack_from(">QQ", f, 40) == (size, size)                # original / current size
    assert struct.unpack_from(">I", f, 60)[0] == 2                         # fixed disk
    stored = struct.unpack_from(">I", f, 64)[0]
    blank = f[:64] + b"\0\0\0\0" + f[68:]
    assert stored == (~sum(blank)) & 0xFFFFFFFF


def test_mbr_prefix():
    head = image.mbr_prefix(100 << 20, "FAT32", signature=0x12345678)
    assert len(head) == image.PREFIX and head[510:512] == b"\x55\xaa"
    status, ptype, start, count = struct.unpack_from("<B3xB3xII", head, 446)
    assert (status, ptype, start, count) == (0, 0x0C, 2048, (100 << 20) // 512)
    assert image.partition_type("NTFS") == 0x07 and image.partition_type("exFAT") == 0x07


def test_copy_writes_vhd():
    import tempfile

    class Src:
        size, bad_bytes = 3 << 20, 0

        def read_raw(self, off, n):
            return bytes([off >> 20]) * n

    path = os.path.join(tempfile.mkdtemp(prefix="bw-img-"), "x.vhd")
    state, sha, done = image.copy(Src(), path, {"stop": False}, lambda *a: None, b"P" * image.PREFIX)
    assert state == "done" and done == 3 << 20
    assert os.path.getsize(path) == image.image_size(3 << 20, True)
    with open(path, "rb") as f:
        data = f.read()
    assert data[:1] == b"P" and data[-512:-504] == b"conectix"
    assert struct.unpack_from(">Q", data, len(data) - 512 + 48)[0] == image.PREFIX + (3 << 20)
    os.remove(path)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
