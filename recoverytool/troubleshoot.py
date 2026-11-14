"""Disk troubleshooter: look at what Windows reports about a disk and say, in plain words,
what is wrong, whether software can fix it, and how.

``diagnose`` is pure: it works on the dictionaries from ``disks.list_disks()`` and
``disks.health()`` and touches nothing.  Each finding is a dict:

    level   "error" | "warning" | "info" | "ok"
    key     message id; the texts are ``ts_<key>`` (title) and ``ts_<key>_d`` (explanation)
    args    values for the texts
    action  None, or one of
              "online", "clear_readonly"     fixes a disk state
              "assign_letter", "check"       act on ``part``
              "recover", "recover_region"    select the disk / ``region`` for recovery
    part / region   what the action applies to
"""

from __future__ import annotations

from . import disks
from .model import human_size

SYSTEM_TYPES = {"System", "Reserved", "Recovery", "Unknown"}


def is_data_partition(p):
    return p.get("type") not in SYSTEM_TYPES


def diagnose(disk, health=None):
    out = []

    def add(level, key, action=None, **kw):
        item = {"level": level, "key": key, "action": action, "args": {}}
        for name in ("part", "region"):
            if name in kw:
                item[name] = kw.pop(name)
        item["args"] = kw
        out.append(item)

    health = health or {}
    no_media = disk["size"] == 0 or "No Media" in (disk.get("status") or "")
    if no_media:
        add("error", "no_media")
        return out                              # nothing else can be said about a disk that shows no storage
    if disk.get("offline"):
        add("warning", "offline", "online")
    if disk.get("readonly") and not disk.get("system"):
        add("warning", "readonly", "clear_readonly")
    if (disk.get("health") or "Healthy") != "Healthy" or (health.get("health") or "Healthy") != "Healthy":
        add("error", "unhealthy", "recover", state=health.get("health") or disk.get("health"))
    if (health.get("read_errors") or 0) > 0 or (health.get("write_errors") or 0) > 0:
        add("error", "io_errors", "recover", n=(health.get("read_errors") or 0) + (health.get("write_errors") or 0))
    if (health.get("wear") or 0) >= 90:
        add("warning", "worn", wear=health["wear"])
    if (health.get("temperature") or 0) >= 60:
        add("warning", "hot", temp=health["temperature"])

    if disk.get("style") == "RAW" and not disk["partitions"]:
        add("error", "no_partition_table", "recover")
    for p in disk["partitions"]:
        if not is_data_partition(p):
            continue
        name = "%s%s" % ((p["letter"] + ": ") if p.get("letter") else "", human_size(p["size"]))
        region = {"offset": p["offset"], "size": p["size"], "filesystem": p.get("filesystem") or "",
                  "label": "partition %d" % p["number"]}
        if not p.get("filesystem"):
            add("error", "partition_raw", "recover_region", part=p, region=region, name=name, n=p["number"])
            continue
        if (p.get("health") or "Healthy") != "Healthy":
            add("warning", "volume_unhealthy", "check", part=p, name=name, n=p["number"], state=p.get("health"))
        if not p.get("letter") and not p.get("hidden") and not disk.get("offline"):
            add("info", "no_letter", "assign_letter", part=p, name=name, n=p["number"], fs=p["filesystem"])
    for row in disks.layout(disk):
        if row["kind"] == "gap" and row["size"] >= max(256 << 20, disk["size"] // 100):
            add("info", "unallocated", "recover_region", size=human_size(row["size"]),
                region={"offset": row["offset"], "size": row["size"], "filesystem": "", "label": "unallocated"})
    if not any(f["level"] in ("error", "warning") for f in out):
        out.insert(0, {"level": "ok", "key": "healthy", "action": None, "args": {}})
    return out
