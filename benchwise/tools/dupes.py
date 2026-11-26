"""Cleanup & Privacy > Duplicate Finder: files with identical content in a folder.  Grouped by size, then
by a hash of the first 64 KB, then by a full SHA-256, so only byte-identical files are reported.
Removing sends files to the Recycle Bin (can be undone); nothing is selected by default."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import hashlib
import os
import stat
import subprocess
import time
from collections import defaultdict
from tkinter import filedialog

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, confirm, human, icon_button, note, texts

texts({
    "dp_how": ("Choose a folder (for example Pictures or Downloads). Only files with exactly the same content are "
               "shown. Removed files go to the Recycle Bin.",
               "Bir klasör seçin (örneğin Resimler veya İndirilenler). Yalnızca içeriği birebir aynı olan dosyalar "
               "gösterilir. Kaldırılan dosyalar Geri Dönüşüm Kutusu'na gider."),
    "dp_choose": ("Choose a folder…", "Klasör seç…"),
    "dp_min": ("Smallest file", "En küçük dosya"),
    "dp_scanning": ("Looking… {n} files", "Aranıyor… {n} dosya"),
    "dp_hashing": ("Comparing contents… {done} / {total}", "İçerikler karşılaştırılıyor… {done} / {total}"),
    "dp_none": ("No duplicates found in {folder}.", "{folder} içinde kopya bulunamadı."),
    "dp_summary": ("{groups} groups of duplicates, {waste} could be freed.", "{groups} kopya grubu; {waste} yer açılabilir."),
    "dp_keep_newest": ("Select all but the newest in each group", "Her grupta en yenisi dışındakileri seç"),
    "dp_clear_sel": ("Clear selection", "Seçimi kaldır"),
    "dp_remove": ("Move selected to Recycle Bin", "Seçilenleri Geri Dönüşüm Kutusu'na taşı"),
    "dp_selected": ("{n} selected · {size}", "{n} seçili · {size}"),
    "dp_ask": ("Move {n} files ({size}) to the Recycle Bin?", "{n} dosya ({size}) Geri Dönüşüm Kutusu'na taşınsın mı?"),
    "dp_keep_one": ("Every file of a group was selected; one copy of each group is always kept.",
                    "Bir grubun bütün dosyaları seçilmişti; her gruptan bir kopya her zaman bırakılır."),
    "dp_moved": ("Moved {n} files to the Recycle Bin.", "{n} dosya Geri Dönüşüm Kutusu'na taşındı."),
    "dp_group": ("{n} copies · {size} each", "{n} kopya · her biri {size}"),
    "dp_more": ("… and {n} more groups (the largest are shown)", "… ve {n} grup daha (en büyükler gösteriliyor)"),
    "dp_ask_one": ("Move {name} to the Recycle Bin?\n\n{folder}", "{name} Geri Dönüşüm Kutusu'na taşınsın mı?\n\n{folder}"),
    "dp_last_copy": ("This is the last copy left of this file; it is kept.", "Bu dosyanın kalan son kopyası bu; silinmez."),
    "dp_moved_one": ("{name} was moved to the Recycle Bin.", "{name} Geri Dönüşüm Kutusu'na taşındı."),
})

MAX_GROUPS_SHOWN = 150


def scan(folder, min_size, progress):
    """{sha256: [(path, size, mtime)]} for groups of 2+ identical files."""
    by_size = defaultdict(list)
    seen = 0
    stack = [folder]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        continue
                    if stat.S_ISDIR(st.st_mode):
                        stack.append(e.path)
                    elif st.st_size >= min_size:
                        by_size[st.st_size].append((e.path, st.st_size, st.st_mtime))
                        seen += 1
                        if seen % 500 == 0:
                            progress("scan", seen, 0)
        except OSError:
            continue
    candidates = [g for g in by_size.values() if len(g) > 1]
    total = sum(len(g) for g in candidates)
    done = 0

    def digest(path, limit=None):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            if limit:
                h.update(f.read(limit))
            else:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        return h.hexdigest()

    groups = {}
    for group in candidates:
        by_head = defaultdict(list)
        for item in group:
            try:
                by_head[digest(item[0], 65536)].append(item)
            except OSError:
                pass
            done += 1
            if done % 50 == 0:
                progress("hash", done, total)
        for same_head in by_head.values():
            if len(same_head) < 2:
                continue
            by_full = defaultdict(list)
            for item in same_head:
                try:
                    by_full[digest(item[0]) if item[1] > 65536 else "h" + str(item[1])].append(item)
                except OSError:
                    pass
            for key, items in by_full.items():
                if len(items) > 1:
                    groups[key + str(items[0][1])] = items
    return groups


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [("hwnd", w.HWND), ("wFunc", w.UINT), ("pFrom", w.LPCWSTR), ("pTo", w.LPCWSTR), ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", w.BOOL), ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", w.LPCWSTR)]


def to_recycle_bin(paths):
    """Send files to the Recycle Bin (undoable).  Returns True on success."""
    if not paths:
        return True
    buf = "\0".join(os.path.abspath(p) for p in paths) + "\0\0"
    op = SHFILEOPSTRUCTW(None, 3, buf, None, 0x0040 | 0x0010 | 0x0004 | 0x0400, False, None, None)
    # FO_DELETE with FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0


class View(ToolView):
    title_key = "tool_dupes"

    def fill(self):
        c = card(self.body, t("tool_dupes"))
        note(c, t("dp_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 12))
        self.choose_btn = ui.button(row, t("dp_choose"), self.choose, 150, primary=True)
        self.choose_btn.pack(side="left")
        ctk.CTkLabel(row, text=t("dp_min"), font=("Segoe UI", 12), text_color=ui.TEXT).pack(side="left", padx=(16, 6))
        self.mins = {"100 KB": 100 << 10, "1 MB": 1 << 20, "10 MB": 10 << 20, "100 MB": 100 << 20}
        self.min_seg = ctk.CTkSegmentedButton(row, values=list(self.mins), font=("Segoe UI", 11), height=26,
                                              selected_color=ui.ACCENT, unselected_color=ui.CARD)
        self.min_seg.set("1 MB")
        self.min_seg.pack(side="left")
        self.info = ctk.CTkLabel(row, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED)
        self.info.pack(side="left", padx=14)
        self.results = ctk.CTkScrollableFrame(self.body, fg_color=ui.BG, scrollbar_button_color=ui.BORDER)
        self.results.pack(fill="both", expand=True)
        bar = ctk.CTkFrame(self.body, fg_color="transparent")
        bar.pack(fill="x", pady=(8, 0))
        self.sel_label = ctk.CTkLabel(bar, text=" ", font=("Segoe UI Semibold", 12), text_color=ui.TEXT)
        self.sel_label.pack(side="left")
        self.remove_btn = ui.button(bar, t("dp_remove"), self.remove, 300, primary=True)
        self.remove_btn.pack(side="right")
        ui.button(bar, t("dp_clear_sel"), lambda: self.select(False), 130).pack(side="right", padx=8)
        ui.button(bar, t("dp_keep_newest"), lambda: self.select(True), 280).pack(side="right")
        self.vars, self.groups = {}, {}

    def choose(self):
        start = getattr(self, "folder", None) or os.path.expanduser("~")
        folder = filedialog.askdirectory(title=t("dp_choose"), initialdir=start)    # not the program's own folder
        if not folder:
            return
        self.folder = folder = os.path.normpath(folder)
        self.choose_btn.configure(state="disabled")

        def progress(kind, a, b):
            text = t("dp_scanning", n=a) if kind == "scan" else t("dp_hashing", done=a, total=b)
            self.post(self.info.configure, {"text": text})
        self.run(lambda: scan(folder, self.mins[self.min_seg.get()], progress), self.show)

    def show(self, groups):
        self.choose_btn.configure(state="normal")
        for w_ in self.results.winfo_children():
            w_.destroy()
        self.vars = {}
        if isinstance(groups, Exception):
            self.info.configure(text=str(groups), text_color=ui.BAD)
            return
        self.groups = groups
        if not groups:
            self.info.configure(text=t("dp_none", folder=self.folder), text_color=ui.GOOD)
            self.update_sel()
            return
        ordered = sorted(groups.values(), key=lambda g: -(len(g) - 1) * g[0][1])
        waste = sum((len(g) - 1) * g[0][1] for g in ordered)
        self.info.configure(text=t("dp_summary", groups=len(ordered), waste=human(waste)), text_color=ui.TEXT)
        for g in ordered[:MAX_GROUPS_SHOWN]:
            box = ui.card(self.results)
            box.pack(fill="x", pady=(0, 8), padx=(0, 8))
            ctk.CTkLabel(box, text=t("dp_group", n=len(g), size=human(g[0][1])), font=("Segoe UI Semibold", 12),
                         text_color=ui.TEXT, anchor="w").pack(fill="x", padx=14, pady=(8, 2))
            for path, size, mtime in sorted(g, key=lambda x: -x[2]):
                var = ctk.BooleanVar(value=False)
                self.vars[path] = (var, size, g)
                line = ctk.CTkFrame(box, fg_color="transparent")
                line.pack(fill="x", padx=(14, 8), pady=0)
                ctk.CTkCheckBox(line, text="", variable=var, command=self.update_sel, width=22, checkbox_width=16,
                                checkbox_height=16, border_width=2, fg_color=ui.ACCENT,
                                border_color=ui.MUTED).pack(side="left")
                ctk.CTkLabel(line, text=os.path.basename(path), font=("Segoe UI", 12), text_color=ui.TEXT,
                             anchor="w").pack(side="left")
                where = os.path.basename(os.path.dirname(path)) or os.path.dirname(path)
                ctk.CTkLabel(line, text="   %s   ·   %s" % (time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)), where),
                             font=("Segoe UI", 11), text_color=ui.MUTED, anchor="w").pack(side="left")
                icon_button(line, "trash", lambda p=path: self.remove_one(p), ui.MUTED).pack(side="right")
                icon_button(line, "folder", lambda p=path: reveal(p), ui.MUTED).pack(side="right", padx=(0, 2))
            ctk.CTkFrame(box, fg_color="transparent", height=6).pack()
        if len(ordered) > MAX_GROUPS_SHOWN:
            note(self.results, t("dp_more", n=len(ordered) - MAX_GROUPS_SHOWN))
        self.update_sel()

    def remove_one(self, path):
        group = self.vars[path][2]
        left = [x for x in group if os.path.exists(x[0])]
        if len(left) < 2:
            self.info.configure(text=t("dp_last_copy"), text_color=ui.WARN)
            return
        name = os.path.basename(path)
        if not confirm(t("tool_dupes"), t("dp_ask_one", name=name, folder=os.path.dirname(path))):
            return
        ok = to_recycle_bin([path]) and not os.path.exists(path)
        self.forget({path} if ok else set())
        self.info.configure(text=t("dp_moved_one", name=name) if ok else "SHFileOperation failed",
                            text_color=ui.GOOD if ok else ui.BAD)

    def forget(self, moved):
        """Drop removed files from the groups (a group of one is no longer a duplicate) and redraw."""
        for key in list(self.groups):
            self.groups[key] = [x for x in self.groups[key] if x[0] not in moved]
            if len(self.groups[key]) < 2:
                del self.groups[key]
        info, color = self.info.cget("text"), self.info.cget("text_color")
        self.show(self.groups)
        self.info.configure(text=info, text_color=color)

    def select(self, keep_newest):
        for path, (var, size, group) in self.vars.items():
            newest = max(group, key=lambda x: x[2])[0]
            var.set(keep_newest and path != newest)
        self.update_sel()

    def chosen(self):
        return [(p, s, g) for p, (v, s, g) in self.vars.items() if v.get()]

    def update_sel(self):
        sel = self.chosen()
        self.sel_label.configure(text=t("dp_selected", n=len(sel), size=human(sum(s for _, s, _ in sel))))

    def remove(self):
        sel = self.chosen()
        if not sel:
            return
        # never remove every copy of a group: keep the newest of any group that is fully selected
        by_group = defaultdict(list)
        for p, s, g in sel:
            by_group[id(g)].append((p, g))
        paths, kept = [], False
        for items in by_group.values():
            group = items[0][1]
            chosen = {p for p, _ in items}
            if len(chosen) >= len(group):
                chosen.discard(max(group, key=lambda x: x[2])[0])
                kept = True
            paths += sorted(chosen)
        size = sum(os.path.getsize(p) for p in paths if os.path.exists(p))
        if not paths or not confirm(t("tool_dupes"), t("dp_ask", n=len(paths), size=human(size))):
            return
        ok = to_recycle_bin(paths)
        msg = t("dp_moved", n=len(paths)) + ("\n" + t("dp_keep_one") if kept else "")
        self.info.configure(text=msg if ok else "SHFileOperation failed", text_color=ui.GOOD if ok else ui.BAD)
        self.forget({p for p in paths if not os.path.exists(p)})


def reveal(path):
    """Open Explorer at the file's folder with the file selected."""
    subprocess.Popen('explorer.exe /select,"%s"' % os.path.normpath(path))
