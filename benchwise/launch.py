"""How the Benchwise window starts (shared by run.py and ``python -m benchwise``).

Window flags:  --open=<tool id>  open a tool at once
               --task            started by the live-monitoring task (hidden unless a click asked)
               --wait            a copy that is just closing may still hold the single-instance lock
               --tray            started at sign-in because Passage is on: hidden, only next to the clock
"""

from __future__ import annotations

import sys


def is_window_start(args):
    return all(a.startswith("--open=") or a in ("--task", "--wait", "--tray") for a in args)


def run_window(args):
    from . import elevate, instance, livemode
    open_tool = next((a.split("=", 1)[1] for a in args if a.startswith("--open=")), None)
    task = "--task" in args
    hidden = "--tray" in args
    if task:
        show, wanted = livemode.take_show_flag()
        hidden = not show
        open_tool = open_tool or wanted
    if not instance.acquire(wait=8 if (task or "--wait" in args) else 0):
        if not hidden:
            instance.signal_show()              # Benchwise is already running: bring it to the front
        return 0                                # (two sign-in starts: the first one is enough)
    if hidden:
        from . import monitor, passage
        if not monitor.selected() and not passage.is_on():
            return 0                            # started with Windows but nothing to show next to the clock
        if "--tray" in args and not elevate.is_admin() and livemode.supported() and livemode.points_here():
            # live mode is on: the elevated copy (which can read temperatures) sits next to the clock
            instance.release()
            if livemode.start_elevated(show=False):
                return 0
            instance.acquire()
    elif livemode.supported():
        cmd = livemode.task_command()                   # None: live mode is off
        if cmd is not None and elevate.is_admin():
            try:
                livemode.repoint()                      # a copy in another folder: the task now starts us
            except Exception:
                pass
        elif cmd is not None:
            instance.release()
            if livemode.points_here(cmd):
                # live mode: run elevated through the task instead of as a standard copy (no UAC prompt)
                if livemode.start_elevated(show=True, open_tool=open_tool):
                    return 0
            elif elevate.restart_as_admin(open_tool):
                # the task starts another copy of Benchwise (e.g. an older one in another folder):
                # one UAC prompt, and that elevated start moves the task over to this exe
                return 0
            instance.acquire()
    from .shell import main
    main(open_tool=open_tool, hidden=hidden)
    return 0


if __name__ == "__main__":
    sys.exit(run_window(sys.argv[1:]))
