"""Network > Network Reset: the usual fixes, each chosen on its own, with what it does said up front.
A restore point is made before the ones that change system settings (Winsock, TCP/IP)."""

from __future__ import annotations

import webbrowser

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, confirm, note, powershell, restore_point, run_command, texts

texts({
    "nr_how": ("Pick what to do. Start with the light ones; Winsock and TCP/IP reset change system settings and "
               "need a restart (a restore point is made first).",
               "Ne yapılacağını seçin. Hafif olanlarla başlayın; Winsock ve TCP/IP sıfırlama sistem ayarlarını "
               "değiştirir ve yeniden başlatma ister (önce geri yükleme noktası oluşturulur)."),
    "nr_flush": ("Clear the DNS cache - fixes sites that moved or stopped opening (harmless)",
                 "DNS önbelleğini temizle - taşınan veya açılmayan siteleri düzeltir (zararsız)"),
    "nr_renew": ("Renew the IP address - the connection drops for a few seconds",
                 "IP adresini yenile - bağlantı birkaç saniye kesilir"),
    "nr_adapters": ("Restart the network adapters - the connection drops for a few seconds",
                    "Ağ kartlarını yeniden başlat - bağlantı birkaç saniye kesilir"),
    "nr_winsock": ("Reset Winsock - fixes damage left by VPNs and security software (restart needed)",
                   "Winsock'u sıfırla - VPN ve güvenlik yazılımlarının bıraktığı bozulmayı düzeltir (yeniden başlatma gerekir)"),
    "nr_tcpip": ("Reset TCP/IP settings - back to Windows defaults (restart needed)",
                 "TCP/IP ayarlarını sıfırla - Windows varsayılanlarına döner (yeniden başlatma gerekir)"),
    "nr_apply": ("Apply", "Uygula"),
    "nr_ask": ("These will be done:\n\n{items}\n\nContinue?", "Şunlar yapılacak:\n\n{items}\n\nDevam edilsin mi?"),
    "nr_restore": ("Making a restore point…", "Geri yükleme noktası oluşturuluyor…"),
    "nr_restore_skipped": ("(Windows did not make a restore point: it is off or one was made recently.)",
                           "(Windows geri yükleme noktası oluşturmadı: kapalı ya da yakın zamanda oluşturulmuş.)"),
    "nr_done": ("Done.", "Tamamlandı."),
    "nr_restart": ("Restart the computer to finish.", "Bitirmek için bilgisayarı yeniden başlatın."),
    "nr_full": ("Full Windows network reset", "Windows'un tam ağ sıfırlaması"),
    "nr_full_how": ("Removes and reinstalls every network adapter and forgets Wi-Fi passwords and VPNs. The last "
                    "resort; Windows does it from Settings.", "Bütün ağ kartlarını kaldırıp yeniden kurar, Wi-Fi "
                    "şifrelerini ve VPN'leri unutur. Son çare; Windows bunu Ayarlar'dan yapar."),
    "nr_full_open": ("Open in Settings", "Ayarlar'da aç"),
})

ACTIONS = [
    ("flush", True, False, [["ipconfig", "/flushdns"]]),
    ("renew", False, False, [["ipconfig", "/release"], ["ipconfig", "/renew"]]),
    ("adapters", False, False, None),           # PowerShell below
    ("winsock", False, True, [["netsh", "winsock", "reset"]]),
    ("tcpip", False, True, [["netsh", "int", "ip", "reset"]]),
]
RESTART_ADAPTERS = ("Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object { "
                    "Restart-NetAdapter -Name $_.Name -Confirm:$false; $_.Name }")


class View(ToolView):
    title_key = "tool_netreset"

    def fill(self):
        c = card(self.body, t("tool_netreset"))
        note(c, t("nr_how"), color=ui.TEXT)
        self.vars = {}
        for key, default, _, _ in ACTIONS:
            var = ctk.BooleanVar(value=default)
            ctk.CTkCheckBox(c, text=t("nr_" + key), variable=var, font=("Segoe UI", 12), text_color=ui.TEXT,
                            checkbox_width=18, checkbox_height=18, border_width=2, fg_color=ui.ACCENT,
                            border_color=ui.MUTED).pack(anchor="w", padx=18, pady=3)
            self.vars[key] = var
        self.apply_btn = ui.button(c, t("nr_apply"), self.apply, 140, primary=True)
        self.apply_btn.pack(anchor="w", padx=18, pady=(10, 8))
        self.log = ctk.CTkTextbox(c, fg_color=ui.BG, text_color=ui.TEXT, font=("Consolas", 11), height=200,
                                  corner_radius=8, border_width=0)
        self.log.pack(fill="x", padx=16, pady=(0, 14))
        f = card(self.body, t("nr_full"))
        note(f, t("nr_full_how"))
        ui.button(f, t("nr_full_open"), lambda: webbrowser.open("ms-settings:network-status"), 160).pack(
            anchor="w", padx=18, pady=(0, 14))

    def write(self, text):
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")

    def apply(self):
        chosen = [a for a in ACTIONS if self.vars[a[0]].get()]
        if not chosen:
            return
        if not confirm(t("tool_netreset"), t("nr_ask", items="\n".join("• " + t("nr_" + a[0]) for a in chosen))):
            return
        self.apply_btn.configure(state="disabled")
        self.log.delete("1.0", "end")
        needs_restart = any(a[2] for a in chosen)

        def work():
            if needs_restart:
                self.post(self.write, t("nr_restore"))
                if not restore_point("Benchwise network reset"):
                    self.post(self.write, t("nr_restore_skipped"))
            for key, _, _, commands in chosen:
                self.post(self.write, "\n> " + t("nr_" + key).split(" - ")[0])
                if commands is None:
                    out = powershell(RESTART_ADAPTERS, timeout=120)
                    self.post(self.write, out or "-")
                    continue
                for cmd in commands:
                    code, out = run_command(cmd, timeout=180)
                    self.post(self.write, out.strip() or ("exit %d" % code))
            return needs_restart

        def done(res):
            self.apply_btn.configure(state="normal")
            if isinstance(res, Exception):
                self.write(str(res))
                return
            self.write("\n" + t("nr_done") + (" " + t("nr_restart") if res else ""))
        self.run(work, done)
