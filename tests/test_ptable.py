"""Partition table and boot sector checks against disks built in memory.

    python tests\\test_ptable.py
"""

from __future__ import annotations

import os
import struct
import sys
import uuid
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from benchwise import ptable  # noqa: E402

SECTOR = 512
SECTORS = 4096                    # a 2 MB disk


def gpt_header(current, backup, entries_lba, entries_crc, disk_guid):
    h = bytearray(SECTOR)
    struct.pack_into("<8sIIIIQQQQ", h, 0, b"EFI PART", 0x10000, 92, 0, 0, current, backup, 34, SECTORS - 34)
    h[56:72] = disk_guid.bytes_le
    struct.pack_into("<QIII", h, 72, entries_lba, 128, 128, entries_crc)
    struct.pack_into("<I", h, 16, zlib.crc32(bytes(h[:92])) & 0xFFFFFFFF)
    return h


def make_disk():
    disk = bytearray(SECTORS * SECTOR)
    disk[446 + 4] = 0xEE
    struct.pack_into("<II", disk, 446 + 8, 1, SECTORS - 1)
    disk[510:512] = b"\x55\xaa"
    entries = bytearray(128 * 128)
    entries[0:16] = uuid.UUID("ebd0a0a2-b9e5-4433-87c0-68b6b72699c7").bytes_le
    entries[16:32] = uuid.uuid4().bytes_le
    struct.pack_into("<QQQ", entries, 32, 2048, 4000, 0)
    entries[56:56 + 8] = "Data".encode("utf-16-le")
    crc = zlib.crc32(bytes(entries)) & 0xFFFFFFFF
    guid = uuid.uuid4()
    disk[SECTOR:2 * SECTOR] = gpt_header(1, SECTORS - 1, 2, crc, guid)
    disk[2 * SECTOR:2 * SECTOR + len(entries)] = entries
    disk[(SECTORS - 33) * SECTOR:(SECTORS - 33) * SECTOR + len(entries)] = entries
    disk[(SECTORS - 1) * SECTOR:] = gpt_header(SECTORS - 1, 1, SECTORS - 33, crc, guid)
    return disk


def reader(buf):
    return lambda off, n: bytes(buf[off:off + n])


def test_healthy_gpt():
    disk = make_disk()
    g = ptable.read_gpt(reader(disk), len(disk), SECTOR)
    assert ptable.gpt_problems(g) == [], ptable.gpt_problems(g)
    assert g["same"] and g["mbr"]["protective"]
    assert [(e["type_name"], e["first"], e["name"]) for e in g["entries"]] == [("Basic data", 2048, "Data")]


def test_damaged_primary_is_reported_and_backup_still_read():
    disk = make_disk()
    disk[2 * SECTOR + 40] ^= 0xFF                     # corrupt the primary entry array
    g = ptable.read_gpt(reader(disk), len(disk), SECTOR)
    assert ptable.gpt_problems(g) == ["primary_bad"], ptable.gpt_problems(g)
    assert g["entries"][0]["first"] == 2048           # taken from the intact backup
    disk = make_disk()
    disk[(SECTORS - 1) * SECTOR:] = bytes(SECTOR)     # wipe the backup header
    assert ptable.gpt_problems(ptable.read_gpt(reader(disk), len(disk), SECTOR)) == ["backup_missing"]


def ntfs_volume(sectors=2048):
    vol = bytearray(sectors * SECTOR)
    boot = bytearray(SECTOR)
    boot[3:11] = b"NTFS    "
    struct.pack_into("<H", boot, 11, SECTOR)
    struct.pack_into("<Q", boot, 0x28, sectors - 1)
    boot[510:512] = b"\x55\xaa"
    vol[:SECTOR] = boot
    vol[(sectors - 1) * SECTOR:] = boot
    return vol


def test_ntfs_boot_backup():
    vol = ntfs_volume()
    assert ptable.check_boot(reader(vol), len(vol)) == ("NTFS", "same")
    vol[-SECTOR + 100] = 1
    assert ptable.check_boot(reader(vol), len(vol)) == ("NTFS", "differ")
    assert ptable.check_boot(reader(bytearray(4096)), 4096) == (None, "unknown")


if __name__ == "__main__":
    test_healthy_gpt()
    test_damaged_primary_is_reported_and_backup_still_read()
    test_ntfs_boot_backup()
    print("ptable tests passed")
