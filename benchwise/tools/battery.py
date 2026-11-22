"""Battery & Power > Battery Health: designed vs. current full capacity (wear), charge cycles, charge
state, and Windows' detailed battery report."""

from __future__ import annotations

import os
import subprocess
import tempfile
import webbrowser

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, as_list, card, kv_grid, note, powershell_json, run_command, texts

texts({
    "bt_loading": ("Reading the battery…", "Pil okunuyor…"),
    "bt_none": ("This computer has no battery (or Windows does not see one).",
                "Bu bilgisayarda pil yok (veya Windows göremiyor)."),
    "bt_battery": ("Battery {n}", "Pil {n}"),
    "bt_health": ("Health", "Sağlık"),
    "bt_design": ("Designed capacity", "Tasarım kapasitesi"),
    "bt_full": ("Full charge now", "Şu anki tam şarj"),
    "bt_wear": ("Wear", "Yıpranma"),
    "bt_cycles": ("Charge cycles", "Şarj döngüsü"),
    "bt_charge": ("Charge", "Şarj"),
    "bt_state": ("State", "Durum"),
    "bt_charging": ("charging", "şarj oluyor"),
    "bt_on_power": ("plugged in", "prize takılı"),
    "bt_on_battery": ("on battery", "pilde"),
    "bt_runtime": ("Time left (estimate)", "Kalan süre (tahmini)"),
    "bt_name": ("Name", "Ad"),
    "bt_chem": ("Chemistry", "Kimya"),
    "bt_good": ("Good: the battery still holds {pct} of its original capacity.",
                "İyi: pil hâlâ ilk kapasitesinin {pct} kadarını tutuyor."),
    "bt_warning": ("Worn: it holds {pct} of its original capacity. Runtime is noticeably shorter.",
                "Yıpranmış: ilk kapasitesinin {pct} kadarını tutuyor. Kullanım süresi belirgin şekilde kısalır."),
    "bt_bad": ("Worn out: only {pct} of its original capacity is left. Plan a replacement.",
               "Ömrünü doldurmuş: ilk kapasitesinin yalnızca {pct} kadarı kaldı. Değişimi planlayın."),
    "bt_unknown": ("Windows does not report the capacities of this battery.",
                   "Windows bu pilin kapasitelerini bildirmiyor."),
    "bt_report": ("Detailed Windows battery report", "Ayrıntılı Windows pil raporu"),
    "bt_report_how": ("Windows keeps a history of capacity and usage; this opens it in your browser.",
                      "Windows kapasite ve kullanım geçmişini tutar; bu düğme raporu tarayıcınızda açar."),
    "bt_report_open": ("Create and open the report", "Raporu oluştur ve aç"),
    "bt_report_failed": ("The report could not be created: {err}", "Rapor oluşturulamadı: {err}"),
    "bt_minutes": ("{h} h {m} min", "{h} sa {m} dk"),
})

SCRIPT = r"""
$static = @(Get-CimInstance -Namespace root/wmi -ClassName BatteryStaticData -ErrorAction SilentlyContinue)
$full = @(Get-CimInstance -Namespace root/wmi -ClassName BatteryFullChargedCapacity -ErrorAction SilentlyContinue)
$cyc = @(Get-CimInstance -Namespace root/wmi -ClassName BatteryCycleCount -ErrorAction SilentlyContinue)
$st = @(Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus -ErrorAction SilentlyContinue)
$wb = @(Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue)
$n = [Math]::Max([Math]::Max($static.Count, $wb.Count), $st.Count)
$out = for ($i = 0; $i -lt $n; $i++) {
  [pscustomobject]@{
    design = $(if ($i -lt $static.Count) { [int64]$static[$i].DesignedCapacity } else { $null })
    full = $(if ($i -lt $full.Count) { [int64]$full[$i].FullChargedCapacity } else { $null })
    cycles = $(if ($i -lt $cyc.Count) { [int]$cyc[$i].CycleCount } else { $null })
    remaining = $(if ($i -lt $st.Count) { [int64]$st[$i].RemainingCapacity } else { $null })
    charging = $(if ($i -lt $st.Count) { [bool]$st[$i].Charging } else { $null })
    online = $(if ($i -lt $st.Count) { [bool]$st[$i].PowerOnline } else { $null })
    percent = $(if ($i -lt $wb.Count) { [int]$wb[$i].EstimatedChargeRemaining } else { $null })
    runtime = $(if ($i -lt $wb.Count) { [int]$wb[$i].EstimatedRunTime } else { $null })
    name = $(if ($i -lt $wb.Count) { [string]$wb[$i].Name } else { $null })
    chem = $(if ($i -lt $wb.Count) { [int]$wb[$i].Chemistry } else { $null })
  }
}
ConvertTo-Json -Compress -InputObject @($out)
"""

CHEMISTRY = {3: "Lead acid", 4: "NiCd", 5: "NiMH", 6: "Li-ion", 7: "Zinc air", 8: "Li-polymer"}


def health(design, full):
    """(percent of the original capacity, level) or (None, "unknown")."""
    if not design or not full or design <= 0:
        return None, "unknown"
    pct = max(0, min(100, round(100 * full / design)))
    return pct, "good" if pct >= 80 else "warning" if pct >= 60 else "bad"


class View(ToolView):
    title_key = "tool_battery"

    def fill(self):
        self.list = ctk.CTkFrame(self.body, fg_color="transparent")
        self.list.pack(fill="x")
        note(self.list, t("bt_loading"))
        r = card(self.body, t("bt_report"))
        note(r, t("bt_report_how"), color=ui.TEXT)
        ui.button(r, t("bt_report_open"), self.report, 230).pack(anchor="w", padx=18, pady=(0, 14))
        self.run(lambda: as_list(powershell_json(SCRIPT)), self.show)

    def show(self, batteries):
        for w_ in self.list.winfo_children():
            w_.destroy()
        if isinstance(batteries, Exception) or not batteries:
            c = card(self.list, t("tool_battery"))
            note(c, t("bt_none"), color=ui.MUTED)
            return
        for i, b in enumerate(batteries, 1):
            c = card(self.list, t("bt_battery", n=i) if len(batteries) > 1 else t("tool_battery"))
            pct, level = health(b.get("design"), b.get("full"))
            color = ui.LEVEL[level]
            msg = t("bt_" + level, pct=t("dh_pct", n=pct)) if pct is not None else t("bt_unknown")
            ctk.CTkLabel(c, text=msg, font=("Segoe UI Semibold", 14), text_color=color, anchor="w", justify="left",
                         wraplength=720).pack(fill="x", padx=18, pady=(0, 8))
            state = (t("bt_charging") if b.get("charging") else t("bt_on_power") if b.get("online")
                     else t("bt_on_battery")) if b.get("online") is not None else ""
            run = b.get("runtime")
            runtime = t("bt_minutes", h=run // 60, m=run % 60) if run and 0 < run < 71582788 and not b.get("online") else ""
            kv_grid(c, [(t("bt_design"), "%s mWh" % "{:,}".format(b["design"]).replace(",", " ") if b.get("design") else ""),
                        (t("bt_full"), "%s mWh" % "{:,}".format(b["full"]).replace(",", " ") if b.get("full") else ""),
                        (t("bt_wear"), t("dh_pct", n=100 - pct) if pct is not None else ""),
                        (t("bt_cycles"), b.get("cycles") if b.get("cycles") else ""),
                        (t("bt_charge"), t("dh_pct", n=b["percent"]) if b.get("percent") is not None else ""),
                        (t("bt_state"), state), (t("bt_runtime"), runtime), (t("bt_name"), b.get("name")),
                        (t("bt_chem"), CHEMISTRY.get(b.get("chem"), ""))])

    def report(self):
        path = os.path.join(tempfile.gettempdir(), "benchwise-battery-report.html")

        def work():
            code, out = run_command(["powercfg", "/batteryreport", "/output", path], timeout=60)
            if not os.path.exists(path):
                raise RuntimeError(out.strip() or "powercfg %d" % code)
            return path
        self.run(work, lambda res: self.set_status(t("bt_report_failed", err=res)) if isinstance(res, Exception)
                 else webbrowser.open(res))
