"""Disk > Secure Erase - the preview half: what is on a disk that an erase would destroy, which method
suits it (an SSD needs its firmware's own erase, a hard disk one overwrite pass), how long it would take,
and - by reading a sample of the disk - how much of it still holds data.

Erasing itself is locked in this version."""

from __future__ import annotations

import random

import customtkinter as ctk

from recoverytool import disks as disklist
from recoverytool.i18n import t
from recoverytool.source import Source

from .. import ui
from ..toolkit import ToolView, card, human, kv_grid, note, texts

texts({
    "er_how": ("Shows what erasing a disk would destroy and how it would be done. Nothing is erased: the erase "
               "itself is locked in this version.",
               "Bir diski silmenin neleri yok edeceğini ve nasıl yapılacağını gösterir. Hiçbir şey silinmez: "
               "silme işlemi bu sürümde kilitli."),
    "er_disk": ("Disk", "Disk"),
    "er_sample": ("Sample the disk", "Diskten örnek oku"),
    "er_sampling": ("Reading {n} samples…", "{n} örnek okunuyor…"),
    "er_system": ("This is the disk Windows runs from. It can never be erased from within Windows.",
                  "Bu, Windows'un çalıştığı disk. Windows içinden asla silinemez."),
    "er_volumes": ("Will be destroyed", "Yok edilecekler"),
    "er_none": ("no partitions", "bölüm yok"),
    "er_method": ("Method", "Yöntem"),
    "er_m_ssd": ("SSD / NVMe: the drive's own secure erase (or sanitize) command. Overwriting an SSD does not "
                 "reliably reach every cell.",
                 "SSD / NVMe: sürücünün kendi güvenli silme (veya sanitize) komutu. SSD'nin üzerine yazmak her "
                 "hücreye güvenilir şekilde ulaşmaz."),
    "er_m_hdd": ("Hard disk: one pass of zeros over every sector. A single pass is enough for modern disks.",
                 "Sabit disk: her sektörün üzerine bir kez sıfır yazılır. Modern diskler için tek geçiş yeterlidir."),
    "er_m_usb": ("USB stick / card: one pass of zeros. Worn-out cells that the controller has retired cannot be "
                 "reached by any tool.",
                 "USB bellek / kart: bir kez sıfır yazılır. Denetleyicinin devre dışı bıraktığı yıpranmış hücrelere "
                 "hiçbir araç ulaşamaz."),
    "er_m_raid": ("RAID array: the member disks are erased one by one, each with the method that suits it "
                  "(the array is gone afterwards).",
                  "RAID dizisi: üye diskler tek tek, her biri kendine uygun yöntemle silinir (dizi sonrasında "
                  "kalmaz)."),
    "er_hours": ("{n} h", "{n} saat"),
    "er_minutes": ("{n} min", "{n} dakika"),
    "er_time": ("Estimated time", "Tahmini süre"),
    "er_time_v": ("about {t} (at {speed}/s)", "yaklaşık {t} ({speed}/sn hızla)"),
    "er_time_fw": ("seconds to a few minutes (done inside the drive)", "saniyeler ile birkaç dakika (sürücünün içinde yapılır)"),
    "er_data": ("Holds data", "Veri içeren"),
    "er_data_v": ("{pct}% of {n} sampled blocks are not empty", "örneklenen {n} bloğun %{pct} kadarı boş değil"),
    "er_denied": ("Run as administrator to read the disk.", "Diski okumak için yönetici olarak çalıştırın."),
    "er_erase": ("Erase disk", "Diski sil"),
    "er_locked": ("Erasing is locked in this version.", "Silme bu sürümde kilitli."),
})

SPEEDS = {"NVMe": 1.5e9, "SSD": 4e8, "HDD": 1.5e8, "USB": 3e7}


def kind_of(d):
    bus = (d.get("bus") or "").upper()
    name = (d.get("name") or "").upper()
    if bus == "NVME":
        return "NVMe"
    if bus in ("USB", "SD", "MMC"):
        return "USB"
    if bus == "RAID":
        return "RAID"
    if "SSD" in name:
        return "SSD"
    return "HDD"


def sample(disk, count=256, block=1 << 20):
    """Share of ``count`` random 1 MB blocks that contain anything but zeros."""
    sector = disk.get("sector") or 512
    src = Source(disk["path"], size=disk["size"], sector=sector)
    try:
        span = max(1, disk["size"] // block)
        picks = sorted(random.sample(range(span), min(count, span)))
        used = 0
        for i in picks:
            data = src.read_raw(i * block, min(block, disk["size"] - i * block))
            if data.count(0) != len(data):
                used += 1
        return used, len(picks)
    finally:
        src.close()


def duration_words(secs):
    h = secs / 3600
    return t("er_hours", n="%.1f" % h) if h >= 1 else t("er_minutes", n=max(1, round(secs / 60)))


class View(ToolView):
    title_key = "tool_erase"

    def fill(self):
        self.disks = []
        self.sampled = {}
        c = card(self.body, t("tool_erase"))
        note(c, t("er_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkLabel(row, text=t("er_disk"), font=("Segoe UI", 12), text_color=ui.TEXT).pack(side="left")
        self.choice = ctk.CTkOptionMenu(row, values=["…"], width=420, fg_color=ui.CARD, button_color=ui.BORDER,
                                        button_hover_color="#33405c", text_color=ui.TEXT, command=lambda _: self.show())
        self.choice.pack(side="left", padx=10)
        self.sample_btn = ui.button(row, t("er_sample"), self.do_sample, 170)
        self.sample_btn.pack(side="left", padx=(8, 0))
        self.warn = ctk.CTkLabel(c, text=" ", font=("Segoe UI Semibold", 12), text_color=ui.BAD, anchor="w",
                                 justify="left", wraplength=760)
        self.warn.pack(fill="x", padx=18)
        self.details = ctk.CTkFrame(c, fg_color="transparent")
        self.details.pack(fill="x", pady=(4, 4))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(4, 14))
        b = ui.button(row, "🔒 " + t("er_erase"), lambda: None, 160)
        b.configure(state="disabled")
        b.pack(side="left")
        ctk.CTkLabel(row, text=t("er_locked"), font=("Segoe UI", 12), text_color=ui.MUTED).pack(side="left", padx=12)
        self.run(disklist.list_disks, self.got_disks)

    def got_disks(self, res):
        if isinstance(res, Exception):
            self.warn.configure(text=str(res))
            return
        self.disks = [d for d in res if d.get("size")]
        labels = ["Disk %d · %s · %s · %s" % (d["number"], d["name"], human(d["size"]), d.get("bus") or "") for d in self.disks]
        self.choice.configure(values=labels or ["-"])
        self.choice.set(labels[0] if labels else "-")
        self.show()

    def current(self):
        label = self.choice.get()
        return next((d for d in self.disks if label.startswith("Disk %d " % d["number"])), None)

    def show(self):
        for w_ in self.details.winfo_children():
            w_.destroy()
        d = self.current()
        if d is None:
            return
        self.warn.configure(text=t("er_system") if d.get("system") else " ")
        vols = []
        for p in d["partitions"]:
            name = " ".join(x for x in ((p.get("letter") + ":") if p.get("letter") else "", p.get("label") or "",
                                         p.get("filesystem") or p.get("type") or "") if x)
            vols.append("%s · %s" % (name, human(p["size"])))
        kind = kind_of(d)
        method = {"NVMe": "er_m_ssd", "SSD": "er_m_ssd", "USB": "er_m_usb", "RAID": "er_m_raid"}.get(kind, "er_m_hdd")
        if method in ("er_m_ssd", "er_m_raid"):
            when = t("er_time_fw")
        else:
            speed = SPEEDS[kind]
            when = t("er_time_v", t=duration_words(d["size"] / speed), speed=human(speed))
        rows = [(t("er_volumes"), "\n".join(vols) or t("er_none")), (t("er_method"), t(method)), (t("er_time"), when)]
        s = self.sampled.get(d["number"])
        if s:
            rows.append((t("er_data"), s))
        kv_grid(self.details, rows)

    def do_sample(self):
        d = self.current()
        if d is None or self.busy():
            return
        self.sample_btn.configure(state="disabled", text=t("er_sampling", n=256))
        self.run(lambda: sample(d), lambda res: self.sampled_done(d, res))

    def sampled_done(self, d, res):
        self.sample_btn.configure(state="normal", text=t("er_sample"))
        if isinstance(res, PermissionError):
            self.sampled[d["number"]] = t("er_denied")
        elif isinstance(res, Exception):
            self.sampled[d["number"]] = str(res)
        else:
            used, n = res
            self.sampled[d["number"]] = t("er_data_v", pct=round(100 * used / n) if n else 0, n=n)
        self.show()
