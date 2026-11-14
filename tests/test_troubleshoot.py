"""Unit tests for the disk layout and the troubleshooter. They use the made-up disk list in
docs/demo-disks.json; no disk is queried.

    python tests\\test_troubleshoot.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["RECOVERYTOOL_FAKE_DISKS"] = os.path.join(ROOT, "docs", "demo-disks.json")

from recoverytool import disks, i18n, troubleshoot  # noqa: E402


def keys(findings):
    return [(f["level"], f["key"], f["action"]) for f in findings]


def main():
    all_disks = {d["number"]: d for d in disks.list_disks()}

    # layout: partitions in order, with the unallocated tail of the external disk
    rows = disks.layout(all_disks[1])
    assert [r["kind"] for r in rows] == ["partition", "partition", "partition", "gap"], rows
    assert rows[-1]["offset"] == 859011284992 + 644245094400
    assert rows[-1]["offset"] + rows[-1]["size"] == all_disks[1]["size"]
    assert [r["kind"] for r in disks.layout(all_disks[0])] == ["partition"] * 4        # no real gaps
    assert disks.layout(all_disks[4]) == []

    # system disk: healthy, and its hidden system partitions are not reported as "no letter"
    assert keys(troubleshoot.diagnose(all_disks[0])) == [("ok", "healthy", None)]

    # external disk: a RAW partition and a large unallocated stretch
    got = keys(troubleshoot.diagnose(all_disks[1]))
    assert ("error", "partition_raw", "recover_region") in got, got
    assert ("info", "unallocated", "recover_region") in got, got
    raw = [f for f in troubleshoot.diagnose(all_disks[1]) if f["key"] == "partition_raw"][0]
    assert raw["region"]["offset"] == 17825792 and raw["region"]["filesystem"] == ""

    # stick with a good filesystem but no drive letter
    assert ("info", "no_letter", "assign_letter") in keys(troubleshoot.diagnose(all_disks[2]))

    # write-protected stick
    assert ("warning", "readonly", "clear_readonly") in keys(troubleshoot.diagnose(all_disks[3]))

    # dead stick: one finding, no action offered, nothing else claimed
    assert keys(troubleshoot.diagnose(all_disks[4])) == [("error", "no_media", None)]

    # reliability counters
    got = keys(troubleshoot.diagnose(all_disks[2], {"health": "Warning", "read_errors": 12, "wear": 95, "temperature": 71}))
    for expected in (("error", "unhealthy", "recover"), ("error", "io_errors", "recover"),
                     ("warning", "worn", None), ("warning", "hot", None)):
        assert expected in got, (expected, got)

    # every finding has both texts in both languages, and they format with the finding's values
    for lang in ("en", "tr"):
        i18n.set_language(lang)
        for d in all_disks.values():
            for f in troubleshoot.diagnose(d, {"health": "Warning", "read_errors": 3, "wear": 99, "temperature": 65}):
                for key in ("ts_" + f["key"], "ts_" + f["key"] + "_d"):
                    assert key in i18n.STRINGS, key
                    assert i18n.t(key, **f["args"])
                if f["action"]:
                    assert "b_" + f["action"] in i18n.STRINGS, f["action"]

    # demo mode refuses every operation
    assert disks.set_offline(1, True) == (False, "demo mode: no disk is touched")
    assert disks.set_readonly(3, False)[0] is False
    assert disks.assign_letter(2, all_disks[2]["partitions"][0], "K")[0] is False
    print("troubleshooter tests passed")


if __name__ == "__main__":
    main()
