"""System & Memory > System Information: processor, board, BIOS, memory modules slot by slot,
graphics (with the real amount of video memory), disks, network adapters, Windows.  Save or copy as text."""

from __future__ import annotations

import datetime
import os
from tkinter import filedialog

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, as_list, card, human, kv_grid, note, powershell_json, scroll_body, table, texts

texts({
    "si_loading": ("Reading the hardware…", "Donanım okunuyor…"),
    "si_failed": ("Could not read the hardware: {err}", "Donanım okunamadı: {err}"),
    "si_computer": ("Computer", "Bilgisayar"),
    "si_cpu": ("Processor", "İşlemci"),
    "si_board": ("Motherboard and BIOS", "Anakart ve BIOS"),
    "si_memory": ("Memory", "Bellek"),
    "si_gpu": ("Graphics", "Ekran kartı"),
    "si_disks": ("Disks", "Diskler"),
    "si_net": ("Network adapters", "Ağ kartları"),
    "si_os": ("Windows", "Windows"),
    "si_maker": ("Maker", "Üretici"),
    "si_model": ("Model", "Model"),
    "si_serial": ("Serial number", "Seri numarası"),
    "si_name": ("Name", "Ad"),
    "si_cores": ("Cores / threads", "Çekirdek / iş parçacığı"),
    "si_clock": ("Base clock", "Temel saat hızı"),
    "si_cache": ("Cache L2 / L3", "Önbellek L2 / L3"),
    "si_socket": ("Socket", "Soket"),
    "si_bios": ("BIOS", "BIOS"),
    "si_bios_date": ("BIOS date", "BIOS tarihi"),
    "si_total_ram": ("Installed", "Takılı"),
    "si_slots": ("Slots", "Slotlar"),
    "si_slots_used": ("{used} of {total} used", "{total} slottan {used} tanesi dolu"),
    "si_max_ram": ("Board maximum", "Anakartın azami desteği"),
    "si_col_slot": ("Slot", "Slot"),
    "si_col_size": ("Size", "Boyut"),
    "si_col_speed": ("Speed", "Hız"),
    "si_col_maker": ("Maker", "Üretici"),
    "si_col_part": ("Part number", "Parça numarası"),
    "si_vram": ("Video memory", "Video belleği"),
    "si_driver": ("Driver", "Sürücü"),
    "si_resolution": ("Resolution", "Çözünürlük"),
    "si_edition": ("Edition", "Sürüm"),
    "si_build": ("Version / build", "Sürüm / derleme"),
    "si_installed": ("Installed on", "Kurulum tarihi"),
    "si_boot": ("Started", "Son açılış"),
    "si_save": ("Save report", "Raporu kaydet"),
    "si_copy": ("Copy", "Kopyala"),
    "si_copied": ("Copied to the clipboard.", "Panoya kopyalandı."),
    "si_saved": ("Saved: {path}", "Kaydedildi: {path}"),
    "si_mhz": ("{n} MHz", "{n} MHz"),
    "si_link": ("Speed", "Hız"),
})

SCRIPT = r"""
function D($v) { if ($v) { ([datetime]$v).ToString('yyyy-MM-dd HH:mm') } else { $null } }
$cs = Get-CimInstance Win32_ComputerSystem; $bb = Get-CimInstance Win32_BaseBoard; $bios = Get-CimInstance Win32_BIOS
$os = Get-CimInstance Win32_OperatingSystem; $arr = Get-CimInstance Win32_PhysicalMemoryArray
$vram = @{}
Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}' -ErrorAction SilentlyContinue |
  ForEach-Object { $p = Get-ItemProperty $_.PSPath; if ($p.DriverDesc -and $p.'HardwareInformation.qwMemorySize') { $vram[$p.DriverDesc] = [int64]$p.'HardwareInformation.qwMemorySize' } }
[pscustomobject]@{
  computer = [pscustomobject]@{ maker = $cs.Manufacturer; model = $cs.Model; ram = [int64]$cs.TotalPhysicalMemory; name = $cs.Name }
  cpu = @(Get-CimInstance Win32_Processor | ForEach-Object { [pscustomobject]@{ name = $_.Name.Trim(); cores = $_.NumberOfCores;
        threads = $_.NumberOfLogicalProcessors; mhz = $_.MaxClockSpeed; l2 = $_.L2CacheSize; l3 = $_.L3CacheSize; socket = $_.SocketDesignation } })
  board = [pscustomobject]@{ maker = $bb.Manufacturer; model = $bb.Product; serial = $bb.SerialNumber; bios = ($bios.Manufacturer + ' ' + $bios.SMBIOSBIOSVersion).Trim();
        bios_date = D $bios.ReleaseDate; pc_serial = $bios.SerialNumber }
  slots = [int](($arr | Measure-Object -Property MemoryDevices -Sum).Sum); max_ram = [int64](($arr | Measure-Object -Property MaxCapacityEx -Sum).Sum)
  ram = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object { [pscustomobject]@{ slot = $_.DeviceLocator; bank = $_.BankLabel;
        size = [int64]$_.Capacity; speed = $_.ConfiguredClockSpeed; rated = $_.Speed; maker = $_.Manufacturer; part = ([string]$_.PartNumber).Trim() } })
  gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object { [pscustomobject]@{ name = $_.Name; driver = $_.DriverVersion;
        vram = $(if ($vram.ContainsKey($_.Name)) { $vram[$_.Name] } else { [int64]$_.AdapterRAM });
        res = $(if ($_.CurrentHorizontalResolution) { '{0} x {1} @ {2} Hz' -f $_.CurrentHorizontalResolution, $_.CurrentVerticalResolution, $_.CurrentRefreshRate } else { $null }) } })
  disks = @(Get-CimInstance Win32_DiskDrive | ForEach-Object { [pscustomobject]@{ model = $_.Model; size = [int64]$_.Size; iface = $_.InterfaceType } })
  net = @(Get-CimInstance Win32_NetworkAdapter -Filter 'PhysicalAdapter=True' | ForEach-Object { [pscustomobject]@{ name = $_.Name; mac = $_.MACAddress;
        speed = $_.Speed; up = [bool]$_.NetEnabled } })
  os = [pscustomobject]@{ caption = $os.Caption; version = $os.Version; build = $os.BuildNumber; arch = $os.OSArchitecture;
        installed = D $os.InstallDate; boot = D $os.LastBootUpTime }
} | ConvertTo-Json -Depth 4 -Compress
"""


def collect():
    return powershell_json(SCRIPT, timeout=120)


def gb(n):
    return human(n) if n else ""


def report_text(info):
    """The same information as plain text (for saving or the clipboard)."""
    lines = ["Benchwise - %s - %s" % (t("tool_sysinfo"), datetime.datetime.now().strftime("%Y-%m-%d %H:%M")), ""]
    for title, rows in sections(info):
        lines.append("== " + title)
        for label, value in rows:
            if value not in (None, ""):
                lines.append("  %-26s %s" % (label, value))
        lines.append("")
    if info.get("ram"):
        lines.append("== " + t("si_slots"))
        for m in as_list(info["ram"]):
            lines.append("  %-14s %-9s %-9s %-14s %s" % (m.get("slot") or "?", gb(m.get("size")),
                                                     t("si_mhz", n=m.get("speed") or m.get("rated") or "?"),
                                                     m.get("maker") or "", m.get("part") or ""))
    return "\n".join(lines)


PLACEHOLDERS = {"to be filled by o.e.m.", "default string", "system serial number", "system product name",
                "system manufacturer", "not specified", "none", "0", "123456789", "o.e.m.", "oem"}


def real(value):
    """Makers often leave placeholder texts in these fields; show nothing instead."""
    return None if str(value or "").strip().lower() in PLACEHOLDERS else value


def sections(info):
    c, b, o = info.get("computer") or {}, info.get("board") or {}, info.get("os") or {}
    c = {k: real(v) for k, v in c.items()}
    b = {k: real(v) for k, v in b.items()}
    out = [(t("si_computer"), [(t("si_maker"), c.get("maker")), (t("si_model"), c.get("model")),
                               (t("si_name"), c.get("name")), (t("si_serial"), b.get("pc_serial"))])]
    for cpu in as_list(info.get("cpu")):
        out.append((t("si_cpu"), [(t("si_name"), cpu.get("name")),
                                  (t("si_cores"), "%s / %s" % (cpu.get("cores"), cpu.get("threads"))),
                                  (t("si_clock"), t("si_mhz", n=cpu.get("mhz")) if cpu.get("mhz") else ""),
                                  (t("si_cache"), "%s / %s" % (human((cpu.get("l2") or 0) * 1024),
                                                               human((cpu.get("l3") or 0) * 1024))),
                                  (t("si_socket"), cpu.get("socket"))]))
    out.append((t("si_board"), [(t("si_maker"), b.get("maker")), (t("si_model"), b.get("model")),
                                (t("si_serial"), b.get("serial")), (t("si_bios"), b.get("bios")),
                                (t("si_bios_date"), (b.get("bios_date") or "")[:10])]))
    ram = as_list(info.get("ram"))
    out.append((t("si_memory"), [(t("si_total_ram"), gb(sum(m.get("size") or 0 for m in ram) or c.get("ram"))),
                                 (t("si_slots"), t("si_slots_used", used=len(ram), total=info.get("slots") or len(ram))),
                                 (t("si_max_ram"), gb((info.get("max_ram") or 0) * 1024))]))
    for g in as_list(info.get("gpu")):
        out.append((t("si_gpu"), [(t("si_name"), g.get("name")), (t("si_vram"), gb(g.get("vram"))),
                                  (t("si_driver"), g.get("driver")), (t("si_resolution"), g.get("res"))]))
    out.append((t("si_os"), [(t("si_edition"), "%s %s" % (o.get("caption") or "", o.get("arch") or "")),
                             (t("si_build"), "%s (%s)" % (o.get("version") or "", o.get("build") or "")),
                             (t("si_installed"), o.get("installed")), (t("si_boot"), o.get("boot"))]))
    return out


class View(ToolView):
    title_key = "tool_sysinfo"

    def fill(self):
        self.data = getattr(self, "data", None)
        ui.button(self.head, t("si_save"), self.save, 130).pack(side="right")
        ui.button(self.head, t("si_copy"), self.copy, 100).pack(side="right", padx=(0, 8))
        self.page = scroll_body(self)
        if self.data:
            self.show(self.data)
        else:
            note(self.page, t("si_loading"))
            self.run(collect, self.show, status=t("si_loading"))

    def show(self, info):
        for w_ in self.page.winfo_children():
            w_.destroy()
        if isinstance(info, Exception):
            note(self.page, t("si_failed", err=info), color=ui.BAD)
            return
        self.data = info
        for title, rows in sections(info):
            c = card(self.page, title)
            kv_grid(c, rows)
            if title == t("si_memory") and info.get("ram"):
                mods = as_list(info["ram"])
                holder, tree = table(c, [("slot", t("si_col_slot"), 150), ("size", t("si_col_size"), 90),
                                         ("speed", t("si_col_speed"), 110), ("maker", t("si_col_maker"), 160),
                                         ("part", t("si_col_part"), 220)], height=len(mods), stretch="part")
                holder.pack(fill="x", padx=16, pady=(0, 12))
                for m in mods:
                    speed = m.get("speed") or m.get("rated")
                    tree.insert("", "end", values=(m.get("slot") or m.get("bank") or "?", gb(m.get("size")),
                                                   t("si_mhz", n=speed) if speed else "", m.get("maker") or "",
                                                   m.get("part") or ""))
        disks = as_list(info.get("disks"))
        if disks:
            c = card(self.page, t("si_disks"))
            kv_grid(c, [(d.get("model") or "?", "%s · %s" % (gb(d.get("size")), d.get("iface") or "")) for d in disks])
        nets = as_list(info.get("net"))
        if nets:
            c = card(self.page, t("si_net"))
            kv_grid(c, [(n.get("name") or "?", " · ".join(x for x in (
                n.get("mac"), ("%d Mbit/s" % (n["speed"] // 1000000)) if n.get("speed") else "") if x)) for n in nets])

    def copy(self):
        if self.data:
            self.clipboard_clear()
            self.clipboard_append(report_text(self.data))
            self.set_status(t("si_copied"))

    def save(self):
        if not self.data:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="Benchwise-system.txt",
                                            filetypes=[("Text", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(report_text(self.data))
            self.set_status(t("si_saved", path=os.path.basename(path)))
