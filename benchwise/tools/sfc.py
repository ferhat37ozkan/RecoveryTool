"""Windows Repair > System File Repair: DISM (the Windows image) and SFC (the system files) with live
progress, in the order Microsoft recommends: DISM /RestoreHealth first, then SFC /scannow."""

from __future__ import annotations

import os
import re
import subprocess

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, note, texts

texts({
    "sf_how": ("Quick check only looks (seconds). Repair first fixes the Windows image with DISM - it may "
               "download parts from Windows Update - then SFC replaces damaged system files. It can take 15-45 "
               "minutes; the computer stays usable.",
               "Hızlı kontrol yalnızca bakar (saniyeler). Onarım önce DISM ile Windows görüntüsünü düzeltir - "
               "Windows Update'ten parça indirebilir - sonra SFC bozuk sistem dosyalarını değiştirir. 15-45 dakika "
               "sürebilir; bu sırada bilgisayar kullanılabilir."),
    "sf_check": ("Quick check", "Hızlı kontrol"),
    "sf_repair": ("Repair (DISM + SFC)", "Onar (DISM + SFC)"),
    "sf_step_check": ("Checking the Windows image (DISM /CheckHealth)…", "Windows görüntüsü kontrol ediliyor (DISM /CheckHealth)…"),
    "sf_step_dism": ("Repairing the Windows image (DISM /RestoreHealth)…", "Windows görüntüsü onarılıyor (DISM /RestoreHealth)…"),
    "sf_step_sfc": ("Checking and repairing system files (SFC /scannow)…", "Sistem dosyaları kontrol ediliyor ve onarılıyor (SFC /scannow)…"),
    "sf_ok": ("No problems found.", "Sorun bulunamadı."),
    "sf_fixed": ("Damaged files were found and repaired. Restart the computer.",
                 "Bozuk dosyalar bulundu ve onarıldı. Bilgisayarı yeniden başlatın."),
    "sf_unfixed": ("Damaged files were found that could not all be repaired. Details: {log}",
                   "Bozuk dosyalar bulundu ama hepsi onarılamadı. Ayrıntılar: {log}"),
    "sf_image_bad": ("The Windows image is damaged: run Repair.", "Windows görüntüsü bozuk: Onar'ı çalıştırın."),
    "sf_failed": ("The tool ended with an error (code {code}). See the log below.",
                  "Araç bir hatayla bitti (kod {code}). Aşağıdaki kayda bakın."),
    "sf_running": ("{step}  {pct}", "{step}  {pct}"),
})

PCT = re.compile(r"(\d{1,3}(?:[.,]\d)?)\s?%")
CBS_LOG = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Logs", "CBS", "CBS.log")


def decode(raw):
    """SFC writes UTF-16 to a pipe; DISM writes the console (OEM) code page."""
    if raw.count(b"\x00") > len(raw) // 4:
        return raw.decode("utf-16-le", "replace")
    for enc in ("cp857", "cp850", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def run_streaming(cmd, on_text):
    """Run a console tool, handing each progress chunk (split on CR and LF) to ``on_text``; returns
    (exit code, whole output)."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=flags)
    raw = b""
    pending = b""
    while True:
        chunk = p.stdout.read1(4096) if hasattr(p.stdout, "read1") else p.stdout.read(4096)
        if not chunk:
            break
        raw += chunk
        pending += chunk
        text = decode(pending)
        if "\r" in text or "\n" in text:
            on_text(text)
            pending = b""
    p.wait()
    return p.returncode, decode(raw)


class View(ToolView):
    title_key = "tool_sfc"

    def fill(self):
        c = card(self.body, t("tool_sfc"))
        note(c, t("sf_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        self.check_btn = ui.button(row, t("sf_check"), lambda: self.start(False), 140)
        self.check_btn.pack(side="left")
        self.repair_btn = ui.button(row, t("sf_repair"), lambda: self.start(True), 180, primary=True)
        self.repair_btn.pack(side="left", padx=8)
        self.step = ctk.CTkLabel(c, text=" ", font=("Segoe UI Semibold", 12), text_color=ui.TEXT, anchor="w")
        self.step.pack(fill="x", padx=18)
        self.bar = ctk.CTkProgressBar(c, height=12, fg_color=ui.BORDER, progress_color=ui.ACCENT, corner_radius=6)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=18, pady=(6, 6))
        self.result = ctk.CTkLabel(c, text=" ", font=("Segoe UI Semibold", 13), text_color=ui.TEXT, anchor="w",
                                   justify="left", wraplength=760)
        self.result.pack(fill="x", padx=18, pady=(0, 8))
        self.log = ctk.CTkTextbox(c, fg_color=ui.BG, text_color=ui.TEXT, font=("Consolas", 11), height=220,
                                  corner_radius=8, border_width=0)
        self.log.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    def progress(self, step, text):
        found = PCT.findall(text)
        if found:
            pct = float(found[-1].replace(",", "."))
            self.bar.set(min(1.0, pct / 100))
            self.step.configure(text=t("sf_running", step=t(step), pct="%d %%" % pct))

    def start(self, repair):
        self.check_btn.configure(state="disabled")
        self.repair_btn.configure(state="disabled")
        self.log.delete("1.0", "end")
        self.result.configure(text=" ")

        def step(key, cmd):
            self.post(self.step.configure, {"text": t(key)})
            self.post(self.bar.set, 0)
            code, out = run_streaming(cmd, lambda text: self.post(self.progress, key, text))
            lines = [ln.strip() for ln in re.split(r"[\r\n]+", out) if ln.strip() and not PCT.fullmatch(ln.strip())]
            self.post(self.write, "> " + " ".join(cmd) + "\n" + "\n".join(lines[-12:]) + "\n")
            return code, out

        def work():
            if not repair:
                return [("check",) + step("sf_step_check", ["DISM.exe", "/Online", "/Cleanup-Image", "/CheckHealth"])]
            return [("dism",) + step("sf_step_dism", ["DISM.exe", "/Online", "/Cleanup-Image", "/RestoreHealth"]),
                    ("sfc",) + step("sf_step_sfc", ["sfc.exe", "/scannow"])]

        self.run(work, self.finished)

    def write(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def finished(self, res):
        self.check_btn.configure(state="normal")
        self.repair_btn.configure(state="normal")
        self.step.configure(text=" ")
        if isinstance(res, Exception):
            self.result.configure(text=str(res), text_color=ui.BAD)
            return
        self.bar.set(1)
        msgs, color = [], ui.GOOD
        for kind, code, out in res:
            low = out.lower()
            if code not in (0, None):
                msgs.append(t("sf_failed", code=code))
                color = ui.BAD
            elif kind == "check" and ("repairable" in low or "onarılabilir" in low or "corrupt" in low):
                msgs.append(t("sf_image_bad"))
                color = ui.WARN
            elif kind == "sfc" and ("successfully repaired" in low or "başarıyla onardı" in low):
                msgs.append(t("sf_fixed"))
                color = ui.WARN
            elif kind == "sfc" and ("unable to fix" in low or "onaramadı" in low):
                msgs.append(t("sf_unfixed", log=CBS_LOG))
                color = ui.BAD
        self.result.configure(text="\n".join(msgs) or t("sf_ok"), text_color=color)
