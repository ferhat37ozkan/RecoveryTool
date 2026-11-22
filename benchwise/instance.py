"""One Benchwise at a time.

A named mutex marks the running copy.  A second start (a double click while Benchwise sits next to
the clock) does not open another window: it sets a named event, the running copy brings its window
to the front, and the second copy exits.  The event allows a standard-rights process to signal an
elevated one (its security descriptor grants "everyone" and carries a low integrity label).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import threading
import time

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
kernel32.CreateMutexW.restype = w.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
kernel32.CreateEventW.restype = w.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
kernel32.OpenEventW.restype = w.HANDLE
kernel32.OpenEventW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
kernel32.SetEvent.argtypes = [w.HANDLE]
kernel32.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
kernel32.CloseHandle.argtypes = [w.HANDLE]
advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
    w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]

MUTEX = "Local\\Benchwise.Instance"
EVENT = "Local\\Benchwise.Show"
ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED = 183, 5
EVENT_MODIFY_STATE = 0x0002


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", w.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p), ("bInheritHandle", w.BOOL)]


def _open_to_all():
    """Security attributes: everyone may use the object, from any integrity level."""
    sd = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW("D:(A;;GA;;;WD)S:(ML;;NW;;;LW)", 1,
                                                                         ctypes.byref(sd), None):
        return None
    sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), sd, False)
    return sa


_held = []


def acquire(wait=0.0):
    """True when this is the only Benchwise (the mutex is now ours).  ``wait`` seconds are given to a
    copy that is just closing (after an update or a restart as administrator)."""
    deadline = time.time() + wait
    sa = _open_to_all()
    while True:
        h = kernel32.CreateMutexW(ctypes.byref(sa) if sa else None, True, MUTEX)
        err = ctypes.get_last_error()
        if h and err != ERROR_ALREADY_EXISTS:
            _held.append(h)
            return True
        if h:
            kernel32.CloseHandle(h)
        if time.time() >= deadline:
            return False                # exists (or access denied: an elevated copy holds it)
        time.sleep(0.25)


def release():
    while _held:
        h = _held.pop()
        kernel32.ReleaseMutex(h)
        kernel32.CloseHandle(h)


def signal_show():
    h = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, EVENT)
    if not h:
        return False
    kernel32.SetEvent(h)
    kernel32.CloseHandle(h)
    return True


def listen(callback):
    """Call ``callback()`` (from a background thread) each time another start asks to be shown."""
    sa = _open_to_all()
    h = kernel32.CreateEventW(ctypes.byref(sa) if sa else None, False, False, EVENT)
    if not h:
        return

    def loop():
        while True:
            if kernel32.WaitForSingleObject(h, 0xFFFFFFFF) == 0:
                callback()
    threading.Thread(target=loop, name="show-listener", daemon=True).start()
