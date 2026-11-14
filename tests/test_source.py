"""Unit tests for reading from a failing source. No hardware or admin rights needed.

    python tests\\test_source.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recoverytool.source import Source, SourceLost  # noqa: E402

SIZE = 8 << 20


class Flaky(Source):
    """A source whose listed byte ranges cannot be read; ``dead`` simulates an unplugged disk."""

    bad_ranges = ()
    dead = False

    def _read_exact(self, off, n):
        if self.dead or any(off < e and off + n > s for s, e in self.bad_ranges):
            raise OSError("simulated I/O error")
        return super()._read_exact(off, n)


def main():
    path = os.path.join(tempfile.gettempdir(), "rt_source_test.bin")
    data = bytes(range(256)) * (SIZE // 256)
    with open(path, "wb") as f:
        f.write(data)
    try:
        # 1) one bad sector: everything else is returned intact, the bad sector as zeros
        src = Flaky(path)
        src.bad_ranges = [(1024 * 1024 + 512, 1024 * 1024 + 1024)]
        got = src.read_raw(0, SIZE)
        expected = bytearray(data)
        expected[1024 * 1024 + 512:1024 * 1024 + 1024] = bytes(512)
        assert got == bytes(expected), "data around a bad sector must be preserved"
        assert src.bad_bytes == 512, src.bad_bytes
        src.close()

        # 2) a large bad area: zeros, counted, no exception while the device still answers
        src = Flaky(path)
        src.bad_ranges = [(2 << 20, 4 << 20)]
        got = src.read_raw(0, SIZE)
        assert got[:2 << 20] == data[:2 << 20] and got[4 << 20:] == data[4 << 20:]
        assert got[2 << 20:4 << 20] == bytes(2 << 20)
        assert src.bad_bytes == 2 << 20, src.bad_bytes
        src.close()

        # 3) device unplugged: must raise instead of pretending the rest of the disk is zeros
        src = Flaky(path)
        src.dead = True
        try:
            src.read_raw(0, SIZE)
        except SourceLost:
            pass
        else:
            raise AssertionError("a dead device must raise SourceLost")
        src.close()
    finally:
        os.remove(path)
    print("source tests passed")


if __name__ == "__main__":
    main()
