"""How the Benchwise window starts (shared by run.py and ``python -m benchwise``).

Window flags:  --open=<tool id>  open a tool at once
               --task            started by the live-monitoring task (hidden unless a click asked)
               --wait            a copy that is just closing may still hold the single-instance lock
"""

from __future__ import annotations

import sys


def is_window_start(args):
    return all(a.startswith("--open=") or a in ("--task", "--wait") for a in args)


def run_window(args):
    from . import elevate, instance, livemode
    open_tool = next((a.split("=", 1)[1] for a in args if a.startswith("--open=")), None)
    task = "--task" in args
    if not instance.acquire(wait=8 if (task or "--wait" in args) else 0):
        instance.signal_show()                  # Benchwise is already running: bring it to the front
        return 0
    hidden = False
    if task:
        show, wanted = livemode.take_show_flag()
        hidden = not show
        open_tool = open_tool or wanted
        from . import monitor
        if hidden and not monitor.selected():
            return 0                            # started with Windows but no disk is watched: nothing to do
    elif not elevate.is_admin() and livemode.supported() and livemode.enabled():
        # live mode: run elevated through the task instead of as a standard copy (no UAC prompt)
        instance.release()
        if livemode.start_elevated(show=True, open_tool=open_tool):
            return 0
        instance.acquire()
    from .shell import main
    main(open_tool=open_tool, hidden=hidden)
    return 0


if __name__ == "__main__":
    sys.exit(run_window(sys.argv[1:]))
