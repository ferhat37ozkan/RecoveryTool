"""The disks inside an AMD RAID array (AMD RAIDXpert2 / rcraid driver).

Windows only sees the array as one virtual disk; the AMD driver hides the real disks behind it.
They can be reached through AMD_RC2t7, a free library by Gakuto Matsumura (the one
CrystalDiskInfo uses): https://thilmera.com/en/project/AMD_RC2t7/

Benchwise does not ship the library (its license does not clearly allow that).  When an AMD RAID
array is found, the user is asked, and the library is downloaded from its official address.
Safety rules, because this talks to the driver of what is often the system disk:

* only the pinned release is accepted: the archive and the DLL must match the SHA-256 values
  below, and the DLL must carry a valid Authenticode signature by Gakuto Matsumura;
* the hash is checked again before every use;
* the library runs in a separate process (this program started with ``--amdrc2-helper``), so a
  crash cannot take Benchwise down.  That process is never killed: the library's notes say an
  abnormal end can unsettle the driver.  After a timeout Benchwise stops waiting and lets it
  finish on its own;
* it only reads: identify data and the SMART / NVMe health block.

The library refuses to run unless it sits in (or below) the folder of the running .exe, so it
only works in the built Benchwise.exe, not when running from source.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wintypes
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

URL = "https://repo.thilmera.com/pac/AMD_RC2t7/zip"
INFO_URL = "https://thilmera.com/en/project/AMD_RC2t7/"
LICENSE_URL = "https://thilmera.com/en/project/AMD_RC2t7/page-help-3"
VERSION = "0b8 Rev.2"
ZIP_SHA256 = "a2e108467c72deb52e77c2cdf7e60fd2ec9fb51b371e61d3209b121651ddd57c"
DLL_SHA256 = {"AMD_RC2t7x64.dll": "bdb01316ec6f444049bfef2b13ca34ee2f5f1713df2007e611d3220bc1b3b8b0",
              "AMD_RC2t7x86.dll": "68d7f33a3fa41668a07e4febe68f15d1d0107024cbbafc938a1af283ca0ff07c"}
SIGNER = "Gakuto Matsumura"
KEEP = ("AMD_RC2t7.COPYRIGHT-en.txt", "AMD_RC2t7.COPYRIGHT-ja.txt", "AMD_RC2t7.version-en.txt",
        "AMD_RC2t7.readme.hash.txt")
TIMEOUT = 60
STATUS = {0: "uninitial", 1: "loaded", 2: "unloaded", 3: "failed_signature", 4: "driver_not_found",
          5: "cannot_open", 6: "failed_memory_alloc", 7: "offset_overflow", 8: "driver_version_old",
          9: "not_admin", 10: "name_failed"}

_running = None             # helper process that did not finish in time; no new one until it ends


def dll_name():
    return "AMD_RC2t7x64.dll" if ctypes.sizeof(ctypes.c_void_p) == 8 else "AMD_RC2t7x86.dll"


def supported():
    """Only the built exe can use the library (it checks that it sits below the running .exe)."""
    return bool(getattr(sys, "frozen", False))


def addon_dir():
    return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "benchwise-addons")


def dll_path():
    return os.path.join(addon_dir(), dll_name())


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def installed():
    p = dll_path()
    return os.path.isfile(p) and sha256(p) == DLL_SHA256[dll_name()]


def is_amd_raid(disk):
    return disk.get("bus") == "RAID" and "AMD-RAID" in (disk.get("name") or "").upper()


def _signed_by_author(path):
    script = ("$s = Get-AuthenticodeSignature -LiteralPath '%s'; "
              "'{0}|{1}' -f $s.Status, $s.SignerCertificate.Subject" % path.replace("'", "''"))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                       text=True, timeout=60, creationflags=flags)
    status, _, subject = p.stdout.strip().partition("|")
    return status == "Valid" and ("CN=%s," % SIGNER) in subject + ",", subject or p.stderr.strip()


def download(progress=lambda step, done=0, total=0: None):
    """Fetch, verify and install the library.  Raises RuntimeError with a readable reason.

    ``progress(step, done, total)`` is called with step "download" (bytes so far / size),
    then "verify", "signature" and "install"."""
    req = urllib.request.Request(URL, headers={"User-Agent": "Benchwise"})
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length") or 0)
        progress("download", 0, total)
        chunks, got = [], 0
        while True:
            chunk = r.read(16384)
            if not chunk:
                break
            chunks.append(chunk)
            got += len(chunk)
            if got > 4 << 20:
                raise RuntimeError("the download is far larger than the expected package; stopped")
            progress("download", got, total or got)
        data = b"".join(chunks)
    progress("verify")
    if hashlib.sha256(data).hexdigest() != ZIP_SHA256:
        raise RuntimeError("the downloaded package is not the expected release (%s); nothing was installed" % VERSION)
    name = dll_name()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        dll = z.read(name)
        texts = {n: z.read(n) for n in KEEP if n in z.namelist()}
    if hashlib.sha256(dll).hexdigest() != DLL_SHA256[name]:
        raise RuntimeError("the library inside the package does not match the expected release; nothing was installed")
    os.makedirs(addon_dir(), exist_ok=True)
    tmp = os.path.join(addon_dir(), name + ".part")
    with open(tmp, "wb") as f:
        f.write(dll)
    progress("signature")
    ok, who = _signed_by_author(tmp)
    if not ok:
        os.remove(tmp)
        raise RuntimeError("the library's digital signature is not valid (%s); nothing was installed" % who)
    progress("install")
    os.replace(tmp, dll_path())
    for n, b in texts.items():
        with open(os.path.join(addon_dir(), n), "wb") as f:
            f.write(b)
    with open(os.path.join(addon_dir(), "AMD_RC2t7.source.txt"), "w", encoding="utf-8") as f:
        f.write("AMD_RC2t7 %s - developed by %s (%s)\n"
                "Downloaded by Benchwise from %s at the user's request.\n"
                "SHA-256 %s  %s\nLicense: %s\n\n"
                "This library is not part of Benchwise. Benchwise does not distribute or modify it and is not\n"
                "responsible for it; its use is governed by its own license.\n"
                % (VERSION, SIGNER, INFO_URL, URL, DLL_SHA256[name], name, LICENSE_URL))


# -- reading (in the helper process) -----------------------------------------------------------
def _parent_alive(pid):
    """Is the process ``pid`` still running?  (The watching helper ends itself when Benchwise is gone.)"""
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x00100000, False, int(pid))          # SYNCHRONIZE
    if not h:
        return False
    try:
        return k32.WaitForSingleObject(h, 0) == 0x102            # WAIT_TIMEOUT: still running
    finally:
        k32.CloseHandle(h)


def _write_json(out, result):
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f)
    os.replace(tmp, out)


def helper_main(dll, out, interval=None, parent=None):
    """Entry of ``--amdrc2-helper <dll> <out.json> [<seconds> <parent pid>]``.

    Without the last two: read every member disk once, write JSON, exit.  With them: keep the
    library loaded and write a fresh reading every ``seconds`` until the parent process is gone,
    then return normally (the library is unloaded the regular way, never killed)."""
    result = {}
    try:
        if sha256(dll) != DLL_SHA256[os.path.basename(dll)]:
            raise RuntimeError("library hash mismatch")
        w = wintypes
        lib = ctypes.WinDLL(dll)
        U = ctypes.c_uint
        for n in ("AMD_RC2_Init", "AMD_RC2_GetStatus", "AMD_RC2_GetDrives"):
            getattr(lib, n).restype, getattr(lib, n).argtypes = U, []

        class Identify(ctypes.Structure):
            _fields_ = [("uStructSize", U), ("uStructVersion", U), ("uDiskNum", U), ("iPhysicalDrive", ctypes.c_int),
                        ("uDriveSize64", ctypes.c_uint64), ("uDriveSize", w.DWORD), ("isSSD", ctypes.c_ubyte),
                        ("isNVMe", ctypes.c_ubyte), ("reserved1", ctypes.c_ubyte), ("reserved2", ctypes.c_ubyte),
                        ("sModel", ctypes.c_char * 41), ("sSerialNumber", ctypes.c_char * 21),
                        ("sFirmwareRev", ctypes.c_char * 9), ("sSpeed", ctypes.c_char * 60),
                        ("reserved3", ctypes.c_ubyte * 93)]
        lib.AMD_RC2_GetIdentify.restype, lib.AMD_RC2_GetIdentify.argtypes = w.BOOL, [ctypes.POINTER(Identify)]
        lib.AMD_RC2_GetSmartData.restype = w.BOOL
        lib.AMD_RC2_GetSmartData.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        status = lib.AMD_RC2_Init()
        result["status"] = STATUS.get(status, str(status))
        found = []                           # identify data, read once
        if status == 1:
            for i in range(min(lib.AMD_RC2_GetDrives(), 128)):
                idn = Identify()
                idn.uStructSize, idn.uStructVersion, idn.uDiskNum = ctypes.sizeof(Identify), 1, i
                if not lib.AMD_RC2_GetIdentify(ctypes.byref(idn)):
                    continue
                txt = lambda b: b.decode("ascii", "replace").strip()
                found.append({"index": i, "model": txt(idn.sModel), "serial": txt(idn.sSerialNumber),
                              "firmware": txt(idn.sFirmwareRev), "speed": txt(idn.sSpeed), "size": idn.uDriveSize64,
                              "ssd": bool(idn.isSSD), "nvme": bool(idn.isNVMe)})

        def read():
            disks = []
            for base in found:
                entry = dict(base)
                data, thr = (ctypes.c_ubyte * 512)(), (ctypes.c_ubyte * 512)()
                if lib.AMD_RC2_GetSmartData(entry["index"], data, 512, thr, 512):
                    entry["smart"] = base64.b64encode(bytes(data)).decode()
                    entry["thresholds"] = base64.b64encode(bytes(thr)).decode()
                disks.append(entry)
            return disks
        result["disks"] = read() if status == 1 else []
        result["time"] = time.time()
        _write_json(out, result)
        if status != 1 or not interval:
            return
        while parent and _parent_alive(parent):
            try:                             # Benchwise may change the interval while we run
                with open(out + ".interval") as f:
                    interval = float(f.read().strip() or interval)
            except (OSError, ValueError):
                pass
            time.sleep(max(2.0, float(interval)))
            if not _parent_alive(parent):
                break
            result = {"status": result["status"], "disks": read(), "time": time.time()}
            _write_json(out, result)
        return
    except Exception as ex:                  # reported back; the main program shows it
        result["error"] = str(ex)
    _write_json(out, result)


class Watcher:
    """A helper process that keeps the library loaded and writes a reading every ``interval`` s.
    It ends by itself (normally) when Benchwise is gone; Benchwise never kills it."""

    def __init__(self, interval):
        fd, self.out = tempfile.mkstemp(prefix="benchwise-amdrc2-watch-", suffix=".json")
        os.close(fd)
        os.remove(self.out)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen([sys.executable, "--amdrc2-helper", dll_path(), self.out, str(interval),
                                      str(os.getpid())], creationflags=flags, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.interval = interval

    def set_interval(self, interval):
        """The helper reads this before each pause (it is never restarted or stopped from outside)."""
        with open(self.out + ".interval", "w") as f:
            f.write(str(interval))
        self.interval = interval

    def alive(self):
        return self.proc.poll() is None

    def latest(self):
        """``(members, error, time)`` of the newest reading, or None before the first one."""
        try:
            with open(self.out, encoding="utf-8") as f:
                res = json.load(f)
        except (OSError, ValueError):
            return None
        if res.get("error") or res.get("status") != "loaded":
            return [], res.get("error") or res.get("status") or "?", res.get("time", 0)
        return res.get("disks", []), None, res.get("time", 0)


_watcher = None


def watch(interval):
    """Start (or restart with a new interval) the watching helper; returns it.  The library must be set up."""
    global _watcher
    if _watcher is not None and _watcher.alive():
        if _watcher.interval != interval:
            _watcher.set_interval(interval)
        return _watcher
    _watcher = Watcher(interval)
    return _watcher


def read_members():
    """Ask the helper process for the member disks.  Returns ``(members, error)``."""
    global _running
    if _watcher is not None and _watcher.alive():      # never two processes on the library at once
        got = _watcher.latest()
        if got is not None:
            return got[0], got[1]
    if _running is not None and _running.poll() is None:
        return [], "still_running"
    exe = sys.executable
    fd, out = tempfile.mkstemp(prefix="benchwise-amdrc2-", suffix=".json")
    os.close(fd)
    os.remove(out)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([exe, "--amdrc2-helper", dll_path(), out], creationflags=flags,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    while proc.poll() is None:
        if time.time() - t0 > TIMEOUT:
            _running = proc                  # never killed (see the module notes)
            return [], "timeout"
        time.sleep(0.2)
    try:
        with open(out, encoding="utf-8") as f:
            res = json.load(f)
    except (OSError, ValueError):
        return [], "no_result"
    finally:
        try:
            os.remove(out)
        except OSError:
            pass
    if res.get("error"):
        return [], res["error"]
    if res.get("status") != "loaded":
        return [], res.get("status") or "?"
    return res.get("disks", []), None


# -- turning the raw blocks into health figures ------------------------------------------------
def parse_nvme(blob):
    """NVMe SMART / Health Information log page (log 02h, 512 bytes)."""
    if isinstance(blob, str):
        blob = base64.b64decode(blob)
    if not blob or len(blob) < 200 or not any(blob[:200]):
        return None
    le = lambda o, n: int.from_bytes(blob[o:o + n], "little")
    kelvin = le(1, 2)
    sensors = [le(200 + 2 * i, 2) - 273 for i in range(8) if le(200 + 2 * i, 2)]
    return {"critical_warning": blob[0], "temperature": kelvin - 273 if kelvin else None, "spare": blob[3],
            "spare_threshold": blob[4], "used": blob[5], "data_read": le(32, 16) * 512000,
            "data_written": le(48, 16) * 512000, "power_cycles": le(112, 16), "hours": le(128, 16),
            "unsafe_shutdowns": le(144, 16), "media_errors": le(160, 16), "error_log_entries": le(176, 16),
            "warning_temp_minutes": le(192, 4), "critical_temp_minutes": le(196, 4), "sensors": sensors}


def member_disk(array, m):
    """A member as a disk dict the verdict and the screen understand."""
    from .data import parse_smart
    d = {"id": "%s.%d" % (array["number"], m["index"]), "number": array["number"], "member_of": array["number"],
         "member_index": m["index"], "name": m.get("model") or "?", "serial": m.get("serial") or "",
         "firmware": m.get("firmware") or "", "speed": m.get("speed") or "", "size": m.get("size") or 0,
         "bus": "NVMe" if m.get("nvme") else "SATA", "media": "SSD" if m.get("ssd") or m.get("nvme") else "HDD",
         "spindle": None, "health": "", "status": "", "temperature": None, "temperature_max": None, "wear": None,
         "hours": None, "read_errors": None, "write_errors": None, "start_stop": None, "load_unload": None,
         "predict_failure": None, "smart": [], "nvme": None, "partitions": [], "system": array.get("system")}
    if m.get("nvme"):
        h = parse_nvme(m.get("smart"))
        if h:
            d["nvme"] = h
            d.update(temperature=h["temperature"], wear=min(h["used"], 100), hours=h["hours"],
                     start_stop=h["power_cycles"])
    elif m.get("smart"):
        d["smart"] = parse_smart(m["smart"], m.get("thresholds"))
    return d


def attach_members(disks):
    """Insert the member disks of AMD RAID arrays right after their array (when the library is set up)."""
    out = []
    for d in disks:
        out.append(d)
        if is_amd_raid(d) and supported() and installed():
            members, err = read_members()
            if members:
                d["members"] = [member_disk(d, m) for m in members]
                out += d["members"]
            else:
                d["raid_error"] = err
    return out


def disk_key(d):
    """A name for a disk that survives reboots and renumbering: its serial number when it has one."""
    serial = (d.get("serial") or "").strip()
    return "sn:" + serial if serial else "id:%s" % d["id"]
