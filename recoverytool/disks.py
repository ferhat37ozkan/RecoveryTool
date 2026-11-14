"""Enumerate physical disks the way Disk Management does, and the few maintenance operations
the app offers (write protection, online/offline, drive letters, filesystem check).

Every disk known to Windows is listed - including disks without a drive letter, offline
disks and disks with no recognisable (RAW) filesystem.

Nothing here formats, initialises, partitions or deletes anything.

Set RECOVERYTOOL_FAKE_DISKS to a JSON file (see docs/demo-disks.json) to run the interface
against a made-up disk list.  In that mode no disk is queried and every operation is refused.
"""

from __future__ import annotations

import ctypes
import json
import os
import string
import subprocess

GAP_MIN = 16 << 20          # smaller unallocated stretches are alignment slack, not lost partitions

_LIST_SCRIPT = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'
$disks = Get-Disk | Sort-Object Number | ForEach-Object {
  $n = $_.Number
  $parts = @(Get-Partition -DiskNumber $n | Sort-Object Offset | ForEach-Object {
    $v = $_ | Get-Volume
    $l = [string]$_.DriveLetter; if ($l -notmatch '^[A-Za-z]$') { $l = '' }
    [pscustomobject]@{ number = $_.PartitionNumber; letter = $l; size = [int64]$_.Size
      offset = [int64]$_.Offset; type = [string]$_.Type; hidden = [bool]$_.IsHidden
      filesystem = [string]$v.FileSystem; label = [string]$v.FileSystemLabel
      health = [string]$v.HealthStatus; free = [int64]$v.SizeRemaining }
  })
  [pscustomobject]@{ number = $n; name = [string]$_.FriendlyName; serial = ([string]$_.SerialNumber).Trim()
    bus = [string]$_.BusType; size = [int64]$_.Size; sector = [int]$_.LogicalSectorSize
    style = [string]$_.PartitionStyle; readonly = [bool]$_.IsReadOnly; offline = [bool]$_.IsOffline
    system = [bool]($_.IsSystem -or $_.IsBoot); health = [string]$_.HealthStatus
    status = [string]$_.OperationalStatus; partitions = $parts }
}
ConvertTo-Json -Depth 5 -Compress -InputObject @($disks)
"""

_HEALTH_SCRIPT = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'
$p = Get-PhysicalDisk | Where-Object { $_.DeviceId -eq '%d' } | Select-Object -First 1
if ($p) {
  $c = $p | Get-StorageReliabilityCounter
  [pscustomobject]@{ health = [string]$p.HealthStatus; media = [string]$p.MediaType
    status = [string]$p.OperationalStatus; temperature = $c.Temperature
    read_errors = $c.ReadErrorsUncorrected; read_errors_total = $c.ReadErrorsTotal
    write_errors = $c.WriteErrorsUncorrected; wear = $c.Wear; hours = $c.PowerOnHours } | ConvertTo-Json -Compress
}
"""


def fake_mode():
    return bool(os.environ.get("RECOVERYTOOL_FAKE_DISKS"))


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


def _run(script, timeout=120):
    """Run a modifying command. Returns (ok, text)."""
    if fake_mode():
        return False, "demo mode: no disk is touched"
    try:
        code, out, err = _powershell("$ErrorActionPreference='Stop'; " + script, timeout)
    except subprocess.TimeoutExpired:
        return False, "timed out"
    return code == 0, (err if code else out)


def list_disks():
    """Return a list of dicts describing every disk (see ``_LIST_SCRIPT`` for the fields)."""
    if fake_mode():
        with open(os.environ["RECOVERYTOOL_FAKE_DISKS"], encoding="utf-8") as f:
            disks = json.load(f)
    else:
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
        d["partitions"] = sorted(parts, key=lambda p: p.get("offset", 0))
        d["path"] = r"\\.\PhysicalDrive%d" % d["number"]
    return disks


def layout(disk):
    """Partitions and unallocated stretches of a disk, in on-disk order.

    Returns a list of dicts with ``kind`` ("partition" or "gap"), ``offset`` and ``size``;
    partitions carry the partition dict under ``part``.
    """
    rows, pos = [], 0
    for p in disk["partitions"]:
        if p["offset"] - pos >= GAP_MIN:
            rows.append({"kind": "gap", "offset": pos, "size": p["offset"] - pos})
        rows.append({"kind": "partition", "offset": p["offset"], "size": p["size"], "part": p})
        pos = max(pos, p["offset"] + p["size"])
    if disk["partitions"] and disk["size"] - pos >= GAP_MIN:
        rows.append({"kind": "gap", "offset": pos, "size": disk["size"] - pos})
    return rows


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


def free_letters():
    """Drive letters that are not in use (asks Windows for the bitmask; touches no disk)."""
    try:
        mask = ctypes.windll.kernel32.GetLogicalDrives()
    except Exception:
        mask = 0
    return [c for i, c in enumerate(string.ascii_uppercase) if i >= 3 and not mask >> i & 1]


# -- maintenance operations -----------------------------------------------------------------
def set_readonly(disk_number, readonly):
    """Set or clear the disk-level write protection. Returns (ok, error_text)."""
    return _run("Set-Disk -Number %d -IsReadOnly $%s" % (int(disk_number), "true" if readonly else "false"))


def set_offline(disk_number, offline):
    return _run("Set-Disk -Number %d -IsOffline $%s" % (int(disk_number), "true" if offline else "false"))


def assign_letter(disk_number, part, letter):
    """Give a partition a drive letter, or change the one it has."""
    letter = letter.upper()[:1]
    if letter not in string.ascii_uppercase:
        return False, "bad letter"
    if part.get("letter"):
        return _run("Set-Partition -DiskNumber %d -PartitionNumber %d -NewDriveLetter %s"
                    % (int(disk_number), int(part["number"]), letter))
    return _run("Add-PartitionAccessPath -DiskNumber %d -PartitionNumber %d -AccessPath '%s:\\'"
                % (int(disk_number), int(part["number"]), letter))


def remove_letter(disk_number, part):
    if not part.get("letter"):
        return False, "no letter"
    return _run("Remove-PartitionAccessPath -DiskNumber %d -PartitionNumber %d -AccessPath '%s:\\'"
                % (int(disk_number), int(part["number"]), part["letter"].upper()))


def check_filesystem(disk_number, part):
    """Read-only filesystem check. Returns (ran, text, errors_found)."""
    if fake_mode():
        return False, "demo mode: no disk is touched", False
    try:
        if (part.get("filesystem") or "").upper() in ("NTFS", "REFS"):
            code, out, err = _powershell(
                "$ErrorActionPreference='Stop'; Get-Partition -DiskNumber %d -PartitionNumber %d | Get-Volume | "
                "Repair-Volume -Scan" % (int(disk_number), int(part["number"])), timeout=3600)
            return code == 0, (out or err), code == 0 and "NoErrorsFound" not in out
        if not part.get("letter"):
            return False, "needs a drive letter", False
        code, out, err = _powershell("chkdsk %s:" % part["letter"], timeout=3600)
        return code in (0, 1, 2, 3), (out or err)[-1500:], code in (2, 3)
    except subprocess.TimeoutExpired:
        return False, "timed out", False


def repair_filesystem(disk_number, part):
    """Let Windows repair the filesystem (chkdsk /f). This writes to the volume."""
    if (part.get("filesystem") or "").upper() in ("NTFS", "REFS"):
        return _run("Get-Partition -DiskNumber %d -PartitionNumber %d | Get-Volume | Repair-Volume -OfflineScanAndFix"
                    % (int(disk_number), int(part["number"])), timeout=7200)
    if not part.get("letter"):
        return False, "needs a drive letter"
    return _run("chkdsk %s: /f /x; if ($LASTEXITCODE -gt 1) { throw \"chkdsk exit code $LASTEXITCODE\" }"
                % part["letter"], timeout=7200)


def rescan():
    return _run("Update-HostStorageCache")


def health(disk_number):
    """Reliability counters of a disk (may be empty: many USB bridges do not report them)."""
    if fake_mode():
        return {}
    try:
        code, out, err = _powershell(_HEALTH_SCRIPT % int(disk_number), timeout=60)
        return json.loads(out) if out else {}
    except (subprocess.TimeoutExpired, ValueError):
        return {}


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
    if fake_mode():
        return []
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
