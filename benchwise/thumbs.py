"""The picture Windows Explorer shows for a file: a thumbnail of its content where Windows has one
(images, videos, PDFs when a PDF viewer provides thumbnails, ...), otherwise the file type's icon.

Uses the shell's IShellItemImageFactory, so it is exactly what Explorer shows (and uses its cache).
Call ``init_thread()`` once on the thread that asks (COM), then ``get(path, size)``.
"""

from __future__ import annotations

import ctypes
import os
import ctypes.wintypes as w

from PIL import Image

_ole32 = ctypes.windll.ole32
_shell32 = ctypes.windll.shell32
_gdi32 = ctypes.windll.gdi32


class GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        _ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(self))


class SIZE(ctypes.Structure):
    _fields_ = [("cx", w.LONG), ("cy", w.LONG)]


class BITMAP(ctypes.Structure):
    _fields_ = [("bmType", w.LONG), ("bmWidth", w.LONG), ("bmHeight", w.LONG), ("bmWidthBytes", w.LONG),
                ("bmPlanes", w.WORD), ("bmBitsPixel", w.WORD), ("bmBits", ctypes.c_void_p)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG), ("biPlanes", w.WORD),
                ("biBitCount", w.WORD), ("biCompression", w.DWORD), ("biSizeImage", w.DWORD),
                ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


IID_IShellItemImageFactory = GUID("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")
SIIGBF_BIGGERSIZEOK = 0x01

_shell32.SHCreateItemFromParsingName.argtypes = [w.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID),
                                                 ctypes.POINTER(ctypes.c_void_p)]
_GetImage = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, SIZE, ctypes.c_int, ctypes.POINTER(w.HBITMAP))
_Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
_gdi32.GetObjectW.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p]
_gdi32.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p, ctypes.c_void_p, w.UINT]
_gdi32.DeleteObject.argtypes = [w.HANDLE]


def init_thread():
    _ole32.CoInitializeEx(None, 0x2)        # COINIT_APARTMENTTHREADED


def _to_image(hbm):
    bm = BITMAP()
    if not _gdi32.GetObjectW(hbm, ctypes.sizeof(bm), ctypes.byref(bm)):
        return None
    width, height = bm.bmWidth, bm.bmHeight
    hdr = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down BGRA
    buf = ctypes.create_string_buffer(width * height * 4)
    hdc = ctypes.windll.user32.GetDC(None)
    try:
        if not _gdi32.GetDIBits(hdc, hbm, 0, height, buf, ctypes.byref(hdr), 0):
            return None
    finally:
        ctypes.windll.user32.ReleaseDC(None, hdc)
    img = Image.frombuffer("RGBA", (width, height), buf.raw, "raw", "BGRA", 0, 1).copy()
    if img.getchannel("A").getextrema() == (0, 0):      # a bitmap without alpha: fully opaque
        img.putalpha(255)
    return img


def get(path, size=64):
    """A PIL image (at most ``size`` px), or None when Windows has nothing for the file."""
    path = os.path.normpath(os.path.abspath(path))     # the shell does not parse forward slashes
    item = ctypes.c_void_p()
    if _shell32.SHCreateItemFromParsingName(path, None, ctypes.byref(IID_IShellItemImageFactory),
                                            ctypes.byref(item)) != 0 or not item:
        return None
    try:
        vtbl = ctypes.cast(item, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        hbm = w.HBITMAP()
        try:
            hr = _GetImage(vtbl[3])(item, SIZE(size, size), SIIGBF_BIGGERSIZEOK, ctypes.byref(hbm))
        except OSError:
            return None
        if hr != 0 or not hbm:
            return None
        try:
            img = _to_image(hbm)
        finally:
            _gdi32.DeleteObject(hbm)
        if img is not None and max(img.size) > size:
            img.thumbnail((size, size), Image.LANCZOS)
        return img
    finally:
        _Release(vtbl[2])(item)
