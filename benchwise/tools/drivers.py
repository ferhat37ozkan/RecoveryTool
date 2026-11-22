"""Windows Repair > Drivers: devices with a problem (and what the code means), third-party drivers with
their date and version (old ones flagged), and a backup of all third-party drivers to a folder."""

from __future__ import annotations

import datetime
import os
import subprocess
from tkinter import filedialog

import customtkinter as ctk

from recoverytool.i18n import t

from .. import elevate, ui
from ..toolkit import ToolView, as_list, card, note, powershell_json, run_command, scroll_body, table, texts

texts({
    "dr_loading": ("Reading the drivers…", "Sürücüler okunuyor…"),
    "dr_problems": ("Devices with a problem", "Sorunlu aygıtlar"),
    "dr_problems_none": ("Every device works.", "Bütün aygıtlar çalışıyor."),
    "dr_col_device": ("Device", "Aygıt"),
    "dr_col_problem": ("Problem", "Sorun"),
    "dr_third": ("Third-party drivers", "Üçüncü taraf sürücüler"),
    "dr_third_note": ("Drivers not made by Microsoft. Ones older than 5 years are yellow: check the maker's site "
                      "for a newer one if that device misbehaves.",
                      "Microsoft dışındaki sürücüler. 5 yıldan eski olanlar sarı: o aygıt sorun çıkarıyorsa "
                      "üreticinin sitesinde daha yenisine bakın."),
    "dr_col_maker": ("Maker", "Üretici"),
    "dr_col_date": ("Date", "Tarih"),
    "dr_col_version": ("Version", "Sürüm"),
    "dr_backup": ("Back up drivers", "Sürücüleri yedekle"),
    "dr_backup_how": ("Copies every third-party driver to a folder. After reinstalling Windows, point Device Manager "
                      "to that folder (Update driver > Browse) to get them back.",
                      "Bütün üçüncü taraf sürücüleri bir klasöre kopyalar. Windows'u yeniden kurduktan sonra Aygıt "
                      "Yöneticisi'nde o klasörü gösterin (Sürücüyü güncelleştir > Gözat) ve geri yükleyin."),
    "dr_backup_start": ("Choose a folder and back up", "Klasör seç ve yedekle"),
    "dr_backup_admin": ("Needs administrator rights.", "Yönetici yetkisi gerekir."),
    "dr_backup_running": ("Backing up…", "Yedekleniyor…"),
    "dr_backup_done": ("Backed up {n} drivers to {path}", "{n} sürücü yedeklendi: {path}"),
    "dr_backup_failed": ("Backup failed: {err}", "Yedekleme başarısız: {err}"),
    "dr_open_devmgmt": ("Open Device Manager", "Aygıt Yöneticisi'ni aç"),
    "dr_code": ("Code {code}: {text}", "Kod {code}: {text}"),
    "dr_c1": ("not configured correctly", "doğru yapılandırılmamış"),
    "dr_c10": ("cannot start", "başlatılamıyor"),
    "dr_c12": ("not enough free resources", "yeterli boş kaynak yok"),
    "dr_c14": ("needs a restart", "yeniden başlatma gerekiyor"),
    "dr_c18": ("reinstall the driver", "sürücüyü yeniden kurun"),
    "dr_c19": ("registry information is damaged", "kayıt defteri bilgisi bozuk"),
    "dr_c21": ("being removed", "kaldırılıyor"),
    "dr_c22": ("disabled", "devre dışı"),
    "dr_c24": ("not present or not working", "yok veya çalışmıyor"),
    "dr_c28": ("no driver installed", "sürücü yüklü değil"),
    "dr_c29": ("disabled by the firmware", "donanım yazılımı tarafından kapatılmış"),
    "dr_c31": ("Windows cannot load the driver", "Windows sürücüyü yükleyemiyor"),
    "dr_c32": ("driver service disabled", "sürücü servisi kapalı"),
    "dr_c37": ("the driver failed to start", "sürücü başlatılamadı"),
    "dr_c39": ("driver missing or damaged", "sürücü eksik veya bozuk"),
    "dr_c43": ("the device reported a problem (often hardware or a failed USB device)",
               "aygıt bir sorun bildirdi (çoğu zaman donanım veya arızalı USB aygıtı)"),
    "dr_c45": ("not connected right now", "şu an bağlı değil"),
    "dr_c48": ("driver blocked for known problems", "bilinen sorunlar yüzünden sürücü engellendi"),
    "dr_c52": ("driver signature cannot be verified", "sürücü imzası doğrulanamıyor"),
    "dr_cx": ("see Device Manager", "Aygıt Yöneticisi'ne bakın"),
})

SCRIPT = r"""
$problems = @(Get-CimInstance Win32_PnPEntity -Filter 'ConfigManagerErrorCode <> 0' | Where-Object { $_.ConfigManagerErrorCode -ne 45 } |
  ForEach-Object { [pscustomobject]@{ name = $(if ($_.Name) { $_.Name } else { $_.DeviceID }); code = [int]$_.ConfigManagerErrorCode } })
$drivers = @(Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DriverProviderName -and $_.DriverProviderName -notmatch '^Microsoft' -and $_.DeviceName } |
  Sort-Object DeviceName -Unique | ForEach-Object { [pscustomobject]@{ device = $_.DeviceName; maker = $_.DriverProviderName;
    date = $(if ($_.DriverDate) { ([datetime]$_.DriverDate).ToString('yyyy-MM-dd') } else { '' }); version = $_.DriverVersion } })
[pscustomobject]@{ problems = $problems; drivers = $drivers } | ConvertTo-Json -Depth 4 -Compress
"""


def problem_text(code):
    key = "dr_c%d" % code
    text = t(key)
    return t("dr_code", code=code, text=text if text != key else t("dr_cx"))


def is_old(date, years=5):
    try:
        return datetime.date.fromisoformat(date) < datetime.date.today() - datetime.timedelta(days=365 * years)
    except (TypeError, ValueError):
        return False


class View(ToolView):
    title_key = "tool_drivers"

    def fill(self):
        ui.button(self.head, t("dr_open_devmgmt"), lambda: subprocess.Popen(["mmc.exe", "devmgmt.msc"]), 190).pack(side="right")
        self.page = scroll_body(self)
        note(self.page, t("dr_loading"))
        self.run(lambda: powershell_json(SCRIPT, timeout=180), self.show, status=t("dr_loading"))

    def show(self, data):
        for w_ in self.page.winfo_children():
            w_.destroy()
        if isinstance(data, Exception) or not isinstance(data, dict):
            note(self.page, str(data), color=ui.BAD)
            return
        c = card(self.page, t("dr_problems"))
        problems = as_list(data.get("problems"))
        if problems:
            holder, tree = table(c, [("device", t("dr_col_device"), 380), ("problem", t("dr_col_problem"), 400)],
                                 height=min(8, len(problems)), stretch="problem")
            holder.pack(fill="x", padx=16, pady=(0, 12))
            for p in problems:
                tree.insert("", "end", values=(p.get("name"), problem_text(p.get("code") or 0)),
                            tags=("warn" if p.get("code") == 22 else "bad",))
        else:
            note(c, t("dr_problems_none"), color=ui.GOOD)

        b = card(self.page, t("dr_backup"))
        note(b, t("dr_backup_how"), color=ui.TEXT)
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 12))
        self.backup_btn = ui.button(row, t("dr_backup_start"), self.backup, 210)
        self.backup_btn.pack(side="left")
        self.backup_note = ctk.CTkLabel(row, text=" " if elevate.is_admin() else t("dr_backup_admin"),
                                        font=("Segoe UI", 12), text_color=ui.MUTED)
        self.backup_note.pack(side="left", padx=12)
        if not elevate.is_admin():
            self.backup_btn.configure(state="disabled")

        c = card(self.page, t("dr_third"))
        note(c, t("dr_third_note"))
        drivers = as_list(data.get("drivers"))
        holder, tree = table(c, [("device", t("dr_col_device"), 330), ("maker", t("dr_col_maker"), 190),
                                 ("date", t("dr_col_date"), 100), ("version", t("dr_col_version"), 150)],
                             height=min(16, max(1, len(drivers))), stretch="device")
        holder.pack(fill="x", padx=16, pady=(0, 12))
        for d in sorted(drivers, key=lambda d: d.get("date") or ""):
            tree.insert("", "end", values=(d.get("device"), d.get("maker"), d.get("date"), d.get("version")),
                        tags=("warn",) if is_old(d.get("date")) else ())

    def backup(self):
        folder = filedialog.askdirectory(title=t("dr_backup"))
        if not folder:
            return
        target = os.path.join(folder, "Benchwise-drivers-" + datetime.date.today().isoformat())
        os.makedirs(target, exist_ok=True)
        self.backup_btn.configure(state="disabled")
        self.backup_note.configure(text=t("dr_backup_running"), text_color=ui.MUTED)

        def work():
            code, out = run_command(["pnputil", "/export-driver", "*", target], timeout=1800)
            n = sum(1 for _ in os.scandir(target)) if os.path.isdir(target) else 0
            if code not in (0, 3010) and not n:
                raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "pnputil %d" % code)
            return n

        def done(res):
            self.backup_btn.configure(state="normal")
            if isinstance(res, Exception):
                self.backup_note.configure(text=t("dr_backup_failed", err=res), text_color=ui.BAD)
            else:
                self.backup_note.configure(text=t("dr_backup_done", n=res, path=target), text_color=ui.GOOD)
                subprocess.Popen(["explorer.exe", target])
        self.run(work, done)
