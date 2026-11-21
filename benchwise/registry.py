"""What the Benchwise window shows: categories and the tools in them.

Adding a tool is one ``Tool`` line here.  A tool without ``view`` is shown as "coming soon".
``view`` is a function ``master -> frame``; it is imported only when the tool is opened, so a
tool that needs a heavy library costs nothing until someone uses it.

``admin=True`` makes the window ask for administrator rights before opening the tool (see
``benchwise.elevate``); the tool itself does not need to deal with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Tool:
    id: str                     # "<category>.<tool>", also used on the command line: --open=disk.recovery
    icon: str                   # name of a drawing in benchwise.art
    admin: bool = False
    view: Optional[Callable] = None

    @property
    def key(self):
        return "tool_" + self.id.split(".", 1)[1]

    @property
    def ready(self):
        return self.view is not None


@dataclass
class Category:
    id: str
    icon: str
    tools: list = field(default_factory=list)

    @property
    def key(self):
        return "cat_" + self.id


def _recovery(master):
    from recoverytool.gui import RecoveryView
    return RecoveryView(master)


CATEGORIES = [
    Category("disk", "disk", [
        Tool("disk.recovery", "recover", admin=True, view=_recovery),
        Tool("disk.health", "pulse", admin=True),
        Tool("disk.surface", "grid", admin=True),
        Tool("disk.repair", "wrench", admin=True),
        Tool("disk.image", "copy", admin=True),
        Tool("disk.partitions", "pie", admin=True),
        Tool("disk.erase", "shred", admin=True),
        Tool("disk.speed", "gauge", admin=True),
    ]),
    Category("system", "chip", [
        Tool("system.sysinfo", "info"),
        Tool("system.memtest", "memory", admin=True),
        Tool("system.crash", "bolt", admin=True),
        Tool("system.stress", "flame"),
    ]),
    Category("power", "battery", [
        Tool("power.battery", "battery"),
        Tool("power.wake", "moon", admin=True),
    ]),
    Category("display", "monitor", [
        Tool("display.pixels", "pixels"),
        Tool("display.keyboard", "keyboard"),
        Tool("display.mouse", "mouse"),
        Tool("display.audio", "speaker"),
        Tool("display.camera", "camera"),
    ]),
    Category("network", "globe", [
        Tool("network.netdiag", "route"),
        Tool("network.netspeed", "gauge"),
        Tool("network.wifi", "wifi"),
        Tool("network.netreset", "refresh", admin=True),
    ]),
    Category("windows", "windows", [
        Tool("windows.sfc", "shield", admin=True),
        Tool("windows.update", "refresh", admin=True),
        Tool("windows.drivers", "chip"),
        Tool("windows.startup", "rocket"),
    ]),
    Category("cleanup", "broom", [
        Tool("cleanup.junk", "broom"),
        Tool("cleanup.dupes", "copy"),
        Tool("cleanup.wipefree", "shred", admin=True),
        Tool("cleanup.space", "pie"),
    ]),
]


def find_tool(tool_id):
    for cat in CATEGORIES:
        for tool in cat.tools:
            if tool.id == tool_id:
                return cat, tool
    return None, None
