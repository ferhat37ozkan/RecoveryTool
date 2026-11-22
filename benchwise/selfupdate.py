"""Download and install a new Benchwise.exe from inside the program.

1. The release's Benchwise.exe is downloaded to %LOCALAPPDATA%\\Benchwise\\update, with progress.
2. It is accepted only if its size and its SHA-256 match what GitHub publishes for the asset
   (the release "digest"); otherwise it is deleted and nothing changes.
3. Windows does not let a running .exe be deleted, but it can be renamed: the running file becomes
   Benchwise.old.exe, the new one takes its name, the new one is started and this one closes.
   The new one deletes Benchwise.old.exe when it starts (``cleanup``).
4. If the folder cannot be written (for example Program Files without administrator rights), a
   small elevated PowerShell step does the same after this program has closed.

Only for the built exe; from source there is nothing to replace.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from . import __version__

OLD_NAME = "Benchwise.old.exe"


class Cancelled(Exception):
    pass


def supported():
    return bool(getattr(sys, "frozen", False))


def exe_path():
    return os.path.abspath(sys.executable)


def work_dir():
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    path = os.path.join(base, "Benchwise", "update")
    os.makedirs(path, exist_ok=True)
    return path


def download(info, progress=lambda done, total: None, cancelled=lambda: False):
    """Fetch the new exe and check it.  Returns its path; raises RuntimeError / Cancelled."""
    url, size, digest = info.get("exe"), info.get("size"), (info.get("digest") or "").lower()
    if not url or not digest.startswith("sha256:"):
        raise RuntimeError("the release does not publish a checksum for Benchwise.exe")
    target = os.path.join(work_dir(), "Benchwise-%s.exe" % info["version"])
    part = target + ".part"
    h = hashlib.sha256()
    got = 0
    req = urllib.request.Request(url, headers={"User-Agent": "Benchwise/%s" % __version__})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or size or 0)
            progress(0, total)
            while True:
                if cancelled():
                    raise Cancelled()
                chunk = r.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if size and got > size:
                    raise RuntimeError("the download is larger than the published file")
                progress(got, total)
        if size and got != size:
            raise RuntimeError("the download is incomplete (%d of %d bytes)" % (got, size))
        if h.hexdigest() != digest.split(":", 1)[1]:
            raise RuntimeError("the downloaded file does not match the published SHA-256")
        with open(part, "rb") as f:
            if f.read(2) != b"MZ":
                raise RuntimeError("the downloaded file is not a Windows program")
        os.replace(part, target)
        return target
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise


def install(new_exe):
    """Put ``new_exe`` in place of the running exe and start it.  The caller then closes.

    Returns "done", or "elevated" when an administrator step was started instead (the caller
    must close at once so that step can replace the file)."""
    exe = exe_path()
    folder = os.path.dirname(exe)
    old = os.path.join(folder, OLD_NAME)
    try:
        if os.path.exists(old):
            os.remove(old)              # left over from an earlier update
        os.replace(exe, old)            # allowed while running
        try:
            shutil.copyfile(new_exe, exe)
        except OSError:
            os.replace(old, exe)        # put the running version back
            raise
    except PermissionError:
        return _install_elevated(new_exe, exe)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([exe, "--wait"], cwd=folder, creationflags=flags, close_fds=True)    # we still hold the lock
    return "done"


def _install_elevated(new_exe, exe):
    """The folder needs administrator rights: let an elevated PowerShell swap the file once this
    process has ended, then start the new version."""
    import ctypes
    q = lambda s: "'" + s.replace("'", "''") + "'"
    script = os.path.join(work_dir(), "install.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write("$ErrorActionPreference = 'Stop'\n"
                "try { Wait-Process -Id %d -Timeout 60 -ErrorAction SilentlyContinue } catch {}\n"
                "for ($i = 0; $i -lt 20; $i++) {\n"
                "  try { Copy-Item -LiteralPath %s -Destination %s -Force; break } catch { Start-Sleep -Milliseconds 500 }\n"
                "}\n"
                "Start-Process -FilePath %s -ArgumentList '--wait'\n" % (os.getpid(), q(new_exe), q(exe), q(exe)))
    params = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%s"' % script
    if ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", params, None, 0) <= 32:
        raise RuntimeError("administrator rights are needed to replace Benchwise.exe in its folder")
    return "elevated"


def cleanup():
    """At start: remove what an earlier update left behind (the old exe, downloaded files)."""
    if not supported():
        return
    old = os.path.join(os.path.dirname(exe_path()), OLD_NAME)
    try:
        if os.path.exists(old):
            os.remove(old)              # may still be in use for a moment; then next start
    except OSError:
        pass
    try:
        folder = work_dir()
        for name in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass
    except OSError:
        pass
