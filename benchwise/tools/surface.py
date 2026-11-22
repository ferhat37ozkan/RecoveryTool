"""Disk > Surface Scan: reads the whole disk from start to end - only reads - timing every block, and
draws a map of fast, slow and unreadable areas.  Uses File Recovery's reader, which retries failing
reads in smaller pieces, counts what stays unreadable and notices when the device itself goes away."""

from __future__ import annotations

import time
import tkinter as tk

import customtkinter as ctk

from recoverytool import disks as disklist
from recoverytool.source import Source, SourceLost

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, human, note, texts

texts({
    "sc_how": ("Reads every sector of the disk once and times it; nothing is written. Slow areas are early signs "
               "of wear on a hard disk; unreadable ones mean damaged sectors - copy your data off. A full disk can "
               "take hours; you can stop at any time.",
               "Diskin her sektörünü bir kez okuyup süresini ölçer; hiçbir şey yazılmaz. Yavaş alanlar sabit diskte "
               "yıpranmanın erken işaretleridir; okunamayanlar hasarlı sektör demektir - verilerinizi kopyalayın. "
               "Bütün bir disk saatler sürebilir; istediğiniz an durdurabilirsiniz."),
    "sc_disk": ("Disk", "Disk"),
    "sc_start": ("Start", "Başlat"),
    "sc_stop": ("Stop", "Durdur"),
    "sc_loading": ("Reading the disk list…", "Disk listesi okunuyor…"),
    "sc_progress": ("{done} of {total} · {speed}/s · about {eta} left", "{total} içinde {done} · {speed}/sn · yaklaşık {eta} kaldı"),
    "sc_legend_fast": ("< 50 ms", "< 50 ms"),
    "sc_legend_ok": ("< 150 ms", "< 150 ms"),
    "sc_legend_slow": ("< 500 ms", "< 500 ms"),
    "sc_legend_vslow": ("> 500 ms", "> 500 ms"),
    "sc_legend_bad": ("unreadable", "okunamayan"),
    "sc_counts": ("Blocks: {fast} fast · {ok} normal · {slow} slow · {vslow} very slow · {bad} unreadable",
                  "Bloklar: {fast} hızlı · {ok} normal · {slow} yavaş · {vslow} çok yavaş · {bad} okunamayan"),
    "sc_done_ok": ("Finished: every block could be read.", "Bitti: bütün bloklar okunabildi."),
    "sc_done_slow": ("Finished: no unreadable sectors, but {n} slow blocks - watch this disk's health.",
                     "Bitti: okunamayan sektör yok ama {n} yavaş blok var - bu diskin sağlığını takip edin."),
    "sc_done_bad": ("Finished: {size} could not be read. Copy your data off this disk now.",
                    "Bitti: {size} okunamadı. Bu diskteki verileri hemen kopyalayın."),
    "sc_stopped": ("Stopped at {pos}.", "{pos} konumunda durduruldu."),
    "sc_lost": ("The disk stopped responding during the scan.", "Disk tarama sırasında yanıt vermeyi bıraktı."),
    "sc_open_failed": ("The disk could not be opened: {err}", "Disk açılamadı: {err}"),
    "sc_ssd_note": ("On an SSD every block is about equally fast; the scan mainly finds unreadable areas.",
                    "SSD'de her blok yaklaşık aynı hızdadır; tarama daha çok okunamayan alanları bulur."),
})

CHUNK = 4 << 20
CELLS_X, CELLS_Y = 60, 18
LEVELS = [("fast", 0.05, "#1f7a4a"), ("ok", 0.15, "#3ecf8e"), ("slow", 0.5, "#f5b84b"), ("vslow", 1e9, "#e07a2c")]
BAD_COLOR, EMPTY = "#f26d6d", "#222c42"
RANK = {"empty": 0, "fast": 1, "ok": 2, "slow": 3, "vslow": 4, "bad": 5}


def level_of(seconds, bad):
    if bad:
        return "bad"
    for name, limit, _ in LEVELS:
        if seconds < limit:
            return name
    return "vslow"


def duration(secs):
    secs = int(secs)
    h, rest = divmod(secs, 3600)
    return ("%d:%02d:%02d" % (h, rest // 60, rest % 60)) if h else ("%d:%02d" % divmod(secs, 60))


class View(ToolView):
    title_key = "tool_surface"

    def fill(self):
        self.job = None
        self.disks = []
        c = card(self.body, t("tool_surface"))
        note(c, t("sc_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(row, text=t("sc_disk"), font=("Segoe UI", 12), text_color=ui.TEXT).pack(side="left")
        self.choice = ctk.CTkOptionMenu(row, values=[t("sc_loading")], width=420, fg_color=ui.CARD,
                                        button_color=ui.BORDER, button_hover_color="#33405c", text_color=ui.TEXT)
        self.choice.pack(side="left", padx=10)
        self.start_btn = ui.button(row, t("sc_start"), self.start, 110, primary=True)
        self.start_btn.pack(side="left", padx=(8, 0))
        self.stop_btn = ui.button(row, t("sc_stop"), self.stop, 100)
        self.stop_btn.pack(side="left", padx=8)
        self.stop_btn.configure(state="disabled")
        self.status_line = ctk.CTkLabel(c, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w")
        self.status_line.pack(fill="x", padx=18)
        self.canvas = tk.Canvas(c, height=CELLS_Y * 16 + 4, bg=ui.CARD, highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", padx=18, pady=(8, 6))
        self.canvas.bind("<Configure>", lambda e: self.draw_grid())
        legend = ctk.CTkFrame(c, fg_color="transparent")
        legend.pack(fill="x", padx=18)
        for name, _, color in LEVELS + [("bad", 0, BAD_COLOR)]:
            ctk.CTkFrame(legend, width=14, height=14, fg_color=color, corner_radius=3).pack(side="left", padx=(0, 4))
            ctk.CTkLabel(legend, text=t("sc_legend_" + name), font=("Segoe UI", 11), text_color=ui.MUTED).pack(side="left", padx=(0, 14))
        self.counts = ctk.CTkLabel(c, text=" ", font=("Segoe UI", 12), text_color=ui.TEXT, anchor="w")
        self.counts.pack(fill="x", padx=18, pady=(8, 2))
        self.result = ctk.CTkLabel(c, text=" ", font=("Segoe UI Semibold", 13), text_color=ui.TEXT, anchor="w",
                                   justify="left", wraplength=760)
        self.result.pack(fill="x", padx=18, pady=(0, 14))
        self.cells = ["empty"] * (CELLS_X * CELLS_Y)
        self.run(disklist.list_disks, self.got_disks)

    def got_disks(self, res):
        if isinstance(res, Exception):
            self.choice.configure(values=[str(res)])
            return
        self.disks = [d for d in res if d.get("size")]
        labels = ["Disk %d · %s · %s · %s" % (d["number"], d["name"], human(d["size"]), d.get("bus") or "") for d in self.disks]
        self.choice.configure(values=labels or ["-"])
        self.choice.set(labels[0] if labels else "-")

    def draw_grid(self):
        self.canvas.delete("all")
        w = max(self.canvas.winfo_width(), 100)
        cw = (w - 4) / CELLS_X
        ch = 16
        colors = {name: color for name, _, color in LEVELS}
        colors.update(bad=BAD_COLOR, empty=EMPTY)
        self.rects = []
        for i, state in enumerate(self.cells):
            x, y = 2 + (i % CELLS_X) * cw, 2 + (i // CELLS_X) * ch
            self.rects.append(self.canvas.create_rectangle(x, y, x + cw - 2, y + ch - 2, fill=colors[state], width=0))

    def paint(self, index, state):
        if RANK[state] <= RANK[self.cells[index]]:
            return
        self.cells[index] = state
        colors = {name: color for name, _, color in LEVELS}
        colors.update(bad=BAD_COLOR, empty=EMPTY)
        if index < len(getattr(self, "rects", [])):
            self.canvas.itemconfigure(self.rects[index], fill=colors[state])

    def busy(self):
        return self.job is not None

    def selected_disk(self):
        label = self.choice.get()
        for d in self.disks:
            if label.startswith("Disk %d " % d["number"]):
                return d
        return None

    def start(self):
        d = self.selected_disk()
        if d is None:
            return
        try:
            src = Source(d["path"], size=d["size"], sector=d.get("sector") or 512, label=d["name"])
        except OSError as ex:
            self.result.configure(text=t("sc_open_failed", err=ex), text_color=ui.BAD)
            return
        self.cells = ["empty"] * (CELLS_X * CELLS_Y)
        self.draw_grid()
        self.result.configure(text=t("sc_ssd_note") if d.get("bus") == "NVMe" else " ", text_color=ui.MUTED)
        self.job = {"stop": False, "src": src, "size": d["size"], "counts": dict.fromkeys(RANK, 0)}
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        job = self.job

        def work():
            pos, t0 = 0, time.time()
            size = job["size"]
            per_cell = max(1, size // len(self.cells))
            try:
                while pos < size and not job["stop"]:
                    n = min(CHUNK, size - pos)
                    bad_before = src.bad_bytes
                    a = time.perf_counter()
                    src.read_raw(pos, n)
                    secs = time.perf_counter() - a
                    state = level_of(secs, src.bad_bytes > bad_before)
                    job["counts"][state] += 1
                    first, last = pos // per_cell, min(len(self.cells) - 1, (pos + n - 1) // per_cell)
                    pos += n
                    elapsed = time.time() - t0
                    self.post(self.step, first, last, state, pos, size, elapsed)
                return ("stopped" if job["stop"] else "done"), pos, src.bad_bytes
            except SourceLost:
                return "lost", pos, src.bad_bytes
            finally:
                src.close()
        self.run(work, self.finished)

    def step(self, first, last, state, pos, size, elapsed):
        for i in range(first, last + 1):
            self.paint(i, state)
        speed = pos / elapsed if elapsed > 0 else 0
        eta = (size - pos) / speed if speed else 0
        self.status_line.configure(text=t("sc_progress", done=human(pos), total=human(size), speed=human(speed),
                                          eta=duration(eta)))
        c = self.job["counts"] if self.job else None
        if c:
            self.counts.configure(text=t("sc_counts", **{k: c[k] for k in ("fast", "ok", "slow", "vslow", "bad")}))

    def stop(self):
        if self.job:
            self.job["stop"] = True

    def finished(self, res):
        job, self.job = self.job, None
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if isinstance(res, Exception):
            self.result.configure(text=str(res), text_color=ui.BAD)
            return
        how, pos, bad = res
        counts = job["counts"] if job else {}
        slow = counts.get("slow", 0) + counts.get("vslow", 0)
        if how == "lost":
            self.result.configure(text=t("sc_lost"), text_color=ui.BAD)
        elif bad:
            self.result.configure(text=t("sc_done_bad", size=human(bad)), text_color=ui.BAD)
        elif how == "stopped":
            self.result.configure(text=t("sc_stopped", pos=human(pos)), text_color=ui.MUTED)
        elif slow:
            self.result.configure(text=t("sc_done_slow", n=slow), text_color=ui.WARN)
        else:
            self.result.configure(text=t("sc_done_ok"), text_color=ui.GOOD)

    def destroy(self):
        if self.job:
            self.job["stop"] = True
        super().destroy()
