"""Administrator rights, asked for only when a tool needs them.

Windows cannot raise the rights of a running program, so Benchwise starts a second, elevated
copy of itself that opens the tool straight away (``--open=<tool id>``), and the first copy
closes.  The user sees one UAC prompt and lands in the tool they clicked.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def restart_as_admin(open_tool=None):
    """Start Benchwise elevated.  True when the elevated copy is running (the user said yes)."""
    args = (["--open=" + open_tool] if open_tool else []) + ["--wait"]       # this copy is still closing
    if getattr(sys, "frozen", False):
        exe, params, cwd = sys.executable, subprocess.list2cmdline(args), None
    else:                       # from a source checkout: python -m benchwise, in the repository root
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        exe, params, cwd = sys.executable, subprocess.list2cmdline(["-m", "benchwise"] + args), root
    # SW_SHOWNORMAL; ShellExecute returns a value above 32 when the program was started
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, cwd, 1) > 32
