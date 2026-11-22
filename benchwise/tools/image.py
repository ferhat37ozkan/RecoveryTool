"""Disk > Image & Clone.  Copies a whole disk or one partition, sector by sector, into an image file
(raw .img, which File Recovery and most tools can open).  The source is only read; sectors that
cannot be read are written as zeros and counted.  A SHA-256 of the image and a short report are
saved next to it.

Cloning to another disk and writing an image back to a disk overwrite that disk and stay locked in
this version."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
from tkinter import filedialog

import customtkinter as ctk

from recoverytool import disks as disklist
from recoverytool.engine import long_path
from recoverytool.i18n import t
from recoverytool.source import Source, SourceLost

from .. import ui
from ..toolkit import ToolView, card, human, note, texts
from .surface import duration

texts({
    "im_how": ("Copies a disk or a partition into an image file. The source is only read. Work on the image "
               "instead of a failing disk, or keep it as a backup. The image must go to a different disk.",
               "Bir diski veya bölümü imaj dosyasına kopyalar. Kaynak yalnızca okunur. Arızalı bir disk yerine "
               "imaj üzerinde çalışın veya yedek olarak saklayın. İmaj başka bir diske kaydedilmelidir."),
    "im_source": ("Source", "Kaynak"),
    "im_whole": ("whole disk", "bütün disk"),
    "im_part": ("partition", "bölüm"),
    "im_create": ("Create image…", "İmaj oluştur…"),
    "im_stop": ("Stop", "Durdur"),
    "im_same_disk": ("The image cannot be saved on the disk that is being copied.",
                     "İmaj, kopyalanan diskin üzerine kaydedilemez."),
    "im_no_room": ("Not enough free space there: {need} needed, {free} free.",
                   "Orada yeterli boş alan yok: {need} gerekli, {free} boş."),
    "im_progress": ("{done} of {total} · {speed}/s · about {eta} left · unreadable: {bad}",
                    "{total} içinde {done} · {speed}/sn · yaklaşık {eta} kaldı · okunamayan: {bad}"),
    "im_done": ("Image saved: {path}\nSHA-256: {sha}", "İmaj kaydedildi: {path}\nSHA-256: {sha}"),
    "im_done_bad": ("{bad} could not be read and were written as zeros.", "{bad} okunamadı ve sıfır olarak yazıldı."),
    "im_stopped": ("Stopped. The incomplete image was deleted.", "Durduruldu. Yarım kalan imaj silindi."),
    "im_lost": ("The source disk stopped responding. The incomplete image was kept: {path}",
                "Kaynak disk yanıt vermeyi bıraktı. Yarım kalan imaj saklandı: {path}"),
    "im_clone": ("Clone / restore", "Klonla / geri yükle"),
    "im_clone_note": ("Copying a disk directly onto another disk, or writing an image back to a disk, erases "
                      "everything on the target. Locked in this version.",
                      "Bir diski doğrudan başka bir diske kopyalamak veya bir imajı diske geri yazmak hedefteki "
                      "her şeyi siler. Bu sürümde kilitli."),
    "im_clone_btn": ("Clone disk to disk", "Diskten diske klonla"),
    "im_restore_btn": ("Restore image to disk", "İmajı diske geri yükle"),
})

CHUNK = 4 << 20


def sources(disks):
    """[(label, disk, offset, size, name)] - every disk, then its partitions."""
    out = []
    for d in disks:
        if not d.get("size"):
            continue
        out.append(("Disk %d · %s · %s · %s" % (d["number"], d["name"], human(d["size"]), t("im_whole")),
                    d, 0, d["size"], "disk%d" % d["number"]))
        for p in d["partitions"]:
            what = " ".join(x for x in ((p.get("letter") + ":") if p.get("letter") else "", p.get("label") or "",
                                         p.get("filesystem") or p.get("type") or "") if x)
            out.append(("      Disk %d · %s #%d · %s · %s" % (d["number"], t("im_part"), p["number"], what, human(p["size"])),
                        d, p["offset"], p["size"], "disk%d-part%d" % (d["number"], p["number"])))
    return out


def copy(src, path, job, progress):
    """Copy ``src`` into ``path``; returns (state, sha256 hex, bytes done)."""
    h = hashlib.sha256()
    pos, t0, last = 0, time.time(), 0.0
    with open(long_path(path), "wb") as out:
        while pos < src.size:
            if job["stop"]:
                return "stopped", None, pos
            data = src.read_raw(pos, min(CHUNK, src.size - pos))
            out.write(data)
            h.update(data)
            pos += len(data)
            now = time.time()
            if now - last > 0.25:
                last = now
                progress(pos, src.size, now - t0, src.bad_bytes)
    return "done", h.hexdigest(), pos


class View(ToolView):
    title_key = "tool_image"

    def fill(self):
        self.job = None
        self.items = []
        c = card(self.body, t("tool_image"))
        note(c, t("im_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(row, text=t("im_source"), font=("Segoe UI", 12), text_color=ui.TEXT).pack(side="left")
        self.choice = ctk.CTkOptionMenu(row, values=["…"], width=520, fg_color=ui.CARD, button_color=ui.BORDER,
                                        button_hover_color="#33405c", text_color=ui.TEXT)
        self.choice.pack(side="left", padx=10)
        self.go_btn = ui.button(row, t("im_create"), self.start, 150, primary=True)
        self.go_btn.pack(side="left", padx=(8, 0))
        self.stop_btn = ui.button(row, t("im_stop"), self.stop, 100)
        self.stop_btn.pack(side="left", padx=8)
        self.stop_btn.configure(state="disabled")
        self.bar = ctk.CTkProgressBar(c, height=8, progress_color=ui.ACCENT, fg_color=ui.BORDER)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=18, pady=(6, 6))
        self.status_line = ctk.CTkLabel(c, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w")
        self.status_line.pack(fill="x", padx=18)
        self.result = ctk.CTkLabel(c, text=" ", font=("Segoe UI Semibold", 12), text_color=ui.TEXT, anchor="w",
                                   justify="left", wraplength=760)
        self.result.pack(fill="x", padx=18, pady=(4, 14))
        cl = card(self.body, t("im_clone"))
        note(cl, t("im_clone_note"))
        row = ctk.CTkFrame(cl, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 14))
        for key in ("im_clone_btn", "im_restore_btn"):
            b = ui.button(row, "🔒 " + t(key), lambda: None, 230)
            b.configure(state="disabled")
            b.pack(side="left", padx=(0, 8))
        self.run(disklist.list_disks, self.got_disks)

    def got_disks(self, res):
        if isinstance(res, Exception):
            self.choice.configure(values=[str(res)])
            self.choice.set(str(res))
            return
        self.disks = res
        self.items = sources(res)
        labels = [i[0] for i in self.items]
        self.choice.configure(values=labels or ["-"])
        self.choice.set(labels[0] if labels else "-")

    def busy(self):
        return self.job is not None

    def start(self):
        item = next((i for i in self.items if i[0] == self.choice.get()), None)
        if item is None:
            return
        label, d, offset, size, name = item
        path = filedialog.asksaveasfilename(defaultextension=".img", initialfile="%s-%s.img" % (name, time.strftime("%Y%m%d")),
                                            filetypes=[("Disk image", "*.img"), ("*", "*.*")])
        if not path:
            return
        path = os.path.normpath(path)
        if disklist.disk_of_path(path, self.disks) == d["number"]:
            self.result.configure(text=t("im_same_disk"), text_color=ui.BAD)
            return
        free = shutil.disk_usage(os.path.dirname(path)).free
        if free < size + (64 << 20):
            self.result.configure(text=t("im_no_room", need=human(size), free=human(free)), text_color=ui.BAD)
            return
        try:
            src = Source(d["path"], size=size, sector=d.get("sector") or 512, label=label, base=offset)
        except OSError as ex:
            self.result.configure(text=str(ex), text_color=ui.BAD)
            return
        self.job = {"stop": False}
        job = self.job
        self.go_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.result.configure(text=" ", text_color=ui.TEXT)

        def work():
            try:
                state, sha, done = copy(src, path, job, lambda *a: self.post(self.progress, *a))
            except SourceLost:
                return "lost", None, 0, src.bad_bytes, path
            finally:
                src.close()
            if state == "stopped":
                try:
                    os.remove(long_path(path))
                except OSError:
                    pass
            else:
                with open(long_path(path + ".txt"), "w", encoding="utf-8") as f:
                    f.write("Benchwise disk image\nsource: %s\nsize: %d bytes\nunreadable: %d bytes (written as zeros)\n"
                            "sha256: %s\ncreated: %s\n" % (label.strip(), done, src.bad_bytes, sha,
                                                          time.strftime("%Y-%m-%d %H:%M:%S")))
            return state, sha, done, src.bad_bytes, path
        self.run(work, self.finished)

    def progress(self, pos, size, elapsed, bad):
        speed = pos / elapsed if elapsed > 0 else 0
        self.bar.set(pos / size if size else 0)
        self.status_line.configure(text=t("im_progress", done=human(pos), total=human(size), speed=human(speed),
                                          eta=duration((size - pos) / speed if speed else 0), bad=human(bad)))

    def stop(self):
        if self.job:
            self.job["stop"] = True

    def finished(self, res):
        self.job = None
        self.go_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if isinstance(res, Exception):
            self.result.configure(text=str(res), text_color=ui.BAD)
            return
        state, sha, done, bad, path = res
        if state == "stopped":
            self.bar.set(0)
            self.result.configure(text=t("im_stopped"), text_color=ui.MUTED)
        elif state == "lost":
            self.result.configure(text=t("im_lost", path=path), text_color=ui.BAD)
        else:
            self.bar.set(1)
            text = t("im_done", path=path, sha=sha) + ("\n" + t("im_done_bad", bad=human(bad)) if bad else "")
            self.result.configure(text=text, text_color=ui.WARN if bad else ui.GOOD)

    def destroy(self):
        if self.job:
            self.job["stop"] = True
        super().destroy()
