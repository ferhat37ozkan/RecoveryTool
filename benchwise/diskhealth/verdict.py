"""From numbers to a verdict a non-technical person can act on.  Pure: works on ``data.collect``.

    level   "bad"      at risk: copy your data off now
            "warning"  watch it: early signs, or a condition to fix (heat)
            "good"     nothing worrying in what the disk reports
            "unknown"  the disk (or its USB enclosure / RAID controller) reports nothing useful

Each reason is ``(level, key, args)``; texts are ``dh_r_<key>`` in the translation table.
The thresholds follow what drive makers and long-running field studies agree on: any pending or
uncorrectable sector is serious, a few reallocated sectors are a warning that tends to grow, CRC
errors are almost always the cable, and an attribute at or below its threshold means the disk
itself predicts failure.
"""

from __future__ import annotations

ORDER = {"unknown": 0, "good": 1, "warning": 2, "bad": 3}

# ATA attributes that matter for the verdict, and how
CRITICAL_ZERO = {197: "pending", 198: "offline_uncorrectable", 187: "reported_uncorrectable", 184: "end_to_end",
                 10: "spin_retry"}     # anything above zero is bad
REALLOCATED = (5, 196)
TEMP_IDS = (194, 190)
HOURS_ID = 9
LIFE_IDS = (231, 232, 233, 202, 169)   # "percent life left" style attributes (normalised value = % left)


def raw32(a):
    return a["raw"] & 0xFFFFFFFF


def attr(disk, aid):
    return next((a for a in disk.get("smart") or () if a["id"] == aid), None)


def figures(disk):
    """The headline numbers, from whichever source has them.  None means not reported."""
    temp = disk.get("temperature")
    if temp is None:
        for aid in TEMP_IDS:
            a = attr(disk, aid)
            if a and 0 < (a["raw"] & 0xFF) < 120:
                temp = a["raw"] & 0xFF
                break
    hours = disk.get("hours")
    if hours is None and attr(disk, HOURS_ID):
        hours = raw32(attr(disk, HOURS_ID))
    wear = disk.get("wear")
    if wear is None:
        for aid in LIFE_IDS:
            a = attr(disk, aid)
            if a and 0 < a["current"] <= 100:
                wear = 100 - a["current"]
                break
    realloc = raw32(attr(disk, 5)) if attr(disk, 5) else None
    pending = raw32(attr(disk, 197)) if attr(disk, 197) else None
    nv = disk.get("nvme") or {}
    return {"temperature": temp, "hours": hours, "wear": wear, "reallocated": realloc, "pending": pending,
            "read_errors": disk.get("read_errors"), "write_errors": disk.get("write_errors"),
            "power_cycles": raw32(attr(disk, 12)) if attr(disk, 12) else disk.get("start_stop"),
            "spare": nv.get("spare"), "written": nv.get("data_written"), "media_errors": nv.get("media_errors"),
            "unsafe": nv.get("unsafe_shutdowns")}


# NVMe "critical warning" bits (NVMe base specification, SMART / Health log byte 0)
NVME_WARNINGS = ((0x01, "bad", "nvme_spare_low"), (0x02, "warning", "nvme_temp_warn"), (0x04, "bad", "nvme_degraded"),
                 (0x08, "bad", "nvme_readonly"), (0x10, "warning", "nvme_backup_failed"))


def assess_array(disk):
    """A RAID array whose member disks could be read: as bad as its worst member."""
    results = [assess(m) for m in disk["members"]]
    level = max((r["level"] for r in results), key=ORDER.get) if results else "unknown"
    reasons = [("info", "raid_members", {"n": len(results)})]
    worst = [(m, r) for m, r in zip(disk["members"], results) if r["level"] == level and level in ("bad", "warning")]
    for m, r in worst:
        reasons.insert(0, (level, "raid_member_" + level, {"name": m["name"], "n": m["member_index"] + 1}))
    return {"level": level, "reasons": reasons, "figures": figures(disk)}


def assess(disk):
    if disk.get("members"):
        return assess_array(disk)
    reasons = []

    def add(level, key, **args):
        reasons.append((level, key, args))

    f = figures(disk)
    ssd = disk.get("media") == "SSD" or disk.get("bus") == "NVMe"
    if disk.get("predict_failure"):
        add("bad", "predict_failure")
    if disk.get("health") and disk["health"] not in ("Healthy",):
        add("bad" if disk["health"] == "Unhealthy" else "warning", "health_status", state=disk["health"])
    # (the view translates ``state``)
    for a in disk.get("smart") or ():
        if a.get("threshold") and a["current"] <= a["threshold"] and a["id"] not in (194, 190):
            add("bad", "below_threshold", name=a["name"], id=a["id"], value=a["current"], threshold=a["threshold"])
    for aid, key in CRITICAL_ZERO.items():
        a = attr(disk, aid)
        if a and raw32(a) > 0:
            add("bad", key, n=raw32(a))
    for aid in REALLOCATED:
        a = attr(disk, aid)
        if a and raw32(a) > 0:
            add("bad" if raw32(a) >= 100 else "warning", "reallocated", n=raw32(a))
            break
    a = attr(disk, 199)
    if a and raw32(a) > 0:
        add("warning", "crc", n=raw32(a))
    nv = disk.get("nvme")
    if nv:
        seen = set()
        for bit, level, key in NVME_WARNINGS:
            if nv["critical_warning"] & bit:
                add(level, key)
                seen.add(key)
        if nv["spare_threshold"] and nv["spare"] <= nv["spare_threshold"] and "nvme_spare_low" not in seen:
            add("bad", "nvme_spare_low")
        if nv["media_errors"]:
            add("bad", "nvme_media_errors", n=nv["media_errors"])
        if nv["critical_temp_minutes"]:
            add("warning", "nvme_overheated", n=nv["critical_temp_minutes"])
    errors = (f["read_errors"] or 0) + (f["write_errors"] or 0)
    if errors:
        add("bad", "io_errors", n=errors)
    if f["wear"] is not None:
        if f["wear"] >= 90:
            add("bad", "worn", wear=f["wear"])
        elif f["wear"] >= 70:
            add("warning", "wearing", wear=f["wear"])
    if f["temperature"] is not None:
        hot = 70 if ssd else 55
        if f["temperature"] >= hot + 10:
            add("bad", "too_hot", temp=f["temperature"])
        elif f["temperature"] >= hot:
            add("warning", "hot", temp=f["temperature"])

    known = any(v is not None for v in f.values()) or bool(disk.get("smart")) or disk.get("predict_failure") is not None
    if reasons:
        level = max((r[0] for r in reasons), key=ORDER.get)
    elif known:
        level = "good"
    else:
        level = "unknown"
        amd = disk.get("bus") == "RAID" and "AMD-RAID" in (disk.get("name") or "").upper()
        add("unknown", "no_data_amd_raid" if amd else "no_data_raid" if disk.get("bus") == "RAID" else
            "no_data_usb" if disk.get("bus") == "USB" else "no_data")
    if level == "good":
        add("good", "all_good")
    if nv and nv["power_cycles"] and nv["unsafe_shutdowns"] >= 10 and nv["unsafe_shutdowns"] >= 0.3 * nv["power_cycles"]:
        add("info", "nvme_unsafe", n=nv["unsafe_shutdowns"], of=nv["power_cycles"])
    if level in ("good", "warning") and known and not disk.get("smart") and not ssd and disk.get("bus") != "NVMe":
        add("info", "no_smart_table")
    reasons.sort(key=lambda r: -ORDER.get(r[0], 0))
    return {"level": level, "reasons": reasons, "figures": f}


def attr_state(a):
    """Colour of one SMART table row: "bad", "warning" or "" (fine / not judged)."""
    if a.get("threshold") and a["current"] <= a["threshold"] and a["id"] not in (194, 190):
        return "bad"
    if a["id"] in CRITICAL_ZERO and raw32(a) > 0:
        return "bad"
    if a["id"] in REALLOCATED and raw32(a) > 0:
        return "bad" if raw32(a) >= 100 else "warning"
    if a["id"] == 199 and raw32(a) > 0:
        return "warning"
    return ""
