"""Live temperatures next to the clock: colours, tooltips, disk keys, start flags, icon images.
No administrator rights, and no icon is actually added.

    python tests\\test_tray.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from recoverytool import i18n  # noqa: E402

from benchwise import art, launch, monitor, strings  # noqa: E402,F401
from benchwise.diskhealth import amdraid, verdict  # noqa: E402


def test_levels():
    ssd, hdd = {"media": "SSD"}, {"media": "HDD"}
    assert monitor.temp_level(ssd, 65) == "good" and monitor.temp_level(ssd, 72) == "warning"
    assert monitor.temp_level(ssd, 81) == "bad" and monitor.temp_level(hdd, 50) == "good"
    assert monitor.temp_level(hdd, 56) == "warning" and monitor.temp_level(hdd, 66) == "bad"
    assert monitor.temp_level(hdd, None) == "unknown"


def test_tooltip():
    i18n.set_language("tr")
    d = {"id": "0.1", "number": 0, "member_of": 0, "member_index": 1, "name": "KIOXIA-EXCERIA PLUS G4 SSD" * 3,
         "speed": "NVMe Gen4 x2", "bus": "NVMe", "media": "SSD", "temperature": 39, "smart": []}
    tip = monitor.tooltip(d, verdict.assess(d))
    assert len(tip) <= 127, len(tip)                     # Windows' limit for a notification tooltip
    d2 = dict(d, name="Short", member_of=None)
    d2.pop("member_of")
    tip2 = monitor.tooltip(d2, verdict.assess(d2))
    assert tip2.splitlines()[0] == "Short · 39 °C" and "Disk 0 · NVMe Gen4 x2" in tip2 and "Sağlık:" in tip2, tip2


def test_keys_and_flags():
    assert amdraid.disk_key({"serial": " WD-1 ", "id": 3}) == "sn:WD-1"
    assert amdraid.disk_key({"serial": "", "id": "0.1"}) == "id:0.1"
    assert launch.is_window_start([]) and launch.is_window_start(["--task"])
    assert launch.is_window_start(["--open=disk.health", "--wait"])
    assert not launch.is_window_start(["--list"]) and not launch.is_window_start(["--task", "--disk", "1"])


def test_icons():
    for temp, level in ((42, "good"), (105, "bad"), (None, "unknown")):
        img = art.temp_icon(temp, level)
        assert img.size == (32, 32) and img.mode == "RGBA"
        assert img.getpixel((16, 16))[3] == 255             # opaque tile behind the digits


def test_custom_colours():
    tile = art.temp_icon(40, "good", colors={"good": ("#1565c0", "#ffff00")})
    from collections import Counter
    tile_colour = Counter(p[:3] for p in tile.getdata() if p[3] == 255).most_common(1)[0][0]   # the tile
    assert tile_colour == (0x15, 0x65, 0xC0), tile_colour
    pixels = set(tile.getdata())
    assert any(p[0] > 240 and p[1] > 240 and p[2] < 40 for p in pixels)     # yellow digits are drawn
    broken = art.temp_icon(40, "good", colors={"good": ("not a colour", "#zz")})  # bad values: defaults
    assert broken.size == (32, 32)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("tray tests passed")
