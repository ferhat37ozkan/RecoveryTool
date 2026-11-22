"""System & Memory > CPU Stress Test.

One thread per logical processor hashes a 1 MB buffer with SHA-256 again and again.  hashlib releases
Python's lock for large inputs, so every core really runs at full load.  Each result is compared with
the known answer: an unstable processor (overclock, undervolt, overheating) computes a wrong one,
which is counted as an error.  Windows has no standard way to report the processor temperature; when
the ACPI thermal zone gives one, the test stops at STOP_AT_C.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import hashlib
import os
import threading
import time

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, note, powershell_json, texts

texts({
    "st_how": ("Loads every processor core to 100 % and checks every result. Errors mean the processor is "
               "unstable (too much overclock, too little voltage, overheating). Watch the temperature with the "
               "maker's tool if Windows does not report it here.",
               "İşlemcinin bütün çekirdeklerini %100 yükler ve her sonucu kontrol eder. Hata, işlemcinin "
               "kararsız olduğu anlamına gelir (fazla hız aşırtma, düşük voltaj, aşırı ısınma). Windows sıcaklığı "
               "burada bildirmiyorsa üreticinin aracıyla izleyin."),
    "st_duration": ("Duration", "Süre"),
    "st_minutes": ("{n} min", "{n} dk"),
    "st_start": ("Start", "Başlat"),
    "st_stop": ("Stop", "Durdur"),
    "st_threads": ("{n} threads", "{n} iş parçacığı"),
    "st_elapsed": ("Elapsed", "Geçen süre"),
    "st_load": ("Processor load", "İşlemci yükü"),
    "st_score": ("Score (hashes per second)", "Puan (saniyede özet)"),
    "st_errors": ("Calculation errors", "Hesaplama hatası"),
    "st_temp": ("Temperature", "Sıcaklık"),
    "st_not_reported": ("not reported by Windows", "Windows bildirmiyor"),
    "st_done_ok": ("Finished: no calculation errors in {mins} minutes.", "Bitti: {mins} dakikada hiç hesaplama hatası yok."),
    "st_done_bad": ("{n} calculation errors: the processor is not stable under load.",
                    "{n} hesaplama hatası: işlemci yük altında kararlı değil."),
    "st_hot_stop": ("Stopped at {temp} °C to protect the processor.", "İşlemciyi korumak için {temp} °C'de durduruldu."),
    "st_throttle": ("The score dropped by {pct} % during the test: the processor slowed down (heat or power "
                    "limit).", "Test sırasında puan %{pct} düştü: işlemci yavaşladı (ısı veya güç sınırı)."),
    "st_stopped": ("Stopped.", "Durduruldu."),
})

STOP_AT_C = 95
BUF = os.urandom(1 << 20)
EXPECTED = hashlib.sha256(BUF).digest()


class FILETIME(ctypes.Structure):
    _fields_ = [("lo", w.DWORD), ("hi", w.DWORD)]


def cpu_times():
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    v = lambda f: (f.hi << 32) | f.lo
    return v(idle), v(kernel) + v(user)


def thermal_c():
    """ACPI thermal zone temperature in °C, or None (most desktops do not expose one)."""
    try:
        res = powershell_json("Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature | "
                              "Select-Object -First 1 -ExpandProperty CurrentTemperature | ConvertTo-Json", timeout=15)
        if isinstance(res, (int, float)) and res > 0:
            c = res / 10.0 - 273.15
            return round(c) if 0 < c < 130 else None
    except Exception:
        pass
    return None


class Stress:
    def __init__(self, threads):
        self.count = [0] * threads
        self.errors = 0
        self.stop = False
        self.workers = [threading.Thread(target=self._work, args=(i,), daemon=True) for i in range(threads)]
        for th in self.workers:
            th.start()

    def _work(self, i):
        while not self.stop:
            if hashlib.sha256(BUF).digest() != EXPECTED:
                self.errors += 1
            self.count[i] += 1

    def total(self):
        return sum(self.count)

    def end(self):
        self.stop = True


class View(ToolView):
    title_key = "tool_stress"

    def fill(self):
        self.job = None
        c = card(self.body, t("tool_stress"))
        note(c, t("st_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(row, text=t("st_duration"), font=("Segoe UI", 12), text_color=ui.TEXT).pack(side="left")
        self.minutes = {t("st_minutes", n=n): n for n in (1, 5, 10)}
        self.duration = ctk.CTkSegmentedButton(row, values=list(self.minutes), font=("Segoe UI", 11), height=26,
                                               selected_color=ui.ACCENT, unselected_color=ui.CARD)
        self.duration.set(list(self.minutes)[0])
        self.duration.pack(side="left", padx=10)
        ctk.CTkLabel(row, text=t("st_threads", n=os.cpu_count()), font=("Segoe UI", 11), text_color=ui.MUTED).pack(side="left")
        self.start_btn = ui.button(row, t("st_start"), self.start, 120, primary=True)
        self.start_btn.pack(side="right")
        self.stop_btn = ui.button(row, t("st_stop"), self.stop, 100)
        self.stop_btn.pack(side="right", padx=8)
        self.stop_btn.configure(state="disabled")
        self.bar = ctk.CTkProgressBar(c, height=12, fg_color=ui.BORDER, progress_color=ui.ACCENT, corner_radius=6)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=18, pady=(4, 10))
        tiles = ctk.CTkFrame(c, fg_color="transparent")
        tiles.pack(fill="x", padx=18, pady=(0, 8))
        self.values = {}
        for i, key in enumerate(("st_elapsed", "st_load", "st_score", "st_errors", "st_temp")):
            tile = ui.card(tiles)
            tile.grid(row=0, column=i, sticky="nsew", padx=(0, 8))
            tiles.grid_columnconfigure(i, weight=1, uniform="t")
            ctk.CTkLabel(tile, text=t(key), font=("Segoe UI", 11), text_color=ui.MUTED, anchor="w").pack(fill="x", padx=12, pady=(8, 0))
            self.values[key] = ctk.CTkLabel(tile, text="–", font=("Segoe UI Semibold", 16), text_color=ui.TEXT, anchor="w")
            self.values[key].pack(fill="x", padx=12, pady=(0, 8))
        self.result = ctk.CTkLabel(c, text=" ", font=("Segoe UI Semibold", 12), text_color=ui.TEXT, anchor="w",
                                   justify="left", wraplength=720)
        self.result.pack(fill="x", padx=18, pady=(0, 14))

    def busy(self):
        return self.job is not None

    def start(self):
        self.job = {"stress": Stress(os.cpu_count() or 4), "t0": time.time(), "secs": self.minutes[self.duration.get()] * 60,
                    "cpu": cpu_times(), "last": (time.time(), 0), "first_rate": None, "rate": 0.0, "min_rate": None,
                    "temp": None, "temp_at": 0.0, "hot": None}
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.result.configure(text=" ")
        self.after(1000, self.tick)

    def tick(self):
        j = self.job
        if j is None:
            return
        now = time.time()
        elapsed = now - j["t0"]
        s = j["stress"]
        idle, busy = cpu_times()
        di, db = idle - j["cpu"][0], busy - j["cpu"][1]
        j["cpu"] = (idle, busy)
        load = int(100 * (db - di) / db) if db else 0
        t_last, c_last = j["last"]
        total = s.total()
        rate = (total - c_last) / max(now - t_last, 0.001)
        j["last"] = (now, total)
        if elapsed > 10:                                   # after the warm-up
            j["first_rate"] = j["first_rate"] or rate
            j["min_rate"] = rate if j["min_rate"] is None else min(j["min_rate"], 0.7 * j["min_rate"] + 0.3 * rate)
        if now - j["temp_at"] > 10:
            j["temp_at"] = now
            threading.Thread(target=lambda: j.__setitem__("temp", thermal_c()), daemon=True).start()
        self.values["st_elapsed"].configure(text="%d:%02d" % divmod(int(elapsed), 60))
        self.values["st_load"].configure(text=t("dh_pct", n=max(0, min(100, load))))
        self.values["st_score"].configure(text="{:,}".format(int(rate)).replace(",", " "))
        self.values["st_errors"].configure(text=str(s.errors), text_color=ui.BAD if s.errors else ui.GOOD)
        temp = j["temp"]
        self.values["st_temp"].configure(text="%d °C" % temp if temp is not None else t("st_not_reported"),
                                         font=("Segoe UI Semibold", 16 if temp is not None else 11))
        self.bar.set(min(1.0, elapsed / j["secs"]))
        if temp is not None and temp >= STOP_AT_C:
            j["hot"] = temp
            return self.finish()
        if elapsed >= j["secs"]:
            return self.finish()
        self.after(1000, self.tick)

    def stop(self):
        if self.job:
            self.job["stopped"] = True
            self.finish()

    def finish(self):
        j, self.job = self.job, None
        if j is None:
            return
        j["stress"].end()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        lines, color = [], ui.GOOD
        errors = j["stress"].errors
        if j.get("hot"):
            lines.append(t("st_hot_stop", temp=j["hot"]))
            color = ui.WARN
        elif j.get("stopped"):
            lines.append(t("st_stopped"))
            color = ui.MUTED
        if errors:
            lines.insert(0, t("st_done_bad", n=errors))
            color = ui.BAD
        elif not j.get("stopped") and not j.get("hot"):
            lines.append(t("st_done_ok", mins=int(j["secs"] // 60)))
        if j["first_rate"] and j["min_rate"] and j["min_rate"] < 0.85 * j["first_rate"]:
            lines.append(t("st_throttle", pct=int(100 - 100 * j["min_rate"] / j["first_rate"])))
            color = ui.WARN if color == ui.GOOD else color
        self.result.configure(text="\n".join(lines), text_color=color)

    def destroy(self):
        if self.job:
            self.job["stress"].end()
        super().destroy()
