"""Passage from outside the window.

* ``Benchwise-cli.exe --hideme [on|off|repair|status]``: in a terminal, with output.  ``on`` is the default.
* ``Benchwise.exe --hideme [on|off]``: no window; asks for administrator rights once if needed and
  switches Passage in the background.
* ``Benchwise.exe --passage=on|off|repair``: the elevated step the window starts (no output; the window
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
    """Start the elevated ``--passage=on|off|repair`` step (one UAC prompt).  ``on`` is True, False
    or "repair".  True when it was started."""
    mode = on if isinstance(on, str) else ("on" if on else "off")
    exe, params = _self_command(["--passage=" + mode])
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 0) > 32


def _mode(args):
    rest = [a.lower() for a in args if a.lower() in ("on", "off", "repair", "status")]
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
        mode = first.split("=", 1)[1]
        if mode == "repair":
            ok, _ = passage.repair()
        else:
            ok, _ = passage.enable() if mode == "on" else passage.disable()
        return 0 if ok else 1
    if first == "--hideme":
        mode = _mode(args[1:])
        if mode == "repair":
            if passage.is_admin():
                return 0 if passage.repair()[0] else 1
            return 0 if start_elevated("repair") else 1
        on = mode != "off"
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
        for p in passage.problems():
            print("  ! " + passage.t("ps_problem_" + p))
        return 0
    if not passage.is_admin():
        print(passage.t("ps_need_admin"), file=sys.stderr)
        print("Benchwise-cli.exe --hideme  (Run as administrator / Yönetici olarak çalıştırın)", file=sys.stderr)
        return 2
    report = lambda text: print("  " + text, flush=True)
    if mode == "repair":
        ok, message = passage.repair(report)
        print(message)
        return 0 if ok else 1
    on = mode == "on"
    ok, message = passage.enable(report) if on else passage.disable(report)
    print(message)
    if ok:
        set_autostart(on)
    return 0 if ok else 1
