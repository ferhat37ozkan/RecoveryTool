"""Notification-area (next to the clock) icons, straight on the Win32 API.

Each icon is identified by a key (one per disk).  A hidden window on its own thread owns the
icons and runs the Win32 message loop; the Tk thread only queues requests (``set_icons``,
``notify``, ``stop``) and receives clicks through callbacks it polls with ``events``.
Icons come back by themselves when Explorer restarts (the "TaskbarCreated" message).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import queue
import threading

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_DESTROY, WM_COMMAND, WM_USER, WM_APP = 0x0002, 0x0111, 0x0400, 0x8000
WM_LBUTTONUP, WM_RBUTTONUP, WM_LBUTTONDBLCLK = 0x0202, 0x0205, 0x0203
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
CALLBACK = WM_USER + 20
WAKE = WM_APP + 1
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH),
                ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128), ("dwState", w.DWORD),
                ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256), ("uVersion", w.UINT),
                ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD), ("guidItem", GUID), ("hBalloonIcon", w.HICON)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", w.BOOL), ("xHotspot", w.DWORD), ("yHotspot", w.DWORD), ("hbmMask", w.HBITMAP),
                ("hbmColor", w.HBITMAP)]


class BITMAPV5HEADER(ctypes.Structure):
    _fields_ = [("bV5Size", w.DWORD), ("bV5Width", w.LONG), ("bV5Height", w.LONG), ("bV5Planes", w.WORD),
                ("bV5BitCount", w.WORD), ("bV5Compression", w.DWORD), ("bV5SizeImage", w.DWORD),
                ("bV5XPelsPerMeter", w.LONG), ("bV5YPelsPerMeter", w.LONG), ("bV5ClrUsed", w.DWORD),
                ("bV5ClrImportant", w.DWORD), ("bV5RedMask", w.DWORD), ("bV5GreenMask", w.DWORD),
                ("bV5BlueMask", w.DWORD), ("bV5AlphaMask", w.DWORD), ("bV5CSType", w.DWORD),
                ("bV5Endpoints", ctypes.c_byte * 36), ("bV5GammaRed", w.DWORD), ("bV5GammaGreen", w.DWORD),
                ("bV5GammaBlue", w.DWORD), ("bV5Intent", w.DWORD), ("bV5ProfileData", w.DWORD),
                ("bV5ProfileSize", w.DWORD), ("bV5Reserved", w.DWORD)]


user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.CreateWindowExW.restype = w.HWND
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterWindowMessageW.argtypes = [w.LPCWSTR]
user32.RegisterWindowMessageW.restype = w.UINT
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
user32.CreatePopupMenu.restype = w.HMENU
user32.AppendMenuW.argtypes = [w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR]
user32.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.LPVOID]
user32.DestroyMenu.argtypes = [w.HMENU]
user32.CreateIconIndirect.restype = w.HICON
user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
user32.DestroyIcon.argtypes = [w.HICON]
user32.DestroyWindow.argtypes = [w.HWND]
user32.SetForegroundWindow.argtypes = [w.HWND]
gdi32.CreateDIBSection.restype = w.HBITMAP
gdi32.CreateDIBSection.argtypes = [w.HDC, ctypes.c_void_p, w.UINT, ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD]
gdi32.CreateBitmap.restype = w.HBITMAP
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, w.UINT, w.UINT, ctypes.c_void_p]
gdi32.DeleteObject.argtypes = [w.HANDLE]
shell32.Shell_NotifyIconW.argtypes = [w.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
kernel32.GetModuleHandleW.restype = w.HMODULE
kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]


def promote_icons(exe_path):
    """Windows 11 hides new notification icons behind the "^" by default.  Show ours next to the
    clock - but only where the user has not decided (``IsPromoted`` missing); an icon the user hid
    on purpose (0) stays hidden.  Returns how many entries were changed."""
    import winreg
    changed = 0
    target = exe_path.lower()
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\NotifyIconSettings")
    except OSError:
        return 0                                    # Windows 10: icons are managed differently
    with root:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, name, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                    path = winreg.QueryValueEx(k, "ExecutablePath")[0]
                    if str(path).lower() != target:
                        continue
                    try:
                        winreg.QueryValueEx(k, "IsPromoted")
                    except FileNotFoundError:
                        winreg.SetValueEx(k, "IsPromoted", 0, winreg.REG_DWORD, 1)
                        changed += 1
            except OSError:
                continue
    return changed


def hicon_from_image(img):
    """A Windows icon handle from a square RGBA Pillow image (alpha kept)."""
    img = img.convert("RGBA")
    width, height = img.size
    hdr = BITMAPV5HEADER()
    hdr.bV5Size, hdr.bV5Width, hdr.bV5Height = ctypes.sizeof(BITMAPV5HEADER), width, -height    # top-down
    hdr.bV5Planes, hdr.bV5BitCount, hdr.bV5Compression = 1, 32, 3                               # BI_BITFIELDS
    hdr.bV5RedMask, hdr.bV5GreenMask, hdr.bV5BlueMask, hdr.bV5AlphaMask = 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000
    bits = ctypes.c_void_p()
    color = gdi32.CreateDIBSection(None, ctypes.byref(hdr), 0, ctypes.byref(bits), None, 0)
    ctypes.memmove(bits, img.tobytes("raw", "BGRA"), width * height * 4)
    mask = gdi32.CreateBitmap(width, height, 1, 1, None)
    info = ICONINFO(True, 0, 0, mask, color)
    icon = user32.CreateIconIndirect(ctypes.byref(info))
    gdi32.DeleteObject(color)
    gdi32.DeleteObject(mask)
    return icon


# The window class is registered once per process and stays registered after a Tray stops, so its
# window procedure must not belong to one Tray: a second Tray (icons turned off, then on again)
# would otherwise get the first one's procedure and never handle its own requests.  The single
# procedure below hands each message to the Tray that owns the window.
CLASS_NAME = "BenchwiseTrayWindow"
_windows = {}                   # hwnd -> Tray
_class_lock = threading.Lock()
_class_proc = None
_taskbar_msg = None


def _taskbar_created():
    global _taskbar_msg
    if _taskbar_msg is None:
        _taskbar_msg = user32.RegisterWindowMessageW("TaskbarCreated")
    return _taskbar_msg


def _dispatch(hwnd, msg, wparam, lparam):
    owner = _windows.get(hwnd)
    if owner is None:                               # while the window is being created or after it is gone
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    return owner._handle(hwnd, msg, wparam, lparam)


def _register_class(hinst):
    global _class_proc
    with _class_lock:
        if _class_proc is not None:
            return
        _class_proc = WNDPROC(_dispatch)            # kept for the life of the process: called from C
        cls = WNDCLASSW()
        cls.lpfnWndProc, cls.hInstance, cls.lpszClassName = _class_proc, hinst, CLASS_NAME
        user32.RegisterClassW(ctypes.byref(cls))


class Tray:
    """Icons next to the clock.  ``events`` gets ("click", key), ("open", None), ("passage", None)
    and ("quit", None).  The Passage line shows only when ``passage`` is set: (label, checked)."""

    MENU_OPEN, MENU_QUIT, MENU_PASSAGE = 1, 2, 3

    def __init__(self, labels=("Open", "Quit")):
        self.labels = labels
        self.passage = None
        self.events = queue.Queue()
        self.requests = queue.Queue()
        self.icons = {}             # key -> (uID, HICON, tip)
        self.next_id = 1
        self.hwnd = None
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self.thread.start()
        self.ready.wait(5)

    # -- called from the Tk thread --------------------------------------------------------------
    def set_icons(self, items):
        """``items``: list of dicts with key, image (Pillow RGBA), tip.  Others are removed."""
        self._ask(("set", items))

    def notify(self, title, text):
        """A balloon / toast from the first icon."""
        self._ask(("notify", (title, text)))

    def set_labels(self, labels):
        self.labels = labels

    def stop(self):
        self._ask(("stop", None))
        self.thread.join(3)

    def _ask(self, req):
        self.requests.put(req)
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WAKE, 0, 0)

    # -- tray thread ----------------------------------------------------------------------------
    def _data(self, uid, flags=0):
        nid = NOTIFYICONDATAW()
        nid.cbSize, nid.hWnd, nid.uID, nid.uFlags, nid.uCallbackMessage = ctypes.sizeof(nid), self.hwnd, uid, flags, CALLBACK
        return nid

    def _apply(self, items):
        wanted = {it["key"]: it for it in items}
        for key in [k for k in self.icons if k not in wanted]:
            uid, hicon, _ = self.icons.pop(key)
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data(uid)))
            user32.DestroyIcon(hicon)
        for key, it in wanted.items():
            hicon = hicon_from_image(it["image"])
            new = key not in self.icons
            uid = self.next_id if new else self.icons[key][0]
            if new:
                self.next_id += 1
            nid = self._data(uid, NIF_MESSAGE | NIF_ICON | NIF_TIP)
            nid.hIcon, nid.szTip = hicon, (it.get("tip") or "")[:127]
            if not shell32.Shell_NotifyIconW(NIM_ADD if new else NIM_MODIFY, ctypes.byref(nid)) and not new:
                shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))       # Explorer lost it meanwhile
            if not new:
                user32.DestroyIcon(self.icons[key][1])
            self.icons[key] = (uid, hicon, it.get("tip") or "")

    def _readd(self):
        """Explorer restarted: every icon must be added again."""
        for key, (uid, hicon, tip) in self.icons.items():
            nid = self._data(uid, NIF_MESSAGE | NIF_ICON | NIF_TIP)
            nid.hIcon, nid.szTip = hicon, tip[:127]
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def _key_of(self, uid):
        return next((k for k, v in self.icons.items() if v[0] == uid), None)

    def _menu(self):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, 0, self.MENU_OPEN, self.labels[0])
        if self.passage:
            label, checked = self.passage
            user32.AppendMenuW(menu, 0x8 if checked else 0, self.MENU_PASSAGE, label)    # MF_CHECKED
        user32.AppendMenuW(menu, 0x800, 0, None)                   # separator
        user32.AppendMenuW(menu, 0, self.MENU_QUIT, self.labels[1])
        pt = w.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)                       # so the menu closes when clicking elsewhere
        cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0020, pt.x, pt.y, 0, self.hwnd, None)   # RETURNCMD | BOTTOMALIGN
        user32.DestroyMenu(menu)
        if cmd == self.MENU_OPEN:
            self.events.put(("open", None))
        elif cmd == self.MENU_QUIT:
            self.events.put(("quit", None))
        elif cmd == self.MENU_PASSAGE:
            self.events.put(("passage", None))

    def _handle(self, hwnd, msg, wparam, lparam):
        if msg == CALLBACK:
            event = lparam & 0xFFFF
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self.events.put(("click", self._key_of(wparam)))
            elif event == WM_RBUTTONUP:
                self._menu()
            return 0
        if msg == WAKE:
            self._drain()
            return 0
        if msg == _taskbar_created() and msg:
            self._readd()
            return 0
        if msg == WM_DESTROY:
            _windows.pop(hwnd, None)
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run(self):
        hinst = kernel32.GetModuleHandleW(None)
        _register_class(hinst)
        self.hwnd = user32.CreateWindowExW(0, CLASS_NAME, "Benchwise tray", 0, 0, 0, 0, 0, None, None, hinst, None)
        _windows[self.hwnd] = self
        self.ready.set()
        self._drain()
        msg = w.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _drain(self):
        while True:
            try:
                kind, value = self.requests.get_nowait()
            except queue.Empty:
                return
            if kind == "set":
                self._apply(value)
            elif kind == "notify" and self.icons:
                uid = next(iter(self.icons.values()))[0]
                nid = self._data(uid, NIF_INFO)
                nid.szInfoTitle, nid.szInfo, nid.dwInfoFlags = value[0][:63], value[1][:255], 0x01    # NIIF_INFO
                shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
            elif kind == "stop":
                self._apply([])
                user32.DestroyWindow(self.hwnd)
                return
