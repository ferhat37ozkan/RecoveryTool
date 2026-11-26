"""Cleanup & Privacy > Duplicate Finder: files with identical content in a folder.  Grouped by size, then
by a hash of the first 64 KB, then by a full SHA-256, so only byte-identical files are reported.
Removing sends files to the Recycle Bin (can be undone); nothing is selected by default."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import hashlib
import os
import queue
import stat
import subprocess
import threading
import time
from collections import OrderedDict, defaultdict
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
    "dp_scanning": ("Searching… {d} folders, {n} files · {groups} groups of duplicates so far",
                    "Aranıyor… {d} klasör, {n} dosya · şimdiye dek {groups} kopya grubu"),
    "dp_stop": ("Stop", "Durdur"),
    "dp_stopped": ("Stopped. {groups} groups found until then.", "Durduruldu. O ana kadar {groups} grup bulundu."),
    "dp_start": ("Starting…", "Başlıyor…"),
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

MAX_GROUPS_SHOWN = 100
LIVE_GROUPS_SHOWN = 40         # cards drawn while the search runs; all are sorted and drawn at the end
THUMB = 48


def scan(folder, min_size, progress, found=None, job=None):
    """{key: [(path, size, mtime)]} for groups of 2+ identical files.

    Files are compared while the folders are walked: a file is read only when another file of the
    same size was seen, first its first 64 KB, then (if those match) all of it.  So a duplicate is
    known, and ``found(key, files)`` told, as soon as its second copy turns up; a group that grows
    later is told again.  ``progress(files, folders, groups)`` a few times a second.
    ``job["stop"]`` ends early (what was found until then is returned)."""
    job = job or {"stop": False}
    by_size = defaultdict(list)
    heads, fulls = {}, {}
    groups, member = {}, {}             # key -> files; path -> key
    seen = dirs = 0
    last = 0.0

    def digest(path, limit=None):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            if limit:
                h.update(f.read(limit))
            else:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    if job["stop"]:
                        raise InterruptedError
                    h.update(chunk)
        return h.hexdigest()

    def head(item):
        if item[0] not in heads:
            try:
                heads[item[0]] = digest(item[0], 65536)
            except OSError:
                heads[item[0]] = None
        return heads[item[0]]

    def full(item):                     # up to 64 KB the head already is the whole file
        if item[1] <= 65536:
            return head(item)
        if item[0] not in fulls:
            try:
                fulls[item[0]] = digest(item[0])
            except OSError:
                fulls[item[0]] = None
        return fulls[item[0]]

    def compare(item):
        peers = list(by_size[item[1]])
        by_size[item[1]].append(item)
        if not peers or head(item) is None:
            return
        same = [x for x in peers if head(x) == heads[item[0]]]
        if not same or full(item) is None:
            return
        same = [x for x in same if full(x) == full(item)]
        if not same:
            return
        key = full(item) + str(item[1])
        if key in groups:
            groups[key].append(item)
        else:
            groups[key] = same + [item]
            for x in same:
                member[x[0]] = key
        member[item[0]] = key
        if found:
            found(key, list(groups[key]))

    stack = [folder]
    try:
        while stack and not job["stop"]:
            d = stack.pop()
            dirs += 1
            try:
                with os.scandir(d) as it:
                    entries = list(it)
            except OSError:
                continue
            for e in entries:
                if job["stop"]:
                    break
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                if stat.S_ISDIR(st.st_mode):
                    stack.append(e.path)
                elif st.st_size >= min_size:
                    seen += 1
                    compare((e.path, st.st_size, st.st_mtime))
                now = time.time()
                if now - last > 0.2:
                    last = now
                    progress(seen, dirs, len(groups))
    except InterruptedError:
        pass
    progress(seen, dirs, len(groups))
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
        self.stop_btn = ui.button(row, t("dp_stop"), self.stop, 100)
        self.stop_btn.pack(side="left", padx=(16, 0))
        self.stop_btn.configure(state="disabled")
        self.bar = ctk.CTkProgressBar(c, height=8, progress_color=ui.ACCENT, fg_color=ui.BORDER)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=18, pady=(0, 6))
        self.info = ctk.CTkLabel(c, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w")
        self.info.pack(fill="x", padx=18, pady=(0, 10))
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
        self.job, self.cards = None, {}
        self.pending, self.draining, self.draw_token = OrderedDict(), False, 0
        self.thumbs, self.thumb_q, self.thumb_thread = {}, queue.Queue(), None

    def busy(self):
        return self.job is not None

    def stop(self):
        if self.job:
            self.job["stop"] = True

    def choose(self):
        start = getattr(self, "folder", None) or os.path.expanduser("~")
        folder = filedialog.askdirectory(title=t("dp_choose"), initialdir=start)    # not the program's own folder
        if not folder:
            return
        self.folder = folder = os.path.normpath(folder)
        self.choose_btn.configure(state="disabled")
        self.min_seg.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.draw_token += 1
        self.pending.clear()
        for w_ in self.results.winfo_children():
            w_.destroy()
        self.vars, self.groups, self.cards = {}, {}, {}
        self.update_sel()
        self.info.configure(text=t("dp_start"), text_color=ui.MUTED)
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        self.job = job = {"stop": False}
        min_size = self.mins[self.min_seg.get()]
        self.run(lambda: scan(folder, min_size, lambda *a: self.post(self.progress, *a),
                              lambda *a: self.post(self.found, *a), job), self.finished)

    def progress(self, files, folders, groups):
        self.info.configure(text=t("dp_scanning", n=files, d=folders, groups=groups))

    # Drawing customtkinter widgets is slow, so new groups are drawn a few at a time (about 40 ms of
    # work per 60 ms): the window keeps answering while hundreds of duplicates turn up.
    def found(self, key, files):
        """A duplicate turned up during the search: listed at once (a group that grew is redrawn)."""
        self.pending[key] = files
        self.pending.move_to_end(key)
        if not self.draining:
            self.draining = True
            self.after(30, self.drain)

    def drain(self):
        t0 = time.time()
        while self.pending and time.time() - t0 < 0.04:
            key, files = self.pending.popitem(last=False)
            if key in self.cards:
                self.fill_group(self.cards[key], files)
            elif len(self.cards) < LIVE_GROUPS_SHOWN:
                self.add_group(files, key=key)
        if self.pending:
            self.after(60, self.drain)
        else:
            self.draining = False

    def finished(self, groups):
        stopped = bool(self.job and self.job["stop"])
        self.job = None
        self.pending.clear()
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self.bar.set(0 if stopped else 1)
        self.stop_btn.configure(state="disabled")
        self.min_seg.configure(state="normal")
        keep = {p for p, (v, _, _) in self.vars.items() if v.get()}
        if not isinstance(groups, Exception):        # files removed while it ran are left out
            groups = {k: [x for x in g if os.path.exists(x[0])] for k, g in groups.items()}
            groups = {k: g for k, g in groups.items() if len(g) > 1}
        self.show(groups, keep)
        if stopped and not isinstance(groups, Exception):
            self.info.configure(text=t("dp_stopped", groups=len(groups)), text_color=ui.WARN)

    def show(self, groups, keep=()):
        """All groups, the most space first, drawn in small steps."""
        self.choose_btn.configure(state="normal")
        self.draw_token += 1
        token = self.draw_token
        for w_ in self.results.winfo_children():
            w_.destroy()
        self.vars, self.cards = {}, {}
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
        todo = ordered[:MAX_GROUPS_SHOWN]

        def step(i):
            if token != self.draw_token or not self.winfo_exists():
                return
            t0 = time.time()
            while i < len(todo) and time.time() - t0 < 0.04:
                self.add_group(todo[i], keep)
                i += 1
            if i < len(todo):
                self.after(30, lambda: step(i))
            elif len(ordered) > MAX_GROUPS_SHOWN:
                note(self.results, t("dp_more", n=len(ordered) - MAX_GROUPS_SHOWN))
        step(0)
        self.update_sel()

    def add_group(self, g, keep=(), key=None):
        box = ui.card(self.results)
        box.pack(fill="x", pady=(0, 8), padx=(0, 8))
        if key is not None:
            self.cards[key] = box
        self.fill_group(box, g, keep)

    def fill_group(self, box, g, keep=()):
        """One card: the picture Windows shows for the file (all copies have the same content, so one is
        enough), then the copies, newest first, each with reveal and delete icons."""
        keep = set(keep) | {p for p, (v, _, _) in self.vars.items() if v.get()}
        for w_ in box.winfo_children():
            w_.destroy()
        thumb = ctk.CTkLabel(box, text="", width=THUMB + 8, height=THUMB + 8, fg_color=ui.BG, corner_radius=8)
        thumb.pack(side="left", anchor="n", padx=(12, 0), pady=10)
        self.want_thumb(g[0][0], thumb)
        right = ctk.CTkFrame(box, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(right, text=t("dp_group", n=len(g), size=human(g[0][1])), font=("Segoe UI Semibold", 12),
                     text_color=ui.TEXT, anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        for path, size, mtime in sorted(g, key=lambda x: -x[2]):
            var = ctk.BooleanVar(value=path in keep)
            self.vars[path] = (var, size, g)
            line = ctk.CTkFrame(right, fg_color="transparent")
            line.pack(fill="x", padx=(10, 8), pady=0)
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
        ctk.CTkFrame(right, fg_color="transparent", height=6).pack()

    # -- pictures, from Windows on a thread of their own ------------------------------------------
    def want_thumb(self, path, label):
        if path in self.thumbs:
            if self.thumbs[path] is not None:
                label.configure(image=self.thumbs[path])
            return
        self.thumb_q.put((path, label))
        if self.thumb_thread is None:
            self.thumb_thread = threading.Thread(target=self.thumb_worker, daemon=True)
            self.thumb_thread.start()

    def thumb_worker(self):
        from .. import thumbs
        thumbs.init_thread()
        while True:
            path, label = self.thumb_q.get()
            if path is None:
                return
            try:
                img = thumbs.get(path, THUMB * 2)       # twice the size: sharp on scaled displays
            except Exception:
                img = None
            self.post(self.got_thumb, path, label, img)

    def got_thumb(self, path, label, img):
        if path not in self.thumbs:
            if img is None:
                self.thumbs[path] = None
            else:
                k = THUMB / max(img.size)
                self.thumbs[path] = ctk.CTkImage(light_image=img, dark_image=img,
                                                 size=(max(1, round(img.width * k)), max(1, round(img.height * k))))
        try:
            if self.thumbs[path] is not None and label.winfo_exists():
                label.configure(image=self.thumbs[path])
        except Exception:
            pass

    def destroy(self):
        if self.job:
            self.job["stop"] = True
        self.thumb_q.put((None, None))
        super().destroy()

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
