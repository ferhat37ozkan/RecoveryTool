"""Passage from outside the window.

* ``Benchwise-cli.exe --hideme [on|off|status]``: in a terminal, with output.  ``on`` is the default.
* ``Benchwise.exe --hideme [on|off]``: no window; asks for administrator rights once if needed and
  switches Passage in the background.
* ``Benchwise.exe --passage=on|off``: the elevated step the window starts (no output; the window
  follows it through ``passage.read_progress``).
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys


def _self_command(args):
    """(exe, parameters) that start this program again with ``args``."""
    if getattr(sys, "frozen", False):
        return sys.executable, subprocess.list2cmdline(args)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return sys.executable, subprocess.list2cmdline([os.path.join(root, "run.py")] + args)


def start_elevated(on):
    """Start the elevated ``--passage=on|off`` step (one UAC prompt).  True when it was started."""
    exe, params = _self_command(["--passage=" + ("on" if on else "off")])
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 0) > 32


def _mode(args):
    rest = [a.lower() for a in args if a.lower() in ("on", "off", "status")]
    return rest[0] if rest else "on"


def set_autostart(on):
    from . import passage
    try:
        passage.set_tray_autostart(on, passage.exe_for_tray())
    except OSError:
        pass


def window_entry(args):
    """run.py: ``--passage=on|off`` or ``--hideme [on|off]``.  Returns an exit code, or None when
    the arguments are not ours."""
    from . import passage
    first = args[0] if args else ""
    if first.startswith("--passage="):
        on = first.split("=", 1)[1] == "on"
        ok, _ = passage.enable() if on else passage.disable()
        return 0 if ok else 1
    if first == "--hideme":
        on = _mode(args[1:]) != "off"
        set_autostart(on)
        if passage.is_admin():
            ok, _ = passage.enable() if on else passage.disable()
            return 0 if ok else 1
        return 0 if start_elevated(on) else 1
    return None


def cli_entry(args):
    """Benchwise-cli ``--hideme [on|off|status]``: prints the steps and the result."""
    from . import passage
    mode = _mode(args)
    if mode == "status":
        print("%s: %s" % (passage.t("ps_name"), passage.summary()))
        return 0
    if not passage.is_admin():
        print(passage.t("ps_need_admin"), file=sys.stderr)
        print("Benchwise-cli.exe --hideme  (Run as administrator / Yönetici olarak çalıştırın)", file=sys.stderr)
        return 2
    on = mode == "on"
    report = lambda text: print("  " + text, flush=True)
    ok, message = passage.enable(report) if on else passage.disable(report)
    print(message)
    if ok:
        set_autostart(on)
    return 0 if ok else 1
