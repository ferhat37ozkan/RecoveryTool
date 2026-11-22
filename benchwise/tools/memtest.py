"""System & Memory > Memory Test.

* Quick test, inside Benchwise: part of the free memory is filled with bit patterns and read back.
  Copies and comparisons run as memory operations (memcpy / memcmp), so gigabytes take seconds.
  Windows decides which physical pages we get, and most of the memory is in use by Windows, so this
  finds a failing module often but not always.
* Full test: Windows Memory Diagnostic checks all of the memory at the next restart; its last result
  is read from the event log.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import subprocess
import time

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, human, note, powershell_json, texts

texts({
    "mt_quick": ("Quick test (no restart)", "Hızlı test (yeniden başlatmadan)"),
    "mt_quick_how": ("Fills part of the free memory with patterns and reads them back. Takes seconds to a few "
                     "minutes. It cannot reach the memory Windows itself uses, so for a final answer run the full "
                     "test too.", "Boş belleğin bir kısmını desenlerle doldurup geri okur. Birkaç saniye ile birkaç "
                     "dakika sürer. Windows'un kendi kullandığı belleğe erişemez; kesin sonuç için tam testi de "
                     "çalıştırın."),
    "mt_amount": ("Amount to test", "Test edilecek miktar"),
    "mt_free": ("{free} free of {total}", "{total} belleğin {free} kadarı boş"),
    "mt_start": ("Start the quick test", "Hızlı testi başlat"),
    "mt_stop": ("Stop", "Durdur"),
    "mt_running": ("Pass {p} of {n}: pattern {name} · {done} / {total}", "Geçiş {p} / {n}: {name} deseni · {done} / {total}"),
    "mt_alloc": ("Reserving {size}…", "{size} ayrılıyor…"),
    "mt_alloc_failed": ("Windows would not give that much memory; try a smaller amount.",
                        "Windows bu kadar belleği vermedi; daha küçük bir miktar deneyin."),
    "mt_passed": ("No errors in {size} tested ({secs} s).", "Test edilen {size} içinde hata yok ({secs} sn)."),
    "mt_errors": ("{n} errors found: a memory module is faulty. Run the full test, then test the modules one by "
                  "one.", "{n} hata bulundu: bir bellek modülü arızalı. Tam testi çalıştırın, sonra modülleri tek "
                  "tek deneyin."),
    "mt_stopped": ("Stopped.", "Durduruldu."),
    "mt_full": ("Full test (at the next restart)", "Tam test (sonraki yeniden başlatmada)"),
    "mt_full_how": ("Windows Memory Diagnostic checks all of the memory before Windows starts. It opens its own "
                    "window: choose to restart now or at the next start. The result appears here afterwards.",
                    "Windows Bellek Tanılama, Windows başlamadan önce belleğin tamamını test eder. Kendi penceresi "
                    "açılır: şimdi veya bir sonraki açılışta yeniden başlatmayı seçin. Sonuç daha sonra burada "
                    "görünür."),
    "mt_full_start": ("Open Windows Memory Diagnostic", "Windows Bellek Tanılama'yı aç"),
    "mt_last": ("Last full test: {date} - {result}", "Son tam test: {date} - {result}"),
    "mt_last_none": ("No full test has been run on this computer yet (or its record was cleared).",
                     "Bu bilgisayarda henüz tam test yapılmamış (veya kaydı silinmiş)."),
    "mt_result_ok": ("no errors", "hata yok"),
    "mt_result_bad": ("ERRORS FOUND - a memory module is faulty", "HATA BULUNDU - bir bellek modülü arızalı"),
})

BLOCK = 64 << 20
PATTERNS = [("00", b"\x00"), ("FF", b"\xff"), ("AA", b"\xaa"), ("55", b"\x55"),
            ("ramp", bytes(range(256))), ("CC33", b"\xcc\x33")]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", w.DWORD), ("dwMemoryLoad", w.DWORD), ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64), ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64), ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64), ("ullAvailExtendedVirtual", ctypes.c_uint64)]


def memory():
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullTotalPhys, m.ullAvailPhys


def quick_test(size, progress, stop):
    """Fill ``size`` bytes in 64 MB blocks with each pattern and compare.  Returns (errors, tested)."""
    progress("alloc", 0, 0, size)
    blocks = []
    try:
        for _ in range(max(1, size // BLOCK)):
            if stop():
                return None
            blocks.append(bytearray(BLOCK))
    except MemoryError:
        blocks.clear()
        raise
    errors = 0
    total = len(blocks) * len(PATTERNS)
    done = 0
    for p, (name, unit) in enumerate(PATTERNS):
        reference = bytes(unit * (BLOCK // len(unit)))
        for b in blocks:
            if stop():
                return None
            b[:] = reference                    # write the pattern (memcpy)
        for b in blocks:
            if stop():
                return None
            if b != reference:                  # read it back (memcmp); count wrong bytes only when needed
                errors += sum(1 for i in range(0, BLOCK, 4096) if b[i:i + 4096] != reference[i:i + 4096])
            done += 1
            progress("run", p + 1, done, total, name)
    return errors, len(blocks) * BLOCK


LAST_RESULT = r"""
$e = Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-MemoryDiagnostics-Results' } -MaxEvents 1 -ErrorAction SilentlyContinue
if ($e) { [pscustomobject]@{ date = $e.TimeCreated.ToString('yyyy-MM-dd HH:mm'); id = $e.Id } | ConvertTo-Json -Compress }
"""


class View(ToolView):
    title_key = "tool_memtest"

    def fill(self):
        total, free = memory()
        self.total, self.free = total, free
        self.stop_flag = False
        q = card(self.body, t("mt_quick"))
        note(q, t("mt_quick_how"), color=ui.TEXT)
        row = ctk.CTkFrame(q, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 6))
        ctk.CTkLabel(row, text=t("mt_amount"), font=("Segoe UI", 12), text_color=ui.TEXT).pack(side="left")
        usable = max(0, free - (2 << 30))         # always leave 2 GB to Windows and the other programs
        choices = [g for g in (1, 2, 4, 8, 16, 32) if (g << 30) <= usable] or [0.5]
        self.sizes = {("%g GB" % g): int(g * (1 << 30)) for g in choices}
        default = [k for k in self.sizes if self.sizes[k] <= usable * 0.6][-1:] or list(self.sizes)[:1]
        self.amount = ctk.CTkSegmentedButton(row, values=list(self.sizes), font=("Segoe UI", 11), height=26,
                                             selected_color=ui.ACCENT, unselected_color=ui.CARD)
        self.amount.set(default[0])
        self.amount.pack(side="left", padx=10)
        ctk.CTkLabel(row, text=t("mt_free", free=human(free), total=human(total)), font=("Segoe UI", 11),
                     text_color=ui.MUTED).pack(side="left", padx=8)
        row2 = ctk.CTkFrame(q, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=(4, 4))
        self.start_btn = ui.button(row2, t("mt_start"), self.start, 190, primary=True)
        self.start_btn.pack(side="left")
        self.stop_btn = ui.button(row2, t("mt_stop"), self.stop, 100)
        self.stop_btn.pack(side="left", padx=8)
        self.stop_btn.configure(state="disabled")
        self.bar = ctk.CTkProgressBar(q, height=12, fg_color=ui.BORDER, progress_color=ui.ACCENT, corner_radius=6)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=18, pady=(6, 2))
        self.result = ctk.CTkLabel(q, text=" ", font=("Segoe UI Semibold", 12), text_color=ui.TEXT, anchor="w",
                                   justify="left", wraplength=720)
        self.result.pack(fill="x", padx=18, pady=(2, 14))

        f = card(self.body, t("mt_full"))
        note(f, t("mt_full_how"), color=ui.TEXT)
        ui.button(f, t("mt_full_start"), self.full, 260).pack(anchor="w", padx=18, pady=(0, 8))
        self.last = ctk.CTkLabel(f, text="…", font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w")
        self.last.pack(fill="x", padx=18, pady=(0, 14))
        self.run(lambda: powershell_json(LAST_RESULT), self.show_last)

    def show_last(self, res):
        if isinstance(res, Exception) or not res:
            self.last.configure(text=t("mt_last_none"), text_color=ui.MUTED)
            return
        bad = res.get("id") in (1102, 1202)
        self.last.configure(text=t("mt_last", date=res.get("date"), result=t("mt_result_bad" if bad else "mt_result_ok")),
                            text_color=ui.BAD if bad else ui.GOOD)

    def start(self):
        size = self.sizes[self.amount.get()]
        self.stop_flag = False
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.result.configure(text=" ")
        t0 = time.time()

        def progress(kind, p, done, total, name=""):
            if kind == "alloc":
                self.post(self.result.configure, {"text": t("mt_alloc", size=human(total)), "text_color": ui.MUTED})
            else:
                self.post(self.show_progress, p, done, total, name)

        def work():
            try:
                return quick_test(size, progress, lambda: self.stop_flag), time.time() - t0
            except MemoryError:
                return "nomem", 0

        self.run(work, self.finished)

    def show_progress(self, p, done, total, name):
        self.bar.set(done / total if total else 0)
        per = total // len(PATTERNS)
        self.result.configure(text=t("mt_running", p=p, n=len(PATTERNS), name=name,
                                     done=human((done - (p - 1) * per) * BLOCK), total=human(per * BLOCK)),
                              text_color=ui.MUTED)

    def stop(self):
        self.stop_flag = True

    def finished(self, res):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if isinstance(res, Exception):
            self.result.configure(text=str(res), text_color=ui.BAD)
            return
        outcome, secs = res
        if outcome == "nomem":
            self.result.configure(text=t("mt_alloc_failed"), text_color=ui.WARN)
        elif outcome is None:
            self.result.configure(text=t("mt_stopped"), text_color=ui.MUTED)
            self.bar.set(0)
        else:
            errors, tested = outcome
            self.bar.set(1)
            if errors:
                self.result.configure(text=t("mt_errors", n=errors), text_color=ui.BAD)
            else:
                self.result.configure(text=t("mt_passed", size=human(tested), secs=int(secs)), text_color=ui.GOOD)

    def full(self):
        subprocess.Popen(["mdsched.exe"])
