"""System & Memory > Crash Analysis: blue screens, hardware (WHEA) errors and unexpected shutdowns from
the Windows event log, with a plain explanation of each stop code, and the crash dump files.

Naming the exact driver behind a blue screen needs Microsoft's debugger and symbol server; this tool
says which kind of part a stop code usually points to instead.
"""

from __future__ import annotations

import os
import subprocess

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, as_list, card, human, note, powershell_json, scroll_body, table, texts

texts({
    "cr_loading": ("Reading the event log…", "Olay günlüğü okunuyor…"),
    "cr_bsod": ("Blue screens", "Mavi ekranlar"),
    "cr_bsod_none": ("No blue screen recorded. ", "Kayıtlı mavi ekran yok."),
    "cr_whea": ("Hardware errors (WHEA)", "Donanım hataları (WHEA)"),
    "cr_whea_none": ("No hardware errors recorded.", "Kayıtlı donanım hatası yok."),
    "cr_whea_note": ("Reported by the processor, memory controller or PCIe bus itself. A few corrected errors can "
                     "be harmless; many, or uncorrected ones, point to unstable hardware (overclock, memory, power).",
                     "İşlemci, bellek denetleyicisi veya PCIe yolunun kendisi bildirir. Birkaç düzeltilmiş hata "
                     "zararsız olabilir; çok sayıda ya da düzeltilemeyen hata kararsız donanıma işaret eder "
                     "(hız aşırtma, bellek, güç)."),
    "cr_power": ("Unexpected shutdowns", "Beklenmedik kapanmalar"),
    "cr_power_none": ("No unexpected shutdowns recorded.", "Kayıtlı beklenmedik kapanma yok."),
    "cr_power_note": ("Windows did not shut down normally: a power cut, holding the power button, or a freeze / "
                      "reset without a blue screen.", "Windows normal kapanmadı: elektrik kesintisi, güç düğmesine "
                      "basılı tutma ya da mavi ekransız bir donma / yeniden başlama."),
    "cr_dumps": ("Crash dump files", "Çökme döküm dosyaları"),
    "cr_dumps_none": ("No crash dump files.", "Çökme döküm dosyası yok."),
    "cr_open_dumps": ("Open the folder", "Klasörü aç"),
    "cr_col_date": ("Date", "Tarih"),
    "cr_col_code": ("Stop code", "Hata kodu"),
    "cr_col_meaning": ("What it usually means", "Genellikle ne anlama gelir"),
    "cr_col_source": ("Source", "Kaynak"),
    "cr_col_file": ("File", "Dosya"),
    "cr_col_size": ("Size", "Boyut"),
    "cr_unknown_code": ("Less common code: search for it with the code number.",
                        "Daha seyrek bir kod: kod numarasıyla aratın."),
    "cr_summary": ("Last 90 days: {b} blue screens, {w} hardware errors, {p} unexpected shutdowns.",
                   "Son 90 gün: {b} mavi ekran, {w} donanım hatası, {p} beklenmedik kapanma."),
    "cr_hint_driver": ("a driver", "bir sürücü"),
    "cr_hint_memory": ("memory (RAM)", "bellek (RAM)"),
    "cr_hint_disk": ("the disk or its cable", "disk veya kablosu"),
    "cr_hint_gpu": ("the graphics card or its driver", "ekran kartı veya sürücüsü"),
    "cr_hint_hw": ("hardware (CPU, memory, power, overclock)", "donanım (işlemci, bellek, güç, hız aşırtma)"),
    "cr_hint_sys": ("a system file or service", "bir sistem dosyası veya servis"),
})

# stop code -> (name, likely part)
CODES = {
    0x0A: ("IRQL_NOT_LESS_OR_EQUAL", "driver"), 0x1A: ("MEMORY_MANAGEMENT", "memory"),
    0x1E: ("KMODE_EXCEPTION_NOT_HANDLED", "driver"), 0x19: ("BAD_POOL_HEADER", "driver"),
    0x24: ("NTFS_FILE_SYSTEM", "disk"), 0x3B: ("SYSTEM_SERVICE_EXCEPTION", "driver"),
    0x4E: ("PFN_LIST_CORRUPT", "memory"), 0x50: ("PAGE_FAULT_IN_NONPAGED_AREA", "memory"),
    0x7A: ("KERNEL_DATA_INPAGE_ERROR", "disk"), 0x77: ("KERNEL_STACK_INPAGE_ERROR", "disk"),
    0x7E: ("SYSTEM_THREAD_EXCEPTION_NOT_HANDLED", "driver"), 0x7F: ("UNEXPECTED_KERNEL_MODE_TRAP", "hw"),
    0x9F: ("DRIVER_POWER_STATE_FAILURE", "driver"), 0xA0: ("INTERNAL_POWER_ERROR", "driver"),
    0xC2: ("BAD_POOL_CALLER", "driver"), 0xC4: ("DRIVER_VERIFIER_DETECTED_VIOLATION", "driver"),
    0xC5: ("DRIVER_CORRUPTED_EXPOOL", "driver"), 0xD1: ("DRIVER_IRQL_NOT_LESS_OR_EQUAL", "driver"),
    0xEF: ("CRITICAL_PROCESS_DIED", "sys"), 0xF4: ("CRITICAL_OBJECT_TERMINATION", "disk"),
    0xFC: ("ATTEMPTED_EXECUTE_OF_NOEXECUTE_MEMORY", "driver"), 0x101: ("CLOCK_WATCHDOG_TIMEOUT", "hw"),
    0x109: ("CRITICAL_STRUCTURE_CORRUPTION", "memory"), 0x10E: ("VIDEO_MEMORY_MANAGEMENT_INTERNAL", "gpu"),
    0x113: ("VIDEO_DXGKRNL_FATAL_ERROR", "gpu"), 0x116: ("VIDEO_TDR_FAILURE", "gpu"),
    0x117: ("VIDEO_TDR_TIMEOUT_DETECTED", "gpu"), 0x119: ("VIDEO_SCHEDULER_INTERNAL_ERROR", "gpu"),
    0x124: ("WHEA_UNCORRECTABLE_ERROR", "hw"), 0x133: ("DPC_WATCHDOG_VIOLATION", "driver"),
    0x139: ("KERNEL_SECURITY_CHECK_FAILURE", "driver"), 0x13A: ("KERNEL_MODE_HEAP_CORRUPTION", "driver"),
    0x154: ("UNEXPECTED_STORE_EXCEPTION", "disk"), 0x1D3: ("UNEXPECTED_SHUTDOWN", "hw"),
    0x7B: ("INACCESSIBLE_BOOT_DEVICE", "disk"), 0xED: ("UNMOUNTABLE_BOOT_VOLUME", "disk"),
    0x12B: ("FAULTY_HARDWARE_CORRUPTED_PAGE", "memory"), 0x1000007E: ("SYSTEM_THREAD_EXCEPTION_NOT_HANDLED_M", "driver"),
    0x1000008E: ("KERNEL_MODE_EXCEPTION_NOT_HANDLED_M", "driver"),
    0xA0000001: ("graphics driver crash (AMD)", "gpu"), 0x8E: ("KERNEL_MODE_EXCEPTION_NOT_HANDLED", "driver"),
    0x9C: ("MACHINE_CHECK_EXCEPTION", "hw"), 0x1D: ("UNEXPECTED_INITIALIZATION_CALL", "driver"),
}

SCRIPT = r"""
$since = (Get-Date).AddDays(-90)
$b = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 1001; ProviderName = 'Microsoft-Windows-WER-SystemErrorReporting'; StartTime = $since } -ErrorAction SilentlyContinue |
  ForEach-Object { [pscustomobject]@{ date = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm'); text = $_.Properties[0].Value } })
$k = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 41; ProviderName = 'Microsoft-Windows-Kernel-Power'; StartTime = $since } -ErrorAction SilentlyContinue |
  ForEach-Object { [pscustomobject]@{ date = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm'); code = [int64]$_.Properties[0].Value } })
$w = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-WHEA-Logger'; StartTime = $since } -ErrorAction SilentlyContinue |
  Select-Object -First 200 | ForEach-Object { [pscustomobject]@{ date = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm'); id = $_.Id; level = $_.LevelDisplayName; text = ($_.Message -split "`n")[0] } })
$d = @(Get-ChildItem "$env:SystemRoot\Minidump\*.dmp", "$env:SystemRoot\MEMORY.DMP" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | ForEach-Object { [pscustomobject]@{ name = $_.FullName; date = $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm'); size = $_.Length } })
[pscustomobject]@{ bsod = $b; power = $k; whea = $w; dumps = $d } | ConvertTo-Json -Depth 4 -Compress
"""


def stop_code(text):
    """The stop code from a "The computer has rebooted from a bugcheck. The bugcheck was: 0x000000d1 (...)" text
    (or a bare number)."""
    import re
    if isinstance(text, int):
        return text
    m = re.search(r"0x([0-9a-fA-F]{1,16})", str(text or ""))
    return int(m.group(1), 16) if m else None


def meaning(code):
    if code is None:
        return "?", t("cr_unknown_code")
    name, part = CODES.get(code, (None, None))
    if not name:
        return "0x%X" % code, t("cr_unknown_code")
    return "0x%X %s" % (code, name), t("cr_hint_" + part)


class View(ToolView):
    title_key = "tool_crash"

    def fill(self):
        self.page = scroll_body(self)
        note(self.page, t("cr_loading"))
        self.run(lambda: powershell_json(SCRIPT, timeout=180), self.show, status=t("cr_loading"))

    def show(self, data):
        for w_ in self.page.winfo_children():
            w_.destroy()
        if isinstance(data, Exception) or not isinstance(data, dict):
            note(self.page, str(data), color=ui.BAD)
            return
        bsod, power, whea, dumps = (as_list(data.get(k)) for k in ("bsod", "power", "whea", "dumps"))
        crashes_from_power = [p for p in power if p.get("code")]      # Kernel-Power 41 with a stop code = a blue screen too
        rows = [(b["date"], stop_code(b.get("text"))) for b in bsod]
        rows += [(p["date"], p["code"]) for p in crashes_from_power if p["date"] not in {r[0] for r in rows}]
        summary = t("cr_summary", b=len(rows), w=len(whea), p=len(power) - len(crashes_from_power))
        note(self.page, summary, color=ui.BAD if rows or whea else ui.GOOD if not power else ui.WARN, padx=4)

        c = card(self.page, t("cr_bsod"))
        if rows:
            holder, tree = table(c, [("date", t("cr_col_date"), 140), ("code", t("cr_col_code"), 330),
                                     ("meaning", t("cr_col_meaning"), 300)], height=min(10, len(rows)), stretch="meaning")
            holder.pack(fill="x", padx=16, pady=(0, 12))
            for date, code in sorted(rows, reverse=True):
                name, hint = meaning(code)
                tree.insert("", "end", values=(date, name, hint), tags=("bad",))
        else:
            note(c, t("cr_bsod_none"), color=ui.GOOD)

        c = card(self.page, t("cr_whea"))
        if whea:
            note(c, t("cr_whea_note"))
            holder, tree = table(c, [("date", t("cr_col_date"), 140), ("source", t("cr_col_source"), 520)],
                                 height=min(8, len(whea)), stretch="source")
            holder.pack(fill="x", padx=16, pady=(0, 12))
            for e in whea:
                tree.insert("", "end", values=(e.get("date"), e.get("text") or e.get("id")),
                            tags=("bad",) if e.get("level") in ("Error", "Hata", "Critical", "Kritik") else ("warn",))
        else:
            note(c, t("cr_whea_none"), color=ui.GOOD)

        c = card(self.page, t("cr_power"))
        plain = [p for p in power if not p.get("code")]
        if plain:
            note(c, t("cr_power_note"))
            note(c, ", ".join(p["date"] for p in plain[:12]) + (" …" if len(plain) > 12 else ""), color=ui.WARN)
        else:
            note(c, t("cr_power_none"), color=ui.GOOD)

        c = card(self.page, t("cr_dumps"))
        if dumps:
            holder, tree = table(c, [("file", t("cr_col_file"), 420), ("date", t("cr_col_date"), 140),
                                     ("size", t("cr_col_size"), 100)], height=min(6, len(dumps)), stretch="file")
            holder.pack(fill="x", padx=16, pady=(0, 8))
            for d in dumps:
                tree.insert("", "end", values=(d.get("name"), d.get("date"), human(d.get("size"))))
        else:
            note(c, t("cr_dumps_none"), color=ui.GOOD)
        ui.button(c, t("cr_open_dumps"), self.open_folder, 140).pack(anchor="w", padx=18, pady=(0, 12))

    def open_folder(self):
        folder = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Minidump")
        subprocess.Popen(["explorer.exe", folder if os.path.isdir(folder) else os.path.dirname(folder)])
