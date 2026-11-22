"""Disk > Speed & Capacity Test: sequential and 4 KB random speed of a drive, measured with a temporary
file that bypasses the Windows cache (so the numbers are the drive's, not the RAM's).  The file is
opened delete-on-close, so it disappears even if the program is stopped half way.

The fake-capacity check (filling the whole free space and reading it back) stays locked in this
version."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import os
import random
import shutil
import string
import tempfile
import time

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, human, kv_grid, note, texts

texts({
    "spd_how": ("Writes a temporary test file to the chosen drive and reads it back, bypassing the Windows cache. "
                "Nothing else on the drive is touched; the file is deleted at the end (or when you stop).",
                "Seçilen sürücüye geçici bir test dosyası yazar ve Windows önbelleğini atlayarak geri okur. "
                "Sürücüdeki başka hiçbir şeye dokunulmaz; dosya sonunda (veya durdurduğunuzda) silinir."),
    "spd_drive": ("Drive", "Sürücü"),
    "spd_size": ("Test size", "Test boyutu"),
    "spd_start": ("Start", "Başlat"),
    "spd_stop": ("Stop", "Durdur"),
    "spd_free": ("{free} free", "{free} boş"),
    "spd_no_room": ("Not enough free space for this test size.", "Bu test boyutu için yeterli boş alan yok."),
    "spd_phase_sw": ("Sequential write", "Sıralı yazma"),
    "spd_phase_sr": ("Sequential read", "Sıralı okuma"),
    "spd_phase_rr": ("4 KB random read", "4 KB rastgele okuma"),
    "spd_phase_rw": ("4 KB random write", "4 KB rastgele yazma"),
    "spd_running": ("{phase}… {pct}%", "{phase}… %{pct}"),
    "spd_rate": ("{speed}/s", "{speed}/sn"),
    "spd_iops": ("{speed}/s · {iops} IOPS", "{speed}/sn · {iops} IOPS"),
    "spd_done": ("Finished. The test file was deleted.", "Bitti. Test dosyası silindi."),
    "spd_stopped": ("Stopped. The test file was deleted.", "Durduruldu. Test dosyası silindi."),
    "spd_hint_usb2": ("Sequential speed under 40 MB/s: this looks like a USB 2.0 port or a slow stick.",
                      "Sıralı hız 40 MB/sn altında: USB 2.0 port veya yavaş bir bellek gibi görünüyor."),
    "spd_hint_hdd": ("Low 4 KB random speed is normal for a hard disk.", "Düşük 4 KB rastgele hız sabit disk için normaldir."),
    "spd_capacity": ("Fake-capacity check", "Sahte kapasite kontrolü"),
    "spd_capacity_note": ("Fills all free space and reads it back to catch USB sticks that report more space than "
                          "they have. Locked in this version.",
                          "Gerçekte olduğundan fazla alan bildiren USB bellekleri yakalamak için bütün boş alanı "
                          "doldurup geri okur. Bu sürümde kilitli."),
    "spd_locked": ("Locked", "Kilitli"),
})

GENERIC_RW = 0xC0000000
CREATE_ALWAYS = 2
FLAGS = 0x20000000 | 0x80000000 | 0x04000000      # NO_BUFFERING | WRITE_THROUGH | DELETE_ON_CLOSE
INVALID = w.HANDLE(-1).value
SEQ_BLOCK = 8 << 20
RAND_BLOCK = 4096
RAND_SECONDS = 6

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateFileW.restype = w.HANDLE
k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
k32.VirtualAlloc.restype = ctypes.c_void_p
k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, w.DWORD, w.DWORD]
k32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, w.DWORD]
k32.ReadFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
k32.WriteFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
k32.SetFilePointerEx.argtypes = [w.HANDLE, ctypes.c_longlong, ctypes.c_void_p, w.DWORD]
k32.CloseHandle.argtypes = [w.HANDLE]


def drives():
    """[(root, free bytes)] for fixed and removable drives."""
    out = []
    mask = k32.GetLogicalDrives()
    for i, c in enumerate(string.ascii_uppercase):
        root = "%s:\\" % c
        if mask & (1 << i) and k32.GetDriveTypeW(root) in (2, 3):
            try:
                out.append((root, shutil.disk_usage(root).free))
            except OSError:
                pass
    return out


def test_folder(root):
    system = os.environ.get("SystemDrive", "C:").upper() + "\\"
    return tempfile.gettempdir() if root.upper() == system else root


class Bench:
    """One test run; ``stop`` may be set from the UI thread."""

    def __init__(self, folder, size, progress):
        self.path = os.path.join(folder, "benchwise-speedtest-%d.tmp" % os.getpid())
        self.size = size - size % SEQ_BLOCK
        self.progress = progress
        self.stop = False
        self.results = {}

    def _io(self, fn, h, buf, n):
        done = w.DWORD()
        if not fn(h, buf, n, ctypes.byref(done), None) or done.value != n:
            raise ctypes.WinError(ctypes.get_last_error())

    def _seek(self, h, pos):
        if not k32.SetFilePointerEx(h, pos, None, 0):
            raise ctypes.WinError(ctypes.get_last_error())

    def _sequential(self, key, h, buf, fn):
        self._seek(h, 0)
        pos, t0 = 0, time.perf_counter()
        while pos < self.size and not self.stop:
            self._io(fn, h, buf, SEQ_BLOCK)
            pos += SEQ_BLOCK
            self.progress(key, pos * 100 // self.size)
        secs = time.perf_counter() - t0
        if pos:
            self.results[key] = (pos / secs, None)

    def _random(self, key, h, buf, fn):
        blocks = self.size // RAND_BLOCK
        ops, t0 = 0, time.perf_counter()
        end = t0 + RAND_SECONDS
        while not self.stop:
            self._seek(h, random.randrange(blocks) * RAND_BLOCK)
            self._io(fn, h, buf, RAND_BLOCK)
            ops += 1
            if ops % 256 == 0:
                now = time.perf_counter()
                self.progress(key, int((now - t0) * 100 / RAND_SECONDS))
                if now >= end:
                    break
        secs = time.perf_counter() - t0
        if ops:
            self.results[key] = (ops * RAND_BLOCK / secs, ops / secs)

    def run(self):
        buf = k32.VirtualAlloc(None, SEQ_BLOCK, 0x3000, 0x04)      # page-aligned, as unbuffered I/O requires
        if not buf:
            raise MemoryError
        ctypes.memmove(buf, os.urandom(SEQ_BLOCK), SEQ_BLOCK)      # random data: no compression shortcuts
        h = k32.CreateFileW(self.path, GENERIC_RW, 0, None, CREATE_ALWAYS, FLAGS, None)
        if h in (None, INVALID):
            k32.VirtualFree(buf, 0, 0x8000)
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            for key, kind, fn in (("sw", self._sequential, k32.WriteFile), ("sr", self._sequential, k32.ReadFile),
                                  ("rr", self._random, k32.ReadFile), ("rw", self._random, k32.WriteFile)):
                if self.stop:
                    break
                kind(key, h, buf, fn)
        finally:
            k32.CloseHandle(h)                                       # delete-on-close removes the file
            k32.VirtualFree(buf, 0, 0x8000)
        return self.results


class View(ToolView):
    title_key = "tool_speed"

    def fill(self):
        self.bench = None
        c = card(self.body, t("tool_speed"))
        note(c, t("spd_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(row, text=t("spd_drive"), font=("Segoe UI", 12), text_color=ui.TEXT).pack(side="left")
        self.drive_list = drives()
        labels = ["%s  ·  %s" % (r.rstrip("\\"), t("spd_free", free=human(f))) for r, f in self.drive_list]
        self.drive = ctk.CTkOptionMenu(row, values=labels or ["-"], width=200, fg_color=ui.CARD, button_color=ui.BORDER,
                                       button_hover_color="#33405c", text_color=ui.TEXT)
        self.drive.pack(side="left", padx=10)
        ctk.CTkLabel(row, text=t("spd_size"), font=("Segoe UI", 12), text_color=ui.TEXT).pack(side="left", padx=(10, 6))
        self.sizes = {"256 MB": 256 << 20, "1 GB": 1 << 30, "4 GB": 4 << 30}
        self.size_seg = ctk.CTkSegmentedButton(row, values=list(self.sizes), font=("Segoe UI", 11), height=26,
                                               selected_color=ui.ACCENT, unselected_color=ui.CARD)
        self.size_seg.set("1 GB")
        self.size_seg.pack(side="left")
        self.start_btn = ui.button(row, t("spd_start"), self.start, 110, primary=True)
        self.start_btn.pack(side="left", padx=(16, 0))
        self.stop_btn = ui.button(row, t("spd_stop"), self.stop, 100)
        self.stop_btn.pack(side="left", padx=8)
        self.stop_btn.configure(state="disabled")
        self.status_line = ctk.CTkLabel(c, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w")
        self.status_line.pack(fill="x", padx=18)
        self.bar = ctk.CTkProgressBar(c, height=8, progress_color=ui.ACCENT, fg_color=ui.BORDER)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=18, pady=(6, 10))
        self.grid_box = ctk.CTkFrame(c, fg_color="transparent")
        self.grid_box.pack(fill="x", padx=0, pady=(0, 4))
        self.result = ctk.CTkLabel(c, text=" ", font=("Segoe UI Semibold", 13), text_color=ui.TEXT, anchor="w",
                                   justify="left", wraplength=760)
        self.result.pack(fill="x", padx=18, pady=(0, 14))
        self.show_results({})

        cap = card(self.body, t("spd_capacity"))
        note(cap, t("spd_capacity_note"))
        b = ui.button(cap, "🔒 " + t("spd_locked"), lambda: None, 140)
        b.configure(state="disabled")
        b.pack(anchor="w", padx=18, pady=(0, 14))

    def show_results(self, res):
        for w_ in self.grid_box.winfo_children():
            w_.destroy()
        rows = []
        for key in ("sw", "sr", "rr", "rw"):
            val = res.get(key)
            if val is None:
                text = "-"
            elif val[1] is None:
                text = t("spd_rate", speed=human(val[0]))
            else:
                text = t("spd_iops", speed=human(val[0]), iops="{:,}".format(int(val[1])).replace(",", " "))
            rows.append((t("spd_phase_" + key), text))
        kv_grid(self.grid_box, rows)

    def busy(self):
        return self.bench is not None

    def start(self):
        label = self.drive.get()
        match = [d for d in self.drive_list if label.startswith(d[0].rstrip("\\"))]
        if not match:
            return
        root, _ = match[0]
        size = self.sizes[self.size_seg.get()]
        folder = test_folder(root)
        if shutil.disk_usage(folder).free < size + (512 << 20):
            self.result.configure(text=t("spd_no_room"), text_color=ui.BAD)
            return
        self.show_results({})
        self.result.configure(text=" ", text_color=ui.TEXT)
        self.bench = Bench(folder, size, lambda k, p: self.post(self.progress, k, p))
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.run(self.bench.run, self.finished)

    def progress(self, key, pct):
        pct = max(0, min(100, pct))
        self.status_line.configure(text=t("spd_running", phase=t("spd_phase_" + key), pct=pct))
        self.bar.set(pct / 100)
        if self.bench:
            self.show_partial(self.bench.results)

    def show_partial(self, res):
        if len(res) != getattr(self, "_shown", -1):
            self._shown = len(res)
            self.show_results(dict(res))

    def stop(self):
        if self.bench:
            self.bench.stop = True

    def finished(self, res):
        bench, self.bench = self.bench, None
        self._shown = -1
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.bar.set(0 if bench and bench.stop else 1)
        self.status_line.configure(text=" ")
        if isinstance(res, Exception):
            self.result.configure(text=str(res), text_color=ui.BAD)
            return
        self.show_results(res)
        lines = [t("spd_stopped") if bench and bench.stop else t("spd_done")]
        seq = min((res[k][0] for k in ("sw", "sr") if k in res), default=None)
        if seq is not None and seq < 40e6:
            lines.append(t("spd_hint_usb2"))
        if "rr" in res and res["rr"][0] < 2e6:
            lines.append(t("spd_hint_hdd"))
        self.result.configure(text="\n".join(lines), text_color=ui.GOOD if not (bench and bench.stop) else ui.MUTED)

    def destroy(self):
        if self.bench:
            self.bench.stop = True
        super().destroy()
