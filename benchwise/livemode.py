"""Live monitoring mode: Benchwise always runs with administrator rights, asked for once.

Disk temperatures are only given to administrators, so watching them next to the clock needs
Benchwise to run elevated all the time.  With the user's one-time consent a Windows Task
Scheduler task is registered ("run with highest privileges"):

* if the user also chose "start with Windows", at sign-in it starts Benchwise in the background
  (``--task``: no window, only the icons next to the clock; a click on one brings the window);
* a normal double click on Benchwise starts that task instead of a standard copy, so Benchwise
  opens elevated without a UAC prompt (a small flag file says "show the window this time").

Switching the mode off deletes the task.  Only for the built exe.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from xml.sax.saxutils import escape

from . import settings

TASK = "Benchwise"
FLAG = "show.flag"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def supported():
    return bool(getattr(sys, "frozen", False))


def _schtasks(*args, timeout=30):
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, timeout=timeout,
                          creationflags=_NO_WINDOW)


def task_command():
    """The exe the task starts, or None when there is no task."""
    p = _schtasks("/Query", "/TN", TASK, "/XML")
    if p.returncode != 0:
        return None
    out = p.stdout
    a, b = out.find("<Command>"), out.find("</Command>")
    return out[a + 9:b].strip().strip('"') if a >= 0 and b > a else ""


def enabled():
    return supported() and task_command() is not None


def autostart():
    """Is the sign-in trigger of the task switched on?"""
    p = _schtasks("/Query", "/TN", TASK, "/XML")
    if p.returncode != 0:
        return False
    out = p.stdout
    a = out.find("<LogonTrigger>")
    # exported XML leaves out default values: an enabled trigger has no <Enabled> line at all
    return a >= 0 and "<Enabled>false</Enabled>" not in out[a:out.find("</LogonTrigger>", a)]


def enable(start_with_windows=True):
    """Register the task (needs administrator rights).  Raises RuntimeError with the reason."""
    exe = os.path.abspath(sys.executable)
    user = "%s\\%s" % (os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", ""))
    xml = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Author>Benchwise</Author>
    <Description>Benchwise live disk temperatures next to the clock. Runs Benchwise with administrator rights without asking; remove it from Benchwise (Disk Health) or here.</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>%(auto)s</Enabled><UserId>%(user)s</UserId><Delay>PT10S</Delay></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>%(user)s</UserId><LogonType>InteractiveToken</LogonType>
    <RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>false</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit><Priority>7</Priority></Settings>
  <Actions Context="Author"><Exec><Command>"%(exe)s"</Command><Arguments>--task</Arguments>
    <WorkingDirectory>%(dir)s</WorkingDirectory></Exec></Actions>
</Task>
""" % {"user": escape(user), "exe": escape(exe), "dir": escape(os.path.dirname(exe)),
       "auto": "true" if start_with_windows else "false"}
    fd, path = tempfile.mkstemp(prefix="benchwise-task-", suffix=".xml")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-16") as f:
            f.write(xml)
        p = _schtasks("/Create", "/TN", TASK, "/XML", path, "/F")
        if p.returncode != 0:
            raise RuntimeError((p.stderr or p.stdout).strip() or "schtasks failed")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def disable():
    p = _schtasks("/Delete", "/TN", TASK, "/F")
    if p.returncode != 0 and task_command() is not None:
        raise RuntimeError((p.stderr or p.stdout).strip() or "schtasks failed")


def start_elevated(show=True, open_tool=None):
    """Start Benchwise through the task (elevated, no prompt).  True when it was started."""
    if show:
        with open(os.path.join(settings.folder(), FLAG), "w") as f:
            f.write("%s|%s" % (time.time(), open_tool or ""))
    return _schtasks("/Run", "/TN", TASK).returncode == 0


def take_show_flag(max_age=60):
    """``(show, tool)``: did a double click ask this task-started copy to show its window (and a tool)?"""
    path = os.path.join(settings.folder(), FLAG)
    try:
        with open(path) as f:
            when, _, tool = f.read().strip().partition("|")
        os.remove(path)
        if time.time() - float(when or 0) < max_age:
            return True, tool or None
    except (OSError, ValueError):
        pass
    return False, None
