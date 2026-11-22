"""Battery & Power > Sleep & Wake: what woke the computer, which devices may wake it (and switching
that off), wake timers, and what keeps it from sleeping right now.  All from powercfg and the
Power-Troubleshooter events; needs administrator rights."""

from __future__ import annotations

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, as_list, card, confirm, note, powershell_json, run_command, scroll_body, table, texts

texts({
    "wk_loading": ("Asking Windows…", "Windows'a soruluyor…"),
    "wk_last": ("Last wake", "Son uyanma"),
    "wk_recent": ("Recent wakes", "Son uyanmalar"),
    "wk_recent_none": ("No wake from sleep recorded recently.", "Yakın zamanda uykudan uyanma kaydı yok."),
    "wk_col_slept": ("Went to sleep", "Uykuya geçti"),
    "wk_col_woke": ("Woke up", "Uyandı"),
    "wk_col_source": ("Woken by", "Uyandıran"),
    "wk_armed": ("Devices allowed to wake the computer", "Bilgisayarı uyandırmasına izin verilen aygıtlar"),
    "wk_armed_how": ("If the computer wakes up by itself, the usual cause is a mouse moved by a vibration or a "
                     "network card. Taking the permission away does not stop the device from working.",
                     "Bilgisayar kendiliğinden uyanıyorsa genellikle bir titreşimle oynayan mouse veya ağ kartıdır. "
                     "İzni kaldırmak aygıtın çalışmasını engellemez."),
    "wk_armed_none": ("No device may wake the computer.", "Bilgisayarı uyandırabilen aygıt yok."),
    "wk_disable": ("Remove permission", "İzni kaldır"),
    "wk_disable_ask": ("Stop \"{name}\" from waking the computer?\n\nIt keeps working normally; it just cannot "
                       "wake the computer from sleep. Device Manager > the device > Power Management can turn it "
                       "back on.", "\"{name}\" bilgisayarı uyandırmasın mı?\n\nAygıt normal çalışmaya devam eder; "
                       "yalnızca bilgisayarı uykudan uyandıramaz. Aygıt Yöneticisi > aygıt > Güç Yönetimi'nden geri "
                       "açılabilir."),
    "wk_timers": ("Wake timers", "Uyandırma zamanlayıcıları"),
    "wk_requests": ("What keeps the computer awake now", "Şu an bilgisayarın uyumasını engelleyenler"),
    "wk_requests_how": ("For example a playing video, a download or a program that asked Windows not to sleep.",
                        "Örneğin oynayan bir video, bir indirme veya Windows'tan uyumamasını isteyen bir program."),
})

EVENTS = r"""
@(Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-Power-Troubleshooter'; Id = 1 } -MaxEvents 15 -ErrorAction SilentlyContinue |
  ForEach-Object { $lines = @($_.Message -split "`r?`n" | Where-Object { $_.Trim() })
    [pscustomobject]@{ slept = ([datetime]$_.Properties[0].Value).ToLocalTime().ToString('yyyy-MM-dd HH:mm');
                       woke = ([datetime]$_.Properties[1].Value).ToLocalTime().ToString('yyyy-MM-dd HH:mm');
                       source = ($lines[-1] -replace '^[^:]+:\s*', '') } }) | ConvertTo-Json -Compress
"""


def lines_of(text):
    return [ln.rstrip() for ln in (text or "").splitlines() if ln.strip()]


def gather():
    out = {}
    for key, args in (("last", ["/lastwake"]), ("armed", ["/devicequery", "wake_armed"]),
                      ("timers", ["/waketimers"]), ("requests", ["/requests"])):
        code, text = run_command(["powercfg"] + args, timeout=60)
        out[key] = text.strip()
    try:
        out["events"] = as_list(powershell_json(EVENTS))
    except Exception:
        out["events"] = []
    return out


def armed_devices(text):
    """Device names from ``powercfg /devicequery wake_armed`` (one per line; "NONE"/"YOK" when empty)."""
    names = lines_of(text)
    return [] if len(names) == 1 and names[0].strip().upper() in ("NONE", "YOK", "HİÇBİRİ", "HICBIRI") else names


class View(ToolView):
    title_key = "tool_wake"

    def fill(self):
        self.page = scroll_body(self)
        note(self.page, t("wk_loading"))
        self.load()

    def load(self):
        self.run(gather, self.show, status=t("wk_loading"))

    def raw(self, parent, text):
        box = ctk.CTkTextbox(parent, fg_color=ui.BG, text_color=ui.TEXT, font=("Consolas", 11), corner_radius=8,
                             wrap="word", height=min(220, 22 + 17 * max(1, len(lines_of(text)))), border_width=0)
        box.insert("1.0", text or "-")
        box.configure(state="disabled")
        box.pack(fill="x", padx=16, pady=(0, 12))

    def show(self, data):
        for w_ in self.page.winfo_children():
            w_.destroy()
        if isinstance(data, Exception):
            note(self.page, str(data), color=ui.BAD)
            return
        c = card(self.page, t("wk_last"))
        self.raw(c, data["last"])

        c = card(self.page, t("wk_recent"))
        events = data["events"]
        if events:
            holder, tree = table(c, [("slept", t("wk_col_slept"), 140), ("woke", t("wk_col_woke"), 140),
                                     ("source", t("wk_col_source"), 420)], height=min(8, len(events)), stretch="source")
            holder.pack(fill="x", padx=16, pady=(0, 12))
            for e in events:
                tree.insert("", "end", values=(e.get("slept"), e.get("woke"), e.get("source")))
        else:
            note(c, t("wk_recent_none"))

        c = card(self.page, t("wk_armed"))
        note(c, t("wk_armed_how"))
        devices = armed_devices(data["armed"])
        if not devices:
            note(c, t("wk_armed_none"), color=ui.GOOD)
        for name in devices:
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(row, text=name, font=("Segoe UI", 12), text_color=ui.TEXT, anchor="w").pack(side="left")
            ui.button(row, t("wk_disable"), lambda n=name: self.disable(n), 130).pack(side="right")
        ctk.CTkFrame(c, fg_color="transparent", height=8).pack()

        c = card(self.page, t("wk_timers"))
        self.raw(c, data["timers"])
        c = card(self.page, t("wk_requests"))
        note(c, t("wk_requests_how"))
        self.raw(c, data["requests"])

    def disable(self, name):
        if not confirm(t("tool_wake"), t("wk_disable_ask", name=name)):
            return
        self.run(lambda: run_command(["powercfg", "/devicedisablewake", name], timeout=30), lambda r: self.load())
