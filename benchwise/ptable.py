"""Reading - only reading - partition tables and boot sectors.

Every function takes ``read(offset, length) -> bytes`` so it works on a physical disk, a partition
window of one, or an image file, and can be tested against bytes built in memory."""

from __future__ import annotations

import struct
import uuid
import zlib

GPT_SIG = b"EFI PART"

MBR_TYPES = {0x07: "NTFS / exFAT", 0x0B: "FAT32", 0x0C: "FAT32 (LBA)", 0x0E: "FAT16 (LBA)", 0x0F: "Extended (LBA)",
             0x05: "Extended", 0x06: "FAT16", 0x27: "Recovery", 0x83: "Linux", 0x82: "Linux swap", 0x8E: "Linux LVM",
             0xEE: "GPT protective", 0xEF: "EFI system", 0x17: "Hidden NTFS", 0x1C: "Hidden FAT32"}

GPT_TYPES = {
    "c12a7328-f81f-11d2-ba4b-00a0c93ec93b": "EFI system",
    "e3c9e316-0b5c-4db8-817d-f92df00215ae": "Microsoft reserved",
    "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7": "Basic data",
    "de94bba4-06d1-4d40-a16a-bfd50179d6ac": "Windows recovery",
    "5808c8aa-7e8f-42e0-85d2-e1e90434cfb3": "LDM metadata",
    "af9b60a0-1431-4f62-bc68-3311714a69ad": "LDM data",
    "e75caf8f-f680-4cee-afa3-b001e56efc2d": "Storage Spaces",
    "0fc63daf-8483-4772-8e79-3d69d8477de4": "Linux filesystem",
    "0657fd6d-a4ab-43c4-84e5-0933c84b4f4f": "Linux swap",
    "e6d6d379-f507-44c2-a23c-238f2a3df928": "Linux LVM",
    "48465300-0000-11aa-aa11-00306543ecac": "Apple HFS+",
    "7c3457ef-0000-11aa-aa11-00306543ecac": "Apple APFS",
}


def parse_mbr(sector0):
    """{'signature': bool, 'disk_id', 'entries': [...], 'protective': bool}"""
    sig = len(sector0) >= 512 and sector0[510:512] == b"\x55\xaa"
    entries = []
    if sig:
        for i in range(4):
            e = sector0[446 + 16 * i: 462 + 16 * i]
            ptype = e[4]
            lba, count = struct.unpack_from("<II", e, 8)
            if ptype:
                entries.append({"index": i + 1, "boot": e[0] == 0x80, "type": ptype,
                                "type_name": MBR_TYPES.get(ptype, "0x%02X" % ptype), "lba": lba, "sectors": count})
    return {"signature": sig, "disk_id": "%08X" % struct.unpack_from("<I", sector0, 440)[0] if sig else "",
            "entries": entries, "protective": any(e["type"] == 0xEE for e in entries)}


def parse_gpt_header(raw):
    """Header fields plus ``crc_ok``, or None if the signature is missing."""
    if len(raw) < 92 or raw[:8] != GPT_SIG:
        return None
    (rev, hsize, hcrc, _r, cur, backup, first, last) = struct.unpack_from("<IIIIQQQQ", raw, 8)
    guid = str(uuid.UUID(bytes_le=bytes(raw[56:72])))
    entries_lba, count, esize, ecrc = struct.unpack_from("<QIII", raw, 72)
    hsize = hsize if 92 <= hsize <= len(raw) else 92
    h = bytearray(raw[:hsize])
    h[16:20] = b"\0\0\0\0"
    return {"revision": rev, "current": cur, "backup": backup, "first": first, "last": last, "guid": guid,
            "entries_lba": entries_lba, "count": count, "entry_size": esize, "entries_crc": ecrc,
            "crc_ok": zlib.crc32(bytes(h)) & 0xFFFFFFFF == hcrc}


def parse_gpt_entries(raw, count, esize):
    out = []
    for i in range(count):
        e = raw[i * esize:(i + 1) * esize]
        if len(e) < 128 or e[:16] == b"\0" * 16:
            continue
        tguid = str(uuid.UUID(bytes_le=bytes(e[:16])))
        first, last, attrs = struct.unpack_from("<QQQ", e, 32)
        name = bytes(e[56:128]).decode("utf-16-le", "replace").split("\0")[0]
        out.append({"index": i + 1, "type_guid": tguid, "type_name": GPT_TYPES.get(tguid, tguid),
                    "guid": str(uuid.UUID(bytes_le=bytes(e[16:32]))), "first": first, "last": last,
                    "attrs": attrs, "name": name})
    return out


def read_gpt(read, size, sector):
    """Both GPT copies of a disk, each checked on its own and against each other.

    Returns {'mbr', 'primary', 'backup', 'entries', 'entries_ok': (primary, backup), 'same'} - header
    dicts are None when that copy is missing."""
    mbr = parse_mbr(read(0, sector))
    out = {"mbr": mbr, "primary": None, "backup": None, "entries": [], "entries_ok": (None, None), "same": None}
    last_lba = size // sector - 1
    primary = parse_gpt_header(read(sector, sector))
    backup_lba = primary["backup"] if primary and 0 < primary["backup"] <= last_lba else last_lba
    backup = parse_gpt_header(read(backup_lba * sector, sector))
    oks = []
    tables = []
    for h in (primary, backup):
        if h is None or not (0 < h["count"] <= 1024 and 128 <= h["entry_size"] <= 4096):
            oks.append(None)
            tables.append(None)
            continue
        raw = read(h["entries_lba"] * sector, h["count"] * h["entry_size"])
        oks.append(zlib.crc32(raw) & 0xFFFFFFFF == h["entries_crc"])
        tables.append(raw)
    out.update(primary=primary, backup=backup, entries_ok=tuple(oks))
    good = tables[0] if oks[0] else tables[1] if oks[1] else tables[0] or tables[1]
    src = primary if oks[0] else backup if oks[1] else primary or backup
    if good and src:
        out["entries"] = parse_gpt_entries(good, src["count"], src["entry_size"])
    if primary and backup:
        out["same"] = (primary["guid"] == backup["guid"] and tables[0] == tables[1]
                       and primary["first"] == backup["first"] and primary["last"] == backup["last"])
    return out


def gpt_problems(g):
    """Short problem keys for a ``read_gpt`` result (empty list = healthy)."""
    p = []
    if not g["mbr"]["signature"]:
        p.append("no_mbr")
    if g["primary"] is None:
        p.append("primary_missing")
    elif not g["primary"]["crc_ok"] or g["entries_ok"][0] is False:
        p.append("primary_bad")
    if g["backup"] is None:
        p.append("backup_missing")
    elif not g["backup"]["crc_ok"] or g["entries_ok"][1] is False:
        p.append("backup_bad")
    if g["same"] is False and not p:
        p.append("differ")
    return p


def boot_kind(sector0):
    oem = bytes(sector0[3:11])
    if oem == b"NTFS    ":
        return "NTFS"
    if oem == b"EXFAT   ":
        return "exFAT"
    if bytes(sector0[82:90]).startswith(b"FAT32"):
        return "FAT32"
    if bytes(sector0[54:59]).startswith(b"FAT1"):
        return "FAT"
    return None


def check_boot(read, size):
    """Compare a volume's boot sector with its backup copy.

    Returns (kind, state) where state is 'same', 'differ', 'no_backup' (FAT12/16 keep none) or
    'unknown' (no recognised boot sector)."""
    s0 = read(0, 512)
    kind = boot_kind(s0)
    if kind is None or s0[510:512] != b"\x55\xaa":
        return kind, "unknown"
    bps = struct.unpack_from("<H", s0, 11)[0] if kind != "exFAT" else 1 << s0[108]
    if bps not in (512, 1024, 2048, 4096):
        return kind, "unknown"
    primary = read(0, bps)
    if kind == "NTFS":
        total = struct.unpack_from("<Q", s0, 0x28)[0]
        off = total * bps if total * bps < size else size - bps
        backup = read(off, bps)
    elif kind == "FAT32":
        bk = struct.unpack_from("<H", s0, 0x32)[0]
        if not bk or bk == 0xFFFF:
            return kind, "no_backup"
        backup = read(bk * bps, bps)
    elif kind == "exFAT":
        backup = read(12 * bps, bps)
        primary, backup = bytearray(primary), bytearray(backup)
        for b in (primary, backup):                 # VolumeFlags and PercentInUse change at run time
            b[106:108] = b"\0\0"
            b[112] = 0
    else:
        return kind, "no_backup"
    return kind, "same" if bytes(primary) == bytes(backup) else "differ"
