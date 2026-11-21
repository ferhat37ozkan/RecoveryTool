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
    assert raid["level"] == "unknown" and raid["reasons"][0][1] == "no_data_raid", raid
    # a new SSD really at 0 % wear, with other figures present, keeps its 0
    ssd = data._clean({"number": 1, "bus": "NVMe", "media": "SSD", "temperature": 40, "wear": 0, "hours": 10,
                       "read_errors": 0, "write_errors": 0, "smart": None})
    assert ssd["wear"] == 0 and verdict.assess(ssd)["level"] == "good"


def test_demo_disks():
    os.environ["BENCHWISE_FAKE_HEALTH"] = os.path.join(ROOT, "docs", "demo-health.json")
    disks = {d["number"]: d for d in data.collect()}
    levels = {n: verdict.assess(d)["level"] for n, d in disks.items()}
    assert levels == {0: "good", 1: "warning", 2: "bad", 3: "unknown"}, levels
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("disk health tests passed")
