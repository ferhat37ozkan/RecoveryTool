"""Windows Repair > Windows Update Repair: recent update failures with their codes, and the standard
reset (stop the update services, set the caches aside under a backup name - nothing is deleted -,
start the services again).  A restore point is made first."""

from __future__ import annotations

import webbrowser

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, as_list, card, confirm, note, powershell, powershell_json, restore_point, table, texts

texts({
    "wu_failures": ("Recent update failures", "Son güncelleme hataları"),
    "wu_none": ("No failed updates in the last 60 days.", "Son 60 günde başarısız güncelleme yok."),
    "wu_col_date": ("Date", "Tarih"),
    "wu_col_update": ("Update", "Güncelleme"),
    "wu_col_code": ("Error code", "Hata kodu"),
    "wu_reset": ("Reset Windows Update", "Windows Update'i sıfırla"),
    "wu_reset_how": ("When updates keep failing or hang at a percentage: stops the update services, moves the "
                     "download cache (SoftwareDistribution) and the signature cache (catroot2) aside under a "
                     "backup name, and starts the services again. Windows builds fresh caches at the next check. "
                     "Nothing is deleted; update history may look empty afterwards.",
                     "Güncellemeler sürekli başarısız olduğunda veya bir yüzdede takıldığında: güncelleme "
                     "servislerini durdurur, indirme önbelleğini (SoftwareDistribution) ve imza önbelleğini "
                     "(catroot2) yedek adıyla kenara alır ve servisleri yeniden başlatır. Windows bir sonraki "
                     "kontrolde yeni önbellek oluşturur. Hiçbir şey silinmez; güncelleme geçmişi sonra boş "
                     "görünebilir."),
    "wu_reset_start": ("Reset now", "Şimdi sıfırla"),
    "wu_reset_ask": ("Reset Windows Update now?\n\nThe update services are stopped and started again, and the "
                     "caches are renamed to *.bak-<date>. A restore point is made first.",
                     "Windows Update şimdi sıfırlansın mı?\n\nGüncelleme servisleri durdurulup yeniden başlatılır, "
                     "önbellekler *.bak-<tarih> olarak yeniden adlandırılır. Önce geri yükleme noktası oluşturulur."),
    "wu_working": ("Resetting…", "Sıfırlanıyor…"),
    "wu_done": ("Done. Open Windows Update and check for updates.", "Tamamlandı. Windows Update'i açıp güncellemeleri denetleyin."),
    "wu_open": ("Open Windows Update", "Windows Update'i aç"),
    "wu_lookup": ("Look up an error code: search for it together with \"Windows Update\".",
                  "Bir hata kodunu öğrenmek için \"Windows Update\" ile birlikte aratın."),
})

FAILURES = r"""
@(Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-WindowsUpdateClient'; Id = 20; StartTime = (Get-Date).AddDays(-60) } -ErrorAction SilentlyContinue |
  Select-Object -First 40 | ForEach-Object { [pscustomobject]@{ date = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm');
    code = [string]$_.Properties[0].Value; update = [string]$_.Properties[1].Value } }) | ConvertTo-Json -Compress
"""

RESET = r"""
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$services = 'wuauserv', 'bits', 'cryptsvc', 'msiserver', 'usosvc'
foreach ($s in $services) { Stop-Service -Name $s -Force -ErrorAction SilentlyContinue; "stopped $s" }
Start-Sleep -Seconds 2
$sd = Join-Path $env:SystemRoot 'SoftwareDistribution'
$cr = Join-Path $env:SystemRoot 'System32\catroot2'
foreach ($p in $sd, $cr) {
  if (Test-Path $p) {
    try { Rename-Item -LiteralPath $p -NewName ((Split-Path $p -Leaf) + '.bak-' + $stamp) -ErrorAction Stop; "renamed $p" }
    catch { "could not rename ${p}: $($_.Exception.Message)" }
  }
}
foreach ($s in 'cryptsvc', 'bits', 'wuauserv', 'usosvc') { Start-Service -Name $s -ErrorAction SilentlyContinue; "started $s" }
"""


def hresult(code):
    """Event code as 0x8024xxxx (Windows logs it as a signed or unsigned decimal)."""
    try:
        return "0x%08X" % (int(code) & 0xFFFFFFFF)
    except (TypeError, ValueError):
        return str(code or "")


class View(ToolView):
    title_key = "tool_update"

    def fill(self):
        self.fail_card = card(self.body, t("wu_failures"))
        note(self.fail_card, "…")
        r = card(self.body, t("wu_reset"))
        note(r, t("wu_reset_how"), color=ui.TEXT)
        row = ctk.CTkFrame(r, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        self.reset_btn = ui.button(row, t("wu_reset_start"), self.reset, 150, primary=True)
        self.reset_btn.pack(side="left")
        ui.button(row, t("wu_open"), lambda: webbrowser.open("ms-settings:windowsupdate"), 170).pack(side="left", padx=8)
        self.log = ctk.CTkTextbox(r, fg_color=ui.BG, text_color=ui.TEXT, font=("Consolas", 11), height=150,
                                  corner_radius=8, border_width=0)
        self.log.pack(fill="x", padx=16, pady=(0, 14))
        self.run(lambda: as_list(powershell_json(FAILURES)), self.show)

    def show(self, rows):
        for w_ in self.fail_card.winfo_children()[1:]:
            w_.destroy()
        if isinstance(rows, Exception) or not rows:
            note(self.fail_card, t("wu_none"), color=ui.GOOD)
            return
        holder, tree = table(self.fail_card, [("date", t("wu_col_date"), 140), ("update", t("wu_col_update"), 520),
                                              ("code", t("wu_col_code"), 120)], height=min(8, len(rows)), stretch="update")
        holder.pack(fill="x", padx=16, pady=(0, 6))
        for r in rows:
            tree.insert("", "end", values=(r.get("date"), r.get("update"), hresult(r.get("code"))), tags=("bad",))
        note(self.fail_card, t("wu_lookup"))

    def reset(self):
        if not confirm(t("wu_reset"), t("wu_reset_ask")):
            return
        self.reset_btn.configure(state="disabled")
        self.log.delete("1.0", "end")
        self.log.insert("end", t("wu_working") + "\n")

        def work():
            restore_point("Benchwise Windows Update reset")
            return powershell(RESET, timeout=300)

        def done(res):
            self.reset_btn.configure(state="normal")
            self.log.insert("end", (str(res) if isinstance(res, Exception) else res) + "\n\n" + t("wu_done"))
            self.log.see("end")
        self.run(work, done)
