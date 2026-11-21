"""File Recovery tool of Benchwise (customtkinter).

``RecoveryView`` is a frame that the Benchwise window shows when the File Recovery card is
opened; it no longer owns the window.  The work goes in two steps.  A scan lists everything that can be recovered and writes nothing;
the result is shown as a folder tree with tick boxes.  The user then recovers what is ticked,
as often as needed: what has been recovered gets a green check mark, the rest stays grey and
can be fetched later, into another folder or after making room.  A panel on the right shows
live figures while the program is working, and the work can be paused at any time.
"""

from __future__ import annotations

import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import APP_NAME, __version__, disks, i18n, icons, session, troubleshoot
from .catalog import Catalog
from .engine import RESERVE, Options, RecoveryError, format_duration, interrupted_scan, recover_session, scan_source
from .i18n import t
from .model import Cancelled, Control, filetime_to_text, human_size

BG, CARD, BORDER = "#0f1420", "#182033", "#263149"
TEXT, MUTED, ACCENT, ACCENT_HOVER = "#e8ecf4", "#8b96ad", "#2f7cf6", "#2467d3"
GOOD, WARN, BAD = "#3ecf8e", "#f5b84b", "#f26d6d"
LEVEL_COLOR = {"ok": GOOD, "info": ACCENT, "warning": WARN, "error": BAD}
PANEL_WIDTH = 330
ROW_LIMIT = 3000            # rows shown per folder; the rest is reached with the search box
BUSY = ("scan", "recover", "load")
LOG_FRAME = 24              # customtkinter units the log box adds around its text area (corners, border)


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", name)


def part_name(p):
    """Short human name of a partition: "E: Backup" or "Partition 3"."""
    if p.get("letter"):
        return ("%s: %s" % (p["letter"], p.get("label") or "")).strip()
    return p.get("label") or t("partition_n", n=p["number"])


def count(n):
    return "{:,}".format(n).replace(",", " ")


class RecoveryView(ctk.CTkFrame):
    """The File Recovery tool.  Lives inside the Benchwise window, which it never closes itself
    except through ``on_close`` (asked by the window when the user closes it)."""

    def __init__(self, master):
        super().__init__(master, fg_color=BG)
        self.events = queue.Queue()
        self.control = Control()
        self.worker = None
        self.disks = []
        self.image_path = None
        self.summary = None
        self.closing = False
        self.asked_locks = set()
        self.rows = {}                  # disk tree item id -> description of what it stands for
        self.wanted = None              # disk row to select once the disk list is in (asked by another tool)
        self.ts_window = None
        self.scans_window = None
        self.mode = "select"            # select | scan | results | recover | load
        self.session = None             # the saved scan on screen
        self.catalog = None
        self.rrows = {}                 # result tree item id -> catalogue Entry
        self.searching = False
        self.search_job = None
        self.panel_shown = False
        self.panel_wanted = True        # the user's choice; the panel opens by itself when work starts
        self.grown = 0                  # pixels the window was widened for the panel
        self.rate = (0.0, 0)            # (time, bytes) of the previous progress sample
        self.speed = 0.0
        self.t_start = None             # start of the running job
        self.first = None               # (idle-corrected time, bytes) of the first progress sample of a phase
        self.last_progress = (0, 0)
        self.samples = deque(maxlen=120)
        self.unit = "bytes"             # what the progress counts: "bytes", or "records" while rebuilding folders
        self.stage = None               # sub-step of the current phase; a new one restarts the speed figures
        self.recent = deque(maxlen=7)
        self.dest = tk.StringVar()
        self.find = tk.StringVar()
        self.opt_lock = tk.BooleanVar(value=True)
        self.opt_deleted = tk.BooleanVar(value=True)
        self.opt_live = tk.BooleanVar(value=False)
        self.opt_twin = tk.BooleanVar(value=True)
        self.opt_image = tk.BooleanVar(value=False)
        self.dest.trace_add("write", lambda *a: (self.update_space(), self.update_selection()))
        self.find.trace_add("write", lambda *a: self.schedule_search())
        self.style_tree()
        scale = self.winfo_fpixels("1i") / 96.0
        self.icons = {k: tk.PhotoImage(master=self, data=v) for k, v in icons.build(scale).items()}
        self.build()
        self.after(80, self.poll)
        self.after(500, self.tick)
        self.after(200, self.startup_checks)
        self.selftest = os.environ.get("RECOVERYTOOL_SELFTEST")  # "image|destination[|keep]": used by the UI test
        if self.selftest:
            self.after(2500, self.run_selftest)
        self.uitest = os.environ.get("RECOVERYTOOL_UITEST")      # "select=<row id>[;troubleshoot]": UI test

    def run_selftest(self):
        image, dest = self.selftest.split("|")[:2]
        self.image_path = image
        self.fill_tree()
        self.tree.selection_set("image")
        self.dest.set(dest)
        self.start_scan()

    # -- construction ---------------------------------------------------------------------------
    def style_tree(self):
        s = ttk.Style(self)
        s.theme_use("default")
        s.configure("Disk.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=28,
                    borderwidth=0, font=("Segoe UI", 10))
        s.configure("Disk.Treeview.Heading", background=BORDER, foreground=MUTED, relief="flat",
                    font=("Segoe UI", 9, "bold"), padding=(8, 6))
        s.map("Disk.Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
        s.map("Disk.Treeview.Heading", background=[("active", BORDER)])
        s.layout("Disk.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.configure("Files.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=28,
                    borderwidth=0, font=("Segoe UI", 10))
        s.configure("Files.Treeview.Heading", background=BORDER, foreground=MUTED, relief="flat",
                    font=("Segoe UI", 9, "bold"), padding=(8, 6))
        s.map("Files.Treeview", background=[("selected", "#22304d")], foreground=[("selected", "#ffffff")])
        s.map("Files.Treeview.Heading", background=[("active", BORDER)])
        s.layout("Files.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    def card(self, parent, title):
        frame = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        ctk.CTkLabel(frame, text=title, font=("Segoe UI Semibold", 14), text_color=TEXT, anchor="w").pack(
            fill="x", padx=18, pady=(12, 6))
        return frame

    def small_button(self, parent, text, command, width=100):
        return ctk.CTkButton(parent, text=text, width=width, height=28, fg_color=BORDER, hover_color="#33405c",
                             text_color=TEXT, command=command)

    def plain_button(self, parent, text, command, width=110):
        return ctk.CTkButton(parent, text=text, height=42, width=width, fg_color=CARD, hover_color=BORDER,
                             border_width=1, border_color=BORDER, text_color=TEXT, command=command)

    def build(self):
        for w in self.winfo_children():
            w.destroy()
        self.ts_window = self.scans_window = None
        self.panel_shown = False
        outer = ctk.CTkFrame(self, fg_color=BG)
        outer.pack(fill="both", expand=True)
        self.side = ctk.CTkFrame(outer, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER,
                                 width=PANEL_WIDTH)
        self.side.pack_propagate(False)
        root = self.rootf = ctk.CTkFrame(outer, fg_color=BG)
        root.pack(side="left", fill="both", expand=True, padx=22, pady=(16, 18))
        self.build_panel()

        head = ctk.CTkFrame(root, fg_color=BG)
        head.pack(fill="x")
        ctk.CTkLabel(head, text=t("tool_recovery"), font=("Segoe UI Semibold", 22), text_color=TEXT).pack(side="left")
        top = dict(height=28, fg_color=CARD, hover_color=BORDER, border_width=1, border_color=BORDER, text_color=TEXT)
        self.panel_btn = ctk.CTkButton(head, text=t("panel_show"), width=120, command=self.toggle_panel, **top)
        self.panel_btn.pack(side="right")
        self.scans_btn = ctk.CTkButton(head, text=t("scans"), width=130, command=self.open_scans, **top)
        self.scans_btn.pack(side="right", padx=(0, 8))
        ctk.CTkLabel(root, text=t("subtitle"), font=("Segoe UI", 12), text_color=MUTED, anchor="w").pack(fill="x", pady=(0, 10))

        # page 1: what to scan ----------------------------------------------------------------
        page = self.page_select = ctk.CTkFrame(root, fg_color=BG)
        c1 = self.c1 = self.card(page, t("step1"))
        c1.pack(fill="both", expand=True)
        bar = ctk.CTkFrame(c1, fg_color=CARD)
        bar.place(relx=1.0, x=-14, y=9, anchor="ne")
        self.refresh_btn = self.small_button(bar, t("refresh"), self.load_disks, 86)
        self.refresh_btn.pack(side="right")
        self.image_btn = self.small_button(bar, t("open_image"), self.pick_image, 130)
        self.image_btn.pack(side="right", padx=(0, 8))
        self.ts_btn = self.small_button(bar, t("troubleshoot"), self.open_troubleshooter, 120)
        self.ts_btn.pack(side="right", padx=(0, 8))
        holder = ctk.CTkFrame(c1, fg_color=CARD)
        holder.pack(fill="both", expand=True, padx=16, pady=(2, 12))
        cols = ("label", "type", "size", "fs", "state")
        self.tree = ttk.Treeview(holder, columns=cols, show="tree headings", height=7, style="Disk.Treeview",
                                 selectmode="browse")
        self.tree.heading("#0", text=t("col_item"), anchor="w")
        self.tree.column("#0", width=190, stretch=False, anchor="w")
        for col, width, stretch in (("label", 250, 0), ("type", 96, 0), ("size", 90, 0), ("fs", 96, 0), ("state", 240, 1)):
            self.tree.heading(col, text=t("col_" + col), anchor="w")
            self.tree.column(col, width=width, stretch=bool(stretch), anchor="w")
        scroll = ctk.CTkScrollbar(holder, command=self.tree.yview, fg_color=CARD, button_color=BORDER,
                                  button_hover_color="#33405c", width=12)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("muted", foreground=MUTED)
        self.tree.tag_configure("warn", foreground=WARN)
        self.tree.tag_configure("bad", foreground=BAD)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.on_select())
        self.tree.bind("<Button-3>", self.on_right_click)

        c2 = self.c2 = self.card(page, t("step2"))
        c2.pack(side="bottom", fill="x", pady=(10, 0))    # before the disk list gets its share
        self.space_label = ctk.CTkLabel(c2, text=" ", font=("Segoe UI", 11), text_color=MUTED, anchor="e")
        self.space_label.place(relx=1.0, x=-18, y=12, anchor="ne")
        row = ctk.CTkFrame(c2, fg_color=CARD)
        row.pack(fill="x", padx=16, pady=(0, 8))
        self.dest_entry = ctk.CTkEntry(row, textvariable=self.dest, height=34, fg_color=BG, border_color=BORDER,
                                       text_color=TEXT, placeholder_text=t("dest_placeholder"))
        self.dest_entry.pack(side="left", fill="x", expand=True)
        self.browse_btn = ctk.CTkButton(row, text=t("browse"), width=100, height=34, fg_color=BORDER, hover_color="#33405c",
                                        text_color=TEXT, command=self.pick_dest)
        self.browse_btn.pack(side="left", padx=(8, 0))
        grid = ctk.CTkFrame(c2, fg_color=CARD)      # options, in the same card to keep the window short
        grid.pack(fill="x", padx=16, pady=(0, 10))
        self.checks = []
        for i, (var, key) in enumerate(((self.opt_lock, "opt_lock"), (self.opt_deleted, "opt_deleted"),
                                        (self.opt_twin, "opt_twin"), (self.opt_live, "opt_live"),
                                        (self.opt_image, "opt_image"))):
            cb = ctk.CTkCheckBox(grid, text=t(key), variable=var, font=("Segoe UI", 12), text_color=TEXT,
                                 checkbox_width=18, checkbox_height=18, border_width=2, fg_color=ACCENT,
                                 hover_color=ACCENT_HOVER, border_color=MUTED)
            cb.grid(row=i % 3, column=i // 3, sticky="w", pady=3, padx=(0, 28))
            self.checks.append(cb)

        # page 2: what was found, and what to recover -----------------------------------------
        page = self.page_results = ctk.CTkFrame(root, fg_color=BG)
        c3 = self.card(page, t("found_title"))
        c3.pack(fill="both", expand=True)
        self.source_label = ctk.CTkLabel(c3, text=" ", font=("Segoe UI", 11), text_color=MUTED, anchor="e")
        self.source_label.place(relx=1.0, x=-18, y=12, anchor="ne")
        tools = ctk.CTkFrame(c3, fg_color=CARD)
        tools.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(tools, text=t("find_label"), font=("Segoe UI", 12), text_color=TEXT).pack(side="left", padx=(0, 8))
        self.find_entry = ctk.CTkEntry(tools, textvariable=self.find, width=220, height=30, fg_color=BG,
                                       border_color=BORDER, text_color=TEXT)
        self.find_entry.pack(side="left")
        self.all_btn = self.small_button(tools, t("select_all"), lambda: self.select_all(True), 150)
        self.all_btn.pack(side="left", padx=(8, 0))
        self.none_btn = self.small_button(tools, t("select_none"), lambda: self.select_all(False), 120)
        self.none_btn.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(tools, text=t("legend"), font=("Segoe UI", 11), text_color=MUTED, anchor="e").pack(side="right")
        holder = ctk.CTkFrame(c3, fg_color=CARD)
        self.rtree = ttk.Treeview(holder, columns=("size", "modified", "state"), show="tree headings", height=8,
                                  style="Files.Treeview", selectmode="browse")
        self.rtree.heading("#0", text=t("col_file"), anchor="w")
        self.rtree.column("#0", width=420, stretch=True, anchor="w")
        for col, width in (("size", 90), ("modified", 140), ("state", 190)):
            self.rtree.heading(col, text=t("col_" + col), anchor="w")
            self.rtree.column(col, width=width, stretch=False, anchor="w")
        scroll = ctk.CTkScrollbar(holder, command=self.rtree.yview, fg_color=CARD, button_color=BORDER,
                                  button_hover_color="#33405c", width=12)
        self.rtree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.rtree.pack(side="left", fill="both", expand=True)
        self.rtree.tag_configure("muted", foreground=MUTED)
        self.rtree.bind("<Button-1>", self.on_file_click)
        self.rtree.bind("<space>", self.on_file_space)
        self.rtree.bind("<<TreeviewOpen>>", lambda e: self.expand_row(self.rtree.focus()))
        self.rtree.bind("<Button-3>", self.on_file_menu)
        self.rtree.bind("<Double-1>", self.on_file_double)
        row = ctk.CTkFrame(c3, fg_color=CARD)
        ctk.CTkLabel(row, text=t("recover_into"), font=("Segoe UI", 12), text_color=TEXT).pack(side="left", padx=(0, 8))
        self.dest_entry2 = ctk.CTkEntry(row, textvariable=self.dest, height=32, fg_color=BG, border_color=BORDER,
                                        text_color=TEXT, placeholder_text=t("dest_placeholder"))
        self.dest_entry2.pack(side="left", fill="x", expand=True)
        self.browse_btn2 = ctk.CTkButton(row, text=t("browse"), width=100, height=32, fg_color=BORDER,
                                         hover_color="#33405c", text_color=TEXT, command=self.pick_dest)
        self.browse_btn2.pack(side="left", padx=(8, 0))
        self.sel_label = ctk.CTkLabel(c3, text=" ", font=("Segoe UI Semibold", 12), text_color=TEXT, anchor="w")
        self.fit_label = ctk.CTkLabel(c3, text=" ", font=("Segoe UI", 11), text_color=MUTED, anchor="w", justify="left")
        # the rows under the file list are packed first (from the bottom up), so a short window
        # shrinks the list (it scrolls) instead of cutting them off
        self.fit_label.pack(side="bottom", fill="x", padx=18, pady=(0, 10))
        self.sel_label.pack(side="bottom", fill="x", padx=18)
        row.pack(side="bottom", fill="x", padx=16, pady=(0, 6))
        holder.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # run area ----------------------------------------------------------------------------
        # Packed at the bottom before the pages, so it always gets its height: when the window is
        # short, the lists above shrink (they scroll) instead of the log being squeezed.
        bottom = self.bottom = ctk.CTkFrame(root, fg_color=BG)
        bottom.pack(side="bottom", fill="x")
        run = self.run_frame = ctk.CTkFrame(bottom, fg_color=BG)
        run.pack(fill="x", pady=(12, 0))
        self.start_btn = ctk.CTkButton(run, text=t("start_scan"), height=42, width=220, font=("Segoe UI Semibold", 14),
                                       fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.start_scan)
        self.start_btn.pack(side="left")
        self.pause_btn = self.plain_button(run, t("pause"), self.toggle_pause)
        self.pause_btn.pack(side="left", padx=(10, 0))
        self.cancel_btn = self.plain_button(run, t("stop"), self.request_cancel, 100)
        self.cancel_btn.pack(side="left", padx=(10, 0))
        self.back_btn = self.plain_button(run, t("new_scan"), self.back_to_select, 120)
        self.folder_btn = ctk.CTkButton(run, text=t("open_folder"), height=42, width=120, fg_color=GOOD, hover_color="#32b078",
                                        text_color="#06210f", command=lambda: self.open_path(self.summary["dest"]))
        self.report_btn = self.plain_button(run, t("open_report"), lambda: self.open_path(self.summary["report_dir"]), 120)
        self.phase_label = ctk.CTkLabel(run, text=t("ready"), font=("Segoe UI Semibold", 13), text_color=TEXT, anchor="e")
        self.phase_label.pack(side="right")

        self.bar = ctk.CTkProgressBar(bottom, height=10, fg_color=CARD, progress_color=ACCENT, corner_radius=5)
        self.bar.set(0)
        self.bar.pack(fill="x", pady=(10, 2))
        self.detail_label = ctk.CTkLabel(bottom, text=" ", font=("Segoe UI", 11), text_color=MUTED, anchor="w")
        self.detail_label.pack(fill="x")
        self.log = ctk.CTkTextbox(bottom, fg_color=CARD, border_width=1, border_color=BORDER, text_color=TEXT,
                                  font=("Consolas", 11), corner_radius=12, wrap="word")
        self.log.pack(fill="both", expand=False, pady=(8, 0))
        for tag, color in (("good", GOOD), ("warn", WARN), ("bad", BAD), ("head", "#ffffff")):
            self.log.tag_config(tag, foreground=color)
        self.log.configure(state="disabled")
        self.fill_tree()
        self.set_mode(self.mode)
        if self.catalog is not None:
            self.fill_results()

    # -- live panel -----------------------------------------------------------------------------
    def build_panel(self):
        side = self.side
        head = ctk.CTkFrame(side, fg_color=CARD)
        head.pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(head, text=t("panel_title"), font=("Segoe UI Semibold", 15), text_color=TEXT).pack(side="left")
        self.p_state = ctk.CTkLabel(head, text=t("ps_idle"), font=("Segoe UI Semibold", 11), text_color=BG,
                                    fg_color=MUTED, corner_radius=8, width=92, height=22)
        self.p_state.pack(side="right")
        self.p_pct = ctk.CTkLabel(side, text="–", font=("Segoe UI Semibold", 34), text_color=TEXT, anchor="w")
        self.p_pct.pack(fill="x", padx=16, pady=(6, 0))
        self.p_phase = ctk.CTkLabel(side, text=t("ready"), font=("Segoe UI", 12), text_color=MUTED, anchor="w")
        self.p_phase.pack(fill="x", padx=16)
        self.graph = tk.Canvas(side, height=54, bg=BG, highlightthickness=0, bd=0)
        self.graph.pack(fill="x", padx=16, pady=(8, 4))
        body = ctk.CTkScrollableFrame(side, fg_color=CARD, scrollbar_button_color=BORDER,
                                      scrollbar_button_hover_color="#33405c")
        body.pack(fill="both", expand=True, padx=(6, 2), pady=(0, 10))
        self.pv = {}

        def section(title):
            ctk.CTkLabel(body, text=title.upper(), font=("Segoe UI Semibold", 10), text_color=MUTED, anchor="w").pack(
                fill="x", padx=8, pady=(10, 2))

        def line(key, color=TEXT):
            row = ctk.CTkFrame(body, fg_color=CARD, height=22)
            row.pack(fill="x", padx=8)
            ctk.CTkLabel(row, text=t("pl_" + key), font=("Segoe UI", 11), text_color=MUTED, anchor="w", height=20).pack(side="left")
            self.pv[key] = ctk.CTkLabel(row, text="–", font=("Segoe UI Semibold", 11), text_color=color, anchor="e", height=20)
            self.pv[key].pack(side="right")

        def block(key):
            self.pv[key] = ctk.CTkLabel(body, text="–", font=("Segoe UI", 11), text_color=TEXT, anchor="w",
                                        justify="left", wraplength=PANEL_WIDTH - 60)
            self.pv[key].pack(fill="x", padx=8)

        section(t("pg_progress"))
        block("step")
        for key in ("elapsed", "eta", "speed", "avg", "data"):
            line(key)
        section(t("pg_source"))
        block("source")
        line("bad", WARN)
        section(t("pg_scan"))
        for key in ("mft", "fat", "exfat", "boot"):
            line(key)
        block("vols")
        section(t("pg_recover"))
        line("files")
        line("ok", GOOD)
        line("repaired", GOOD)
        line("uncertain", WARN)
        line("damaged", BAD)
        line("failed", BAD)
        line("waiting", WARN)
        line("free")
        block("current")
        section(t("pg_catalog"))
        for key in ("total", "done", "left"):
            line(key)
        section(t("pg_recent"))
        block("recent")

    def toggle_panel(self):
        self.panel_wanted = not self.panel_shown
        self.show_panel(self.panel_wanted)

    def show_panel(self, show, resize=True):
        if show == self.panel_shown:
            return
        self.panel_shown = show
        self.panel_btn.configure(text=t("panel_hide" if show else "panel_show"))
        win = self.winfo_toplevel()
        zoomed = win.state() == "zoomed"
        if show:
            self.side.pack(side="right", fill="y", padx=(0, 16), pady=(16, 18), before=self.rootf)
            if resize and not zoomed and win.winfo_width() + PANEL_WIDTH <= win.winfo_screenwidth() - 40:
                self.grown = PANEL_WIDTH + 16           # widen the window instead of squeezing the lists
                win.geometry("%dx%d" % (win.winfo_width() + self.grown, win.winfo_height()))
        else:
            self.side.pack_forget()
            if self.grown and not zoomed:
                win.geometry("%dx%d" % (max(win.winfo_width() - self.grown, 1000), win.winfo_height()))
            self.grown = 0

    def panel(self, **values):
        for key, value in values.items():
            self.pv[key].configure(text=value)

    def panel_state(self, key):
        color = {"ps_running": GOOD, "ps_paused": WARN, "ps_done": ACCENT, "ps_stopped": BAD}.get(key, MUTED)
        self.p_state.configure(text=t(key), fg_color=color)

    def panel_reset(self, what):
        """Blank the figures of a job that is about to start ("scan" or "recover")."""
        keys = ("step", "elapsed", "eta", "speed", "avg", "data", "bad")
        keys += ("mft", "fat", "exfat", "boot", "vols") if what == "scan" else ()
        keys += ("files", "ok", "repaired", "uncertain", "damaged", "failed", "waiting", "free", "current", "recent")
        self.panel(**{k: "–" for k in keys})
        if what == "scan":
            self.panel(total="–", done="–", left="–")
        self.p_pct.configure(text="–")
        self.samples.clear()
        self.recent.clear()
        self.draw_graph()

    def panel_catalog(self):
        r = self.catalog.root if self.catalog else None
        if r is None:
            return self.panel(total="–", done="–", left="–")
        self.panel(total="%s · %s" % (count(r.files), human_size(r.size)),
                   done="%s · %s" % (count(r.done), human_size(r.done_size)),
                   left="%s · %s" % (count(r.pend), human_size(r.pend_size)))

    def draw_graph(self):
        g = self.graph
        g.delete("all")
        w, h = max(g.winfo_width(), 50), max(g.winfo_height(), 20)
        data = list(self.samples)
        if len(data) < 2:
            g.create_text(w // 2, h // 2, text=t("graph_empty"), fill="#5b657a", font=("Segoe UI", 9))
            return
        top = max(data) or 1.0
        step = (w - 4) / float(self.samples.maxlen - 1)
        x0 = w - 2 - step * (len(data) - 1)
        pts = []
        for i, v in enumerate(data):
            pts += [x0 + i * step, h - 3 - (h - 16) * v / top]
        g.create_polygon([pts[0], h] + pts + [pts[-2], h], fill="#1b3358", outline="")
        g.create_line(pts, fill=ACCENT, width=2)
        g.create_text(4, 2, anchor="nw", text=t("graph_peak", speed=self.amount(top)), fill=MUTED, font=("Segoe UI", 8))

    # -- disk list ------------------------------------------------------------------------------
    def startup_checks(self):
        if disks.fake_mode():
            self.write(t("err_demo"), "warn")
        elif not disks.is_admin():
            self.write(t("admin_needed"), "warn")
        self.load_disks()

    def check_pending_locks(self):
        """Offer to release disks that an interrupted run (crash, power loss) left write-protected."""
        changed = False
        for d in disks.resolve_pending(self.disks):
            key = d.get("serial") or d["number"]
            if key in self.asked_locks:
                continue
            self.asked_locks.add(key)
            if messagebox.askyesno(APP_NAME, t("pending_lock", n=d["number"], name=d.get("name", ""))):
                ok, err = disks.unlock_disk(d["number"], d.get("serial"))
                self.write(t("log_unlocked", n=d["number"]) if ok else t("log_unlock_failed", n=d["number"], err=err),
                           "good" if ok else "bad")
                changed = changed or ok
        if changed:
            self.load_disks()

    def load_disks(self):
        self.refresh_btn.configure(state="disabled")
        self.detail_label.configure(text=t("loading_disks"))

        def work():
            try:
                self.events.put(("disks", disks.list_disks()))
            except Exception as ex:
                self.events.put(("disks_error", str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def fill_tree(self):
        selected = self.tree.selection()
        closed = {i for i in self.tree.get_children() if not self.tree.item(i, "open")}
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for d in self.disks:
            no_media = d["size"] == 0 or "No Media" in (d.get("status") or "")
            state = [t("st_no_media") if no_media else t("state_offline") if d["offline"] else t("state_online")]
            if d["system"]:
                state.append(t("state_system"))
            if d["readonly"]:
                state.append(t("state_readonly"))
            did = "disk%d" % d["number"]
            self.tree.insert("", "end", iid=did, text=" Disk %d" % d["number"], open=did not in closed,
                             values=(d["name"], d["bus"], human_size(d["size"]), d["style"], ", ".join(state)),
                             tags=("bad",) if no_media else ())
            self.rows[did] = {"kind": "disk", "disk": d}
            for i, row in enumerate(disks.layout(d)):
                if row["kind"] == "gap":
                    iid = "gap%d:%d" % (d["number"], i)
                    self.tree.insert(did, "end", iid=iid, text="   " + t("unallocated"), tags=("muted",),
                                     values=("", "", human_size(row["size"]), "", t("gap_hint")))
                    self.rows[iid] = {"kind": "gap", "disk": d, "offset": row["offset"], "size": row["size"]}
                    continue
                p = row["part"]
                data = troubleshoot.is_data_partition(p)
                fs = p.get("filesystem") or ("RAW" if data else "")
                if not p.get("filesystem") and data:
                    status, tags = t("raw_hint"), ("warn",)
                elif p.get("filesystem"):
                    status = t("st_healthy") if (p.get("health") or "Healthy") == "Healthy" else p.get("health")
                    if p.get("free"):
                        status += ", " + t("st_free", free=human_size(p["free"]))
                    tags = () if data else ("muted",)
                else:
                    status, tags = "", ("muted",)
                label = ("%s:  %s" % (p["letter"], p.get("label") or "")).strip() if p.get("letter") else (
                    p.get("label") or ("(%s)" % t("no_letter") if data else ""))
                iid = "part%d:%d" % (d["number"], p["number"])
                self.tree.insert(did, "end", iid=iid, text="   " + t("partition_n", n=p["number"]), tags=tags,
                                 values=(label, p.get("type") or "", human_size(p["size"]), fs, status))
                self.rows[iid] = {"kind": "part", "disk": d, "part": p}
        if self.image_path:
            self.tree.insert("", "end", iid="image", text=" IMG", values=(
                os.path.basename(self.image_path), t("image_file"), human_size(os.path.getsize(self.image_path)),
                "", self.image_path))
            self.rows["image"] = {"kind": "image"}
        for iid in ([self.wanted] if self.wanted else []) + list(selected):
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)
                if iid == self.wanted:
                    self.wanted = None
                break

    def select_disk(self, number):
        """Select a disk in the list (now, or as soon as the list has been read)."""
        if self.busy():
            return
        self.wanted = "disk%d" % number
        if self.tree.exists(self.wanted):
            self.fill_tree()
            self.on_select()

    def selected_row(self):
        sel = self.tree.selection()
        return self.rows.get(sel[0]) if sel else None

    def selected_source(self):
        """What a recovery would read: a disk (optionally narrowed to a region) or an image."""
        row = self.selected_row()
        if not row:
            return None
        if row["kind"] == "image":
            return {"image": self.image_path}
        src = dict(row["disk"])
        if row["kind"] == "part":
            p = row["part"]
            src["region"] = {"offset": p["offset"], "size": p["size"], "filesystem": p.get("filesystem") or "",
                             "label": part_name(p)}
        elif row["kind"] == "gap":
            src["region"] = {"offset": row["offset"], "size": row["size"], "filesystem": "", "label": t("unallocated")}
        return src

    def on_select(self):
        src = self.selected_source()
        system = bool(src and src.get("system"))
        is_image = bool(src and "image" in src)
        busy = self.worker is not None and self.worker.is_alive()
        if not busy:
            self.checks[0].configure(state="disabled" if (system or is_image) else "normal")
            self.checks[4].configure(state="disabled" if is_image else "normal")
        self.update_space()

    def pick_image(self):
        path = filedialog.askopenfilename(title=t("choose_image"), filetypes=[
            ("Disk images", "*.img *.dd *.raw *.bin *.vhd *.iso"), ("All files", "*.*")])
        if path:
            self.image_path = os.path.normpath(path)
            self.fill_tree()
            self.tree.selection_set("image")

    def pick_dest(self):
        path = filedialog.askdirectory(title=t("choose_dest"), mustexist=False)
        if path:
            self.dest.set(os.path.normpath(path))

    def source_size(self, src):
        if not src:
            return 0
        if "image" in src:
            return os.path.getsize(src["image"])
        return src["region"]["size"] if src.get("region") else src["size"]

    def update_space(self):
        text, src = " ", self.selected_source()
        probe = self.dest.get().strip()
        while probe and not os.path.isdir(probe):
            parent = os.path.dirname(probe)
            probe = "" if parent == probe else parent
        if probe:
            try:
                size = self.source_size(src)
                text = t("free_space", free=human_size(shutil.disk_usage(probe).free), size=human_size(size) if size else "-")
            except OSError:
                pass
        self.space_label.configure(text=text)

    # -- context menu and disk operations -------------------------------------------------------
    def on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        row = self.rows.get(iid)
        if not row:
            return
        m = tk.Menu(self, tearoff=0, bg=CARD, fg=TEXT, activebackground=ACCENT, activeforeground="#ffffff",
                    disabledforeground="#5b657a", bd=0, relief="flat", font=("Segoe UI", 10))
        busy = self.worker is not None and self.worker.is_alive()
        lock = "disabled" if busy else "normal"
        if row["kind"] == "image":
            m.add_command(label=t("m_remove_image"), state=lock, command=self.remove_image)
        elif row["kind"] == "gap":
            m.add_command(label=t("m_recover_gap"), state=lock, command=lambda: self.tree.selection_set(iid))
        elif row["kind"] == "disk":
            d = row["disk"]
            sys_state = "disabled" if (busy or d["system"]) else "normal"
            m.add_command(label=t("m_recover_disk"), state=lock, command=lambda: self.tree.selection_set(iid))
            m.add_command(label=t("troubleshoot") + "…", command=self.open_troubleshooter)
            m.add_separator()
            if d["offline"]:
                m.add_command(label=t("m_online"), state=sys_state, command=lambda: self.do_online(d, True))
            else:
                m.add_command(label=t("m_offline"), state=sys_state, command=lambda: self.do_online(d, False))
            if d["readonly"]:
                m.add_command(label=t("m_readonly_off"), state=sys_state, command=lambda: self.do_readonly(d, False))
            else:
                m.add_command(label=t("m_readonly_on"), state=sys_state, command=lambda: self.do_readonly(d, True))
            m.add_separator()
            m.add_command(label=t("m_props"), command=lambda: self.show_properties(row))
        else:
            d, p = row["disk"], row["part"]
            data = troubleshoot.is_data_partition(p)
            has_fs = bool(p.get("filesystem"))
            windows_drive = (p.get("letter") or "").upper() == os.environ.get("SystemDrive", "C:")[:1].upper()
            letters = "disabled" if (busy or not data or not has_fs or windows_drive) else "normal"
            m.add_command(label=t("m_recover_part"), state=lock, command=lambda: self.tree.selection_set(iid))
            m.add_separator()
            m.add_command(label=t("m_letter"), state=letters, command=lambda: self.do_letter(d, p))
            m.add_command(label=t("m_letter_remove"), state=letters if p.get("letter") else "disabled",
                          command=lambda: self.do_remove_letter(d, p))
            m.add_command(label=t("m_explore"), state="normal" if p.get("letter") else "disabled",
                          command=lambda: self.open_path(p["letter"] + ":\\"))
            m.add_separator()
            m.add_command(label=t("m_check"), state="normal" if (has_fs and not busy) else "disabled",
                          command=lambda: self.do_check(d, p))
            m.add_command(label=t("m_repair"), state="normal" if (has_fs and not busy and not windows_drive) else "disabled",
                          command=lambda: self.do_repair(d, p))
            m.add_separator()
            m.add_command(label=t("m_props"), command=lambda: self.show_properties(row))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def remove_image(self):
        self.image_path = None
        self.fill_tree()

    def run_action(self, what, func, *args):
        """Run one disk operation in the background, report it in the log and refresh the list."""
        if self.worker is not None and self.worker.is_alive():
            return messagebox.showinfo(APP_NAME, t("busy_no_action"))
        if disks.fake_mode():
            return messagebox.showinfo(APP_NAME, t("err_demo"))
        self.write(t("act_working", what=what))

        def work():
            try:
                result = func(*args)
            except Exception as ex:
                result = (False, str(ex))
            self.events.put(("action", (what, result)))
        threading.Thread(target=work, daemon=True).start()

    def do_online(self, d, online):
        if not online and not messagebox.askyesno(APP_NAME, t("c_offline", n=d["number"]), icon="warning"):
            return
        self.run_action("Disk %d: %s" % (d["number"], t("m_online" if online else "m_offline")),
                        disks.set_offline, d["number"], not online)

    def do_readonly(self, d, readonly):
        if readonly and not messagebox.askyesno(APP_NAME, t("c_readonly_on", n=d["number"]), icon="warning"):
            return
        func = disks.set_readonly if readonly else (lambda n, _: disks.unlock_disk(n, d.get("serial")))
        self.run_action("Disk %d: %s" % (d["number"], t("m_readonly_on" if readonly else "m_readonly_off")),
                        func, d["number"], readonly)

    def do_letter(self, d, p):
        free = disks.free_letters()
        if not free:
            return messagebox.showinfo(APP_NAME, t("letter_none"))
        win = ctk.CTkToplevel(self, fg_color=BG)
        win.title(t("letter_title"))
        win.geometry("360x170")
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())
        ctk.CTkLabel(win, text=t("letter_prompt", name=part_name(p)), text_color=TEXT, font=("Segoe UI", 13)).pack(pady=(22, 10))
        choice = tk.StringVar(value=free[0])
        ctk.CTkOptionMenu(win, values=free, variable=choice, width=90, fg_color=CARD, button_color=BORDER,
                          button_hover_color="#33405c", text_color=TEXT).pack()

        def apply():
            letter = choice.get()
            win.destroy()
            self.run_action("%s -> %s:" % (part_name(p), letter), disks.assign_letter, d["number"], p, letter)
        ctk.CTkButton(win, text=t("ok"), width=110, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=apply).pack(pady=18)
        win.after(150, win.grab_set)

    def do_remove_letter(self, d, p):
        if messagebox.askyesno(APP_NAME, t("c_letter_remove", letter=p["letter"]), icon="warning"):
            self.run_action("%s: %s" % (part_name(p), t("m_letter_remove")), disks.remove_letter, d["number"], p)

    def do_check(self, d, p):
        name = part_name(p)

        def check():
            ran, text, errors = disks.check_filesystem(d["number"], p)
            if not ran:
                return False, text
            return True, t("check_errors" if errors else "check_clean", name=name)
        self.run_action("%s: %s" % (name, t("m_check")), check)

    def do_repair(self, d, p):
        if messagebox.askyesno(APP_NAME, t("c_repair", name=part_name(p)), icon="warning", default="no"):
            self.run_action("%s: %s" % (part_name(p), t("m_repair").rstrip("…")), disks.repair_filesystem, d["number"], p)

    def show_properties(self, row):
        yn = lambda v: t("yes") if v else t("no")
        d = row["disk"]
        if row["kind"] == "disk":
            text = t("p_disk", n=d["number"], name=d["name"], serial=d.get("serial") or "-", bus=d["bus"],
                     size=human_size(d["size"]), sector=d.get("sector") or "-", style=d["style"],
                     status=d.get("status") or "-", health=d.get("health") or "-", ro=yn(d["readonly"]), off=yn(d["offline"]))
        else:
            p = row["part"]
            text = t("p_part", n=p["number"], d=d["number"], letter=(p["letter"] + ":") if p.get("letter") else "-",
                     label=p.get("label") or "-", fs=p.get("filesystem") or "RAW", type=p.get("type") or "-",
                     size=human_size(p["size"]), free=human_size(p["free"]) if p.get("free") else "-",
                     offset=human_size(p["offset"]), health=p.get("health") or "-")
        messagebox.showinfo(t("m_props"), text)

    # -- troubleshooter -------------------------------------------------------------------------
    def open_troubleshooter(self):
        row = self.selected_row()
        if not row or row["kind"] == "image":
            return messagebox.showinfo(APP_NAME, t("ts_nothing"))
        d = row["disk"]
        if self.ts_window is not None and self.ts_window.winfo_exists():
            self.ts_window.destroy()
        win = self.ts_window = ctk.CTkToplevel(self, fg_color=BG)
        win.title(t("ts_title", n=d["number"], name=d["name"]))
        win.geometry("760x560")
        win.minsize(620, 420)
        win.transient(self.winfo_toplevel())
        win.disk_number = d["number"]
        head = ctk.CTkFrame(win, fg_color=BG)
        head.pack(fill="x", padx=18, pady=(14, 6))
        ctk.CTkLabel(head, text="Disk %d  %s  (%s)" % (d["number"], d["name"], human_size(d["size"])),
                     font=("Segoe UI Semibold", 16), text_color=TEXT).pack(side="left")
        self.small_button(head, t("ts_recheck"), self.load_disks, 120).pack(side="right")
        win.status = ctk.CTkLabel(win, text=t("ts_loading"), font=("Segoe UI", 11), text_color=MUTED, anchor="w")
        win.status.pack(fill="x", padx=20)
        win.body = ctk.CTkScrollableFrame(win, fg_color=BG)
        win.body.pack(fill="both", expand=True, padx=10, pady=(4, 12))
        win.health = None
        self.render_findings(d)

        def work():
            self.events.put(("health", (d["number"], disks.health(d["number"]))))
        threading.Thread(target=work, daemon=True).start()

    def render_findings(self, d):
        win = self.ts_window
        if win is None or not win.winfo_exists():
            return
        for w in win.body.winfo_children():
            w.destroy()
        for f in troubleshoot.diagnose(d, win.health):
            color = LEVEL_COLOR[f["level"]]
            box = ctk.CTkFrame(win.body, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
            box.pack(fill="x", padx=6, pady=5)
            ctk.CTkFrame(box, fg_color=color, width=5, height=10, corner_radius=2).pack(side="left", fill="y", padx=(8, 0), pady=10)
            inner = ctk.CTkFrame(box, fg_color=CARD)
            inner.pack(side="left", fill="both", expand=True, padx=12, pady=10)
            ctk.CTkLabel(inner, text=t("ts_" + f["key"], **f["args"]), font=("Segoe UI Semibold", 13), text_color=TEXT,
                         anchor="w", justify="left", wraplength=640).pack(fill="x")
            ctk.CTkLabel(inner, text=t("ts_" + f["key"] + "_d", **f["args"]), font=("Segoe UI", 12), text_color=MUTED,
                         anchor="w", justify="left", wraplength=640).pack(fill="x", pady=(2, 0))
            if f["action"]:
                ctk.CTkButton(inner, text=t("b_" + f["action"]), height=28, width=150, fg_color=ACCENT,
                              hover_color=ACCENT_HOVER, command=lambda f=f: self.finding_action(d, f)).pack(anchor="w", pady=(8, 0))

    def finding_action(self, d, f):
        action = f["action"]
        if action == "online":
            self.do_online(d, True)
        elif action == "clear_readonly":
            self.do_readonly(d, False)
        elif action == "assign_letter":
            self.do_letter(d, f["part"])
        elif action == "check":
            self.do_check(d, f["part"])
        elif action in ("recover", "recover_region"):
            iid = "disk%d" % d["number"]
            if action == "recover_region":
                for key, row in self.rows.items():
                    if row["disk"]["number"] == d["number"] if "disk" in row else False:
                        off = row["part"]["offset"] if row["kind"] == "part" else row.get("offset")
                        if off == f["region"]["offset"] and row["kind"] in ("part", "gap"):
                            iid = key
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)
            if self.ts_window is not None and self.ts_window.winfo_exists():
                self.ts_window.destroy()

    # -- modes ----------------------------------------------------------------------------------
    def busy(self):
        return self.mode in BUSY

    def set_mode(self, mode):
        """Show the page and enable the buttons that belong to what the program is doing."""
        self.mode = mode
        busy = mode in BUSY
        results = self.catalog is not None
        working = mode in ("scan", "recover")
        self.page_select.pack_forget()
        self.page_results.pack_forget()
        self.log.configure(height=self.log_height(5 if results else 3))
        self.after_idle(lambda: self.log.see("end"))     # the box changed size: keep the last line in view
        if results:
            self.page_results.pack(fill="both", expand=True)
            self.bottom.pack_configure(fill="x", expand=False)
            self.log.pack_configure(expand=False)
        elif busy:                                      # give the room to the progress log while scanning
            self.c2.pack_forget()
            self.page_select.pack(fill="x")
            self.bottom.pack_configure(fill="both", expand=True)
            self.log.pack_configure(expand=True)
        else:
            self.c2.pack(side="bottom", fill="x", pady=(10, 0), before=self.c1)   # its share first
            self.page_select.pack(fill="both", expand=True)
            self.bottom.pack_configure(fill="x", expand=False)
            self.log.pack_configure(expand=False)
        self.start_btn.configure(text=t("recover_selected" if results else "start_scan"),
                                 command=self.start_recover if results else self.start_scan,
                                 state="disabled" if busy else "normal")
        self.pause_btn.configure(text=t("pause"), state="normal" if working else "disabled")
        self.cancel_btn.configure(text=t("stop"), state="normal" if working else "disabled")
        for b in (self.back_btn, self.folder_btn, self.report_btn):
            b.pack_forget()
        if results:
            self.back_btn.pack(side="left", padx=(10, 0))
            self.back_btn.configure(state="disabled" if busy else "normal")
            if self.summary and not busy:
                if self.summary["recovered"]:
                    self.folder_btn.pack(side="left", padx=(10, 0))
                self.report_btn.pack(side="left", padx=(10, 0))
        state = "disabled" if busy else "normal"
        for w in [self.refresh_btn, self.image_btn, self.ts_btn, self.browse_btn, self.dest_entry,
                  self.scans_btn, self.browse_btn2, self.dest_entry2, self.all_btn, self.none_btn] + self.checks:
            w.configure(state=state)
        self.tree.configure(selectmode="none" if busy else "browse")
        if not busy:
            self.on_select()

    def emit(self, kind, **kw):
        self.events.put((kind, kw))

    def begin(self, mode, label):
        """Common start of a scan or a recovery run."""
        self.summary = None
        self.control.clear()
        self.clear_log()
        self.write(label, "head")
        self.t_start, self.first, self.speed = time.time(), None, 0.0
        self.bar.set(0)
        self.detail_label.configure(text=" ")
        self.set_mode(mode)
        self.panel_reset(mode)
        self.panel(source=label)
        self.panel_state("ps_running")
        if self.panel_wanted:
            self.show_panel(True)

    def spawn(self, work):
        def guarded():
            try:
                work()
            except Cancelled:
                self.events.put(("stopped", None))
            except RecoveryError as ex:
                self.events.put(("failed", str(ex)))
            except Exception as ex:                      # show unexpected problems instead of dying silently
                import traceback
                self.events.put(("failed", "%s\n%s" % (ex, traceback.format_exc(limit=4))))
        self.worker = threading.Thread(target=guarded)
        self.worker.start()

    # -- scanning -------------------------------------------------------------------------------
    def start_scan(self):
        src = self.selected_source()
        dest = self.dest.get().strip()
        if not src:
            return messagebox.showwarning(APP_NAME, t("err_select_disk"))
        dest = os.path.abspath(dest) if dest else None
        if "number" in src:
            if disks.fake_mode():
                return messagebox.showinfo(APP_NAME, t("err_demo"))
            if not disks.is_admin():
                return messagebox.showerror(APP_NAME, t("admin_needed"))
            if self.opt_image.get() and not dest:
                return messagebox.showwarning(APP_NAME, t("err_dest_for_image"))
            if dest and disks.disk_of_path(dest, self.disks) == src["number"]:
                return messagebox.showerror(APP_NAME, t("err_same_disk"))
            if src.get("system") and not messagebox.askyesno(APP_NAME, t("warn_system"), icon="warning"):
                return
            label = "Disk %d - %s" % (src["number"], src["name"])
            if src.get("region"):
                label += " / %s (%s)" % (src["region"]["label"], human_size(src["region"]["size"]))
            else:
                label += " (%s, %s)" % (human_size(src["size"]), t("sel_whole"))
        else:
            label = src["image"]
        resume = True
        try:
            found = interrupted_scan(src, dest, self.disks)
        except Exception:
            found = None
        if found and not self.selftest:
            size = self.source_size(src) or 1
            answer = messagebox.askyesnocancel(APP_NAME, t(
                "ask_resume", pct=100.0 * found[0] / size, when=time.strftime("%d.%m.%Y %H:%M", time.localtime(found[1]))))
            if answer is None:
                return
            resume = answer
        opts = Options(include_deleted=self.opt_deleted.get(), include_live=self.opt_live.get(),
                       twin_repair=self.opt_twin.get(), lock=self.opt_lock.get(), image_first=self.opt_image.get())
        self.close_session()
        self.begin("scan", label)

        def work():
            sess = scan_source(src, opts, self.emit, self.control, dest, resume)
            self.emit("phase", key="ph_list", text=t("ph_list"))
            self.events.put(("scanned", (sess, Catalog(sess.items), True)))
        self.spawn(work)

    def load_session(self, path):
        """Open a saved scan instead of scanning again."""
        if self.busy():
            return
        self.close_session()
        self.summary = None
        self.clear_log()
        self.set_mode("load")
        self.phase_label.configure(text=t("loading_scan"))

        def work():
            try:
                sess = session.Session.open(path)
            except ValueError as ex:
                raise RecoveryError(t("err_scan_file", err=ex)) from None
            self.events.put(("scanned", (sess, Catalog(sess.items), False)))
        self.spawn(work)

    def close_session(self):
        if self.session is not None:
            self.session.close()
        self.session = self.catalog = None
        self.clear_rows()

    def back_to_select(self):
        if self.busy():
            return
        if self.session is not None and not self.session.path and self.catalog.root.pend:
            if not messagebox.askyesno(APP_NAME, t("ask_drop_scan"), icon="warning"):
                return
        self.close_session()
        self.summary = None
        self.set_mode("select")
        self.phase_label.configure(text=t("ready"))
        self.bar.set(0)
        self.detail_label.configure(text=" ")
        self.panel_state("ps_idle")
        self.panel_catalog()

    def show_catalog(self, sess, cat, fresh):
        """A scan has finished, or a saved one was opened: list what there is."""
        if not cat.root.files:
            sess.close()
            if fresh and sess.path:
                session.delete_session(sess.path)
            self.set_mode("select")
            self.phase_label.configure(text=t("done_scan"))
            self.write(t("result_none"), "warn")
            self.panel_state("ps_done")
            return self.load_disks()
        self.session, self.catalog = sess, cat
        cat.set_checked(cat.root, True)                 # offer everything that is still to be recovered
        if self.find.get():
            self.find.set("")
        self.set_mode("results")
        self.fill_results()
        r = cat.root
        self.bar.set(1 if fresh else 0)
        self.detail_label.configure(text=" ")
        self.p_pct.configure(text=t("pct", pct=100.0) if fresh else "–")
        self.phase_label.configure(text=t("done_scan" if fresh else "scan_opened"))
        self.p_phase.configure(text=t("done_scan" if fresh else "scan_opened"))
        self.panel(source=sess.meta.get("label") or "")
        self.panel_state("ps_done" if fresh else "ps_idle")
        self.write("")
        self.write(t("scan_result", n=count(r.files), size=human_size(r.size)), "good")
        if r.done:
            self.write("   " + t("scan_progress", done=count(r.done), size=human_size(r.done_size), left=count(r.pend)))
        self.write("   " + (t("scan_saved", path=sess.path) if sess.path else t("scan_unsaved")), None if sess.path else "warn")
        self.write("   " + t("scan_next"))
        if fresh:
            self.load_disks()
        if self.selftest:
            self.after(400, lambda: self.start_recover(ask=False))

    # -- result browser -------------------------------------------------------------------------
    def clear_rows(self):
        for e in self.rrows.values():
            e.iid = None
        self.rrows = {}
        self.rtree.delete(*self.rtree.get_children())

    def fill_results(self):
        self.clear_rows()
        label = self.session.meta.get("label") or ""
        self.source_label.configure(text=label if len(label) < 70 else "…" + label[-68:])
        text = self.find.get().strip()
        self.searching = bool(text)
        if text:
            found, n = self.catalog.find(text, ROW_LIMIT)
            for e in found:
                self.add_row("", e, flat=True)
            if n > len(found):
                self.rtree.insert("", "end", text=" " + t("more_rows", n=count(n - len(found))), tags=("muted",))
            if not n:
                self.rtree.insert("", "end", text=" " + t("find_none"), tags=("muted",))
        else:
            tops = sorted(self.catalog.root.children, key=lambda c: c.name.lower())
            for e in tops:
                self.add_row("", e)
            if len(tops) <= 6:
                for e in tops:
                    self.expand_row(e.iid)
                    self.rtree.item(e.iid, open=True)
        self.update_selection()

    def row_values(self, e):
        modified = filetime_to_text(e.item.node.mtime) if e.item is not None else ""
        if e.is_dir:
            state = t("fs_folder", done=count(e.done), files=count(e.files)) if e.files else ""
        else:
            state = t("fs_" + e.state)
        return human_size(e.size), modified[:16], state

    def add_row(self, parent, e, flat=False):
        iid = "r%d" % len(self.rrows)
        self.rtree.insert(parent, "end", iid=iid, text=" " + (e.path() if flat else e.name), values=self.row_values(e),
                          image=self.icons[(e.tick(), e.mark())], tags=("muted",) if e.state == "fail" else ())
        self.rrows[iid] = e
        e.iid = iid
        if e.is_dir and e.children:
            self.rtree.insert(iid, "end", iid=iid + "+", text="")       # filled when the folder is opened

    def expand_row(self, iid):
        e = self.rrows.get(iid)
        if e is None or not self.rtree.exists(iid + "+"):
            return
        self.rtree.delete(iid + "+")
        kids = sorted(e.children, key=lambda c: (not c.is_dir, c.name.lower()))
        for c in kids[:ROW_LIMIT]:
            self.add_row(iid, c)
        if len(kids) > ROW_LIMIT:
            self.rtree.insert(iid, "end", text=" " + t("more_rows", n=count(len(kids) - ROW_LIMIT)), tags=("muted",))

    def refresh_row(self, e):
        if e.iid is not None:
            self.rtree.item(e.iid, image=self.icons[(e.tick(), e.mark())], values=self.row_values(e),
                            tags=("muted",) if e.state == "fail" else ())

    def refresh_shown(self, iid=""):
        """Redraw the rows below ``iid`` (all rows when empty)."""
        stack = list(self.rtree.get_children(iid))
        while stack:
            i = stack.pop()
            e = self.rrows.get(i)
            if e is not None:
                self.refresh_row(e)
                stack.extend(self.rtree.get_children(i))

    def toggle_entry(self, e):
        self.catalog.toggle(e)
        self.refresh_row(e)
        if e.iid is not None:
            self.refresh_shown(e.iid)
        p = e.parent
        while p is not None:
            self.refresh_row(p)
            p = p.parent
        self.update_selection()

    def on_file_click(self, event):
        e = self.rrows.get(self.rtree.identify_row(event.y))
        if e is None or self.mode != "results":
            return None
        if "image" in str(self.rtree.identify_element(event.x, event.y)):
            self.toggle_entry(e)
            return "break"
        return None

    def on_file_space(self, event):
        e = self.rrows.get(self.rtree.focus())
        if e is not None and self.mode == "results":
            self.toggle_entry(e)
        return "break"

    def select_all(self, on):
        if self.catalog is None or self.mode != "results":
            return
        self.catalog.set_checked(self.catalog.root, on)
        self.refresh_shown()
        self.update_selection()

    def schedule_search(self):
        if self.search_job is not None:
            self.after_cancel(self.search_job)
        self.search_job = self.after(450, self.run_search)

    def run_search(self):
        self.search_job = None
        if self.catalog is not None and (self.find.get().strip() or self.searching):
            self.fill_results()

    def recovered_path(self, e):
        it = e.item if e is not None and not e.is_dir else None
        return it.path if it is not None and it.path and e.state in ("ok", "warn", "bad") else None

    def on_file_menu(self, event):
        iid = self.rtree.identify_row(event.y)
        e = self.rrows.get(iid)
        if e is None:
            return
        self.rtree.selection_set(iid)
        self.rtree.focus(iid)
        m = tk.Menu(self, tearoff=0, bg=CARD, fg=TEXT, activebackground=ACCENT, activeforeground="#ffffff",
                    disabledforeground="#5b657a", bd=0, relief="flat", font=("Segoe UI", 10))
        idle = "normal" if self.mode == "results" else "disabled"
        m.add_command(label=t("m_untick" if e.tick() == 1 else "m_tick"), state=idle if e.state != "fail" else "disabled",
                      command=lambda: self.toggle_entry(e))
        path = self.recovered_path(e)
        there = "normal" if path and os.path.exists(path) else "disabled"
        m.add_separator()
        m.add_command(label=t("m_open_file"), state=there, command=lambda: self.open_path(path))
        m.add_command(label=t("m_show_file"), state=there, command=lambda: self.reveal(path))
        if not e.is_dir and e.item.details:
            m.add_separator()
            m.add_command(label=t("m_details"), command=lambda: messagebox.showinfo(
                e.name, "%s\n\n%s" % (e.item.status or t("fs_pending"), "\n".join(e.item.details))))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def on_file_double(self, event):
        e = self.rrows.get(self.rtree.identify_row(event.y))
        path = self.recovered_path(e)
        if path and "image" not in str(self.rtree.identify_element(event.x, event.y)) and os.path.exists(path):
            self.reveal(path)

    def reveal(self, path):
        import subprocess
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except OSError as ex:
            messagebox.showerror(APP_NAME, str(ex))

    def dest_free(self):
        """Free bytes where the destination is (or would be created), or None when none is given."""
        probe = self.dest.get().strip()
        while probe and not os.path.isdir(probe):
            parent = os.path.dirname(probe)
            probe = "" if parent == probe else parent
        try:
            return shutil.disk_usage(probe).free if probe else None
        except OSError:
            return None

    def update_selection(self):
        if self.catalog is None:
            return
        r = self.catalog.root
        self.sel_label.configure(text=t("sel_info", n=count(r.sel), size=human_size(r.sel_size), total=count(r.files),
                                        done=count(r.done), left=count(r.pend)))
        free = self.dest_free()
        if free is None:
            text, color = t("fit_no_dest"), MUTED
        elif r.sel_size + RESERVE > free:
            text, color = t("fit_partial", free=human_size(free), size=human_size(r.sel_size)), WARN
        else:
            text, color = t("fit_ok", free=human_size(free)), GOOD
        self.fit_label.configure(text=text, text_color=color)
        self.panel_catalog()

    # -- recovering -----------------------------------------------------------------------------
    def start_recover(self, ask=True):
        if self.catalog is None or self.busy():
            return
        items = self.catalog.selected()
        if not items:
            return messagebox.showinfo(APP_NAME, t("err_nothing_ticked"))
        dest = self.dest.get().strip()
        if not dest:
            return messagebox.showwarning(APP_NAME, t("err_select_dest"))
        dest = os.path.abspath(dest)
        src = self.session.meta["source"]
        if "number" in src:
            if disks.fake_mode():
                return messagebox.showinfo(APP_NAME, t("err_demo"))
            if not disks.is_admin():
                return messagebox.showerror(APP_NAME, t("admin_needed"))
            now = [d for d in self.disks if d["size"] == src.get("size") and d.get("serial") == src.get("serial")]
            if now and disks.disk_of_path(dest, self.disks) == now[0]["number"]:
                return messagebox.showerror(APP_NAME, t("err_same_disk"))
        need, free = self.catalog.root.sel_size, self.dest_free()
        if ask and free is not None and need + RESERVE > free:
            if not messagebox.askokcancel(t("space_title"), t("space_body", need=human_size(need), free=human_size(free))):
                return
        opts = Options(twin_repair=self.opt_twin.get(), lock=self.opt_lock.get())
        sess = self.session
        self.begin("recover", sess.meta.get("label") or "")
        self.write("   " + t("recover_start", n=count(len(items)), size=human_size(need), dst=dest))

        def work():
            self.events.put(("done", recover_session(sess, items, dest, opts, self.emit, self.control)))
        self.spawn(work)

    def toggle_pause(self):
        if not self.mode in ("scan", "recover") or self.control.stopping:
            return
        if self.control.paused:
            self.control.resume()
            self.pause_btn.configure(text=t("pause"))
            self.phase_label.configure(text=self.p_phase.cget("text"))
            self.panel_state("ps_running")
            self.write("   " + t("resumed"))
        else:
            self.control.pause()
            self.pause_btn.configure(text=t("resume"))
            self.phase_label.configure(text=t("ps_paused"))
            self.panel_state("ps_paused")
            self.write("   " + t("paused"), "warn")

    def request_cancel(self):
        self.control.set()
        self.cancel_btn.configure(state="disabled", text=t("stopping"))
        self.pause_btn.configure(state="disabled", text=t("pause"))

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def log_height(self, lines):
        """Box height (in customtkinter units) that shows exactly ``lines`` whole lines.

        The text area is the box minus the frame around it (LOG_FRAME units) and its own
        padding; a height that is not a whole number of lines leaves the top line cut in half."""
        box = self.log._textbox
        space = tkfont.Font(font=box.cget("font")).metrics("linespace")
        pad = 2 * (int(box.cget("pady")) + int(box.cget("borderwidth")) + int(box.cget("highlightthickness")))
        return (lines * space + pad) / self._get_widget_scaling() + LOG_FRAME

    def write(self, text, tag=None):
        """Add a line.  The newline goes before it, so there is no empty last line to scroll to."""
        self.log.configure(state="normal")
        if self.log.get("1.0", "end-1c"):
            self.log.insert("end", "\n")
        self.log.insert("end", text, tag or ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                self.handle(kind, data)
        except queue.Empty:
            pass
        if self.closing and (self.worker is None or not self.worker.is_alive()):
            self.close_session()
            self.winfo_toplevel().destroy()
            return
        self.after(80, self.poll)

    def tick(self):
        """Twice a second: the clock of the live panel."""
        if self.mode in ("scan", "recover") and self.t_start is not None:
            self.panel(elapsed=format_duration(max(time.time() - self.t_start - self.control.idle(), 0)))
        self.after(500, self.tick)

    def amount(self, n):
        """A progress figure in the unit of the current phase."""
        return human_size(n) if self.unit == "bytes" else "%s %s" % (count(int(n)), t("u_records"))

    def on_progress(self, data):
        total, done = data.get("total") or 0, data.get("done") or 0
        stats = data.get("stats") or {}
        unit, stage = data.get("unit") or "bytes", data.get("stage")
        if (unit, stage) != (self.unit, self.stage):    # another counter: its speed and ETA start afresh
            self.unit, self.stage = unit, stage
            self.first, self.speed = None, 0.0
            self.samples.clear()
            self.draw_graph()
            self.panel(eta="–", speed="–", avg="–", data="–")
        if stage:
            self.panel(step=data.get("text") or "–")
        if total:
            frac = min(done / total, 1.0)
            self.bar.set(frac)
            clock = time.time() - self.control.idle()   # a clock that stands still while paused
            if self.first is None:
                self.first, self.rate = (clock, done), (clock, done)
            if clock - self.rate[0] >= 1.0:
                inst = max((done - self.rate[1]) / (clock - self.rate[0]), 0.0)
                self.speed = inst if not self.speed else 0.7 * self.speed + 0.3 * inst
                self.rate = (clock, done)
                self.samples.append(inst)
                self.draw_graph()
            line = "%.1f%%" % (100.0 * frac)
            if self.speed > 0:
                left = format_duration((total - done) / self.speed)
                line = t("eta", pct=100.0 * frac, speed=self.amount(self.speed), eta=left)
                spent = clock - self.first[0]
                self.panel(eta=left, speed=self.amount(self.speed) + t("per_s"),
                           avg=(self.amount((done - self.first[1]) / spent) + t("per_s")) if spent > 1 else "–")
            if data.get("text"):
                line += "    " + data["text"][:70]
            self.detail_label.configure(text=line)
            self.p_pct.configure(text=t("pct", pct=100.0 * frac))
            if self.unit == "bytes":
                self.panel(data="%s / %s" % (human_size(done), human_size(total)))
            else:
                self.panel(data="%s / %s" % (count(done), self.amount(total)))
        else:
            self.bar.set(0)
            if data.get("text"):
                self.detail_label.configure(text=data["text"][:90])
        if "mft" in stats:
            self.panel(mft=count(stats["mft"]), fat=count(stats["fat"]), exfat=count(stats["exfat"]), boot=count(stats["boot"]))
        if "files" in stats:
            c = stats["counts"]
            self.panel(files="%s / %s" % (count(stats["files"]), count(stats["files_total"])),
                       ok=count(c.get("OK", 0)), repaired=count(c.get("REPAIRED", 0) + c.get("FILLED_FROM_TWIN", 0)),
                       uncertain=count(c.get("UNCERTAIN", 0)), damaged=count(c.get("DAMAGED", 0)),
                       failed=count(c.get("SKIPPED", 0) + c.get("UNSUPPORTED", 0)),
                       waiting="%s · %s" % (count(stats["waiting"]), human_size(stats["waiting_size"])),
                       free=human_size(max(stats["free"], 0)), current=data.get("text") or "–")
        if "bad" in stats:
            self.panel(bad=human_size(stats["bad"]))

    def on_items(self, items):
        if self.catalog is None:
            return
        touched = {}
        for it in items:
            for e in self.catalog.update(it):
                touched[id(e)] = e
            self.recent.append("%s  %s" % ({"ok": "✓", "warn": "✓?", "bad": "!", "fail": "✗"}.get(
                self.catalog.by_id[it.id].state, "·"), it.rel[-1][:38]))
        for e in touched.values():
            self.refresh_row(e)
        self.panel(recent="\n".join(self.recent))
        self.update_selection()

    def handle(self, kind, data):
        if kind == "disks":
            self.disks = data
            self.fill_tree()
            self.refresh_btn.configure(state="disabled" if self.busy() else "normal")
            if not self.busy():
                self.detail_label.configure(text=" ")
                self.check_pending_locks()
            if self.uitest:
                steps, self.uitest = self.uitest.split(";"), None
                for step in steps:
                    if step.startswith("select=") and self.tree.exists(step[7:]):
                        self.tree.selection_set(step[7:])
                        self.tree.see(step[7:])
                    elif step == "troubleshoot":
                        self.after(300, self.open_troubleshooter)
            if self.ts_window is not None and self.ts_window.winfo_exists():
                d = next((x for x in self.disks if x["number"] == self.ts_window.disk_number), None)
                if d:
                    self.render_findings(d)
        elif kind == "disks_error":
            self.refresh_btn.configure(state="disabled" if self.busy() else "normal")
            self.detail_label.configure(text=" ")
            self.write(data, "bad")
        elif kind == "health":
            number, info = data
            win = self.ts_window
            if win is not None and win.winfo_exists() and win.disk_number == number:
                win.health = info
                win.status.configure(text=" ")
                d = next((x for x in self.disks if x["number"] == number), None)
                if d:
                    self.render_findings(d)
        elif kind == "action":
            what, result = data
            ok, text = result[0], result[1]
            if ok:
                self.write("   " + (text if text and "\n" not in text and len(text) > 20 else t("act_done", what=what)), "good")
            else:
                self.write("   " + t("act_failed", what=what, err=text), "bad")
                messagebox.showerror(APP_NAME, t("act_failed", what=what, err=text))
            self.load_disks()
        elif kind == "phase":
            if not self.control.paused:
                self.phase_label.configure(text=data["text"])
            self.p_phase.configure(text=data["text"])
            self.p_pct.configure(text="–")
            self.write("▸ " + data["text"], "head")
            self.bar.set(0)
            self.detail_label.configure(text=" ")
            self.first, self.speed = None, 0.0
            self.unit, self.stage = "bytes", None
            self.panel(step="–", eta="–", speed="–", avg="–", data="–")
        elif kind == "log":
            text = data["text"]
            self.write("   " + text, "bad" if "COULD NOT" in text or "KALDIRILAMADI" in text else None)
        elif kind == "progress":
            self.on_progress(data)
        elif kind == "volumes":
            self.panel(vols="\n".join(t("vol_line", fs=fs, label=(" " + label) if label else "", files=count(files),
                                        dirs=count(dirs)) for fs, label, files, dirs in data["found"]) or t("vol_none"))
        elif kind == "items":
            self.on_items(data["items"])
        elif kind == "scanned":
            self.show_catalog(*data)
        elif kind == "done":
            self.finish(data)
        elif kind == "stopped":                          # a scan was stopped; it can be continued later
            self.set_mode("results" if self.catalog is not None else "select")
            self.phase_label.configure(text=t("scan_stopped"))
            self.p_phase.configure(text=t("scan_stopped"))
            self.panel_state("ps_stopped")
            self.bar.set(0)
            self.detail_label.configure(text=" ")
            self.write(t("scan_stopped_note"), "warn")
            self.load_disks()
        elif kind == "failed":
            self.set_mode("results" if self.catalog is not None else "select")
            self.phase_label.configure(text=t("err_title"))
            self.panel_state("ps_stopped")
            self.bar.set(0)
            self.detail_label.configure(text=" ")
            self.write(data, "bad")
            self.load_disks()
            if not self.closing:
                messagebox.showerror(t("err_title"), data.split("\n")[0])

    def finish(self, s):
        """A recovery run is over (complete, stopped, or out of space)."""
        self.summary = s
        self.set_mode("results")
        self.refresh_shown()
        self.update_selection()
        self.bar.set(1)
        title = t("run_stopped") if s["stopped"] else t("done_title")
        self.phase_label.configure(text=title)
        self.p_phase.configure(text=title)
        self.panel_state("ps_stopped" if s["stopped"] else "ps_done")
        if not s["stopped"]:
            self.p_pct.configure(text=t("pct", pct=100.0))
        self.detail_label.configure(text=" ")
        self.write("")
        if not s["recovered"]:
            self.write(t("run_none"), "warn")
        else:
            self.write(t("result_head", n=s["recovered"], size=human_size(s["size"]), time=format_duration(s["elapsed"])), "good")
            heads = [t("col_ok"), t("col_repaired"), t("col_uncertain"), t("col_damaged"), t("col_failed")]
            self.write("   %-34s" % "" + "".join("%12s" % h for h in heads))
            for cat in ("main", "orphaned", "deleted"):
                c = s["categories"].get(cat) or {}
                if not c:
                    continue
                vals = [c.get("OK", 0), c.get("REPAIRED", 0) + c.get("FILLED_FROM_TWIN", 0), c.get("UNCERTAIN", 0),
                        c.get("DAMAGED", 0), c.get("SKIPPED", 0) + c.get("UNSUPPORTED", 0)]
                self.write("   %-34s" % t("cat_" + cat) + "".join("%12d" % v for v in vals))
        if s["no_space"]:
            self.write("   " + t("result_no_space", n=count(s["no_space"]), size=human_size(s["no_space_size"])), "warn")
        if s["pending"]:
            self.write("   " + t("result_pending", n=count(s["pending"]), size=human_size(s["pending_size"])))
        else:
            self.write("   " + t("result_all_done"), "good")
        if s["bad_bytes"]:
            self.write("   " + t("result_bad", size=human_size(s["bad_bytes"])), "warn")
        self.write("   %s: %s" % (t("sum_dest"), s["dest"]))
        self.write("   %s: %s" % (t("sum_report"), s["report_dir"]))
        self.load_disks()
        if s["no_space"] and not self.closing and not self.selftest:
            messagebox.showinfo(t("space_title"), t("space_after", n=count(s["no_space"]), size=human_size(s["no_space_size"])))

    # -- saved scans ----------------------------------------------------------------------------
    def open_scans(self):
        if self.busy():
            return
        if self.scans_window is not None and self.scans_window.winfo_exists():
            self.scans_window.destroy()
        win = self.scans_window = ctk.CTkToplevel(self, fg_color=BG)
        win.title(t("scans_title"))
        win.geometry("860x460")
        win.minsize(700, 320)
        win.transient(self.winfo_toplevel())
        ctk.CTkLabel(win, text=t("scans_hint"), font=("Segoe UI", 12), text_color=MUTED, anchor="w", justify="left",
                     wraplength=800).pack(fill="x", padx=18, pady=(14, 8))
        holder = ctk.CTkFrame(win, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
        holder.pack(fill="both", expand=True, padx=16)
        tree = ttk.Treeview(holder, columns=("source", "files", "done"), show="tree headings", style="Disk.Treeview",
                            selectmode="browse")
        tree.heading("#0", text=t("col_when"), anchor="w")
        tree.column("#0", width=150, stretch=False, anchor="w")
        for col, width, stretch in (("source", 330, 1), ("files", 150, 0), ("done", 170, 0)):
            tree.heading(col, text=t("col_scan_" + col), anchor="w")
            tree.column(col, width=width, stretch=bool(stretch), anchor="w")
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        found = {}

        def fill():
            tree.delete(*tree.get_children())
            found.clear()
            for i, info in enumerate(session.list_sessions()):
                found[str(i)] = info
                tree.insert("", "end", iid=str(i), text=" " + time.strftime("%d.%m.%Y %H:%M", time.localtime(info["created"])),
                            values=(info["label"], "%s · %s" % (count(info["files"]), human_size(info["size"])),
                                    "%s · %s" % (count(info["recovered"]), human_size(info["recovered_size"]))))
            if not found:
                tree.insert("", "end", text=" " + t("scans_none"), tags=("muted",))
        tree.tag_configure("muted", foreground=MUTED)

        def chosen():
            sel = tree.selection()
            return found.get(sel[0]) if sel else None

        def open_it(path=None):
            path = path or (chosen() or {}).get("path")
            if path:
                win.destroy()
                self.load_session(path)

        def delete_it():
            info = chosen()
            if info and messagebox.askyesno(APP_NAME, t("ask_delete_scan"), icon="warning", parent=win):
                session.delete_session(info["path"])
                fill()

        def from_file():
            path = filedialog.askopenfilename(parent=win, title=t("scans_file"), filetypes=[
                (t("scans_type"), "*" + session.EXT), ("All files", "*.*")])
            if path:
                open_it(os.path.normpath(path))
        tree.bind("<Double-1>", lambda e: open_it())
        row = ctk.CTkFrame(win, fg_color=BG)
        row.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(row, text=t("scans_open"), width=130, height=32, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=open_it).pack(side="left")
        self.small_button(row, t("scans_delete"), delete_it, 100).pack(side="left", padx=(8, 0))
        self.small_button(row, t("scans_file") + "…", from_file, 150).pack(side="left", padx=(8, 0))
        self.small_button(row, t("close"), win.destroy, 90).pack(side="right")
        fill()
        win.after(150, win.grab_set)

    # -- misc -----------------------------------------------------------------------------------
    def open_path(self, path):
        try:
            os.startfile(path)
        except OSError as ex:
            messagebox.showerror(APP_NAME, str(ex))

    def relabel(self):
        """Rebuild in the language the window has just switched to (never while busy)."""
        selection = self.tree.selection()
        shown = self.panel_shown
        self.clear_rows()
        self.build()
        if selection and self.tree.exists(selection[0]):
            self.tree.selection_set(selection[0])
        self.on_select()
        if shown:
            self.show_panel(True, resize=False)

    def on_close(self):
        """The window is being closed.  Returns True when it may close right away; otherwise
        the running job is being stopped and the window closes when the worker has finished."""
        if self.worker is not None and self.worker.is_alive():
            if self.mode in ("scan", "recover") and not messagebox.askyesno(APP_NAME, t("closing_busy")):
                return False
            self.closing = True
            self.request_cancel()       # the worker releases the write protection before it ends
            return False
        self.close_session()
        return True


def main():
    """Kept for old shortcuts: starts Benchwise straight in the File Recovery tool."""
    from benchwise.shell import main as shell_main
    shell_main(open_tool="disk.recovery")
