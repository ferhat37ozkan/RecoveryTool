"""Disk > Partitions: the layout of each disk - partitions and unallocated space - as Windows sees it,
and a backup of the partition table to a file (the first 34 and the last 33 sectors, which hold the
MBR and both GPT copies), so a damaged table can be rebuilt later.

Creating, deleting and formatting partitions, and writing a table back, change the disk and stay
locked in this version."""

from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from recoverytool import disks as disklist
from recoverytool.i18n import t
from recoverytool.source import Source

from .. import ptable, ui
from ..toolkit import ToolView, card, human, note, table, texts

texts({
    "pt_how": ("The layout of each disk. You can save a backup of the partition table to a file; nothing on the "
               "disk is changed.",
               "Her diskin yerleşimi. Bölüm tablosunun yedeğini bir dosyaya kaydedebilirsiniz; diskte hiçbir şey "
               "değiştirilmez."),
    "pt_disk": ("Disk", "Disk"),
    "pt_style": ("{style} · {sector}-byte sectors · {n} partitions", "{style} · {sector} bayt sektör · {n} bölüm"),
    "pt_col_no": ("#", "#"),
    "pt_col_vol": ("Volume", "Birim"),
    "pt_col_fs": ("File system", "Dosya sistemi"),
    "pt_col_type": ("Type", "Tür"),
    "pt_col_start": ("Starts at", "Başlangıç"),
    "pt_col_size": ("Size", "Boyut"),
    "pt_col_used": ("Used", "Dolu"),
    "pt_unallocated": ("Unallocated", "Ayrılmamış"),
    "pt_backup": ("Back up partition table…", "Bölüm tablosunu yedekle…"),
    "pt_saved": ("Saved: {path}", "Kaydedildi: {path}"),
    "pt_denied": ("Run as administrator to read the partition table.",
                  "Bölüm tablosunu okumak için yönetici olarak çalıştırın."),
    "pt_changes": ("Changes", "Değişiklikler"),
    "pt_changes_note": ("These change the disk and are locked in this version. Windows Disk Management can do them "
                        "meanwhile.",
                        "Bunlar diski değiştirir ve bu sürümde kilitlidir. Şimdilik Windows Disk Yönetimi ile "
                        "yapabilirsiniz."),
    "pt_create": ("Create", "Oluştur"),
    "pt_delete": ("Delete", "Sil"),
    "pt_format": ("Format", "Biçimlendir"),
    "pt_restore": ("Restore table from backup", "Tabloyu yedekten geri yükle"),
    "pt_open_dm": ("Open Disk Management", "Disk Yönetimi'ni aç"),
})

COLORS = ["#4f8cff", "#3ecf8e", "#b085f5", "#f5b84b", "#4fd1d9", "#f28cb1"]
HEAD_SECTORS, TAIL_SECTORS = 34, 33


def backup_table(disk, path):
    """Write the first 34 and last 33 sectors of ``disk`` to ``path`` and a readable report beside it."""
    sector = disk.get("sector") or 512
    src = Source(disk["path"], size=disk["size"], sector=sector)
    try:
        head = src.read_raw(0, HEAD_SECTORS * sector)
        tail_off = disk["size"] - TAIL_SECTORS * sector
        tail = src.read_raw(tail_off, TAIL_SECTORS * sector)
        g = ptable.read_gpt(src.read_raw, disk["size"], sector)
    finally:
        src.close()
    with open(path, "wb") as f:
        f.write(head + tail)
    lines = ["Benchwise partition table backup", "disk: %s" % disk["name"], "size: %d bytes" % disk["size"],
             "sector: %d" % sector, "style: %s" % (disk.get("style") or ""),
             "created: %s" % time.strftime("%Y-%m-%d %H:%M:%S"), "",
             "file layout: bytes 0..%d = disk sectors 0..%d; the rest = disk sectors %d..%d (offset %d)"
             % (len(head) - 1, HEAD_SECTORS - 1, tail_off // sector, disk["size"] // sector - 1, tail_off),
             "problems: %s" % ((", ".join(ptable.gpt_problems(g)) or "none") if (g["primary"] or g["backup"]) else "-"), ""]
    if g["primary"] or g["backup"]:
        lines.append("GPT disk GUID: %s" % (g["primary"] or g["backup"])["guid"])
        for e in g["entries"]:
            lines.append("  #%d  %s  LBA %d-%d  %s  %s" % (e["index"], e["type_name"], e["first"], e["last"], e["name"], e["guid"]))
    else:
        lines.append("MBR disk id: %s" % g["mbr"]["disk_id"])
        for e in g["mbr"]["entries"]:
            lines.append("  #%d  %s  LBA %d  %d sectors%s" % (e["index"], e["type_name"], e["lba"], e["sectors"],
                                                             "  (active)" if e["boot"] else ""))
    with open(path + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


class View(ToolView):
    title_key = "tool_partitions"

    def fill(self):
        self.disks = []
        c = card(self.body, t("tool_partitions"))
        note(c, t("pt_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(row, text=t("pt_disk"), font=("Segoe UI", 12), text_color=ui.TEXT).pack(side="left")
        self.choice = ctk.CTkOptionMenu(row, values=["…"], width=420, fg_color=ui.CARD, button_color=ui.BORDER,
                                        button_hover_color="#33405c", text_color=ui.TEXT, command=lambda _: self.show())
        self.choice.pack(side="left", padx=10)
        self.backup_btn = ui.button(row, t("pt_backup"), self.backup, 230, primary=True)
        self.backup_btn.pack(side="left", padx=(8, 0))
        self.style_line = ctk.CTkLabel(c, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w")
        self.style_line.pack(fill="x", padx=18)
        self.canvas = tk.Canvas(c, height=46, bg=ui.CARD, highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", padx=18, pady=(8, 10))
        self.canvas.bind("<Configure>", lambda e: self.draw())
        holder, self.tree = table(c, [("no", t("pt_col_no"), 40), ("vol", t("pt_col_vol"), 200), ("fs", t("pt_col_fs"), 90),
                                      ("type", t("pt_col_type"), 130), ("start", t("pt_col_start"), 100),
                                      ("size", t("pt_col_size"), 90), ("used", t("pt_col_used"), 150)],
                                  height=4, stretch="vol")
        holder.pack(fill="x", padx=18, pady=(0, 8))
        self.result = ctk.CTkLabel(c, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w", justify="left",
                                   wraplength=760)
        self.result.pack(fill="x", padx=18, pady=(0, 12))
        ch = card(self.body, t("pt_changes"))
        note(ch, t("pt_changes_note"))
        row = ctk.CTkFrame(ch, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 14))
        for key, width in (("pt_create", 120), ("pt_delete", 100), ("pt_format", 130), ("pt_restore", 240)):
            b = ui.button(row, "🔒 " + t(key), lambda: None, width)
            b.configure(state="disabled")
            b.pack(side="left", padx=(0, 8))
        ui.button(row, t("pt_open_dm"), lambda: os.startfile("diskmgmt.msc"), 180).pack(side="right")
        self.run(disklist.list_disks, self.got_disks)

    def got_disks(self, res):
        if isinstance(res, Exception):
            self.style_line.configure(text=str(res), text_color=ui.BAD)
            return
        self.disks = [d for d in res if d.get("size")]
        labels = ["Disk %d · %s · %s" % (d["number"], d["name"], human(d["size"])) for d in self.disks]
        self.choice.configure(values=labels or ["-"])
        self.choice.set(labels[0] if labels else "-")
        self.show()

    def current(self):
        label = self.choice.get()
        return next((d for d in self.disks if label.startswith("Disk %d " % d["number"])), None)

    def show(self):
        d = self.current()
        for item in self.tree.get_children():
            self.tree.delete(item)
        if d is None:
            return
        self.style_line.configure(text=t("pt_style", style=d.get("style") or "-", sector=d.get("sector") or 512,
                                         n=len(d["partitions"])), text_color=ui.MUTED)
        n = 0
        for r in disklist.layout(d):
            if r["kind"] == "gap":
                self.tree.insert("", "end", values=("", t("pt_unallocated"), "", "", human(r["offset"]), human(r["size"]), ""),
                                 tags=("muted",))
                continue
            p = r["part"]
            vol = " ".join(x for x in ((p.get("letter") + ":") if p.get("letter") else "", p.get("label") or "") if x)
            used = ""
            if p.get("filesystem") and p.get("free") is not None and p["size"]:
                u = max(0, p["size"] - p["free"])
                used = "%s (%d%%)" % (human(u), round(100 * u / p["size"]))
            self.tree.insert("", "end", values=(p["number"], vol, p.get("filesystem") or "", p.get("type") or "",
                                                human(p["offset"]), human(p["size"]), used))
            n += 1
        self.tree.configure(height=max(1, min(12, len(self.tree.get_children()))))
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        d = self.current()
        if d is None or not d["size"]:
            return
        w = max(self.canvas.winfo_width(), 100)
        rows = disklist.layout(d)
        if not rows:
            rows = [{"kind": "gap", "offset": 0, "size": d["size"]}]
        # every piece gets at least a sliver so tiny partitions stay visible
        minw = 10
        total = sum(r["size"] for r in rows)
        widths = [max(minw, (w - 2) * r["size"] / total) for r in rows]
        scale = (w - 2) / sum(widths)
        x, ci = 1, 0
        for r, wd in zip(rows, widths):
            wd *= scale
            if r["kind"] == "gap":
                fill, text = ui.BORDER, t("pt_unallocated")
            else:
                p = r["part"]
                fill = COLORS[ci % len(COLORS)]
                ci += 1
                text = (p.get("letter") + ":  " if p.get("letter") else "") + (p.get("filesystem") or p.get("type") or "")
            self.canvas.create_rectangle(x, 2, x + wd - 2, 44, fill=fill, width=0)
            if wd > 60:
                self.canvas.create_text(x + 6, 14, text=text, anchor="w", fill="#0b1020" if r["kind"] != "gap" else ui.MUTED,
                                        font=("Segoe UI Semibold", 9))
                self.canvas.create_text(x + 6, 32, text=human(r["size"]), anchor="w",
                                        fill="#0b1020" if r["kind"] != "gap" else ui.MUTED, font=("Segoe UI", 9))
            x += wd

    def backup(self):
        d = self.current()
        if d is None or self.busy():
            return
        path = filedialog.asksaveasfilename(defaultextension=".bin",
                                            initialfile="partition-table-disk%d-%s.bin" % (d["number"], time.strftime("%Y%m%d")),
                                            filetypes=[("Backup", "*.bin")])
        if not path:
            return
        self.run(lambda: backup_table(d, os.path.normpath(path)), self.saved)

    def saved(self, res):
        if isinstance(res, PermissionError):
            self.result.configure(text=t("pt_denied"), text_color=ui.WARN)
        elif isinstance(res, Exception):
            self.result.configure(text=str(res), text_color=ui.BAD)
        else:
            self.result.configure(text=t("pt_saved", path=res), text_color=ui.GOOD)
