"""Shared building blocks for Benchwise tools.

A tool is a ``ToolView`` subclass: it fills ``self.body`` in ``fill()`` and may run slow work with
``self.run(work, done)``: ``work()`` runs on a thread, ``done(result_or_exception)`` back on the Tk
thread.  ``busy()`` is true while work runs (the window then refuses to switch language or restart).
Texts are registered with ``texts({...})`` at import time, next to the tool that uses them.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from recoverytool import i18n
from recoverytool.i18n import t

from . import ui
from .ui import BG, BORDER, CARD, MUTED, TEXT

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def texts(table):
    i18n.STRINGS.update(table)


def powershell(script, timeout=120):
    """Run a PowerShell script; returns its standard output (UTF-8).  Raises RuntimeError on failure."""
    full = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n$ErrorActionPreference = 'SilentlyContinue'\n" + script
    p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", full],
                       capture_output=True, timeout=timeout, creationflags=_NO_WINDOW)
    out = p.stdout.decode("utf-8", "replace").strip()
    if p.returncode != 0 and not out:
        raise RuntimeError(p.stderr.decode("utf-8", "replace").strip() or "PowerShell exit %d" % p.returncode)
    return out


def powershell_json(script, timeout=120):
    out = powershell(script, timeout)
    if not out:
        return []
    data = json.loads(out)
    return data


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def run_command(args, timeout=600):
    """A program's output (text, OEM code page tolerated)."""
    p = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW)
    raw = p.stdout + p.stderr
    for enc in ("utf-8", "cp857", "cp850", "mbcs"):
        try:
            return p.returncode, raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return p.returncode, raw.decode("utf-8", "replace")


class ToolView(ctk.CTkFrame):
    title_key = ""          # e.g. "tool_sysinfo"

    def __init__(self, master):
        super().__init__(master, fg_color=BG)
        self.events = queue.Queue()
        self.jobs = 0
        self.build()
        self.after(100, self._poll)

    # -- frame ----------------------------------------------------------------------------------
    def build(self):
        for w in self.winfo_children():
            w.destroy()
        root = ctk.CTkFrame(self, fg_color=BG)
        root.pack(fill="both", expand=True, padx=22, pady=(4, 18))
        self.head = ui.tool_header(root, t(self.title_key), t(self.title_key + "_d"))
        self.status = ctk.CTkLabel(self.head, text=" ", font=("Segoe UI", 11), text_color=MUTED)
        self.status.pack(side="right", padx=12)
        self.body = ctk.CTkFrame(root, fg_color=BG)
        self.body.pack(fill="both", expand=True)
        self.fill()

    def fill(self):
        raise NotImplementedError

    def relabel(self):
        self.build()

    def busy(self):
        return self.jobs > 0

    def set_status(self, text):
        self.status.configure(text=text or " ")

    # -- background work ------------------------------------------------------------------------
    def run(self, work, done, status=None):
        self.jobs += 1
        if status:
            self.set_status(status)

        def thread():
            try:
                result = work()
            except Exception as ex:      # handed to done(); the tool shows it
                result = ex
            self.events.put(("done", done, result))
        threading.Thread(target=thread, daemon=True).start()

    def post(self, fn, *args):
        """Call ``fn(*args)`` on the Tk thread (from a worker thread)."""
        self.events.put(("post", fn, args))

    def _poll(self):
        try:
            while True:
                kind, fn, value = self.events.get_nowait()
                try:
                    if kind == "done":
                        self.jobs = max(0, self.jobs - 1)
                        self.set_status(" ")
                        fn(value)
                    else:
                        fn(*value)
                except Exception as ex:          # a bug in a callback must not stop the poll loop
                    self.set_status(str(ex))
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll)


# -- widgets ------------------------------------------------------------------------------------
def card(parent, title=None, **pack):
    c = ui.card(parent, title)
    c.pack(fill=pack.pop("fill", "x"), expand=pack.pop("expand", False), pady=pack.pop("pady", (0, 10)), **pack)
    return c


def kv_grid(parent, rows, padx=18, pady=(0, 12)):
    """Label / value rows; ``rows`` = [(label, value)], empty values skipped."""
    grid = ctk.CTkFrame(parent, fg_color="transparent")
    grid.pack(fill="x", padx=padx, pady=pady)
    i = 0
    for label, value in rows:
        if value in (None, ""):
            continue
        ctk.CTkLabel(grid, text=label, font=("Segoe UI", 12), text_color=MUTED, anchor="w").grid(
            row=i, column=0, sticky="nw", padx=(0, 24), pady=1)
        ctk.CTkLabel(grid, text=str(value), font=("Segoe UI Semibold", 12), text_color=TEXT, anchor="w",
                     justify="left", wraplength=620).grid(row=i, column=1, sticky="w", pady=1)
        i += 1
    return grid


_style_done = set()


def table(parent, columns, height=8, stretch=None):
    """A dark ttk.Treeview with headings; ``columns`` = [(id, heading, width)]."""
    top = parent.winfo_toplevel()
    if id(top) not in _style_done:
        s = ttk.Style(top)
        s.theme_use("default")          # the Windows themes ignore heading colours (white headings)
        s.configure("Tool.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=26,
                    borderwidth=0, font=("Segoe UI", 10))
        s.configure("Tool.Treeview.Heading", background=BORDER, foreground=MUTED, relief="flat",
                    font=("Segoe UI", 9, "bold"), padding=(6, 5))
        s.map("Tool.Treeview", background=[("selected", "#22304d")])
        s.layout("Tool.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        _style_done.add(id(top))
    holder = ctk.CTkFrame(parent, fg_color=CARD)
    tree = ttk.Treeview(holder, columns=[c[0] for c in columns], show="headings", style="Tool.Treeview",
                        height=height, selectmode="browse")
    for cid, heading, width in columns:
        tree.heading(cid, text=heading, anchor="w")
        tree.column(cid, width=width, stretch=(cid == stretch), anchor="w")
    bar = ctk.CTkScrollbar(holder, command=tree.yview, fg_color=CARD, button_color=BORDER, width=12)
    tree.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)
    tree.tag_configure("bad", foreground=ui.BAD)
    tree.tag_configure("warn", foreground=ui.WARN)
    tree.tag_configure("good", foreground=ui.GOOD)
    tree.tag_configure("muted", foreground=MUTED)
    return holder, tree


def text_box(parent, height=10):
    box = ctk.CTkTextbox(parent, fg_color=CARD, text_color=TEXT, font=("Consolas", 11), corner_radius=10,
                         wrap="word", height=height * 18, border_width=0)
    return box


def note(parent, text, color=MUTED, padx=18, pady=(0, 10)):
    lab = ctk.CTkLabel(parent, text=text, font=("Segoe UI", 12), text_color=color, anchor="w", justify="left",
                       wraplength=720)
    lab.pack(fill="x", padx=padx, pady=pady)
    return lab


def scroll_body(view):
    """Replace the tool body by a scrollable one (tools with long pages)."""
    sf = ctk.CTkScrollableFrame(view.body, fg_color=BG, scrollbar_button_color=BORDER)
    sf.pack(fill="both", expand=True)
    return sf


def human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0


def confirm(title, body):
    from tkinter import messagebox
    return messagebox.askyesno(title, body, icon="warning")


def restore_point(description="Benchwise"):
    """Ask Windows for a restore point (may be refused: disabled, or one made in the last 24 h)."""
    try:
        powershell("Checkpoint-Computer -Description '%s' -RestorePointType MODIFY_SETTINGS" % description, timeout=300)
        return True
    except Exception:
        return False
