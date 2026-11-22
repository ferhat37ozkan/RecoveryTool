"""Cleanup & Privacy > Junk Files: categories of throw-away files with their size; the user ticks what
to clear, confirms, and only the files inside those folders are deleted.

Safety: only files below the listed folders are touched - never the folders themselves, and links /
junctions are not followed.  Files in use are skipped.  A browser's cache is left alone while that
browser runs.  The Recycle Bin is emptied through Windows itself."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import os
import stat
import subprocess
import time

import customtkinter as ctk

from recoverytool.i18n import t

from .. import elevate, ui
from ..toolkit import ToolView, card, confirm, human, note, scroll_body, texts

texts({
    "jk_scanning": ("Measuring…", "Ölçülüyor…"),
    "jk_how": ("Tick what to clear. Nothing personal is in these folders: they hold copies Windows and programs make "
               "again when needed. Files in use are skipped.",
               "Temizlenecekleri işaretleyin. Bu klasörlerde kişisel bir şey yoktur: Windows'un ve programların "
               "gerektiğinde yeniden oluşturduğu kopyalar bulunur. Kullanımdaki dosyalar atlanır."),
    "jk_total": ("Selected: {size}", "Seçili: {size}"),
    "jk_clean": ("Clean", "Temizle"),
    "jk_rescan": ("Measure again", "Yeniden ölç"),
    "jk_ask": ("Delete {size} in {n} categories?\n\n{items}\n\nThis cannot be undone (the Recycle Bin is not used "
               "for these).", "{n} kategorideki {size} silinsin mi?\n\n{items}\n\nBu geri alınamaz (bunlar için "
               "Geri Dönüşüm Kutusu kullanılmaz)."),
    "jk_cleaning": ("Cleaning… {name}", "Temizleniyor… {name}"),
    "jk_done": ("Freed {size}. {skipped} files were in use and were left.",
                "{size} yer açıldı. Kullanımdaki {skipped} dosya bırakıldı."),
    "jk_running": ("{browser} is open: close it to clear its cache.", "{browser} açık: önbelleğini temizlemek için kapatın."),
    "jk_admin": ("needs administrator rights", "yönetici yetkisi gerekir"),
    "jk_c_user_temp": ("Your temporary files", "Geçici dosyalarınız"),
    "jk_c_win_temp": ("Windows temporary files", "Windows geçici dosyaları"),
    "jk_c_wu": ("Windows Update downloads (already installed)", "Windows Update indirmeleri (zaten kurulmuş)"),
    "jk_c_do": ("Delivery Optimization cache", "Teslim İyileştirme önbelleği"),
    "jk_c_dumps": ("Crash dumps and error reports", "Çökme dökümleri ve hata raporları"),
    "jk_c_chrome": ("Google Chrome cache", "Google Chrome önbelleği"),
    "jk_c_edge": ("Microsoft Edge cache", "Microsoft Edge önbelleği"),
    "jk_c_brave": ("Brave cache", "Brave önbelleği"),
    "jk_c_opera": ("Opera cache", "Opera önbelleği"),
    "jk_c_firefox": ("Firefox cache", "Firefox önbelleği"),
    "jk_c_recycle": ("Recycle Bin", "Geri Dönüşüm Kutusu"),
    "jk_c_shader": ("Graphics shader caches", "Ekran kartı gölgelendirici önbellekleri"),
})

LOCAL = os.environ.get("LOCALAPPDATA", "")
WIN = os.environ.get("SystemRoot", r"C:\Windows")
PDATA = os.environ.get("ProgramData", r"C:\ProgramData")


def chromium_caches(base):
    """Cache folders of every profile of a Chromium browser (Default, Profile 1, ...)."""
    out = []
    try:
        for entry in os.scandir(base):
            if entry.is_dir(follow_symlinks=False) and (entry.name == "Default" or entry.name.startswith("Profile ")):
                for sub in ("Cache", "Code Cache", "GPUCache", os.path.join("Service Worker", "CacheStorage")):
                    out.append(os.path.join(entry.path, sub))
    except OSError:
        pass
    return out


def firefox_caches():
    root = os.path.join(LOCAL, r"Mozilla\Firefox\Profiles")
    try:
        return [os.path.join(e.path, "cache2") for e in os.scandir(root) if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []


# key, folders, administrator needed, browser process name
CATEGORIES = [
    ("user_temp", lambda: [os.environ.get("TEMP", "")], False, None),
    ("win_temp", lambda: [os.path.join(WIN, "Temp")], True, None),
    ("wu", lambda: [os.path.join(WIN, r"SoftwareDistribution\Download")], True, None),
    ("do", lambda: [os.path.join(WIN, r"ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization\Cache")], True, None),
    ("dumps", lambda: [os.path.join(WIN, "Minidump"), os.path.join(WIN, "LiveKernelReports"),
                       os.path.join(PDATA, r"Microsoft\Windows\WER\ReportArchive"),
                       os.path.join(PDATA, r"Microsoft\Windows\WER\ReportQueue"),
                       os.path.join(LOCAL, "CrashDumps")], True, None),
    ("shader", lambda: [os.path.join(LOCAL, "D3DSCache"), os.path.join(LOCAL, r"NVIDIA\DXCache"),
                        os.path.join(LOCAL, r"NVIDIA\GLCache"), os.path.join(LOCAL, r"AMD\DxCache"),
                        os.path.join(LOCAL, r"AMD\DxcCache"), os.path.join(LOCAL, r"AMD\VkCache")], False, None),
    ("chrome", lambda: chromium_caches(os.path.join(LOCAL, r"Google\Chrome\User Data")), False, "chrome.exe"),
    ("edge", lambda: chromium_caches(os.path.join(LOCAL, r"Microsoft\Edge\User Data")), False, "msedge.exe"),
    ("brave", lambda: chromium_caches(os.path.join(LOCAL, r"BraveSoftware\Brave-Browser\User Data")), False, "brave.exe"),
    ("opera", lambda: [os.path.join(LOCAL, r"Opera Software\Opera Stable\Cache")], False, "opera.exe"),
    ("firefox", firefox_caches, False, "firefox.exe"),
]


def walk_files(root):
    """Every file below ``root`` without following links or junctions (reparse points)."""
    stack = [root]
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
                    else:
                        yield e.path, st.st_size
        except OSError:
            continue


def walk_dirs(root):
    """Folders below ``root``, deepest first, without entering links or junctions."""
    found, stack = [], [root]
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
                        found.append(e.path)
                        stack.append(e.path)
        except OSError:
            continue
    return sorted(found, key=len, reverse=True)


class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("i64Size", ctypes.c_int64), ("i64NumItems", ctypes.c_int64)]


def recycle_bin_size():
    info = SHQUERYRBINFO(ctypes.sizeof(SHQUERYRBINFO), 0, 0)
    ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    return info.i64Size, info.i64NumItems


def running_processes():
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=20).stdout
        return {line.split('","')[0].strip('"').lower() for line in out.splitlines() if line}
    except Exception:
        return set()


def measure():
    procs = running_processes()
    admin = elevate.is_admin()
    rows = []
    for key, folders, needs_admin, browser in CATEGORIES:
        paths = [p for p in folders() if p and os.path.isdir(p)]
        size = files = 0
        for p in paths:
            for _, s in walk_files(p):
                size += s
                files += 1
        if size or key == "user_temp":
            rows.append({"key": key, "paths": paths, "size": size, "files": files,
                         "blocked": (needs_admin and not admin) and "admin" or (browser in procs and browser) or None})
    rb_size, rb_items = recycle_bin_size()
    if rb_size:
        rows.append({"key": "recycle", "paths": [], "size": rb_size, "files": rb_items, "blocked": None})
    return rows


def clean(rows, report):
    freed = skipped = 0
    for row in rows:
        report(row["key"])
        if row["key"] == "recycle":
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)      # no confirmation, progress or sound
            freed += row["size"]
            continue
        for root in row["paths"]:
            for path, size in walk_files(root):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    os.remove(path)
                    freed += size
                except OSError:
                    skipped += 1
            for d in walk_dirs(root):            # emptied folders below the root (links and junctions left alone)
                try:
                    os.rmdir(d)
                except OSError:
                    pass
    return freed, skipped


class View(ToolView):
    title_key = "tool_junk"

    def fill(self):
        ui.button(self.head, t("jk_rescan"), self.measure, 130).pack(side="right")
        self.page = scroll_body(self)
        note(self.page, t("jk_scanning"))
        self.measure()

    def measure(self):
        if self.busy():
            return
        self.run(measure, self.show, status=t("jk_scanning"))

    def show(self, rows):
        for w_ in self.page.winfo_children():
            w_.destroy()
        if isinstance(rows, Exception):
            note(self.page, str(rows), color=ui.BAD)
            return
        self.rows_data = rows
        c = card(self.page, t("tool_junk"))
        note(c, t("jk_how"), color=ui.TEXT)
        self.vars = {}
        for row in rows:
            line = ctk.CTkFrame(c, fg_color="transparent")
            line.pack(fill="x", padx=18, pady=2)
            # the Recycle Bin holds what the user deleted and may still want back: never ticked by default
            var = ctk.BooleanVar(value=bool(row["size"]) and not row["blocked"] and row["key"] != "recycle")
            cb = ctk.CTkCheckBox(line, text=t("jk_c_" + row["key"]), variable=var, command=self.update_total,
                                 font=("Segoe UI", 12), text_color=ui.TEXT, checkbox_width=18, checkbox_height=18,
                                 border_width=2, fg_color=ui.ACCENT, border_color=ui.MUTED)
            cb.pack(side="left")
            if row["blocked"]:
                var.set(False)
                cb.configure(state="disabled")
                why = t("jk_admin") if row["blocked"] == "admin" else t("jk_running", browser=row["blocked"].split(".")[0].title())
                ctk.CTkLabel(line, text=why, font=("Segoe UI", 11), text_color=ui.WARN).pack(side="left", padx=10)
            ctk.CTkLabel(line, text=human(row["size"]), font=("Segoe UI Semibold", 12), text_color=ui.TEXT).pack(side="right")
            self.vars[row["key"]] = var
        bottom = ctk.CTkFrame(c, fg_color="transparent")
        bottom.pack(fill="x", padx=18, pady=(10, 14))
        self.total = ctk.CTkLabel(bottom, text=" ", font=("Segoe UI Semibold", 14), text_color=ui.TEXT)
        self.total.pack(side="left")
        self.clean_btn = ui.button(bottom, t("jk_clean"), self.clean, 140, primary=True)
        self.clean_btn.pack(side="right")
        self.result = ctk.CTkLabel(c, text=" ", font=("Segoe UI", 12), text_color=ui.GOOD, anchor="w")
        self.result.pack(fill="x", padx=18, pady=(0, 12))
        self.update_total()

    def chosen(self):
        return [r for r in self.rows_data if self.vars.get(r["key"]) and self.vars[r["key"]].get()]

    def update_total(self):
        self.total.configure(text=t("jk_total", size=human(sum(r["size"] for r in self.chosen()))))

    def clean(self):
        rows = self.chosen()
        if not rows:
            return
        items = "\n".join("• %s (%s)" % (t("jk_c_" + r["key"]), human(r["size"])) for r in rows)
        if not confirm(t("tool_junk"), t("jk_ask", size=human(sum(r["size"] for r in rows)), n=len(rows), items=items)):
            return
        self.clean_btn.configure(state="disabled")

        def done(res):
            self.clean_btn.configure(state="normal")
            if isinstance(res, Exception):
                self.result.configure(text=str(res), text_color=ui.BAD)
                return
            freed, skipped = res
            self.measure()
            self.after(300, lambda: self.result.configure(text=t("jk_done", size=human(freed), skipped=skipped))
                       if self.result.winfo_exists() else None)
            self.last_result = t("jk_done", size=human(freed), skipped=skipped)
        self.run(lambda: clean(rows, lambda key: self.post(self.result.configure, {"text": t("jk_cleaning", name=t("jk_c_" + key)),
                                                                                       "text_color": ui.MUTED})), done)
