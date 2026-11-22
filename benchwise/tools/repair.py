"""Disk > Disk Repair - the checking half.  Everything here only reads:

* each disk's partition table: the MBR, and for GPT disks both copies of the table with their
  checksums, and whether the two copies agree;
* each volume's boot sector against its backup copy, and what Windows itself reports about the
  volume (HealthStatus);
* ``chkdsk X:`` without /f, which only reports.

The repairs (chkdsk /f, restoring a boot sector or a GPT from its backup) write to the disk and stay
locked in this version."""

from __future__ import annotations

import customtkinter as ctk

from recoverytool import disks as disklist
from recoverytool.i18n import t
from recoverytool.source import Source

from .. import ptable, ui
from ..toolkit import ToolView, card, human, note, scroll_body, table, text_box, texts
from .sfc import run_streaming

texts({
    "rp_how": ("Only checks - nothing on the disks is changed. Repairs that write to a disk are locked in this "
               "version; copy important data off a disk that shows problems before repairing it.",
               "Yalnızca kontrol eder - disklerde hiçbir şey değiştirilmez. Diske yazan onarımlar bu sürümde "
               "kilitli; sorun gösteren bir diski onarmadan önce önemli verilerinizi kopyalayın."),
    "rp_tables": ("Partition tables", "Bölüm tabloları"),
    "rp_volumes": ("Volumes", "Birimler"),
    "rp_reading": ("Reading…", "Okunuyor…"),
    "rp_col_disk": ("Disk", "Disk"),
    "rp_col_style": ("Table", "Tablo"),
    "rp_col_result": ("Result", "Sonuç"),
    "rp_col_vol": ("Volume", "Birim"),
    "rp_col_fs": ("File system", "Dosya sistemi"),
    "rp_col_size": ("Size", "Boyut"),
    "rp_col_windows": ("Windows says", "Windows durumu"),
    "rp_col_boot": ("Boot sector backup", "Önyükleme sektörü yedeği"),
    "rp_ok": ("OK", "Sağlam"),
    "rp_h_scan": ("Scan needed", "Tarama gerekli"),
    "rp_h_spot": ("Small fix needed", "Küçük onarım gerekli"),
    "rp_h_full": ("Full repair needed", "Tam onarım gerekli"),
    "rp_gpt_ok": ("Both copies intact and identical · {n} partitions", "İki kopya da sağlam ve aynı · {n} bölüm"),
    "rp_mbr_ok": ("MBR signature OK · {n} partitions", "MBR imzası sağlam · {n} bölüm"),
    "rp_raw": ("No partition table (empty or RAW disk)", "Bölüm tablosu yok (boş veya RAW disk)"),
    "rp_p_no_mbr": ("MBR signature missing", "MBR imzası yok"),
    "rp_p_primary_missing": ("primary GPT missing", "birincil GPT yok"),
    "rp_p_primary_bad": ("primary GPT damaged (checksum)", "birincil GPT hasarlı (sağlama toplamı)"),
    "rp_p_backup_missing": ("backup GPT missing", "yedek GPT yok"),
    "rp_p_backup_bad": ("backup GPT damaged (checksum)", "yedek GPT hasarlı (sağlama toplamı)"),
    "rp_p_differ": ("the two GPT copies differ", "iki GPT kopyası farklı"),
    "rp_boot_same": ("identical", "aynı"),
    "rp_boot_differ": ("DIFFERENT", "FARKLI"),
    "rp_boot_no_backup": ("none (this file system keeps none)", "yok (bu dosya sistemi tutmaz)"),
    "rp_boot_unknown": ("-", "-"),
    "rp_denied": ("Run as administrator to read the disks.", "Diskleri okumak için yönetici olarak çalıştırın."),
    "rp_check": ("Check selected volume (read-only)", "Seçili birimi kontrol et (salt okunur)"),
    "rp_check_running": ("chkdsk {vol} is running (read-only)…", "chkdsk {vol} çalışıyor (salt okunur)…"),
    "rp_check_done": ("chkdsk finished (exit code {code}).", "chkdsk bitti (çıkış kodu {code})."),
    "rp_pick": ("Select a volume with a drive letter first.", "Önce sürücü harfi olan bir birim seçin."),
    "rp_repairs": ("Repairs", "Onarımlar"),
    "rp_fix_fs": ("Repair file system (chkdsk /f)", "Dosya sistemini onar (chkdsk /f)"),
    "rp_fix_boot": ("Restore boot sector from backup", "Önyükleme sektörünü yedekten geri yükle"),
    "rp_fix_gpt": ("Rebuild GPT from its backup copy", "GPT'yi yedek kopyasından yeniden oluştur"),
    "rp_locked": ("These write to the disk and are locked in this version.",
                  "Bunlar diske yazar ve bu sürümde kilitlidir."),
})

HEALTH = {"Healthy": ("rp_ok", "good"), "ScanNeeded": ("rp_h_scan", "warn"), "SpotFixNeeded": ("rp_h_spot", "warn"),
          "FullRepairNeeded": ("rp_h_full", "bad")}


def inspect(disks):
    """[(disk, table result text, tag, [(partition, boot kind, boot state)])]; reads a few sectors per disk."""
    out = []
    for d in disks:
        sector = d.get("sector") or 512
        try:
            src = Source(d["path"], size=d["size"], sector=sector)
        except OSError as ex:          # usually: not elevated - still list what Windows reports
            out.append((d, ex, "bad", [(p, None, "unknown") for p in d["partitions"] if p.get("filesystem")]))
            continue
        try:
            g = ptable.read_gpt(src.read_raw, d["size"], sector)
            vols = []
            for p in d["partitions"]:
                if not p.get("filesystem"):
                    continue
                kind, state = ptable.check_boot(
                    lambda off, n, base=p["offset"]: src.read_raw(base + off, n), p["size"])
                vols.append((p, kind, state))
        except Exception as ex:      # noqa: BLE001 - shown in the table
            out.append((d, ex, "bad", []))
            continue
        finally:
            src.close()
        out.append((d, g, None, vols))
    return out


class View(ToolView):
    title_key = "tool_repair"

    def fill(self):
        self.vol_rows = {}
        page = scroll_body(self)
        c = card(page, t("tool_repair"))
        note(c, t("rp_how"), color=ui.TEXT)
        top = card(page, t("rp_tables"))
        holder, self.tables = table(top, [("disk", t("rp_col_disk"), 300), ("style", t("rp_col_style"), 70),
                                          ("result", t("rp_col_result"), 420)], height=3, stretch="result")
        holder.pack(fill="x", padx=18, pady=(0, 14))
        vc = card(page, t("rp_volumes"))
        holder, self.vols = table(vc, [("vol", t("rp_col_vol"), 200), ("fs", t("rp_col_fs"), 90),
                                       ("size", t("rp_col_size"), 90), ("win", t("rp_col_windows"), 150),
                                       ("boot", t("rp_col_boot"), 220)], height=4, stretch="boot")
        holder.pack(fill="x", padx=18, pady=(0, 8))
        row = ctk.CTkFrame(vc, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        self.check_btn = ui.button(row, t("rp_check"), self.chkdsk, 280, primary=True)
        self.check_btn.pack(side="left")
        self.check_info = ctk.CTkLabel(row, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED)
        self.check_info.pack(side="left", padx=12)
        self.log = text_box(vc, height=6)
        self.log.pack(fill="x", padx=18, pady=(0, 14))
        rc = card(page, t("rp_repairs"))
        note(rc, t("rp_locked"))
        row = ctk.CTkFrame(rc, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 14))
        for key in ("rp_fix_fs", "rp_fix_boot", "rp_fix_gpt"):
            b = ui.button(row, "🔒 " + t(key), lambda: None, 250)
            b.configure(state="disabled")
            b.pack(side="left", padx=(0, 8))
        self.tables.insert("", "end", values=(t("rp_reading"), "", ""), tags=("muted",))
        self.run(lambda: inspect(disklist.list_disks()), self.show)

    def show(self, res):
        for tree in (self.tables, self.vols):
            for item in tree.get_children():
                tree.delete(item)
        if isinstance(res, Exception):
            self.tables.insert("", "end", values=(str(res), "", ""), tags=("bad",))
            return
        denied = False
        for d, g, tag, vols in res:
            name = "Disk %d · %s · %s" % (d["number"], d["name"], human(d["size"]))
            if isinstance(g, Exception):
                denied |= isinstance(g, PermissionError)
                text = t("rp_denied") if isinstance(g, PermissionError) else str(g)
                self.tables.insert("", "end", values=(name, d.get("style") or "", text), tags=("bad",))
            else:
                style, text, tag = self.describe(g)
                self.tables.insert("", "end", values=(name, style, text), tags=(tag,))
            for p, kind, state in vols:
                vol = "%s%s" % ((p["letter"] + ":  ") if p.get("letter") else "", p.get("label") or "")
                vol = vol.strip() or "Disk %d #%d" % (d["number"], p["number"])
                h = HEALTH.get(p.get("health") or "", (p.get("health") or "-", "muted"))
                win = t(h[0]) if h[0].startswith("rp_") else h[0]
                btag = {"same": "good", "differ": "bad"}.get(state, h[1] if h[1] != "good" else "")
                iid = self.vols.insert("", "end", values=(vol, p.get("filesystem") or kind or "", human(p["size"]), win,
                                                          t("rp_boot_" + state)),
                                       tags=((h[1],) if h[1] in ("warn", "bad") else (btag,) if btag else ()))
                self.vol_rows[iid] = p
        if denied:
            self.check_info.configure(text=t("rp_denied"), text_color=ui.WARN)
        self.tables.configure(height=max(1, len(self.tables.get_children())))
        self.vols.configure(height=max(1, min(10, len(self.vols.get_children()))))

    @staticmethod
    def describe(g):
        primary = g["primary"]
        if primary or g["backup"]:
            problems = ptable.gpt_problems(g)
            if not problems:
                return "GPT", t("rp_gpt_ok", n=len(g["entries"])), "good"
            return "GPT", " · ".join(t("rp_p_" + p) for p in problems), "bad"
        mbr = g["mbr"]
        if mbr["signature"]:
            return "MBR", t("rp_mbr_ok", n=len(mbr["entries"])), "good"
        return "-", t("rp_raw"), "muted"

    def chkdsk(self):
        if self.busy():
            return
        sel = self.vols.selection()
        p = self.vol_rows.get(sel[0]) if sel else None
        if not p or not p.get("letter"):
            self.check_info.configure(text=t("rp_pick"), text_color=ui.WARN)
            return
        vol = p["letter"] + ":"
        self.log.delete("1.0", "end")
        self.check_info.configure(text=t("rp_check_running", vol=vol), text_color=ui.MUTED)
        self.check_btn.configure(state="disabled")

        def on_text(text):
            self.post(self.append, text)
        self.run(lambda: run_streaming(["chkdsk.exe", vol], on_text), self.checked)   # no /f, /r, /x: report only

    def append(self, text):
        lines = [ln for ln in text.replace("\r", "\n").split("\n") if ln.strip()]
        if lines:
            self.log.insert("end", "\n".join(lines) + "\n")
            self.log.see("end")

    def checked(self, res):
        self.check_btn.configure(state="normal")
        if isinstance(res, Exception):
            self.check_info.configure(text=str(res), text_color=ui.BAD)
            return
        code, _ = res
        self.check_info.configure(text=t("rp_check_done", code=code), text_color=ui.GOOD if code == 0 else ui.WARN)
