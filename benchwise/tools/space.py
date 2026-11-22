"""Cleanup & Privacy > Space Analyzer: which folders take up the room on a drive.  The folder sizes are
measured once (links and junctions are not followed, so nothing is counted twice); moving into a
folder and back is then instant.  The 50 largest files are listed too."""

from __future__ import annotations

import heapq
import os
import stat
import string
import subprocess
from tkinter import filedialog

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, human, note, table, texts

texts({
    "sp_how": ("Choose a drive or a folder. Measuring a whole drive can take a few minutes.",
               "Bir sürücü veya klasör seçin. Bütün bir sürücüyü ölçmek birkaç dakika sürebilir."),
    "sp_folder": ("Folder…", "Klasör…"),
    "sp_measuring": ("Measuring… {n} files · {size}", "Ölçülüyor… {n} dosya · {size}"),
    "sp_up": ("Up", "Yukarı"),
    "sp_open": ("Show in Explorer", "Gezgin'de göster"),
    "sp_col_name": ("Name", "Ad"),
    "sp_col_size": ("Size", "Boyut"),
    "sp_col_share": ("Share", "Pay"),
    "sp_col_files": ("Files", "Dosya"),
    "sp_largest": ("Largest files", "En büyük dosyalar"),
    "sp_total": ("{path}: {size} in {n} files", "{path}: {n} dosyada {size}"),
    "sp_files_here": ("(files directly in this folder)", "(doğrudan bu klasördeki dosyalar)"),
    "sp_hint": ("Double-click a folder to look inside.", "İçine bakmak için bir klasöre çift tıklayın."),
})


class Node:
    __slots__ = ("path", "size", "files", "children", "own", "parent")

    def __init__(self, path, parent=None):
        self.path, self.parent = path, parent
        self.size = self.files = self.own = 0
        self.children = []


def measure(root, progress):
    """A tree of folder sizes below ``root`` and the 50 largest files."""
    top = Node(root)
    largest = []
    count = [0, 0]
    stack = [top]
    order = []
    while stack:
        node = stack.pop()
        order.append(node)
        try:
            with os.scandir(node.path) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        continue
                    if stat.S_ISDIR(st.st_mode):
                        child = Node(e.path, node)
                        node.children.append(child)
                        stack.append(child)
                    else:
                        node.own += st.st_size
                        node.files += 1
                        count[0] += 1
                        count[1] += st.st_size
                        if len(largest) < 50:
                            heapq.heappush(largest, (st.st_size, e.path))
                        elif st.st_size > largest[0][0]:
                            heapq.heapreplace(largest, (st.st_size, e.path))
                        if count[0] % 2000 == 0:
                            progress(count[0], count[1])
        except OSError:
            continue
    for node in reversed(order):                 # children before parents: add sizes upwards
        node.size += node.own
        if node.parent:
            node.parent.size += node.size
            node.parent.files += node.files
    return top, sorted(largest, reverse=True)


def drives():
    import ctypes
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    return ["%s:\\" % c for i, c in enumerate(string.ascii_uppercase) if mask & (1 << i)]


class View(ToolView):
    title_key = "tool_space"

    def fill(self):
        self.root = self.current = None
        self.largest = []
        c = card(self.body, t("tool_space"))
        note(c, t("sp_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 12))
        for d in drives():
            ui.button(row, d.rstrip("\\"), lambda d=d: self.start(d), 56).pack(side="left", padx=(0, 6))
        ui.button(row, t("sp_folder"), self.pick, 110).pack(side="left", padx=(6, 0))
        self.info = ctk.CTkLabel(row, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED)
        self.info.pack(side="left", padx=14)
        nav = ctk.CTkFrame(self.body, fg_color="transparent")
        nav.pack(fill="x", pady=(0, 6))
        self.up_btn = ui.button(nav, "↑ " + t("sp_up"), self.go_up, 100)
        self.up_btn.pack(side="left")
        ui.button(nav, t("sp_open"), self.open_selected, 150).pack(side="left", padx=8)
        self.where = ctk.CTkLabel(nav, text=" ", font=("Segoe UI Semibold", 12), text_color=ui.TEXT, anchor="w")
        self.where.pack(side="left", padx=8)
        holder, self.tree = table(self.body, [("name", t("sp_col_name"), 420), ("size", t("sp_col_size"), 100),
                                              ("share", t("sp_col_share"), 220), ("files", t("sp_col_files"), 90)],
                                  height=12, stretch="name")
        holder.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self.enter)
        note(self.body, t("sp_hint"), padx=2, pady=(4, 6))
        holder2, self.big = table(self.body, [("file", t("sp_largest"), 620), ("size", t("sp_col_size"), 100)],
                                  height=6, stretch="file")
        holder2.pack(fill="x")
        self.rows = {}

    def pick(self):
        folder = filedialog.askdirectory()
        if folder:
            self.start(os.path.normpath(folder))

    def start(self, path):
        if self.busy():
            return
        self.info.configure(text=t("sp_measuring", n=0, size="0 B"))
        self.run(lambda: measure(path, lambda n, s: self.post(
            self.info.configure, {"text": t("sp_measuring", n="{:,}".format(n).replace(",", " "), size=human(s))})),
            self.measured)

    def measured(self, res):
        if isinstance(res, Exception):
            self.info.configure(text=str(res), text_color=ui.BAD)
            return
        self.root, self.largest = res
        self.info.configure(text=t("sp_total", path=self.root.path, size=human(self.root.size),
                                   n="{:,}".format(self.root.files).replace(",", " ")), text_color=ui.TEXT)
        for item in self.big.get_children():
            self.big.delete(item)
        for size, path in self.largest:
            self.big.insert("", "end", values=(path, human(size)))
        self.show(self.root)

    def show(self, node):
        self.current = node
        self.where.configure(text=node.path)
        self.up_btn.configure(state="normal" if node.parent else "disabled")
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.rows = {}
        total = max(node.size, 1)
        entries = [(c.size, os.path.basename(c.path) or c.path, c) for c in node.children]
        if node.own:
            entries.append((node.own, t("sp_files_here"), None))
        for size, name, child in sorted(entries, key=lambda x: -x[0]):
            share = size / total
            bar = "█" * int(round(share * 20)) + "  " + "%.1f %%" % (share * 100)
            iid = self.tree.insert("", "end", values=(name, human(size), bar, child.files if child else node.files - sum(
                c.files for c in node.children)))
            self.rows[iid] = child

    def enter(self, _e=None):
        sel = self.tree.selection()
        child = self.rows.get(sel[0]) if sel else None
        if child is not None and child.children or (child is not None and child.files):
            self.show(child)

    def go_up(self):
        if self.current and self.current.parent:
            self.show(self.current.parent)

    def open_selected(self):
        sel = self.tree.selection()
        target = self.rows.get(sel[0]).path if sel and self.rows.get(sel[0]) else (self.current.path if self.current else None)
        if target:
            subprocess.Popen(["explorer.exe", target])
