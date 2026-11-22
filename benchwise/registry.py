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


def _tool(module):
    """A tool in benchwise.tools.<module> (its View class), imported when opened.  The build collects
    every module of benchwise.tools (build.ps1: --collect-submodules), so the import works in the exe."""
    def make(master):
        import importlib
        return importlib.import_module("benchwise.tools." + module).View(master)
    return make


def _health(master):
    from .diskhealth.view import DiskHealthView
    return DiskHealthView(master)


CATEGORIES = [
    Category("disk", "disk", [
        Tool("disk.recovery", "recover", admin=True, view=_recovery),
        Tool("disk.health", "pulse", admin=True, view=_health),
        Tool("disk.surface", "grid", admin=True),
        Tool("disk.repair", "wrench", admin=True),
        Tool("disk.image", "copy", admin=True),
        Tool("disk.partitions", "pie", admin=True),
        Tool("disk.erase", "shred", admin=True),
        Tool("disk.speed", "gauge", admin=True),
    ]),
    Category("system", "chip", [
        Tool("system.sysinfo", "info", view=_tool("sysinfo")),
        Tool("system.memtest", "memory", admin=True, view=_tool("memtest")),
        Tool("system.crash", "bolt", admin=True, view=_tool("crash")),
        Tool("system.stress", "flame", view=_tool("stress")),
    ]),
    Category("power", "battery", [
        Tool("power.battery", "battery", view=_tool("battery")),
        Tool("power.wake", "moon", admin=True, view=_tool("wake")),
    ]),
    Category("display", "monitor", [
        Tool("display.pixels", "pixels", view=_tool("pixels")),
        Tool("display.keyboard", "keyboard", view=_tool("keyboard")),
        Tool("display.mouse", "mouse", view=_tool("mouse")),
        Tool("display.audio", "speaker", view=_tool("audio")),
        Tool("display.camera", "camera", view=_tool("camera")),
    ]),
    Category("network", "globe", [
        Tool("network.netdiag", "route", view=_tool("netdiag")),
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
