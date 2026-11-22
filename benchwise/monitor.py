"""Live disk temperatures next to the clock.

Every INTERVAL seconds a background thread reads the disks (the same data as Disk Health, so the
same verdict and colours) and the window turns the chosen ones into notification-area icons.
Which disks: the keys in setting "tray_disks" (serial numbers, see ``amdraid.disk_key``).
Disk temperatures need administrator rights; without them the icons show "?".
"""

from __future__ import annotations

import threading
import time

from recoverytool.i18n import t

from . import art, settings
from .diskhealth import amdraid, data, verdict

INTERVAL = 30          # seconds between readings
RAID_EVERY = 2         # the AMD RAID members (a separate process) only every second reading


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


def tooltip(d, res):
    """At most 127 characters (a Windows limit): name and degrees, where it is, health."""
    temp = res["figures"].get("temperature")
    where = (t("dh_member_of", n=d["number"], i=d["member_index"] + 1) if "member_of" in d
             else "Disk %d" % d["number"])
    link = d.get("speed") or d.get("bus") or ""
    lines = ["%s · %s" % (d.get("name") or "?", "%d °C" % temp if temp is not None else t("dh_unknown")),
             " · ".join(x for x in (where, link) if x),
             t("tray_health", level=t("dh_level_" + res["level"]))]
    text = "\n".join(lines)
    return text if len(text) <= 127 else text[:126] + "…"


class Monitor:
    def __init__(self):
        self.latest = {}            # key -> (disk dict, verdict result)
        self.version = 0            # bumps on every finished reading
        self.wake = threading.Event()
        self.stopped = False
        self._members = []
        threading.Thread(target=self._loop, name="temperature-monitor", daemon=True).start()

    def refresh(self):
        self.wake.set()

    def stop(self):
        self.stopped = True
        self.wake.set()

    def _loop(self):
        n = 0
        while not self.stopped:
            if selected():
                try:
                    disks = data.collect()
                    if n % RAID_EVERY == 0:
                        disks = amdraid.attach_members(disks)
                        self._members = [d for d in disks if "member_of" in d]
                    else:                       # reuse the last member readings in between
                        disks = disks + self._members
                    self.latest = {amdraid.disk_key(d): (d, verdict.assess(d)) for d in disks}
                    self.version += 1
                except Exception:               # a failed reading keeps the last icons
                    pass
                n += 1
            self.wake.wait(INTERVAL)
            self.wake.clear()

    def icons(self):
        """Notification icons for the chosen disks, in the order they were chosen."""
        items = []
        for key in selected():
            if key not in self.latest:
                continue
            d, res = self.latest[key]
            temp = res["figures"].get("temperature")
            items.append({"key": key, "image": art.temp_icon(temp, temp_level(d, temp)), "tip": tooltip(d, res)})
        return items
