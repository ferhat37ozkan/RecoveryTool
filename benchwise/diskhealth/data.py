"""Collect health data of every physical disk.

Two sources, both through one PowerShell call:

* the Storage module (``Get-PhysicalDisk`` / ``Get-StorageReliabilityCounter``): works for SATA,
  NVMe and many USB disks; gives health status, temperature, wear, power-on hours, error counts;
* ATA SMART through WMI (``MSStorageDriver_FailurePredict*`` in ``root\\wmi``): the raw attribute
  table of SATA disks (reallocated / pending sectors, CRC errors, ...).  NVMe disks, RAID arrays
  and most USB enclosures do not answer it.

Windows reports "unknown" in different ways (missing, null, 0); ``collect`` turns every unknown
value into None so that the verdict never mistakes "not reported" for "zero".

Set BENCHWISE_FAKE_HEALTH to a JSON file (see docs/demo-health.json) to use made-up disks.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess

from recoverytool import disks

_SCRIPT = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'
function B64($v) { if ($v) { [Convert]::ToBase64String([byte[]]$v) } else { $null } }
$smart = @{}; $thr = @{}; $pred = @{}
Get-CimInstance -Namespace root\wmi -ClassName MSStorageDriver_FailurePredictData | ForEach-Object { $smart[$_.InstanceName.ToUpper()] = B64 $_.VendorSpecific }
Get-CimInstance -Namespace root\wmi -ClassName MSStorageDriver_FailurePredictThresholds | ForEach-Object { $thr[$_.InstanceName.ToUpper()] = B64 $_.VendorSpecific }
Get-CimInstance -Namespace root\wmi -ClassName MSStorageDriver_FailurePredictStatus | ForEach-Object { $pred[$_.InstanceName.ToUpper()] = [bool]$_.PredictFailure }
$drives = @{}; Get-CimInstance Win32_DiskDrive | ForEach-Object { $drives[[string]$_.Index] = $_ }
$out = @(Get-PhysicalDisk | Sort-Object { [int]$_.DeviceId } | ForEach-Object {
  $c = $_ | Get-StorageReliabilityCounter
  $w = $drives[[string]$_.DeviceId]
  $key = $null
  if ($w) { $pnp = ([string]$w.PNPDeviceID).ToUpper(); $key = @($smart.Keys | Where-Object { $_.StartsWith($pnp) }) | Select-Object -First 1 }
  [pscustomobject]@{
    number = [int]$_.DeviceId; name = [string]$_.FriendlyName; serial = ([string]$_.SerialNumber).Trim()
    media = [string]$_.MediaType; bus = [string]$_.BusType; spindle = $_.SpindleSpeed
    firmware = ([string]$_.FirmwareVersion).Trim(); size = [int64]$_.Size
    health = [string]$_.HealthStatus; status = [string]($_.OperationalStatus -join ', ')
    temperature = $c.Temperature; temperature_max = $c.TemperatureMax; wear = $c.Wear; hours = $c.PowerOnHours
    read_errors = $c.ReadErrorsUncorrected; read_errors_corrected = $c.ReadErrorsCorrected
    write_errors = $c.WriteErrorsUncorrected; write_errors_corrected = $c.WriteErrorsCorrected
    start_stop = $c.StartStopCycleCount; load_unload = $c.LoadUnloadCycleCount
    smart = $(if ($key) { $smart[$key] } else { $null }); smart_thresholds = $(if ($key) { $thr[$key] } else { $null })
    predict_failure = $(if ($key -and $pred.ContainsKey($key)) { $pred[$key] } else { $null })
  }
})
ConvertTo-Json -Depth 4 -Compress -InputObject $out
"""

# ATA attribute names (the common ones; vendors add their own)
ATTR_NAMES = {
    1: "Raw Read Error Rate", 2: "Throughput Performance", 3: "Spin-Up Time", 4: "Start/Stop Count",
    5: "Reallocated Sectors Count", 7: "Seek Error Rate", 8: "Seek Time Performance", 9: "Power-On Hours",
    10: "Spin Retry Count", 11: "Calibration Retry Count", 12: "Power Cycle Count",
    170: "Available Reserved Space", 171: "Program Fail Count", 172: "Erase Fail Count",
    173: "Wear Leveling Count", 174: "Unexpected Power Loss", 175: "Program Fail Count (chip)",
    177: "Wear Range Delta", 179: "Used Reserved Block Count", 180: "Unused Reserved Block Count",
    181: "Program Fail Count", 182: "Erase Fail Count", 183: "SATA Downshift Error Count",
    184: "End-to-End Error", 187: "Reported Uncorrectable Errors", 188: "Command Timeout",
    189: "High Fly Writes", 190: "Airflow Temperature", 191: "G-Sense Error Rate",
    192: "Power-off Retract Count", 193: "Load/Unload Cycle Count", 194: "Temperature",
    195: "Hardware ECC Recovered", 196: "Reallocation Event Count", 197: "Current Pending Sector Count",
    198: "Offline Uncorrectable", 199: "UltraDMA CRC Error Count", 200: "Write Error Rate",
    202: "Percent Lifetime Remaining", 206: "Flying Height", 220: "Disk Shift", 222: "Loaded Hours",
    223: "Load/Unload Retry Count", 224: "Load Friction", 225: "Load/Unload Cycle Count",
    226: "Load-in Time", 230: "Life Curve Status", 231: "SSD Life Left", 232: "Endurance Remaining",
    233: "Media Wearout Indicator", 234: "Average Erase Count", 235: "Good Block Count",
    240: "Head Flying Hours", 241: "Total LBAs Written", 242: "Total LBAs Read",
    249: "NAND Writes (GiB)", 250: "Read Error Retry Rate", 254: "Free Fall Protection",
}


def parse_smart(data, thresholds=None):
    """The ATA SMART attribute table from the 512-byte blocks WMI returns (bytes or base64).

    Layout: 2 bytes version, then 30 entries of 12 bytes: id, flags (2), current, worst,
    raw (6, little-endian), reserved.  Thresholds use the same layout: id, threshold, 10 reserved.
    """
    if not data:
        return []
    if isinstance(data, str):
        data = base64.b64decode(data)
    if isinstance(thresholds, str):
        thresholds = base64.b64decode(thresholds)
    limits = {}
    if thresholds:
        for i in range(30):
            e = thresholds[2 + i * 12:2 + i * 12 + 12]
            if len(e) == 12 and e[0]:
                limits[e[0]] = e[1]
    out = []
    for i in range(30):
        e = data[2 + i * 12:2 + i * 12 + 12]
        if len(e) < 12 or not e[0]:
            continue
        aid = e[0]
        out.append({"id": aid, "name": ATTR_NAMES.get(aid, "Vendor specific"), "flags": e[1] | e[2] << 8,
                    "current": e[3], "worst": e[4], "threshold": limits.get(aid), "raw": int.from_bytes(e[5:11], "little")})
    return out


def _clean(d):
    """Unknown values to None (Windows says "unknown" as missing, null or 0)."""
    for k in ("temperature", "temperature_max"):
        if not d.get(k):
            d[k] = None
    counters = ("hours", "read_errors", "write_errors", "read_errors_corrected", "write_errors_corrected",
                "start_stop", "load_unload")
    if d.get("temperature") is None and all(d.get(k) is None for k in counters):
        d["wear"] = None                   # nothing else reported: a 0 here means "unknown", not "new"
    for k in ("health", "media", "bus", "firmware", "serial", "status"):
        d[k] = d.get(k) or ""
    if d["media"] == "Unspecified":
        d["media"] = ""
    if d["media"] == "HDD":
        d["wear"] = None                   # flash wear means nothing for a spinning disk (Windows says 0)
    if isinstance(d.get("smart"), list):          # demo data writes the table out directly
        for a in d["smart"]:
            a.setdefault("name", ATTR_NAMES.get(a["id"], "Vendor specific"))
            a.setdefault("flags", 0)
    else:
        d["smart"] = parse_smart(d.get("smart"), d.get("smart_thresholds"))
    d.pop("smart_thresholds", None)
    return d


def collect():
    """Every physical disk with its health data, plus what ``disks.list_disks`` knows (partitions)."""
    fake = os.environ.get("BENCHWISE_FAKE_HEALTH")
    if fake:
        with open(fake, encoding="utf-8") as f:
            raw = json.load(f)
        layout = {}
    else:
        code, out, err = disks._powershell(_SCRIPT, timeout=120)
        if not out:
            raise RuntimeError(err or "Get-PhysicalDisk returned nothing (exit %d)" % code)
        raw = json.loads(out)
        try:
            layout = {d["number"]: d for d in disks.list_disks()}
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):
            layout = {}
    if isinstance(raw, dict):
        raw = [raw]
    result = []
    for d in raw:
        d = _clean(dict(d))
        d["id"] = d["number"]                  # members of a RAID array get "<array>.<n>" (amdraid.py)
        extra = layout.get(d["number"], {})
        d.setdefault("partitions", extra.get("partitions", []))
        d.setdefault("style", extra.get("style", ""))
        d.setdefault("system", extra.get("system", False))
        result.append(d)
    return result
