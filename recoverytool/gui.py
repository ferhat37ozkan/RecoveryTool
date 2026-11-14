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

from . import APP_NAME, __version__, disks, i18n
from .engine import Options, RecoveryError, format_duration, run_recovery
from .i18n import t
from .model import Cancelled, human_size

BG, CARD, BORDER = "#0f1420", "#182033", "#263149"
TEXT, MUTED, ACCENT, ACCENT_HOVER = "#e8ecf4", "#8b96ad", "#2f7cf6", "#2467d3"
GOOD, WARN, BAD = "#3ecf8e", "#f5b84b", "#f26d6d"
PHASES = ["ph_lock", "ph_image", "ph_scan", "ph_analyze", "ph_recover", "ph_verify", "ph_report", "ph_unlock"]


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", name)


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("%s %s" % (APP_NAME, __version__))
        self.geometry("1120x800")
        self.minsize(1000, 680)
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

    def run_selftest(self, image, dest):
        self.image_path = image
        self.fill_tree()
        self.dest.set(dest)
        self.start(confirm=False)

    # -- construction ---------------------------------------------------------------------------
    def style_tree(self):
        s = ttk.Style(self)
        s.theme_use("default")
        s.configure("Disk.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=30,
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

    def build(self):
        for w in self.winfo_children():
            w.destroy()
        root = ctk.CTkFrame(self, fg_color=BG)
        root.pack(fill="both", expand=True, padx=22, pady=(16, 18))

        head = ctk.CTkFrame(root, fg_color=BG)
        head.pack(fill="x")
        ctk.CTkLabel(head, text=APP_NAME, font=("Segoe UI Semibold", 26), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(head, text="v" + __version__, font=("Segoe UI", 11), text_color=MUTED).pack(side="left", padx=(8, 0), pady=(10, 0))
        self.lang_btn = ctk.CTkButton(head, text=t("lang"), width=84, height=28, fg_color=CARD, hover_color=BORDER,
                                      border_width=1, border_color=BORDER, text_color=TEXT, command=self.switch_language)
        self.lang_btn.pack(side="right")
        ctk.CTkLabel(root, text=t("subtitle"), font=("Segoe UI", 12), text_color=MUTED, anchor="w").pack(fill="x", pady=(0, 12))

        # 1 - disks
        c1 = self.card(root, t("step1"))
        c1.pack(fill="x")
        bar = ctk.CTkFrame(c1, fg_color=CARD)
        bar.place(relx=1.0, x=-14, y=9, anchor="ne")
        self.refresh_btn = ctk.CTkButton(bar, text=t("refresh"), width=86, height=28, fg_color=BORDER, hover_color="#33405c",
                                         text_color=TEXT, command=self.load_disks)
        self.refresh_btn.pack(side="right")
        self.image_btn = ctk.CTkButton(bar, text=t("open_image"), width=130, height=28, fg_color=BORDER, hover_color="#33405c",
                                       text_color=TEXT, command=self.pick_image)
        self.image_btn.pack(side="right", padx=(0, 8))
        cols = ("disk", "name", "bus", "size", "style", "volumes", "state")
        self.tree = ttk.Treeview(c1, columns=cols, show="headings", height=4, style="Disk.Treeview", selectmode="browse")
        for col, width, stretch in (("disk", 64, 0), ("name", 230, 0), ("bus", 80, 0), ("size", 88, 0),
                                    ("style", 64, 0), ("volumes", 260, 1), ("state", 190, 0)):
            self.tree.heading(col, text=t("col_" + col), anchor="w")
            self.tree.column(col, width=width, stretch=bool(stretch), anchor="w")
        self.tree.pack(fill="x", padx=16, pady=(2, 12))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.on_select())

        # 2 - destination
        c2 = self.c2 = self.card(root, t("step2"))
        c2.pack(fill="x", pady=(10, 0))
        row = ctk.CTkFrame(c2, fg_color=CARD)
        row.pack(fill="x", padx=16)
        self.dest_entry = ctk.CTkEntry(row, textvariable=self.dest, height=34, fg_color=BG, border_color=BORDER,
                                       text_color=TEXT, placeholder_text=t("dest_placeholder"))
        self.dest_entry.pack(side="left", fill="x", expand=True)
        self.browse_btn = ctk.CTkButton(row, text=t("browse"), width=100, height=34, fg_color=BORDER, hover_color="#33405c",
                                        text_color=TEXT, command=self.pick_dest)
        self.browse_btn.pack(side="left", padx=(8, 0))
        self.space_label = ctk.CTkLabel(c2, text=" ", font=("Segoe UI", 11), text_color=MUTED, anchor="w")
        self.space_label.pack(fill="x", padx=18, pady=(2, 6))

        # 3 - options
        c3 = self.c3 = self.card(root, t("step3"))
        c3.pack(fill="x", pady=(10, 0))
        grid = ctk.CTkFrame(c3, fg_color=CARD)
        grid.pack(fill="x", padx=16, pady=(0, 12))
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
                                  font=("Consolas", 11), corner_radius=12, wrap="word")
        self.log.pack(fill="both", expand=True, pady=(8, 0))
        self.log.tag_config("good", foreground=GOOD)
        self.log.tag_config("warn", foreground=WARN)
        self.log.tag_config("bad", foreground=BAD)
        self.log.tag_config("head", foreground="#ffffff")
        self.log.configure(state="disabled")
        self.fill_tree()

    # -- disk list ------------------------------------------------------------------------------
    def startup_checks(self):
        if not disks.is_admin():
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
        self.tree.delete(*self.tree.get_children())
        for d in self.disks:
            vols = []
            for p in d["partitions"]:
                if p.get("type") in ("Reserved", "System", "Recovery") and not p.get("letter"):
                    continue
                name = (p["letter"] + ":") if p.get("letter") else t("no_letter")
                label = (" " + p["label"]) if p.get("label") else ""
                vols.append("%s%s (%s, %s)" % (name, label, p.get("filesystem") or "RAW", human_size(p["size"])))
            state = [t("state_offline") if d["offline"] else t("state_online")]
            if d["system"]:
                state.append(t("state_system"))
            if d["readonly"]:
                state.append(t("state_readonly"))
            self.tree.insert("", "end", iid="disk%d" % d["number"], values=(
                "Disk %d" % d["number"], d["name"], d["bus"], human_size(d["size"]), d["style"],
                "  ·  ".join(vols) or t("no_volume"), ", ".join(state)))
        if self.image_path:
            self.tree.insert("", "end", iid="image", values=(
                "IMG", os.path.basename(self.image_path), t("image_file"), human_size(os.path.getsize(self.image_path)),
                "", self.image_path, ""))
            self.tree.selection_set("image")

    def selected_source(self):
        sel = self.tree.selection()
        if not sel:
            return None
        if sel[0] == "image":
            return {"image": self.image_path}
        number = int(sel[0][4:])
        return next((d for d in self.disks if d["number"] == number), None)

    def on_select(self):
        src = self.selected_source()
        system = bool(src and src.get("system"))
        is_image = bool(src and "image" in src)
        self.checks[0].configure(state="disabled" if (system or is_image) else "normal")
        self.checks[4].configure(state="disabled" if is_image else "normal")
        self.update_space()

    def pick_image(self):
        path = filedialog.askopenfilename(title=t("choose_image"), filetypes=[
            ("Disk images", "*.img *.dd *.raw *.bin *.vhd *.iso"), ("All files", "*.*")])
        if path:
            self.image_path = os.path.normpath(path)
            self.fill_tree()
            self.on_select()

    def pick_dest(self):
        path = filedialog.askdirectory(title=t("choose_dest"), mustexist=False)
        if path:
            self.dest.set(os.path.normpath(path))

    def update_space(self):
        text, src = " ", self.selected_source()
        path = self.dest.get().strip()
        probe = path
        while probe and not os.path.isdir(probe):
            parent = os.path.dirname(probe)
            if parent == probe:
                probe = ""
            probe = parent
        if probe:
            try:
                free = shutil.disk_usage(probe).free
                size = src["size"] if src and "size" in src else (os.path.getsize(src["image"]) if src else 0)
                text = t("free_space", free=human_size(free), size=human_size(size) if size else "-")
            except OSError:
                pass
        self.space_label.configure(text=text)

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
            if not disks.is_admin():
                return messagebox.showerror(APP_NAME, t("admin_needed"))
            if disks.disk_of_path(dest, self.disks) == src["number"]:
                return messagebox.showerror(APP_NAME, t("err_same_disk"))
            if src.get("system") and not messagebox.askyesno(APP_NAME, t("warn_system"), icon="warning"):
                return
            label = "Disk %d - %s (%s)" % (src["number"], src["name"], human_size(src["size"]))
        else:
            label = src["image"]
        if confirm and not messagebox.askokcancel(t("confirm_title"), t("confirm_body", src=label, dst=dest)):
            return
        opts = Options(include_deleted=self.opt_deleted.get(), include_live=self.opt_live.get(),
                       twin_repair=self.opt_twin.get(), lock=self.opt_lock.get(), image_first=self.opt_image.get())
        self.summary = None
        self.cancel.clear()
        self.c2.pack_forget()               # give the room to the progress log while working
        self.c3.pack_forget()
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
        self.c2.pack(fill="x", pady=(10, 0), before=self.run_frame)
        self.c3.pack(fill="x", pady=(10, 0), before=self.run_frame)
        self.start_btn.configure(text=t("start"), command=self.start)
        self.phase_label.configure(text=t("ready"))
        self.bar.set(0)
        self.detail_label.configure(text=" ")

    def set_busy(self, busy):
        state = "disabled" if busy else "normal"
        for w in [self.start_btn, self.refresh_btn, self.image_btn, self.browse_btn, self.dest_entry, self.lang_btn] + self.checks:
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
            if self.worker is None or not self.worker.is_alive():
                self.check_pending_locks()
        elif kind == "disks_error":
            self.refresh_btn.configure(state="normal")
            self.detail_label.configure(text=" ")
            self.write(data, "bad")
        elif kind == "phase":
            step = PHASES.index(data["key"]) + 1 if data["key"] in PHASES else 0
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
