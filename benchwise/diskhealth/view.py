"""The Disk Health screen: disks on the left, the selected disk's verdict and figures on the right."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from recoverytool.i18n import t
from recoverytool.model import human_size

from .. import ui
from ..ui import BG, BORDER, CARD, CARD_HOVER, LEVEL, MUTED, TEXT
from . import data, verdict

LIST_WIDTH = 300


def count(n):
    return "{:,}".format(n).replace(",", " ")


def hours_text(h):
    if h is None:
        return None
    span = t("dh_years", n=h / 8766) if h >= 8766 else t("dh_days", n=h // 24)
    return t("dh_hours_fmt", h=count(h), d=span)


def state_text(s):
    """Windows' English status words in the interface language (unknown words stay as they are)."""
    key = "dh_state_" + s.replace(" ", "_").lower()
    text = t(key)
    return s if text == key else text


def media_text(d):
    if d.get("media") == "SSD" or d.get("bus") == "NVMe":
        return t("dh_ssd") + (" (NVMe)" if d.get("bus") == "NVMe" else "")
    if d.get("media") == "HDD":
        return t("dh_hdd_rpm", rpm=count(d["spindle"])) if d.get("spindle") else t("dh_hdd")
    return ""


class DiskHealthView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=BG)
        self.disks, self.results, self.selected, self.loading, self.error = [], {}, None, False, None
        self.events = queue.Queue()
        style = ttk.Style(self)
        style.configure("Health.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=26,
                        borderwidth=0, font=("Segoe UI", 10))
        style.configure("Health.Treeview.Heading", background=BORDER, foreground=MUTED, relief="flat",
                        font=("Segoe UI", 9, "bold"), padding=(6, 5))
        style.map("Health.Treeview", background=[("selected", "#22304d")])
        style.layout("Health.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        self.build()
        self.load()
        self.after(100, self.poll)

    # -- data -----------------------------------------------------------------------------------
    def busy(self):
        return self.loading

    def load(self):
        if self.loading:
            return
        self.loading, self.error = True, None
        self.status.configure(text=t("dh_loading"))
        self.refresh_btn.configure(state="disabled")

        def work():
            try:
                self.events.put(("done", data.collect()))
            except Exception as ex:          # shown to the user; the screen stays usable
                self.events.put(("failed", str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                self.loading = False
                self.refresh_btn.configure(state="normal")
                if kind == "done":
                    self.disks = value
                    self.results = {d["number"]: verdict.assess(d) for d in value}
                    if self.selected not in self.results:
                        self.selected = value[0]["number"] if value else None
                    self.status.configure(text=" " if value else t("dh_none"))
                else:
                    self.error = value
                    self.status.configure(text=t("dh_failed", err=value.splitlines()[0] if value else "?"))
                self.render()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self.poll)

    # -- layout ---------------------------------------------------------------------------------
    def build(self):
        for w in self.winfo_children():
            w.destroy()
        root = ctk.CTkFrame(self, fg_color=BG)
        root.pack(fill="both", expand=True, padx=22, pady=(4, 18))
        head = ui.tool_header(root, t("tool_health"), t("tool_health_d"))
        self.refresh_btn = ui.button(head, t("dh_refresh"), self.load, 100)
        self.refresh_btn.pack(side="right")
        self.status = ctk.CTkLabel(head, text=" ", font=("Segoe UI", 11), text_color=MUTED)
        self.status.pack(side="right", padx=12)
        body = ctk.CTkFrame(root, fg_color=BG)
        body.pack(fill="both", expand=True)
        self.listf = ctk.CTkScrollableFrame(body, fg_color=BG, width=LIST_WIDTH, scrollbar_button_color=BORDER)
        self.listf.pack(side="left", fill="y", padx=(0, 12))
        self.detail = ctk.CTkScrollableFrame(body, fg_color=BG, scrollbar_button_color=BORDER)
        self.detail.pack(side="left", fill="both", expand=True)
        if self.disks:
            self.render()

    def relabel(self):
        self.build()
        self.status.configure(text=t("dh_loading") if self.loading else " ")

    def render(self):
        for w in self.listf.winfo_children():
            w.destroy()
        for d in self.disks:
            self.disk_item(d)
        self.render_detail()

    def disk_item(self, d):
        res = self.results[d["number"]]
        color = LEVEL[res["level"]]
        sel = d["number"] == self.selected
        item = ctk.CTkFrame(self.listf, fg_color=CARD_HOVER if sel else CARD, corner_radius=10, border_width=1,
                            border_color=ui.ACCENT if sel else BORDER)
        item.pack(fill="x", pady=(0, 8))
        stripe = ctk.CTkFrame(item, fg_color=color, width=5, height=10, corner_radius=3)
        stripe.pack(side="left", fill="y", padx=(8, 0), pady=10)
        box = ctk.CTkFrame(item, fg_color="transparent")
        box.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        ctk.CTkLabel(box, text=d["name"] or "Disk %d" % d["number"], font=("Segoe UI Semibold", 13), text_color=TEXT,
                     anchor="w", wraplength=LIST_WIDTH - 60, justify="left").pack(fill="x")
        bits = ["Disk %d" % d["number"], human_size(d["size"]), d.get("bus") or ""]
        if d.get("system"):
            bits.append(t("dh_system"))
        ctk.CTkLabel(box, text=" · ".join(b for b in bits if b), font=("Segoe UI", 11), text_color=MUTED,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(box, text=t("dh_level_" + res["level"]), font=("Segoe UI Semibold", 12), text_color=color,
                     anchor="w").pack(fill="x", pady=(2, 0))

        def pick(e, n=d["number"]):
            self.selected = n
            self.render()
        for w in (item, stripe, box) + tuple(box.winfo_children()):
            w.bind("<Button-1>", pick)

    def render_detail(self):
        for w in self.detail.winfo_children():
            w.destroy()
        d = next((x for x in self.disks if x["number"] == self.selected), None)
        if d is None:
            return
        res = self.results[d["number"]]
        self.verdict_card(d, res)
        self.tiles(res["figures"], res)
        self.info_card(d)
        self.smart_card(d)

    def verdict_card(self, d, res):
        color = LEVEL[res["level"]]
        c = ui.card(self.detail)
        c.pack(fill="x", pady=(0, 10))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkFrame(row, fg_color=color, width=8, height=56, corner_radius=4).pack(side="left", fill="y", padx=(0, 14))
        txt = ctk.CTkFrame(row, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(txt, text=t("dh_level_" + res["level"]), font=("Segoe UI Semibold", 24), text_color=color,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(txt, text=t("dh_lead_" + res["level"]), font=("Segoe UI", 12), text_color=TEXT,
                     anchor="w").pack(fill="x")
        if res["level"] in ("bad", "warning"):
            ui.button(row, t("dh_recover"), self.open_recovery, 210, primary=True).pack(side="right", anchor="n")
        box = ctk.CTkFrame(c, fg_color="transparent")
        box.pack(fill="x", padx=18, pady=(6, 14))
        for level, key, args in res["reasons"]:
            line = ctk.CTkFrame(box, fg_color="transparent")
            line.pack(fill="x", pady=2)
            ctk.CTkLabel(line, text="●", font=("Segoe UI", 12), text_color=LEVEL.get(level, MUTED), width=18).pack(
                side="left", anchor="n")
            ctk.CTkLabel(line, text=t("dh_r_" + key, **({**args, "state": state_text(args["state"])} if "state" in args else args)), font=("Segoe UI", 12), text_color=TEXT, anchor="w",
                         justify="left", wraplength=640).pack(side="left", fill="x", expand=True)

    def tiles(self, f, res):
        c = ctk.CTkFrame(self.detail, fg_color="transparent")
        c.pack(fill="x", pady=(0, 10))
        temp = f["temperature"]
        items = [
            ("dh_t_temp", None if temp is None else "%d °C" % temp, self.reason_color(res, ("too_hot", "hot"))),
            ("dh_t_hours", hours_text(f["hours"]), None),
            ("dh_t_wear", None if f["wear"] is None else t("dh_pct", n=f["wear"]), self.reason_color(res, ("worn", "wearing"))),
            ("dh_t_realloc", None if f["reallocated"] is None else count(f["reallocated"]),
             self.reason_color(res, ("reallocated",))),
            ("dh_t_pending", None if f["pending"] is None else count(f["pending"]), self.reason_color(res, ("pending",))),
            ("dh_t_errors", None if f["read_errors"] is None and f["write_errors"] is None else
             count((f["read_errors"] or 0) + (f["write_errors"] or 0)), self.reason_color(res, ("io_errors",))),
            ("dh_t_cycles", None if f["power_cycles"] is None else count(f["power_cycles"]), None),
        ]
        cols = 4
        for i, (key, value, color) in enumerate(items):
            tile = ui.card(c)
            tile.grid(row=i // cols, column=i % cols, sticky="nsew", padx=(0, 8), pady=(0, 8))
            ctk.CTkLabel(tile, text=t(key), font=("Segoe UI", 11), text_color=MUTED, anchor="w").pack(
                fill="x", padx=14, pady=(10, 0))
            ctk.CTkLabel(tile, text=value if value is not None else t("dh_unknown"),
                         font=("Segoe UI Semibold", 17 if value is not None else 12),
                         text_color=color or (TEXT if value is not None else MUTED), anchor="w").pack(
                fill="x", padx=14, pady=(0, 10))
        for i in range(cols):
            c.grid_columnconfigure(i, weight=1, uniform="tile")

    @staticmethod
    def reason_color(res, keys):
        levels = [lv for lv, key, _ in res["reasons"] if key in keys]
        return LEVEL[max(levels, key=verdict.ORDER.get)] if levels else None

    def info_card(self, d):
        c = ui.card(self.detail, t("dh_info"))
        c.pack(fill="x", pady=(0, 10))
        rows = [("dh_model", d.get("name")), ("dh_serial", d.get("serial")), ("dh_bus", d.get("bus")),
                ("dh_media", media_text(d)), ("dh_capacity", human_size(d["size"]) if d.get("size") else ""),
                ("dh_firmware", d.get("firmware")), ("dh_status", " · ".join(state_text(x) for x in (d.get("health"), d.get("status")) if x))]
        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(fill="x", padx=18, pady=(0, 12))
        for i, (key, value) in enumerate(r for r in rows if r[1]):
            ctk.CTkLabel(grid, text=t(key), font=("Segoe UI", 12), text_color=MUTED, anchor="w").grid(
                row=i, column=0, sticky="w", padx=(0, 24), pady=1)
            ctk.CTkLabel(grid, text=value, font=("Segoe UI Semibold", 12), text_color=TEXT, anchor="w").grid(
                row=i, column=1, sticky="w", pady=1)

    def smart_card(self, d):
        c = ui.card(self.detail, t("dh_smart"))
        c.pack(fill="x", pady=(0, 10))
        attrs = d.get("smart") or []
        if not attrs:
            ctk.CTkLabel(c, text=t("dh_smart_none"), font=("Segoe UI", 12), text_color=MUTED, anchor="w",
                         justify="left", wraplength=700).pack(fill="x", padx=18, pady=(0, 14))
            return
        holder = ctk.CTkFrame(c, fg_color=CARD)
        holder.pack(fill="x", padx=16, pady=(0, 14))
        cols = ("id", "name", "value", "worst", "thr", "raw")
        tree = ttk.Treeview(holder, columns=cols, show="headings", style="Health.Treeview", height=len(attrs),
                            selectmode="none")
        for col, width, stretch in (("id", 50, 0), ("name", 260, 1), ("value", 70, 0), ("worst", 70, 0),
                                    ("thr", 70, 0), ("raw", 120, 0)):
            tree.heading(col, text=t("dh_col_" + col), anchor="w")
            tree.column(col, width=width, stretch=bool(stretch), anchor="w")
        tree.tag_configure("bad", foreground=ui.BAD)
        tree.tag_configure("warning", foreground=ui.WARN)
        for a in attrs:
            state = verdict.attr_state(a)
            tree.insert("", "end", values=(a["id"], a["name"], a["current"], a["worst"],
                                           a["threshold"] if a.get("threshold") is not None else "–", count(a["raw"])),
                        tags=(state,) if state else ())
        tree.pack(fill="x")
        tree.bind("<MouseWheel>", lambda e: self.detail._parent_canvas.yview_scroll(-int(e.delta / 120), "units"))

    def open_recovery(self):
        shell = self.winfo_toplevel()
        if hasattr(shell, "open_tool_id"):
            shell.open_tool_id("disk.recovery")
            view = getattr(shell, "views", {}).get("disk.recovery")
            if view is not None and self.selected is not None:
                view.select_disk(self.selected)
