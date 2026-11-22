"""Windows Repair > Startup & Services: programs that start with Windows (Run keys and Startup folders),
switched on/off exactly like Task Manager does (the StartupApproved values; nothing is deleted), and
automatic services not made by Microsoft (listed only: stopping services can break things)."""

from __future__ import annotations

import os
import subprocess
import winreg

import customtkinter as ctk

from recoverytool.i18n import t

from .. import elevate, ui
from ..toolkit import ToolView, as_list, card, note, powershell_json, scroll_body, table, texts

texts({
    "su_programs": ("Programs that start with Windows", "Windows ile açılan programlar"),
    "su_programs_how": ("Turning one off only stops it from starting by itself; it stays installed and can be "
                        "turned back on here or in Task Manager.",
                        "Birini kapatmak yalnızca kendiliğinden açılmasını engeller; program kurulu kalır ve buradan "
                        "veya Görev Yöneticisi'nden yeniden açılabilir."),
    "su_none": ("Nothing starts with Windows.", "Windows ile birlikte açılan bir şey yok."),
    "su_on": ("On", "Açık"),
    "su_off": ("Off", "Kapalı"),
    "su_turn_off": ("Turn off", "Kapat"),
    "su_turn_on": ("Turn on", "Aç"),
    "su_all_users": ("all users", "tüm kullanıcılar"),
    "su_this_user": ("this user", "bu kullanıcı"),
    "su_admin": ("administrator rights needed", "yönetici yetkisi gerekir"),
    "su_services": ("Automatic services not made by Microsoft", "Microsoft dışı otomatik servisler"),
    "su_services_how": ("Listed for information. Stopping services can break the programs or devices they belong "
                        "to; change them only if you know what they are.",
                        "Bilgi amaçlı listelenir. Servisleri durdurmak ait oldukları program veya aygıtları bozabilir; "
                        "ne olduklarını biliyorsanız değiştirin."),
    "su_open_services": ("Open Services", "Servisleri aç"),
    "su_col_service": ("Service", "Servis"),
    "su_col_state": ("State", "Durum"),
    "su_col_path": ("Program", "Program"),
    "su_running": ("running", "çalışıyor"),
    "su_stopped": ("stopped", "durmuş"),
})

RUN_KEYS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "Run", False),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "Run", True),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "Run32", True),
]
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"


def folders():
    user = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    common = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs\Startup")
    return [(user, False), (common, True)]


def approved_state(root, kind, name):
    """True (on) / False (off) from StartupApproved; entries without a value are on."""
    try:
        with winreg.OpenKey(root, APPROVED + "\\" + kind) as k:
            data, _ = winreg.QueryValueEx(k, name)
            return not (data and data[0] & 1)          # 02/06 = on, 03/07 = off (Task Manager's encoding)
    except OSError:
        return True


def set_approved(root, kind, name, on):
    import struct
    import time
    data = struct.pack("<I", 2 if on else 3) + (b"\x00" * 8 if on else struct.pack("<Q", int((time.time() + 11644473600) * 1e7)))
    with winreg.CreateKeyEx(root, APPROVED + "\\" + kind, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_BINARY, data)


def programs():
    items = []
    for root, path, kind, machine in RUN_KEYS:
        try:
            with winreg.OpenKey(root, path) as k:
                i = 0
                while True:
                    try:
                        name, cmd, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    items.append({"name": name, "command": str(cmd), "root": root, "kind": kind, "machine": machine,
                                  "on": approved_state(root, kind, name)})
        except OSError:
            continue
    for folder, machine in folders():
        root = winreg.HKEY_LOCAL_MACHINE if machine else winreg.HKEY_CURRENT_USER
        try:
            for entry in os.scandir(folder):
                if entry.name.lower() == "desktop.ini":
                    continue
                items.append({"name": entry.name, "command": entry.path, "root": root, "kind": "StartupFolder",
                              "machine": machine, "on": approved_state(root, "StartupFolder", entry.name)})
        except OSError:
            continue
    return items


SERVICES = r"""
@(Get-CimInstance Win32_Service -Filter "StartMode='Auto'" | ForEach-Object {
  [pscustomobject]@{ name = $_.DisplayName; state = $_.State; path = $_.PathName } }) | ConvertTo-Json -Compress
"""


def third_party(path):
    """Not part of Windows: under Program Files / ProgramData, a driver package (DriverStore), or outside the
    Windows folder.  (Filtered here: regexes with backslashes do not survive the trip to powershell -Command.)"""
    p = (path or "").lower().replace("/", "\\")
    if not p:
        return False
    if "program files" in p or "programdata" in p or "\\driverstore\\" in p:
        return True
    return "\\windows\\" not in p


class View(ToolView):
    title_key = "tool_startup"

    def fill(self):
        self.page = scroll_body(self)
        self.prog_card = card(self.page, t("su_programs"))
        note(self.prog_card, t("su_programs_how"))
        self.rows = ctk.CTkFrame(self.prog_card, fg_color="transparent")
        self.rows.pack(fill="x", padx=18, pady=(0, 12))
        self.render_programs()
        s = card(self.page, t("su_services"))
        note(s, t("su_services_how"))
        ui.button(s, t("su_open_services"), lambda: subprocess.Popen(["mmc.exe", "services.msc"]), 150).pack(
            anchor="w", padx=18, pady=(0, 8))
        self.svc_card = s
        self.run(lambda: [r for r in as_list(powershell_json(SERVICES)) if third_party(r.get("path"))], self.show_services)

    def render_programs(self):
        for w_ in self.rows.winfo_children():
            w_.destroy()
        items = programs()
        if not items:
            note(self.rows, t("su_none"), padx=0)
        admin = elevate.is_admin()
        for it in sorted(items, key=lambda x: (not x["on"], x["name"].lower())):
            row = ctk.CTkFrame(self.rows, fg_color="transparent")
            row.pack(fill="x", pady=3)
            box = ctk.CTkFrame(row, fg_color="transparent")
            box.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(box, text=it["name"], font=("Segoe UI Semibold", 12), text_color=ui.TEXT if it["on"] else ui.MUTED,
                         anchor="w").pack(fill="x")
            where = t("su_all_users") if it["machine"] else t("su_this_user")
            ctk.CTkLabel(box, text="%s · %s" % (where, it["command"][:110]), font=("Segoe UI", 10), text_color=ui.MUTED,
                         anchor="w").pack(fill="x")
            ctk.CTkLabel(row, text=t("su_on") if it["on"] else t("su_off"), font=("Segoe UI Semibold", 11),
                         text_color=ui.GOOD if it["on"] else ui.MUTED, width=60).pack(side="left", padx=8)
            btn = ui.button(row, t("su_turn_off") if it["on"] else t("su_turn_on"), lambda x=it: self.toggle(x), 100)
            btn.pack(side="left")
            if it["machine"] and not admin:
                btn.configure(state="disabled")

    def toggle(self, it):
        try:
            set_approved(it["root"], it["kind"], it["name"], not it["on"])
        except OSError as ex:
            self.set_status(str(ex))
        self.render_programs()

    def show_services(self, rows):
        if isinstance(rows, Exception) or not rows:
            return
        holder, tree = table(self.svc_card, [("service", t("su_col_service"), 300), ("state", t("su_col_state"), 100),
                                             ("path", t("su_col_path"), 420)], height=min(12, len(rows)), stretch="path")
        holder.pack(fill="x", padx=16, pady=(0, 12))
        for r in sorted(rows, key=lambda r: (r.get("name") or "").lower()):
            running = r.get("state") == "Running"
            tree.insert("", "end", values=(r.get("name"), t("su_running") if running else t("su_stopped"),
                                           (r.get("path") or "").strip('"')), tags=() if running else ("muted",))
