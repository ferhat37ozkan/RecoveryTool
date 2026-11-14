"""Desktop user interface (customtkinter)."""

from __future__ import annotations

import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import APP_NAME, __version__, disks, i18n, troubleshoot
from .engine import Options, RecoveryError, format_duration, run_recovery
from .i18n import t
from .model import Cancelled, human_size

BG, CARD, BORDER = "#0f1420", "#182033", "#263149"
TEXT, MUTED, ACCENT, ACCENT_HOVER = "#e8ecf4", "#8b96ad", "#2f7cf6", "#2467d3"
GOOD, WARN, BAD = "#3ecf8e", "#f5b84b", "#f26d6d"
LEVEL_COLOR = {"ok": GOOD, "info": ACCENT, "warning": WARN, "error": BAD}


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", name)


def part_name(p):
    """Short human name of a partition: "E: Backup" or "Partition 3"."""
    if p.get("letter"):
        return ("%s: %s" % (p["letter"], p.get("label") or "")).strip()
    return p.get("label") or t("partition_n", n=p["number"])


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("%s %s" % (APP_NAME, __version__))
        self.geometry("1120x790")
        self.minsize(1000, 700)
        try:
            self.iconbitmap(resource("icon.ico"))
        except tk.TclError:
            pass
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.disks = []
        self.image_path = None
        self.summary = None
        self.closing = False
        self.asked_locks = set()
        self.rows = {}                  # tree item id -> description of what it stands for
        self.ts_window = None
        self.rate = (0.0, 0)            # (time, bytes) of the previous progress sample
        self.speed = 0.0
        self.dest = tk.StringVar()
        self.opt_lock = tk.BooleanVar(value=True)
        self.opt_deleted = tk.BooleanVar(value=True)
        self.opt_live = tk.BooleanVar(value=False)
        self.opt_twin = tk.BooleanVar(value=True)
        self.opt_image = tk.BooleanVar(value=False)
        self.dest.trace_add("write", lambda *a: self.update_space())
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.style_tree()
        self.build()
        self.after(80, self.poll)
        self.after(200, self.startup_checks)
        selftest = os.environ.get("RECOVERYTOOL_SELFTEST")       # "image|destination": used by the UI test
        if selftest:
            self.after(2500, lambda: self.run_selftest(*selftest.split("|")))
        self.uitest = os.environ.get("RECOVERYTOOL_UITEST")      # "select=<row id>[;troubleshoot]": UI test

    def run_selftest(self, image, dest):
        self.image_path = image
        self.fill_tree()
        self.tree.selection_set("image")
        self.dest.set(dest)
        self.start(confirm=False)

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

    def card(self, parent, title):
        frame = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        ctk.CTkLabel(frame, text=title, font=("Segoe UI Semibold", 14), text_color=TEXT, anchor="w").pack(
            fill="x", padx=18, pady=(12, 6))
        return frame

    def small_button(self, parent, text, command, width=100):
        return ctk.CTkButton(parent, text=text, width=width, height=28, fg_color=BORDER, hover_color="#33405c",
                             text_color=TEXT, command=command)

    def build(self):
        for w in self.winfo_children():
            w.destroy()
        self.ts_window = None
        root = ctk.CTkFrame(self, fg_color=BG)
        root.pack(fill="both", expand=True, padx=22, pady=(16, 18))

        head = ctk.CTkFrame(root, fg_color=BG)
        head.pack(fill="x")
        ctk.CTkLabel(head, text=APP_NAME, font=("Segoe UI Semibold", 26), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(head, text="v" + __version__, font=("Segoe UI", 11), text_color=MUTED).pack(side="left", padx=(8, 0), pady=(10, 0))
        self.lang_btn = ctk.CTkButton(head, text=t("lang"), width=84, height=28, fg_color=CARD, hover_color=BORDER,
                                      border_width=1, border_color=BORDER, text_color=TEXT, command=self.switch_language)
        self.lang_btn.pack(side="right")
        ctk.CTkLabel(root, text=t("subtitle"), font=("Segoe UI", 12), text_color=MUTED, anchor="w").pack(fill="x", pady=(0, 10))

        # 1 - disks and their partitions
        c1 = self.c1 = self.card(root, t("step1"))
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
            self.tree.heading(col, text=t("col_" + ("size" if col == "size" else "state" if col == "state" else col)), anchor="w")
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

        # 2 - destination
        c2 = self.c2 = self.card(root, t("step2"))
        c2.pack(fill="x", pady=(10, 0))
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

        # options, in the same card to keep the window short enough for small screens
        grid = ctk.CTkFrame(c2, fg_color=CARD)
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

        # run area
        run = self.run_frame = ctk.CTkFrame(root, fg_color=BG)
        run.pack(fill="x", pady=(12, 0))
        self.start_btn = ctk.CTkButton(run, text=t("start"), height=42, width=220, font=("Segoe UI Semibold", 14),
                                       fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.start)
        self.start_btn.pack(side="left")
        self.cancel_btn = ctk.CTkButton(run, text=t("cancel"), height=42, width=110, fg_color=CARD, hover_color=BORDER,
                                        border_width=1, border_color=BORDER, text_color=TEXT, state="disabled",
                                        command=self.request_cancel)
        self.cancel_btn.pack(side="left", padx=(10, 0))
        self.folder_btn = ctk.CTkButton(run, text=t("open_folder"), height=42, width=130, fg_color=GOOD, hover_color="#32b078",
                                        text_color="#06210f", command=lambda: self.open_path(self.summary["dest"]))
        self.report_btn = ctk.CTkButton(run, text=t("open_report"), height=42, width=130, fg_color=CARD, hover_color=BORDER,
                                        border_width=1, border_color=BORDER, text_color=TEXT,
                                        command=lambda: self.open_path(self.summary["report_dir"]))
        self.phase_label = ctk.CTkLabel(run, text=t("ready"), font=("Segoe UI Semibold", 13), text_color=TEXT, anchor="e")
        self.phase_label.pack(side="right")

        self.bar = ctk.CTkProgressBar(root, height=10, fg_color=CARD, progress_color=ACCENT, corner_radius=5)
        self.bar.set(0)
        self.bar.pack(fill="x", pady=(10, 2))
        self.detail_label = ctk.CTkLabel(root, text=" ", font=("Segoe UI", 11), text_color=MUTED, anchor="w")
        self.detail_label.pack(fill="x")
        self.log = ctk.CTkTextbox(root, fg_color=CARD, border_width=1, border_color=BORDER, text_color=TEXT,
                                  font=("Consolas", 11), corner_radius=12, wrap="word", height=56)
        self.log.pack(fill="both", expand=False, pady=(8, 0))
        for tag, color in (("good", GOOD), ("warn", WARN), ("bad", BAD), ("head", "#ffffff")):
            self.log.tag_config(tag, foreground=color)
        self.log.configure(state="disabled")
        self.fill_tree()

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
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                break

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
        win.transient(self)
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
        win.transient(self)
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

    # -- running --------------------------------------------------------------------------------
    def start(self, confirm=True):
        src = self.selected_source()
        dest = self.dest.get().strip()
        if not src:
            return messagebox.showwarning(APP_NAME, t("err_select_disk"))
        if not dest:
            return messagebox.showwarning(APP_NAME, t("err_select_dest"))
        dest = os.path.abspath(dest)
        if "number" in src:
            if disks.fake_mode():
                return messagebox.showinfo(APP_NAME, t("err_demo"))
            if not disks.is_admin():
                return messagebox.showerror(APP_NAME, t("admin_needed"))
            if disks.disk_of_path(dest, self.disks) == src["number"]:
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
        if confirm and not messagebox.askokcancel(t("confirm_title"), t("confirm_body", src=label, dst=dest)):
            return
        opts = Options(include_deleted=self.opt_deleted.get(), include_live=self.opt_live.get(),
                       twin_repair=self.opt_twin.get(), lock=self.opt_lock.get(), image_first=self.opt_image.get())
        self.summary = None
        self.cancel.clear()
        self.c2.pack_forget()               # give the room to the progress log while working
        self.c1.pack_configure(expand=False)
        self.log.pack_configure(expand=True)
        self.set_busy(True)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.write(label, "head")

        def work():
            try:
                s = run_recovery(src, dest, opts, lambda kind, **kw: self.events.put((kind, kw)), self.cancel)
                self.events.put(("done", s))
            except Cancelled:
                self.events.put(("failed", t("cancelled")))
            except RecoveryError as ex:
                self.events.put(("failed", str(ex)))
            except Exception as ex:                      # show unexpected problems instead of dying silently
                import traceback
                self.events.put(("failed", "%s\n%s" % (ex, traceback.format_exc(limit=4))))
        self.worker = threading.Thread(target=work)
        self.worker.start()

    def reset_view(self):
        """Back from the result view to the selection view."""
        self.folder_btn.pack_forget()
        self.report_btn.pack_forget()
        self.log.pack_configure(expand=False)
        self.c1.pack_configure(expand=True)
        self.c2.pack(fill="x", pady=(10, 0), before=self.run_frame)
        self.start_btn.configure(text=t("start"), command=self.start)
        self.phase_label.configure(text=t("ready"))
        self.bar.set(0)
        self.detail_label.configure(text=" ")

    def set_busy(self, busy):
        state = "disabled" if busy else "normal"
        for w in [self.start_btn, self.refresh_btn, self.image_btn, self.ts_btn, self.browse_btn, self.dest_entry,
                  self.lang_btn] + self.checks:
            w.configure(state=state)
        self.cancel_btn.configure(state="normal" if busy else "disabled", text=t("cancel"))
        self.tree.configure(selectmode="none" if busy else "browse")
        if not busy:
            self.on_select()
            self.start_btn.configure(text=t("new_recovery"), command=self.reset_view)

    def request_cancel(self):
        self.cancel.set()
        self.cancel_btn.configure(state="disabled", text=t("cancelling"))

    def write(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag or ())
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
            self.destroy()
            return
        self.after(80, self.poll)

    def handle(self, kind, data):
        if kind == "disks":
            self.disks = data
            self.fill_tree()
            self.refresh_btn.configure(state="normal")
            self.detail_label.configure(text=" ")
            busy = self.worker is not None and self.worker.is_alive()
            if not busy:
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
            self.refresh_btn.configure(state="normal")
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
            self.phase_label.configure(text=data["text"])
            self.write("▸ " + data["text"], "head")
            self.bar.set(0)
            self.detail_label.configure(text=" ")
            self.rate, self.speed = (time.time(), 0), 0.0
        elif kind == "log":
            text = data["text"]
            self.write("   " + text, "bad" if "COULD NOT" in text or "KALDIRILAMADI" in text else None)
        elif kind == "progress":
            total, done = data.get("total") or 0, data.get("done") or 0
            if total:
                self.bar.set(min(done / total, 1.0))
                now = time.time()
                if now - self.rate[0] >= 1.0:
                    inst = (done - self.rate[1]) / (now - self.rate[0])
                    self.speed = inst if not self.speed else 0.7 * self.speed + 0.3 * inst
                    self.rate = (now, done)
                line = "%.1f%%" % (100.0 * done / total)
                if self.speed > 0:
                    line = t("eta", pct=100.0 * done / total, speed=human_size(self.speed),
                             eta=format_duration((total - done) / self.speed))
                if data.get("text"):
                    line += "    " + data["text"][:70]
                self.detail_label.configure(text=line)
            else:
                self.bar.set(0)
        elif kind == "done":
            self.finish(data)
        elif kind == "failed":
            self.set_busy(False)
            self.phase_label.configure(text=data if data == t("cancelled") else t("err_title"))
            self.bar.set(0)
            self.detail_label.configure(text=" ")
            self.write(data, "bad")
            self.load_disks()
            if not self.closing and data != t("cancelled"):
                messagebox.showerror(t("err_title"), data.split("\n")[0])

    def finish(self, s):
        self.summary = s
        self.set_busy(False)
        self.bar.set(1)
        self.phase_label.configure(text=t("done_title"))
        self.detail_label.configure(text=" ")
        self.write("")
        if not s["recovered"]:
            self.write(t("result_none"), "warn")
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
        if s["live_skipped"]:
            self.write("   " + t("result_live", n=s["live_skipped"]))
        if s["bad_bytes"]:
            self.write("   " + t("result_bad", size=human_size(s["bad_bytes"])), "warn")
        self.write("   %s: %s" % (t("sum_dest"), s["dest"]))
        self.write("   %s: %s" % (t("sum_report"), s["report_dir"]))
        if s["recovered"]:
            self.folder_btn.pack(side="left", padx=(10, 0))
        self.report_btn.pack(side="left", padx=(10, 0))
        self.load_disks()

    # -- misc -----------------------------------------------------------------------------------
    def open_path(self, path):
        try:
            os.startfile(path)
        except OSError as ex:
            messagebox.showerror(APP_NAME, str(ex))

    def switch_language(self):
        i18n.set_language("en" if i18n.language() == "tr" else "tr")
        selection = self.tree.selection()
        self.build()
        if selection and self.tree.exists(selection[0]):
            self.tree.selection_set(selection[0])
        self.on_select()

    def on_close(self):
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno(APP_NAME, t("closing_busy")):
                return
            self.closing = True
            self.request_cancel()       # the worker releases the write protection before it ends
        else:
            self.destroy()


def main():
    forced = os.environ.get("RECOVERYTOOL_LANG")          # "en" or "tr" overrides the Windows language
    i18n.set_language(forced) if forced else i18n.detect()
    ctk.set_appearance_mode("dark")
    App().mainloop()


if __name__ == "__main__":
    main()
