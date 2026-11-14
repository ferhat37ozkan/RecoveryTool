"""Enumerate physical disks the way Disk Management does, and lock/unlock them.

Every disk known to Windows is listed - including disks without a drive letter, offline
disks and disks with no recognisable (RAW) filesystem.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess

_LIST_SCRIPT = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'
$disks = Get-Disk | Sort-Object Number | ForEach-Object {
  $n = $_.Number
  $parts = @(Get-Partition -DiskNumber $n | Sort-Object Offset | ForEach-Object {
    $v = $_ | Get-Volume
    $l = [string]$_.DriveLetter; if ($l -notmatch '^[A-Za-z]$') { $l = '' }
    [pscustomobject]@{ number = $_.PartitionNumber; letter = $l; size = [int64]$_.Size
      offset = [int64]$_.Offset; type = [string]$_.Type
      filesystem = [string]$v.FileSystem; label = [string]$v.FileSystemLabel }
  })
  [pscustomobject]@{ number = $n; name = [string]$_.FriendlyName; serial = ([string]$_.SerialNumber).Trim()
    bus = [string]$_.BusType; size = [int64]$_.Size; sector = [int]$_.LogicalSectorSize
    style = [string]$_.PartitionStyle; readonly = [bool]$_.IsReadOnly; offline = [bool]$_.IsOffline
    system = [bool]($_.IsSystem -or $_.IsBoot); health = [string]$_.HealthStatus
    status = [string]$_.OperationalStatus; partitions = $parts }
}
ConvertTo-Json -Depth 5 -Compress -InputObject @($disks)
"""


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _powershell(script, timeout=120):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, timeout=timeout, creationflags=flags)
    return p.returncode, p.stdout.decode("utf-8", "replace").strip(), p.stderr.decode("utf-8", "replace").strip()


def list_disks():
    """Return a list of dicts describing every disk (see ``_LIST_SCRIPT`` for the fields)."""
    code, out, err = _powershell(_LIST_SCRIPT)
    if not out:
        raise RuntimeError(err or "Get-Disk returned nothing (exit %d)" % code)
    disks = json.loads(out)
    if isinstance(disks, dict):
        disks = [disks]
    for d in disks:
        parts = d.get("partitions") or []
        if isinstance(parts, dict):
            parts = [parts]
        d["partitions"] = parts
        d["path"] = r"\\.\PhysicalDrive%d" % d["number"]
    return disks


def set_readonly(disk_number, readonly):
    """Set or clear the disk-level write protection. Returns (ok, error_text)."""
    script = "$ErrorActionPreference='Stop'; Set-Disk -Number %d -IsReadOnly $%s" % (
        int(disk_number), "true" if readonly else "false")
    code, out, err = _powershell(script)
    return code == 0, err


def disk_of_path(path, disks):
    """Return the disk number that holds ``path`` (by drive letter), or None."""
    drive = os.path.splitdrive(os.path.abspath(path))[0].rstrip(":").upper()
    if len(drive) != 1:
        return None
    for d in disks:
        for p in d["partitions"]:
            if (p.get("letter") or "").upper() == drive:
                return d["number"]
    return None


# -- crash-safe record of disks we locked, so a later start can release them ---------------
def _state_file():
    base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "RecoveryTool")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "locked_disks.json")


def pending_locks():
    try:
        with open(_state_file(), encoding="utf-8") as f:
            return list(json.load(f))
    except (OSError, ValueError):
        return []


def _save_locks(items):
    try:
        with open(_state_file(), "w", encoding="utf-8") as f:
            json.dump(items, f)
    except OSError:
        pass


def lock_disk(disk):
    """Write-protect ``disk`` unless it already is. Returns (locked_by_us, error_text)."""
    if disk.get("readonly"):
        return False, ""
    ok, err = set_readonly(disk["number"], True)
    if ok:
        _save_locks(pending_locks() + [{"number": disk["number"], "serial": disk.get("serial", ""),
                                        "name": disk.get("name", "")}])
    return ok, err


def unlock_disk(disk_number, serial=None):
    ok, err = set_readonly(disk_number, False)
    if ok:
        _save_locks([x for x in pending_locks()
                     if not (x.get("serial") == serial if serial else x.get("number") == disk_number)])
    return ok, err


def resolve_pending(all_disks):
    """Match the disks an interrupted run left write-protected against what is connected now.

    Disk numbers change between boots, so the match is made on the serial number.  Returns the
    connected disks that are still write-protected because of us; records of disks that are no
    longer protected are dropped, records of disks that are not connected are kept for later.
    """
    still, found = [], []
    for item in pending_locks():
        serial = item.get("serial")
        match = [d for d in all_disks if (d.get("serial") == serial if serial
                                          else d["number"] == item.get("number") and d.get("name") == item.get("name"))]
        if not match:
            still.append(item)                           # not plugged in right now
        elif match[0].get("readonly"):
            still.append(item)
            found.append(match[0])
    _save_locks(still)
    return found
