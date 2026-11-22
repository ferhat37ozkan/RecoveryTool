"""The Disk Health screen: disks on the left, the selected disk's verdict and figures on the right."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import customtkinter as ctk

from recoverytool.i18n import t
from recoverytool.model import human_size

from .. import livemode, monitor, settings, ui
from ..ui import BG, BORDER, CARD, CARD_HOVER, LEVEL, MUTED, TEXT
from . import amdraid, data, verdict

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
        self.dl = None              # (step, done, total) while AMD_RC2t7 is being downloaded
        self.pending_key = None     # a disk to select once the list is in (a click on its clock icon)
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
                self.events.put(("done", self.with_members(data.collect())))
            except Exception as ex:          # shown to the user; the screen stays usable
                self.events.put(("failed", str(ex)))
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def with_members(disks):
        return amdraid.attach_members(disks)

    def get_library(self, intro=None):
        """Ask (``intro`` first, when given) and download AMD_RC2t7."""
        text = t("dh_raid_ask", v=amdraid.VERSION, url=amdraid.URL, lic=amdraid.LICENSE_URL)
        if not messagebox.askyesno(t("dh_raid_title"), (intro + "\n\n" + text) if intro else text):
            return
        self.loading = True
        self.refresh_btn.configure(state="disabled")
        self.status.configure(text=t("dh_raid_downloading"))
        self.dl = ("download", 0, 0)
        self.render_detail()

        def work():
            try:
                amdraid.download(lambda step, done=0, total=0: self.events.put(("dl", (step, done, total))))
            except Exception as ex:          # nothing is installed unless every check passed
                self.events.put(("failed", t("dh_raid_failed", err=ex)))
                return
            try:
                self.events.put(("done", self.with_members(data.collect())))
            except Exception as ex:
                self.events.put(("failed", str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def disk(self, key):
        return next((x for x in self.disks if x["id"] == key), None)

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "dl":
                    self.show_download(*value)
                    continue
                self.dl = None
                self.loading = False
                self.refresh_btn.configure(state="normal")
                if kind == "done":
                    self.disks = value
                    self.results = {d["id"]: verdict.assess(d) for d in value}
                    if self.selected not in self.results:
                        self.selected = value[0]["id"] if value else None
                    if self.pending_key:
                        d = next((x for x in value if amdraid.disk_key(x) == self.pending_key), None)
                        self.selected = d["id"] if d else self.selected
                        self.pending_key = None
                    self.status.configure(text=" " if value else t("dh_none"))
                else:
                    self.error = value
                    self.status.configure(text=t("dh_failed", err=value.splitlines()[0] if value else "?"))
                self.render()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self.poll)

    def show_download(self, step, done, total):
        self.dl = (step, done, total)
        bar, label = getattr(self, "dl_bar", None), getattr(self, "dl_label", None)
        if bar is None or not bar.winfo_exists():
            return
        if step == "download":
            bar.set(done / total if total else 0)
            label.configure(text=t("dh_dl_download", done=human_size(done), total=human_size(total) if total else "?"))
        else:
            bar.set(1)
            label.configure(text=t("dh_dl_" + step))

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
        self.live_row = ctk.CTkFrame(root, fg_color=BG)
        self.live_row.pack(fill="x", pady=(0, 10))
        self.render_live_row()
        body = ctk.CTkFrame(root, fg_color=BG)
        body.pack(fill="both", expand=True)
        self.listf = ctk.CTkScrollableFrame(body, fg_color=BG, width=LIST_WIDTH, scrollbar_button_color=BORDER)
        self.listf.pack(side="left", fill="y", padx=(0, 12))
        self.detail = ctk.CTkScrollableFrame(body, fg_color=BG, scrollbar_button_color=BORDER)
        self.detail.pack(side="left", fill="both", expand=True)
        self.shown, self.items = None, {}
        if self.disks:
            self.render()

    def relabel(self):
        self.build()
        self.status.configure(text=t("dh_loading") if self.loading else " ")

    # -- next to the clock ----------------------------------------------------------------------
    def render_live_row(self):
        """Two lines, so nothing is pushed out when the window is narrow: live monitoring on the first,
        the clock icons (colours, refresh interval) on the second."""
        row = self.live_row
        for w in row.winfo_children():
            w.destroy()
        line1 = ctk.CTkFrame(row, fg_color="transparent")
        line1.pack(fill="x")
        line2 = ctk.CTkFrame(row, fg_color="transparent")
        line2.pack(fill="x", pady=(6, 0))
        on = livemode.enabled()
        ctk.CTkLabel(line1, text=t("live_on") if on else t("live_off"), font=("Segoe UI Semibold", 12),
                     text_color=ui.GOOD if on else MUTED, anchor="w").pack(side="left")
        if not livemode.supported():
            ctk.CTkLabel(line1, text="  " + t("live_source_only"), font=("Segoe UI", 11), text_color=MUTED).pack(side="left")
        elif on:
            self.autostart_var = tk.BooleanVar(value=livemode.autostart())
            ctk.CTkCheckBox(line1, text=t("live_autostart"), variable=self.autostart_var, command=self.toggle_autostart,
                            font=("Segoe UI", 12), text_color=TEXT, checkbox_width=18, checkbox_height=18,
                            border_width=2, fg_color=ui.ACCENT, border_color=MUTED).pack(side="left", padx=(16, 0))
            ui.button(line1, t("live_turn_off"), self.turn_live_off, 110).pack(side="left", padx=(12, 0))
        else:
            ui.button(line1, t("live_turn_on"), lambda: self.ask_live(), 170).pack(side="left", padx=(12, 0))
        ui.button(line2, t("tc_button"), self.open_colors, 130).pack(side="left")
        ctk.CTkLabel(line2, text=t("live_interval"), font=("Segoe UI", 12), text_color=MUTED).pack(side="left", padx=(16, 8))
        seg = ctk.CTkSegmentedButton(line2, values=[t("live_seconds", n=n) for n in monitor.INTERVALS],
                                     command=self.set_interval, font=("Segoe UI", 11), height=26,
                                     selected_color=ui.ACCENT, unselected_color=CARD)
        seg.set(t("live_seconds", n=monitor.interval()))
        seg.pack(side="left")

    def ask_live(self):
        """One-time consent for the permanent administrator mode (and starting with Windows)."""
        win = ctk.CTkToplevel(self, fg_color=BG)
        win.title(t("live_title"))
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        ctk.CTkLabel(win, text=t("live_title"), font=("Segoe UI Semibold", 18), text_color=TEXT, anchor="w").pack(
            fill="x", padx=22, pady=(18, 6))
        ctk.CTkLabel(win, text=t("live_body"), font=("Segoe UI", 12), text_color=TEXT, anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=22)
        auto = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(win, text=t("live_autostart_long"), variable=auto, font=("Segoe UI", 12), text_color=TEXT,
                        checkbox_width=18, checkbox_height=18, border_width=2, fg_color=ui.ACCENT,
                        border_color=MUTED).pack(fill="x", padx=22, pady=(14, 4))
        ctk.CTkLabel(win, text=t("live_note"), font=("Segoe UI", 11), text_color=MUTED, anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=22)
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(16, 18))
        result = {"ok": False}

        def allow():
            try:
                livemode.enable(start_with_windows=auto.get())
                result["ok"] = True
            except Exception as ex:             # schtasks refused: say why, change nothing
                messagebox.showerror(t("live_title"), t("live_failed", err=ex), parent=win)
            win.destroy()
        ui.button(row, t("live_allow"), allow, 150, primary=True).pack(side="left")
        ui.button(row, t("live_not_now"), win.destroy, 140).pack(side="right")
        win.update_idletasks()
        top = self.winfo_toplevel()
        win.geometry("+%d+%d" % (top.winfo_rootx() + (top.winfo_width() - win.winfo_width()) // 2,
                                 top.winfo_rooty() + (top.winfo_height() - win.winfo_height()) // 3))
        self.wait_window(win)
        self.render_live_row()
        return result["ok"]

    def open_colors(self):
        """Tile and digit colour of the clock icons, for each level (ideal / warm / risky)."""
        from tkinter import colorchooser
        from .. import art
        win = ctk.CTkToplevel(self, fg_color=BG)
        win.title(t("tc_title"))
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())
        ctk.CTkLabel(win, text=t("tc_title"), font=("Segoe UI Semibold", 18), text_color=TEXT, anchor="w").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(win, text=t("tc_hint"), font=("Segoe UI", 11), text_color=MUTED, anchor="w", justify="left",
                     wraplength=440).grid(row=1, column=0, columnspan=4, sticky="w", padx=22, pady=(0, 12))
        samples = {"good": 38, "warning": 62, "bad": 74}
        widgets = {}

        def refresh():
            palette = monitor.colors()
            for level, (preview, bg_btn, fg_btn) in widgets.items():
                img = art.temp_icon(samples[level], level, size=64, colors=palette)
                preview.configure(image=ctk.CTkImage(light_image=img, dark_image=img, size=(40, 40)))
                bg, fg = palette[level]
                bg_btn.configure(fg_color=bg, hover_color=bg)
                fg_btn.configure(fg_color=fg, hover_color=fg)
            shell = self.winfo_toplevel()
            if hasattr(shell, "tray_changed"):
                shell.tray_changed()

        def pick(level, part):
            current = monitor.colors()[level][0 if part == "bg" else 1]
            got = colorchooser.askcolor(color=current, parent=win, title=t("tc_" + level) + " - " + t("tc_" + part))
            if got and got[1]:
                monitor.set_color(level, part, got[1])
                refresh()

        for i, level in enumerate(monitor.LEVELS):
            r = 2 + i
            ctk.CTkLabel(win, text=t("tc_" + level), font=("Segoe UI Semibold", 13), text_color=TEXT, anchor="w",
                         width=150).grid(row=r, column=0, sticky="w", padx=(22, 8), pady=6)
            preview = ctk.CTkLabel(win, text="")
            preview.grid(row=r, column=1, padx=8)
            box = ctk.CTkFrame(win, fg_color="transparent")
            box.grid(row=r, column=2, sticky="w", padx=(8, 22))
            parts = []
            for part in ("bg", "fg"):
                cell = ctk.CTkFrame(box, fg_color="transparent")
                cell.pack(side="left", padx=(0, 14))
                swatch = ctk.CTkButton(cell, text="", width=34, height=26, corner_radius=6, border_width=1,
                                       border_color=BORDER, command=lambda lv=level, p=part: pick(lv, p))
                swatch.pack(side="left")
                ctk.CTkLabel(cell, text=t("tc_" + part), font=("Segoe UI", 12), text_color=TEXT).pack(side="left", padx=(6, 0))
                parts.append(swatch)
            widgets[level] = (preview, parts[0], parts[1])
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.grid(row=6, column=0, columnspan=4, sticky="ew", padx=22, pady=(14, 18))
        ui.button(row, t("tc_reset"), lambda: (monitor.reset_colors(), refresh()), 160).pack(side="left")
        ui.button(row, t("tc_close"), win.destroy, 110, primary=True).pack(side="right")
        refresh()
        win.update_idletasks()
        top = self.winfo_toplevel()
        win.geometry("+%d+%d" % (top.winfo_rootx() + (top.winfo_width() - win.winfo_width()) // 2,
                                 top.winfo_rooty() + (top.winfo_height() - win.winfo_height()) // 3))
        win.grab_set()

    def set_interval(self, label):
        for n in monitor.INTERVALS:
            if label == t("live_seconds", n=n):
                settings.put("tray_interval", n)
        shell = self.winfo_toplevel()
        if hasattr(shell, "tray_changed"):
            shell.tray_changed()

    def toggle_autostart(self):
        try:
            livemode.enable(start_with_windows=self.autostart_var.get())
        except Exception as ex:
            messagebox.showerror(t("live_title"), t("live_failed", err=ex))
        self.render_live_row()

    def turn_live_off(self):
        if not messagebox.askyesno(t("live_title"), t("live_off_ask")):
            return
        try:
            livemode.disable()
        except Exception as ex:
            messagebox.showerror(t("live_title"), t("live_failed", err=ex))
        self.render_live_row()

    def toggle_tray(self, key, var):
        keys = monitor.selected()
        d = next((x for x in self.disks if amdraid.disk_key(x) == key), None)
        if d is not None and d.get("members"):
            # ticking the array watches every disk inside it (the array itself has no temperature)
            member_keys = [amdraid.disk_key(m) for m in d["members"]]
            if var.get():
                if not keys and livemode.supported() and not livemode.enabled():
                    self.ask_live()
                keys += [k for k in member_keys if k not in keys]
            else:
                keys = [k for k in keys if k not in member_keys]
            monitor.set_selected(keys)
            self.after_tray_change()
            return
        if var.get() and d is not None and amdraid.is_amd_raid(d) and not d.get("members"):
            # the array itself reports no temperature: its disks can be watched once AMD_RC2t7 is set up
            var.set(False)
            if amdraid.supported() and not amdraid.installed():
                self.select(d["id"])
                self.get_library(intro=t("dh_tray_raid_need"))
            else:
                messagebox.showinfo(t("dh_raid_title"), t("dh_tray_raid_source") if not amdraid.supported()
                                    else t("dh_tray_raid_members"))
            return
        if var.get() and d is not None and self.results.get(d["id"], {}).get("figures", {}).get("temperature") is None:
            why = t("dh_tray_no_temp_usb") if d.get("bus") == "USB" else t("dh_tray_no_temp")
            if not messagebox.askyesno(t("live_title"), why + "\n\n" + t("dh_tray_no_temp_ask")):
                var.set(False)
                return
        if var.get():
            if not keys and livemode.supported() and not livemode.enabled():
                self.ask_live()                 # first disk: offer the permanent mode once (optional)
            keys.append(key)
        else:
            keys = [k for k in keys if k != key]
        monitor.set_selected(keys)
        self.after_tray_change()

    def after_tray_change(self):
        """Tick boxes of arrays and members depend on each other: redraw the list, and tell the window."""
        for w in self.listf.winfo_children():
            w.destroy()
        self.items = {}
        for disk in self.disks:
            self.disk_item(disk)
        shell = self.winfo_toplevel()
        if hasattr(shell, "tray_changed"):
            shell.tray_changed()

    @staticmethod
    def level_text(d, res):
        pct = verdict.health_percent(d, res)
        level = t("dh_level_" + res["level"])
        return level if pct is None else t("dh_level_pct", level=level, pct=pct)

    def select_key(self, key):
        """Select the disk a clock icon stands for (now, or once the list has been read)."""
        d = next((x for x in self.disks if amdraid.disk_key(x) == key), None)
        if d is None:
            self.pending_key = key
            return
        self.select(d["id"])

    def render(self):
        for w in self.listf.winfo_children():
            w.destroy()
        self.items = {}
        for d in self.disks:
            self.disk_item(d)
        self.render_detail()

    def select(self, key):
        """Another disk was clicked: recolour two list entries, swap the detail (no full redraw)."""
        if key == self.selected:
            return
        for k, sel in ((self.selected, False), (key, True)):
            item = self.items.get(k)
            if item is not None:
                item.configure(fg_color=CARD_HOVER if sel else CARD, border_color=ui.ACCENT if sel else BORDER)
        self.selected = key
        self.render_detail()

    def disk_item(self, d):
        res = self.results[d["id"]]
        color = LEVEL[res["level"]]
        sel = d["id"] == self.selected
        member = "member_of" in d
        item = ctk.CTkFrame(self.listf, fg_color=CARD_HOVER if sel else CARD, corner_radius=10, border_width=1,
                            border_color=ui.ACCENT if sel else BORDER)
        item.pack(fill="x", pady=(0, 8), padx=(22, 0) if member else 0)
        self.items[d["id"]] = item
        stripe = ctk.CTkFrame(item, fg_color=color, width=5, height=10, corner_radius=3)
        stripe.pack(side="left", fill="y", padx=(8, 0), pady=10)
        key = amdraid.disk_key(d)
        chosen = monitor.selected()
        if d.get("members"):                    # an array stands for all the disks in it
            var = tk.BooleanVar(value=all(amdraid.disk_key(m) in chosen for m in d["members"]))
        else:
            var = tk.BooleanVar(value=key in chosen)
        side = ctk.CTkFrame(item, fg_color="transparent", width=64)
        side.pack(side="right", fill="y", padx=(0, 8), pady=8)
        temp = res["figures"].get("temperature")
        ctk.CTkLabel(side, text="%d °C" % temp if temp is not None else "– °C", font=("Segoe UI Semibold", 12),
                     text_color=LEVEL[monitor.temp_level(d, temp)] if temp is not None else MUTED).pack()
        ctk.CTkCheckBox(side, text="", variable=var, width=24, checkbox_width=18, checkbox_height=18, border_width=2,
                        fg_color=ui.ACCENT, border_color=MUTED,
                        command=lambda k=key, v=var: self.toggle_tray(k, v)).pack(pady=(2, 0))
        ctk.CTkLabel(side, text=t("dh_tray"), font=("Segoe UI", 9), text_color=MUTED, justify="center",
                     wraplength=64).pack()
        box = ctk.CTkFrame(item, fg_color="transparent")
        box.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        ctk.CTkLabel(box, text=d["name"] or "Disk %d" % d["number"], font=("Segoe UI Semibold", 13), text_color=TEXT,
                     anchor="w", wraplength=LIST_WIDTH - 60, justify="left").pack(fill="x")
        bits = [t("dh_member_of", n=d["number"], i=d["member_index"] + 1) if member else "Disk %d" % d["number"],
                human_size(d["size"]), d.get("bus") or ""]
        if d.get("system") and not member:
            bits.append(t("dh_system"))
        ctk.CTkLabel(box, text=" · ".join(b for b in bits if b), font=("Segoe UI", 11), text_color=MUTED,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(box, text=self.level_text(d, res), font=("Segoe UI Semibold", 12), text_color=color,
                     anchor="w").pack(fill="x", pady=(2, 0))

        def pick(e, n=d["id"]):
            self.select(n)
        for w in (item, stripe, box) + tuple(box.winfo_children()):
            w.bind("<Button-1>", pick)

    def render_detail(self):
        """Build the new detail in a frame that is not shown yet, then swap it in at once."""
        old = getattr(self, "shown", None)
        self.target = ctk.CTkFrame(self.detail, fg_color="transparent")
        d = self.disk(self.selected)
        if d is not None:
            self.fill_detail(d)
        self.target.pack(fill="both", expand=True)
        self.shown = self.target
        if old is not None:
            old.destroy()
        self.detail._parent_canvas.yview_moveto(0)

    def fill_detail(self, d):
        res = self.results[d["id"]]
        self.verdict_card(d, res)
        if amdraid.is_amd_raid(d) and not d.get("members"):
            self.raid_card(d)
        if not d.get("members"):
            self.tiles(res["figures"], res, nvme=bool(d.get("nvme")))
        self.info_card(d)
        if not d.get("nvme") and not d.get("members"):
            self.smart_card(d)

    def raid_card(self, d):
        c = ui.card(self.target, t("dh_raid_title"))
        c.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(c, text=t("dh_raid_body"), font=("Segoe UI", 12), text_color=TEXT, anchor="w", justify="left",
                     wraplength=700).pack(fill="x", padx=18)
        err = d.get("raid_error")
        if err:
            ctk.CTkLabel(c, text=t("dh_raid_read_failed", err=err), font=("Segoe UI", 12), text_color=ui.WARN,
                         anchor="w", justify="left", wraplength=700).pack(fill="x", padx=18, pady=(8, 0))
        ctk.CTkLabel(c, text=t("dh_raid_disclaimer", by=amdraid.SIGNER, site=amdraid.INFO_URL), font=("Segoe UI", 11),
                     text_color=MUTED, anchor="w", justify="left", wraplength=700).pack(fill="x", padx=18, pady=(8, 0))
        if self.dl:
            box = ctk.CTkFrame(c, fg_color="transparent")
            box.pack(fill="x", padx=18, pady=(10, 14))
            self.dl_label = ctk.CTkLabel(box, text=" ", font=("Segoe UI", 12), text_color=TEXT, anchor="w")
            self.dl_label.pack(fill="x")
            self.dl_bar = ctk.CTkProgressBar(box, height=10, fg_color=BORDER, progress_color=ui.ACCENT, corner_radius=5)
            self.dl_bar.pack(fill="x", pady=(4, 0))
            self.show_download(*self.dl)
            return
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(10, 14))
        if not amdraid.supported():
            ctk.CTkLabel(row, text=t("dh_raid_source_only"), font=("Segoe UI", 12), text_color=MUTED,
                         anchor="w").pack(side="left")
        elif not amdraid.installed():
            ui.button(row, t("dh_raid_get"), self.get_library, 230, primary=True).pack(side="left")
        ui.button(row, t("dh_raid_license"), lambda: webbrowser.open(amdraid.LICENSE_URL), 90).pack(
            side="left", padx=(8, 0))

    def verdict_card(self, d, res):
        color = LEVEL[res["level"]]
        c = ui.card(self.target)
        c.pack(fill="x", pady=(0, 10))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkFrame(row, fg_color=color, width=8, height=56, corner_radius=4).pack(side="left", fill="y", padx=(0, 14))
        txt = ctk.CTkFrame(row, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(txt, text=self.level_text(d, res), font=("Segoe UI Semibold", 24), text_color=color,
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

    def tiles(self, f, res, nvme=False):
        c = ctk.CTkFrame(self.target, fg_color="transparent")
        c.pack(fill="x", pady=(0, 10))
        temp = f["temperature"]
        if nvme:
            items = self.nvme_tiles(f, res)
        else:
            items = self.ata_tiles(f, res)
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

    def nvme_tiles(self, f, res):
        temp = f["temperature"]
        return [
            ("dh_t_temp", None if temp is None else "%d °C" % temp,
             self.reason_color(res, ("too_hot", "hot", "nvme_temp_warn"))),
            ("dh_t_hours", hours_text(f["hours"]), None),
            ("dh_t_wear", None if f["wear"] is None else t("dh_pct", n=f["wear"]), self.reason_color(res, ("worn", "wearing"))),
            ("dh_t_spare", None if f["spare"] is None else t("dh_pct", n=f["spare"]), self.reason_color(res, ("nvme_spare_low",))),
            ("dh_t_written", None if f["written"] is None else human_size(f["written"]), None),
            ("dh_t_media", None if f["media_errors"] is None else count(f["media_errors"]),
             self.reason_color(res, ("nvme_media_errors",))),
            ("dh_t_cycles", None if f["power_cycles"] is None else count(f["power_cycles"]), None),
            ("dh_t_unsafe", None if f["unsafe"] is None else count(f["unsafe"]), None),
        ]

    def ata_tiles(self, f, res):
        temp = f["temperature"]
        return [
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

    @staticmethod
    def reason_color(res, keys):
        levels = [lv for lv, key, _ in res["reasons"] if key in keys]
        return LEVEL[max(levels, key=verdict.ORDER.get)] if levels else None

    def info_card(self, d):
        c = ui.card(self.target, t("dh_info"))
        c.pack(fill="x", pady=(0, 10))
        rows = [("dh_model", d.get("name")), ("dh_serial", d.get("serial")), ("dh_bus", d.get("bus")),
                ("dh_media", media_text(d)), ("dh_capacity", human_size(d["size"]) if d.get("size") else ""),
                ("dh_firmware", d.get("firmware")), ("dh_link", d.get("speed")), ("dh_status", " · ".join(state_text(x) for x in (d.get("health"), d.get("status")) if x))]
        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(fill="x", padx=18, pady=(0, 12))
        for i, (key, value) in enumerate(r for r in rows if r[1]):
            ctk.CTkLabel(grid, text=t(key), font=("Segoe UI", 12), text_color=MUTED, anchor="w").grid(
                row=i, column=0, sticky="w", padx=(0, 24), pady=1)
            ctk.CTkLabel(grid, text=value, font=("Segoe UI Semibold", 12), text_color=TEXT, anchor="w").grid(
                row=i, column=1, sticky="w", pady=1)
        if "member_of" in d:
            ctk.CTkLabel(c, text=t("dh_used_by", v=amdraid.VERSION, by=amdraid.SIGNER, site=amdraid.INFO_URL),
                         font=("Segoe UI", 11), text_color=MUTED, justify="left", wraplength=700,
                         anchor="w").pack(fill="x", padx=18, pady=(0, 12))

    def smart_card(self, d):
        c = ui.card(self.target, t("dh_smart"))
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
            d = self.disk(self.selected)
            if view is not None and d is not None:
                view.select_disk(d["number"])         # a RAID member: its array, the disk Windows knows
