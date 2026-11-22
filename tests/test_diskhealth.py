"""Disk Health: SMART parsing and the verdict.  No hardware or administrator rights needed.

    python tests\\test_diskhealth.py
"""

from __future__ import annotations

import base64
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from benchwise.diskhealth import data, verdict  # noqa: E402


def blob(entries, thresholds=False):
    """A 512-byte WMI block: 2 bytes version, then 12-byte entries."""
    b = bytearray(512)
    b[0:2] = b"\x10\x00"
    for i, e in enumerate(entries):
        o = 2 + i * 12
        if thresholds:
            aid, thr = e
            b[o], b[o + 1] = aid, thr
        else:
            aid, cur, worst, raw = e
            b[o] = aid
            b[o + 1:o + 3] = (0x0033).to_bytes(2, "little")
            b[o + 3], b[o + 4] = cur, worst
            b[o + 5:o + 11] = raw.to_bytes(6, "little")
    return bytes(b)


def test_parse():
    d = blob([(5, 100, 100, 24), (9, 90, 90, 12345), (194, 110, 100, 0x0000_2E00_0024), (197, 100, 100, 0)])
    th = blob([(5, 36), (9, 0), (194, 0), (197, 0)], thresholds=True)
    attrs = data.parse_smart(base64.b64encode(d).decode(), base64.b64encode(th).decode())
    by = {a["id"]: a for a in attrs}
    assert [a["id"] for a in attrs] == [5, 9, 194, 197], attrs
    assert by[5]["raw"] == 24 and by[5]["threshold"] == 36 and by[5]["name"] == "Reallocated Sectors Count"
    assert by[9]["raw"] == 12345 and by[9]["current"] == 90
    assert by[5]["flags"] == 0x33
    # temperature lives in the low byte; the rest of the raw value holds min/max
    assert verdict.figures({"smart": attrs})["temperature"] == 0x24
    assert data.parse_smart(None) == [] and data.parse_smart(b"") == []


def test_unknown_is_not_zero():
    usb = data._clean({"number": 3, "bus": "USB", "temperature": 0, "wear": 0, "hours": None, "read_errors": None,
                       "write_errors": None, "smart": None})
    assert usb["temperature"] is None and usb["wear"] is None, usb
    res = verdict.assess(usb)
    assert res["level"] == "unknown" and res["reasons"][0][1] == "no_data_usb", res
    raid = verdict.assess(data._clean({"number": 0, "bus": "RAID", "temperature": 0, "wear": 0, "smart": None}))
    assert raid["level"] == "unknown" and raid["reasons"][0][1] == "no_data_raid", raid  # not AMD: generic text
    # a new SSD really at 0 % wear, with other figures present, keeps its 0
    ssd = data._clean({"number": 1, "bus": "NVMe", "media": "SSD", "temperature": 40, "wear": 0, "hours": 10,
                       "read_errors": 0, "write_errors": 0, "smart": None})
    assert ssd["wear"] == 0 and verdict.assess(ssd)["level"] == "good"


def test_demo_disks():
    os.environ["BENCHWISE_FAKE_HEALTH"] = os.path.join(ROOT, "docs", "demo-health.json")
    disks = {d["number"]: d for d in data.collect()}
    levels = {n: verdict.assess(d)["level"] for n, d in disks.items()}
    assert levels == {0: "good", 1: "warning", 2: "bad", 3: "unknown", 4: "unknown"}, levels
    keys = {r[1] for r in verdict.assess(disks[1])["reasons"]}
    assert keys == {"reallocated", "crc"}, keys
    keys2 = {r[1] for r in verdict.assess(disks[2])["reasons"]}
    assert {"pending", "offline_uncorrectable", "reported_uncorrectable", "reallocated", "health_status"} <= keys2, keys2
    # 312 reallocated sectors is past the warning stage
    assert ("bad", "reallocated", {"n": 312}) in verdict.assess(disks[2])["reasons"]
    assert verdict.attr_state({"id": 199, "current": 200, "threshold": 0, "raw": 3}) == "warning"
    assert verdict.attr_state({"id": 5, "current": 30, "threshold": 36, "raw": 0}) == "bad"
    assert verdict.attr_state({"id": 194, "current": 30, "threshold": 40, "raw": 30}) == ""   # temperature: not judged so


def test_thresholds():
    hot_hdd = {"number": 0, "media": "HDD", "temperature": 58, "hours": 1, "smart": []}
    assert verdict.assess(hot_hdd)["level"] == "warning"
    assert verdict.assess(dict(hot_hdd, media="SSD"))["level"] == "good"      # SSDs run warmer
    assert verdict.assess({"number": 0, "media": "SSD", "wear": 92, "temperature": 40, "smart": []})["level"] == "bad"
    assert verdict.assess({"number": 0, "predict_failure": True, "smart": []})["level"] == "bad"


def nvme_blob(warn=0, kelvin=315, spare=100, spare_thr=5, used=2, cycles=230, hours=1237, unsafe=166, media=0):
    b = bytearray(512)
    b[0] = warn
    b[1:3] = kelvin.to_bytes(2, "little")
    b[3], b[4], b[5] = spare, spare_thr, used
    b[48:64] = (30138973).to_bytes(16, "little")           # data units written (x 512 000 bytes)
    b[112:128] = cycles.to_bytes(16, "little")
    b[128:144] = hours.to_bytes(16, "little")
    b[144:160] = unsafe.to_bytes(16, "little")
    b[160:176] = media.to_bytes(16, "little")
    b[200:202] = kelvin.to_bytes(2, "little")
    return base64.b64encode(bytes(b)).decode()


def test_amd_raid_members():
    from benchwise.diskhealth import amdraid
    h = amdraid.parse_nvme(nvme_blob())
    assert h["temperature"] == 42 and h["used"] == 2 and h["spare"] == 100 and h["hours"] == 1237
    assert h["power_cycles"] == 230 and h["unsafe_shutdowns"] == 166 and h["sensors"] == [42]
    assert round(h["data_written"] / 1e12, 1) == 15.4
    assert amdraid.parse_nvme(base64.b64encode(bytes(512)).decode()) is None      # empty block: no data

    array = data._clean({"number": 0, "name": "AMD-RAID Array 1", "bus": "RAID", "media": "SSD", "temperature": 0,
                         "wear": 0, "smart": None, "system": True})
    array["id"] = 0
    assert amdraid.is_amd_raid(array)
    m0 = amdraid.member_disk(array, {"index": 0, "model": "SSD A", "nvme": True, "ssd": True, "size": 2 * 10 ** 12,
                                     "smart": nvme_blob()})
    m1 = amdraid.member_disk(array, {"index": 1, "model": "SSD B", "nvme": True, "ssd": True, "size": 2 * 10 ** 12,
                                     "smart": nvme_blob(media=3, kelvin=350)})
    assert m0["id"] == "0.0" and m0["temperature"] == 42 and m0["wear"] == 2 and m0["bus"] == "NVMe"
    r0 = verdict.assess(m0)
    assert r0["level"] == "good" and ("info", "nvme_unsafe", {"n": 166, "of": 230}) in r0["reasons"], r0
    r1 = verdict.assess(m1)
    assert r1["level"] == "bad" and {"nvme_media_errors", "hot"} <= {r[1] for r in r1["reasons"]}, r1
    # the array is as bad as its worst member, and says which one
    array["members"] = [m0, m1]
    ra = verdict.assess(array)
    assert ra["level"] == "bad" and ra["reasons"][0] == ("bad", "raid_member_bad", {"name": "SSD B", "n": 2}), ra
    # critical warning bits from the SSD itself
    assert verdict.assess(dict(m0, nvme=amdraid.parse_nvme(nvme_blob(warn=0x08))))["level"] == "bad"
    assert verdict.assess(dict(m0, nvme=amdraid.parse_nvme(nvme_blob(spare=4))))["level"] == "bad"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("disk health tests passed")
