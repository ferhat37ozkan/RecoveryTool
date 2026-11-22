"""Live disk temperatures next to the clock.

Two speeds:
* temperatures every ``interval()`` seconds (setting "tray_interval", 15 s by default) from two
  readers that stay open: one PowerShell for the disks Windows sees (``data.TempReader``) and the
  AMD RAID helper for the disks inside an array (``amdraid.watch``);
* the full health reading (SMART, verdict, health %) every FULL seconds, or when asked.
Which disks: the keys in setting "tray_disks" (serial numbers, see ``amdraid.disk_key``).
Disk temperatures need administrator rights; without them the icons show "?".
"""

from __future__ import annotations

import threading
import time

from recoverytool.i18n import t

from . import art, settings
from .diskhealth import amdraid, data, verdict

FULL = 300              # seconds between full health readings
INTERVALS = (5, 15, 30, 60)
DEFAULT_INTERVAL = 15


def interval():
    value = settings.get("tray_interval", DEFAULT_INTERVAL)
    return value if value in INTERVALS else DEFAULT_INTERVAL


LEVELS = ("good", "warning", "bad")


def colors():
    """{level: (tile, digits)} as the user chose them (Disk Health > icon colours); defaults otherwise."""
    chosen = settings.get("tray_colors", {}) or {}
    out = {}
    for level, (bg, fg) in art.TEMP_COLORS.items():
        c = chosen.get(level) or {}
        out[level] = (c.get("bg") or bg, c.get("fg") or fg)
    return out


def set_color(level, part, value):
    chosen = dict(settings.get("tray_colors", {}) or {})
    entry = dict(chosen.get(level) or {})
    entry[part] = value
    chosen[level] = entry
    settings.put("tray_colors", chosen)


def reset_colors():
    settings.put("tray_colors", {})


def selected():
    return list(settings.get("tray_disks", []))


def set_selected(keys):
    settings.put("tray_disks", list(dict.fromkeys(keys)))


def temp_level(d, temp):
    """Colour of the number: the same limits as the verdict (SSDs run warmer than hard disks)."""
    if temp is None:
        return "unknown"
    ssd = d.get("media") == "SSD" or d.get("bus") == "NVMe"
    hot = 70 if ssd else 55
    return "bad" if temp >= hot + 10 else "warning" if temp >= hot else "good"


def tooltip(d, res, health=None):
    """At most 127 characters (a Windows limit): name and degrees, where it is, health."""
    temp = res["figures"].get("temperature")
    where = (t("dh_member_of", n=d["number"], i=d["member_index"] + 1) if "member_of" in d
             else "Disk %d" % d["number"])
    link = d.get("speed") or d.get("bus") or ""
    level = t("dh_level_" + res["level"])
    lines = ["%s · %s" % (d.get("name") or "?", "%d °C" % temp if temp is not None else t("dh_unknown")),
             " · ".join(x for x in (where, link) if x),
             t("tray_health_pct", pct=health, level=level) if health is not None else t("tray_health", level=level)]
    text = "\n".join(lines)
    return text if len(text) <= 127 else text[:126] + "…"


class Monitor:
    def __init__(self):
        self.latest = {}            # key -> (disk dict, verdict result, health %)
        self.version = 0            # bumps on every update of the figures
        self.wake = threading.Event()
        self.full_due = 0.0
        self.stopped = False
        self.reader = None
        self.watcher = None
        self.disks = []             # last full reading (array members included)
        threading.Thread(target=self._loop, name="temperature-monitor", daemon=True).start()

    def refresh(self):
        """Read everything now (the chosen disks or the interval changed)."""
        self.full_due = 0.0
        self.wake.set()

    def stop(self):
        self.stopped = True
        self.wake.set()
        if self.reader is not None:
            self.reader.stop()      # the AMD helper is never stopped from outside: it ends with us

    # -- background thread ----------------------------------------------------------------------
    def _loop(self):
        while not self.stopped:
            if selected():
                step = interval()
                try:
                    if time.time() >= self.full_due:
                        self._full(step)
                        self.full_due = time.time() + FULL
                    else:
                        self._temps(step)
                except Exception:               # a failed reading keeps the last icons
                    pass
            self.wake.wait(interval())
            self.wake.clear()

    def _members(self, array, step, wait=0.0):
        """Member disks of an AMD RAID array from the watching helper (started when needed)."""
        if not (amdraid.supported() and amdraid.installed()):
            return []
        self.watcher = amdraid.watch(step)
        deadline = time.time() + wait
        got = self.watcher.latest()
        while got is None and time.time() < deadline and self.watcher.alive():
            time.sleep(0.5)
            got = self.watcher.latest()
        if not got or got[1]:
            return []
        return [amdraid.member_disk(array, m) for m in got[0]]

    def _full(self, step):
        disks = data.collect()
        out = []
        for d in disks:
            out.append(d)
            if amdraid.is_amd_raid(d):
                members = self._members(d, step, wait=15)
                if members:
                    d["members"] = members
                    out += members
        self.disks = out
        if self.reader is None:
            self.reader = data.TempReader(step)
        self._publish(out)

    def _temps(self, step):
        if self.reader is not None:
            self.reader.set_interval(step)
        for d in self.disks:
            if "member_of" in d:
                continue
            if self.reader is not None and self.reader.time and d["number"] in self.reader.temps:
                d["temperature"] = self.reader.temps[d["number"]]
            if d.get("members"):
                fresh = self._members(d, step)
                if fresh:
                    by_index = {m["member_index"]: m for m in fresh}
                    d["members"] = [by_index.get(m["member_index"], m) for m in d["members"]]
        self.disks = [x for d in self.disks if "member_of" not in d for x in [d] + (d.get("members") or [])]
        self._publish(self.disks)

    def _publish(self, disks):
        latest = {}
        for d in disks:
            res = verdict.assess(d)
            latest[amdraid.disk_key(d)] = (d, res, verdict.health_percent(d, res))
        self.latest = latest
        self.version += 1

    # -- for the window -------------------------------------------------------------------------
    def icons(self):
        """Notification icons for the chosen disks, in the order they were chosen."""
        items = []
        palette = colors()
        for key in selected():
            if key not in self.latest:
                continue
            d, res, health = self.latest[key]
            temp = res["figures"].get("temperature")
            items.append({"key": key, "image": art.temp_icon(temp, temp_level(d, temp), colors=palette),
                          "tip": tooltip(d, res, health)})
        return items
