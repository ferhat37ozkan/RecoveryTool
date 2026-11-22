"""Display & Input > Camera Test: which cameras Windows sees, whether they work, whether apps may use
them, and one click to see the picture in the Windows Camera app.  (Showing the picture inside
Benchwise would need a video library several times the size of the whole program.)"""

from __future__ import annotations

import subprocess
import webbrowser
import winreg

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, as_list, card, note, powershell_json, table, texts

texts({
    "cam_list": ("Cameras", "Kameralar"),
    "cam_none": ("Windows sees no camera. Check the cable or the camera switch / shortcut key (many laptops "
                 "have one), then press Refresh.",
                 "Windows hiç kamera görmüyor. Kabloyu veya kamera anahtarını / kısayol tuşunu kontrol edin (birçok "
                 "dizüstünde vardır), sonra Yenile'ye basın."),
    "cam_col_name": ("Camera", "Kamera"),
    "cam_col_state": ("State", "Durum"),
    "cam_col_driver": ("Driver", "Sürücü"),
    "cam_ok": ("Working", "Çalışıyor"),
    "cam_disabled": ("Turned off in Device Manager", "Aygıt Yöneticisi'nde kapalı"),
    "cam_problem": ("Problem (code {code})", "Sorun (kod {code})"),
    "cam_privacy": ("Permission", "İzin"),
    "cam_allowed": ("Windows lets apps use the camera.", "Windows uygulamaların kamerayı kullanmasına izin veriyor."),
    "cam_denied": ("Windows blocks the camera for apps. This is the most common reason a camera \"does not "
                   "work\".", "Windows kamerayı uygulamalara kapatmış. Kameranın \"çalışmamasının\" en yaygın "
                   "nedeni budur."),
    "cam_open_settings": ("Open camera privacy settings", "Kamera gizlilik ayarlarını aç"),
    "cam_picture": ("Picture", "Görüntü"),
    "cam_picture_how": ("Opens the Windows Camera app to see what the camera sees.",
                        "Kameranın gördüğünü izlemek için Windows Kamera uygulamasını açar."),
    "cam_open_app": ("Open the Camera app", "Kamera uygulamasını aç"),
    "cam_refresh": ("Refresh", "Yenile"),
})


def privacy_allowed():
    """None when unknown; else whether the camera is allowed for apps (machine and user settings)."""
    path = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, path) as k:
                if winreg.QueryValueEx(k, "Value")[0] == "Deny":
                    return False
        except OSError:
            continue
    return True


class View(ToolView):
    title_key = "tool_camera"

    def fill(self):
        self.list_card = card(self.body, t("cam_list"))
        ui.button(self.head, t("cam_refresh"), self.load, 100).pack(side="right")
        note(self.list_card, "…")
        p = card(self.body, t("cam_privacy"))
        allowed = privacy_allowed()
        note(p, t("cam_allowed") if allowed else t("cam_denied"), color=ui.GOOD if allowed else ui.WARN)
        if not allowed:
            ui.button(p, t("cam_open_settings"), lambda: webbrowser.open("ms-settings:privacy-webcam"), 260).pack(
                anchor="w", padx=18, pady=(0, 12))
        pic = card(self.body, t("cam_picture"))
        note(pic, t("cam_picture_how"), color=ui.TEXT)
        ui.button(pic, t("cam_open_app"), self.open_app, 220, primary=True).pack(anchor="w", padx=18, pady=(0, 14))
        self.load()

    def load(self):
        self.run(lambda: as_list(powershell_json(
            "Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in 'Camera','Image' } | ForEach-Object { "
            "$d = Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_DriverVersion' "
            "-ErrorAction SilentlyContinue; [pscustomobject]@{ Name = $_.FriendlyName; Status = [string]$_.Status; "
            "Problem = [int]$_.Problem; Driver = [string]$d.Data } } | ConvertTo-Json -Compress")), self.show)

    def show(self, result):
        for w_ in self.list_card.winfo_children()[1:]:
            w_.destroy()
        if isinstance(result, Exception) or not result:
            note(self.list_card, t("cam_none"), color=ui.WARN)
            return
        holder, tree = table(self.list_card, [("name", t("cam_col_name"), 320), ("state", t("cam_col_state"), 260),
                                              ("driver", t("cam_col_driver"), 160)], height=min(6, len(result)),
                             stretch="name")
        holder.pack(fill="x", padx=16, pady=(0, 12))
        for d in result:
            if d.get("Status") == "OK":
                state, tag = t("cam_ok"), "good"
            elif d.get("Problem") == 22:
                state, tag = t("cam_disabled"), "warn"
            else:
                state, tag = t("cam_problem", code=d.get("Problem")), "bad"
            tree.insert("", "end", values=(d.get("Name") or "?", state, d.get("Driver") or ""), tags=(tag,))

    def open_app(self):
        subprocess.Popen(["explorer.exe", "microsoft.windows.camera:"])
