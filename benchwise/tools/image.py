"""Disk > Image & Clone: back up a disk to an image file, and mount images as drive letters.

Backup: a USB stick, memory card, external or internal disk (or one partition) is copied sector by
sector into a .vhd file.  A fixed VHD is the raw disk followed by a 512-byte footer, so the file
is still a plain raw image for File Recovery and other tools, and Windows can attach it as a disk.
A single partition gets a 1 MiB partition table in front of it, so it mounts like a disk too.
The source is only read; sectors that cannot be read are written as zeros and counted.

Restore: chosen images (.vhd, .vhdx, .iso) are attached and their volume gets the drive letter
picked for it, so it shows in This PC as that drive.  Only free letters can be picked; several
images can be mounted at once, each on its own letter.  The list is kept between runs (Windows
drops the mounts when it restarts; one click mounts them again).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
import time
import uuid
from tkinter import filedialog

import customtkinter as ctk

from recoverytool import disks as disklist
from recoverytool.engine import long_path
from recoverytool.i18n import t
from recoverytool.source import Source, SourceLost

from .. import settings, ui
from ..toolkit import ToolView, card, human, icon_button, note, powershell_json, texts
from .surface import duration

texts({
    "im_backup": ("Back up: disk to image", "Yedekle: diskten imaja"),
    "im_how": ("Plug in a USB stick, memory card or disk, choose it and a folder, and an image file of it is "
               "made. The disk is only read. The image can be mounted below as a drive.",
               "USB bellek, hafıza kartı veya diski takın, onu ve bir klasör seçin; imaj dosyası oluşturulur. "
               "Disk yalnızca okunur. İmaj aşağıdan sürücü olarak bağlanabilir."),
    "im_source": ("Source", "Kaynak"),
    "im_whole": ("whole disk", "bütün disk"),
    "im_part": ("partition", "bölüm"),
    "im_windows": ("Windows disk", "Windows diski"),
    "im_refresh": ("Refresh", "Yenile"),
    "im_folder": ("Save to", "Kayıt yeri"),
    "im_browse": ("Browse…", "Gözat…"),
    "im_name": ("File name", "Dosya adı"),
    "im_space": ("Needed: {need}  ·  free in {where}: {free}", "Gerekli: {need}  ·  {where} boş: {free}"),
    "im_space_ok": ("enough room", "yer yeterli"),
    "im_no_room": ("not enough room", "yer yetmiyor"),
    "im_same_disk": ("The image cannot be saved on the disk that is being copied.",
                     "İmaj, kopyalanan diskin üzerine kaydedilemez."),
    "im_too_big": ("Images larger than 2 TB are not supported.", "2 TB'tan büyük imajlar desteklenmiyor."),
    "im_4k": ("This disk uses 4 KB sectors: the backup is complete, but Windows may not mount it as a drive. "
              "Back up its partitions one by one to mount them.",
              "Bu disk 4 KB sektör kullanıyor: yedek eksiksiz olur ama Windows onu sürücü olarak bağlamayabilir. "
              "Bağlamak için bölümlerini tek tek yedekleyin."),
    "im_create": ("Create image", "İmaj al"),
    "im_stop": ("Stop", "Durdur"),
    "im_exists": ("A file with this name is already there: {name}", "Bu adla bir dosya zaten var: {name}"),
    "im_progress": ("{done} of {total} · {speed}/s · about {eta} left · unreadable: {bad}",
                    "{total} içinde {done} · {speed}/sn · yaklaşık {eta} kaldı · okunamayan: {bad}"),
    "im_done": ("Image saved: {path}\nSHA-256: {sha}", "İmaj kaydedildi: {path}\nSHA-256: {sha}"),
    "im_done_bad": ("{bad} could not be read and were written as zeros.", "{bad} okunamadı ve sıfır olarak yazıldı."),
    "im_stopped": ("Stopped. The incomplete image was deleted.", "Durduruldu. Yarım kalan imaj silindi."),
    "im_lost": ("The source disk stopped responding. The incomplete image was kept: {path}",
                "Kaynak disk yanıt vermeyi bıraktı. Yarım kalan imaj saklandı: {path}"),
    "im_restore": ("Restore: mount an image as a drive", "Geri yükle: imajı sürücü olarak bağla"),
    "im_mount_how": ("Add an image and pick a letter: it shows in This PC as that drive. Letters in use cannot "
                     "be picked. Several images can be mounted at once. Windows removes the mounts when it "
                     "restarts; they stay in this list and mount again with one click.",
                     "Bir imaj ekleyin ve harf seçin: Bu Bilgisayar'da o harfle sürücü olarak görünür. Kullanımdaki "
                     "harfler seçilemez. Birden fazla imaj aynı anda bağlanabilir. Windows yeniden başlayınca "
                     "bağlantılar kalkar; bu listede kalır ve tek tıkla yeniden bağlanır."),
    "im_add": ("+ Add image…", "+ İmaj ekle…"),
    "im_readonly": ("Read-only (protects the backup)", "Salt okunur (yedeği korur)"),
    "im_empty": ("No image added yet.", "Henüz imaj eklenmedi."),
    "im_mount": ("Mount", "Bağla"),
    "im_eject": ("Eject", "Çıkar"),
    "im_open": ("Open", "Aç"),
    "im_mounted_on": ("mounted as {letter}:", "{letter}: olarak bağlı"),
    "im_not_mounted": ("not mounted", "bağlı değil"),
    "im_missing": ("file not found", "dosya bulunamadı"),
    "im_no_letter": ("no free letter", "boş harf yok"),
    "im_letter_taken": ("{letter}: is in use now. Pick another letter.", "{letter}: şu an kullanımda. Başka bir harf seçin."),
    "im_mount_ok": ("{name} is now drive {letter}:", "{name} artık {letter}: sürücüsü"),
    "im_eject_ok": ("{name} was ejected.", "{name} çıkarıldı."),
    "im_err_novolume": ("The image was attached but holds no volume Windows can read.",
                        "İmaj bağlandı ama içinde Windows'un okuyabildiği bir bölüm yok."),
    "im_err_collision": ("The disk this image was made from is plugged in, and Windows does not open two disks with "
                         "the same identity. Unplug that disk, or turn off read-only.",
                         "Bu imajın alındığı disk şu an takılı; Windows aynı kimlikteki iki diski birlikte açmaz. "
                         "O diski çıkarın veya salt okunur seçeneğini kapatın."),
    "im_err_offline": ("Windows kept the attached disk offline ({why}).", "Windows bağlanan diski çevrim dışı tuttu ({why})."),
    "im_err_attached": ("This image is already mounted.", "Bu imaj zaten bağlı."),
    "im_raw_img": (".img files are raw images and cannot be mounted by Windows. New backups are .vhd files.",
                   ".img dosyaları ham imajdır, Windows bunları bağlayamaz. Yeni yedekler .vhd dosyasıdır."),
})

CHUNK = 4 << 20
PREFIX = 1 << 20                    # partition table + alignment in front of a single-partition image
VHD_MAX = 2040 << 30                # the VHD format's limit
MOUNTABLE = (".vhd", ".vhdx", ".iso")


# -- image format -----------------------------------------------------------------------------------
def chs(size):
    """VHD disk geometry (cylinders, heads, sectors per track) for ``size`` bytes, as the VHD spec computes it."""
    total = min(size // 512, 65535 * 16 * 255)
    if total >= 65535 * 16 * 63:
        spt, heads = 255, 16
        cth = total // spt
    else:
        spt = 17
        cth = total // spt
        heads = max(4, (cth + 1023) // 1024)
        if cth >= heads * 1024 or heads > 16:
            spt, heads = 31, 16
            cth = total // spt
        if cth >= heads * 1024:
            spt, heads = 63, 16
            cth = total // spt
    return cth // heads, heads, spt


def vhd_footer(size, when=None, uid=None):
    """The 512-byte footer that turns a raw image of ``size`` bytes into a fixed VHD."""
    when = time.time() if when is None else when
    stamp = max(0, int(when) - 946684800) & 0xFFFFFFFF          # seconds since 2000-01-01 UTC
    cyl, heads, spt = chs(size)
    head = struct.pack(">8sIIQI4sI4sQQHBBII16sB", b"conectix", 2, 0x00010000, 0xFFFFFFFFFFFFFFFF, stamp,
                       b"bwse", 0x00010000, b"Wi2k", size, size, cyl, heads, spt, 2, 0,
                       (uid or uuid.uuid4()).bytes, 0)
    footer = bytearray(head + bytes(512 - len(head)))
    checksum = (~sum(footer)) & 0xFFFFFFFF
    struct.pack_into(">I", footer, 64, checksum)
    return bytes(footer)


def partition_type(filesystem):
    fs = (filesystem or "").upper()
    if fs == "FAT32":
        return 0x0C
    if fs in ("FAT", "FAT16", "FAT12"):
        return 0x06
    return 0x07                     # NTFS, exFAT, ReFS and anything else


def mbr_prefix(part_size, filesystem, signature=None):
    """``PREFIX`` bytes: an MBR with one partition at 1 MiB covering ``part_size`` bytes."""
    head = bytearray(PREFIX)
    struct.pack_into("<I", head, 440, signature if signature is not None else int.from_bytes(os.urandom(4), "little"))
    entry = struct.pack("<B3sB3sII", 0, b"\xfe\xff\xff", partition_type(filesystem), b"\xfe\xff\xff",
                        PREFIX // 512, part_size // 512)
    head[446:462] = entry
    head[510:512] = b"\x55\xaa"
    return bytes(head)


def image_size(size, partition):
    """Bytes the image file takes: the data, a partition table for a partition, the VHD footer."""
    return size + (PREFIX if partition else 0) + 512


# -- sources ----------------------------------------------------------------------------------------
def sources(disks):
    """[(label, disk, offset, size, name, partition or None)] - every disk, then its partitions."""
    out = []
    for d in disks:
        if not d.get("size"):
            continue
        extra = " · ".join(x for x in (d.get("bus") or "", t("im_windows") if d.get("system") else "") if x)
        out.append(("Disk %d · %s · %s%s · %s" % (d["number"], d["name"], human(d["size"]), (" · " + extra) if extra else "",
                                                 t("im_whole")), d, 0, d["size"], d["name"], None))
        for p in d["partitions"]:
            what = " ".join(x for x in ((p.get("letter") + ":") if p.get("letter") else "", p.get("label") or "",
                                         p.get("filesystem") or p.get("type") or "") if x)
            out.append(("      Disk %d · %s #%d · %s · %s" % (d["number"], t("im_part"), p["number"], what, human(p["size"])),
                        d, p["offset"], p["size"], p.get("label") or "%s-%d" % (d["name"], p["number"]), p))
    return out


def safe_name(text):
    return re.sub(r"[^\w.-]+", "-", text or "disk").strip("-.")[:60] or "disk"


def copy(src, path, job, progress, prefix=b""):
    """Copy ``src`` into the VHD ``path``; returns (state, sha256 of the disk data, bytes done)."""
    h = hashlib.sha256()
    pos, t0, last = 0, time.time(), 0.0
    with open(long_path(path), "wb") as out:
        out.write(prefix)
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
        out.write(vhd_footer(len(prefix) + pos))
    return "done", h.hexdigest(), pos


# -- mounting (PowerShell storage cmdlets; administrator) ----------------------------------------------
def _ps_str(text):
    return "'" + str(text).replace("'", "''") + "'"


_MOUNT = r"""
$p = %(path)s; $L = '%(letter)s'
$out = [ordered]@{ ok = $false; letter = ''; error = '' }
$mounted = $false
try {
  $img = Get-DiskImage -ImagePath $p -ErrorAction Stop
  if ($img.Attached) { throw 'BW_ATTACHED' }
  Mount-DiskImage -ImagePath $p -NoDriveLetter -Access %(access)s -ErrorAction Stop | Out-Null
  $mounted = $true
  $vol = $null
  for ($i = 0; $i -lt 25 -and -not $vol; $i++) {
    $img = Get-DiskImage -ImagePath $p
    if ($img.StorageType -eq 1) { $vols = @(Get-Volume -DiskImage $img) }
    else {
      $disk = $img | Get-Disk
      if ($disk -and $disk.IsOffline) { Set-Disk -Number $disk.Number -IsOffline $false -ErrorAction SilentlyContinue }
      $vols = @(Get-Partition -DiskNumber $disk.Number | Get-Volume)
    }
    $vol = $vols | Where-Object { $_.FileSystem } | Sort-Object Size -Descending | Select-Object -First 1
    if (-not $vol) { Start-Sleep -Milliseconds 400 }
  }
  if (-not $vol) {
    $why = 'novolume'
    if ($img.StorageType -ne 1) {
      $d = Get-DiskImage -ImagePath $p | Get-Disk
      if ($d -and $d.IsOffline) { $why = 'offline:' + [string]$d.OfflineReason }
    }
    throw ('BW_' + $why)
  }
  $wv = Get-CimInstance Win32_Volume | Where-Object { $_.DeviceID -eq $vol.Path } | Select-Object -First 1
  Set-CimInstance -InputObject $wv -Property @{ DriveLetter = "$($L):" } -ErrorAction Stop
  $out.ok = $true; $out.letter = $L
} catch {
  $out.error = [string]$_.Exception.Message
  if ($mounted) { Dismount-DiskImage -ImagePath $p -ErrorAction SilentlyContinue | Out-Null }
}
$out | ConvertTo-Json -Compress
"""

_EJECT = r"""
$out = [ordered]@{ ok = $true; error = '' }
try { Dismount-DiskImage -ImagePath %(path)s -ErrorAction Stop | Out-Null }
catch { $out.ok = $false; $out.error = [string]$_.Exception.Message }
$out | ConvertTo-Json -Compress
"""

_STATE = r"""
$r = foreach ($p in @(%(paths)s)) {
  $i = Get-DiskImage -ImagePath $p
  $ls = @()
  if ($i -and $i.Attached) {
    if ($i.StorageType -eq 1) { $ls = @(Get-Volume -DiskImage $i | ForEach-Object { [string]$_.DriveLetter }) }
    else { $ls = @($i | Get-Disk | Get-Partition | ForEach-Object { [string]$_.DriveLetter }) }
  }
  [pscustomobject]@{ path = $p; attached = [bool]($i -and $i.Attached); letters = @($ls | Where-Object { $_ -match '^[A-Za-z]$' }) }
}
ConvertTo-Json -Compress -Depth 3 -InputObject @($r)
"""


def mount(path, letter, readonly=True):
    access = "ReadOnly" if readonly or path.lower().endswith(".iso") else "ReadWrite"
    return powershell_json(_MOUNT % {"path": _ps_str(path), "letter": letter.upper()[:1], "access": access}, timeout=90)


def eject(path):
    return powershell_json(_EJECT % {"path": _ps_str(path)}, timeout=60)


def states(paths):
    """{path: (attached, [letters])} for the images in the list."""
    if not paths:
        return {}
    data = powershell_json(_STATE % {"paths": ",".join(_ps_str(p) for p in paths)}, timeout=60)
    out = {}
    for item in data if isinstance(data, list) else [data]:
        out[item.get("path")] = (bool(item.get("attached")), [x.upper() for x in item.get("letters") or []])
    return out


def mount_error(text):
    if text == "BW_ATTACHED":
        return t("im_err_attached")
    if text == "BW_novolume":
        return t("im_err_novolume")
    if text.startswith("BW_offline:"):
        why = text.split(":", 1)[1]
        return t("im_err_collision") if "ollision" in why else t("im_err_offline", why=why or "?")
    return text


class View(ToolView):
    title_key = "tool_image"

    def fill(self):
        self.job = None
        self.items, self.disks = [], []
        self.mount_busy = False
        if not hasattr(self, "folder"):
            self.folder = settings.get("image_folder") or os.path.join(os.path.expanduser("~"), "Documents")
        if not hasattr(self, "images"):
            self.images = [{"path": p, "attached": False, "letters": []}
                           for p in settings.get("image_mounts", []) if isinstance(p, str)]
        body = ctk.CTkScrollableFrame(self.body, fg_color=ui.BG, scrollbar_button_color=ui.BORDER)
        body.pack(fill="both", expand=True)
        self.build_backup(body)
        self.build_restore(body)
        self.run(disklist.list_disks, self.got_disks)
        self.refresh_states()

    # -- backup ---------------------------------------------------------------------------------------
    def build_backup(self, parent):
        c = card(parent, t("im_backup"), padx=(0, 8))
        note(c, t("im_how"), color=ui.TEXT)
        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(fill="x", padx=18, pady=(0, 6))
        grid.grid_columnconfigure(1, weight=1)
        label = dict(font=("Segoe UI", 12), text_color=ui.TEXT, anchor="w")
        ctk.CTkLabel(grid, text=t("im_source"), **label).grid(row=0, column=0, sticky="w", padx=(0, 12), pady=4)
        self.choice = ctk.CTkOptionMenu(grid, values=["…"], fg_color=ui.CARD, button_color=ui.BORDER, dynamic_resizing=False,
                                        button_hover_color="#33405c", text_color=ui.TEXT, command=lambda _: self.source_changed())
        self.choice.grid(row=0, column=1, sticky="ew", pady=4)
        ui.button(grid, t("im_refresh"), self.reload_disks, 100).grid(row=0, column=2, padx=(8, 0), pady=4)
        ctk.CTkLabel(grid, text=t("im_folder"), **label).grid(row=1, column=0, sticky="w", padx=(0, 12), pady=4)
        self.folder_label = ctk.CTkLabel(grid, text=self.folder, font=("Segoe UI", 12), text_color=ui.TEXT, anchor="w",
                                         fg_color=ui.BG, corner_radius=6, height=30)
        self.folder_label.grid(row=1, column=1, sticky="ew", pady=4)
        ui.button(grid, t("im_browse"), self.browse, 100).grid(row=1, column=2, padx=(8, 0), pady=4)
        ctk.CTkLabel(grid, text=t("im_name"), **label).grid(row=2, column=0, sticky="w", padx=(0, 12), pady=4)
        self.name_var = ctk.StringVar(value="")
        name_row = ctk.CTkFrame(grid, fg_color="transparent")
        name_row.grid(row=2, column=1, sticky="ew", pady=4)
        ctk.CTkEntry(name_row, textvariable=self.name_var, fg_color=ui.BG, border_color=ui.BORDER,
                     text_color=ui.TEXT).pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(name_row, text=".vhd", font=("Segoe UI", 12), text_color=ui.MUTED).pack(side="left", padx=(6, 0))
        self.space = ctk.CTkLabel(c, text=" ", font=("Segoe UI Semibold", 12), text_color=ui.MUTED, anchor="w",
                                  justify="left", wraplength=760)
        self.space.pack(fill="x", padx=18, pady=(2, 6))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 4))
        self.go_btn = ui.button(row, t("im_create"), self.start, 150, primary=True)
        self.go_btn.pack(side="left")
        self.stop_btn = ui.button(row, t("im_stop"), self.stop, 100)
        self.stop_btn.pack(side="left", padx=8)
        self.stop_btn.configure(state="disabled")
        self.bar = ctk.CTkProgressBar(c, height=8, progress_color=ui.ACCENT, fg_color=ui.BORDER)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=18, pady=(8, 6))
        self.status_line = ctk.CTkLabel(c, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w")
        self.status_line.pack(fill="x", padx=18)
        self.result = ctk.CTkLabel(c, text=" ", font=("Segoe UI Semibold", 12), text_color=ui.TEXT, anchor="w",
                                   justify="left", wraplength=760)
        self.result.pack(fill="x", padx=18, pady=(4, 14))

    def reload_disks(self):
        if self.job:
            return
        self.choice.configure(values=["…"])
        self.choice.set("…")
        self.run(disklist.list_disks, self.got_disks)

    def got_disks(self, res):
        if isinstance(res, Exception):
            self.choice.configure(values=[str(res)])
            self.choice.set(str(res))
            return
        self.disks = res
        old = self.choice.get()
        self.items = sources(res)
        labels = [i[0] for i in self.items]
        self.choice.configure(values=labels or ["-"])
        if old in labels:
            self.choice.set(old)
        else:   # a removable or non-Windows disk first: that is what people back up here
            first = next((i[0] for i in self.items if i[5] is None and not i[1].get("system")), labels[0] if labels else "-")
            self.choice.set(first)
        self.source_changed()

    def selected(self):
        return next((i for i in self.items if i[0] == self.choice.get()), None)

    def source_changed(self):
        item = self.selected()
        if item:
            self.name_var.set("%s-%s" % (safe_name(item[4]), time.strftime("%Y%m%d-%H%M")))
        self.check_space()

    def browse(self):
        folder = filedialog.askdirectory(title=t("im_folder"), initialdir=self.folder if os.path.isdir(self.folder) else None)
        if not folder:
            return
        self.folder = os.path.normpath(folder)
        settings.put("image_folder", self.folder)
        self.folder_label.configure(text=self.folder)
        self.check_space()

    def check_space(self):
        """Show needed vs free space; returns an error text or None (the button follows it)."""
        item = self.selected()
        if item is None or self.job:
            self.go_btn.configure(state="disabled")
            return "-"
        _, d, _, size, _, part = item
        need = image_size(size, part is not None)
        try:
            free = shutil.disk_usage(self.folder).free
        except OSError as ex:
            self.space.configure(text=str(ex), text_color=ui.BAD)
            self.go_btn.configure(state="disabled")
            return str(ex)
        where = os.path.splitdrive(self.folder)[0] or self.folder
        text = t("im_space", need=human(need), where=where, free=human(free))
        error = None
        if disklist.disk_of_path(self.folder, self.disks) == d["number"]:
            error = t("im_same_disk")
        elif need > VHD_MAX:
            error = t("im_too_big")
        elif free < need + (64 << 20):
            error = text + "  ·  " + t("im_no_room")
        if error:
            self.space.configure(text=error, text_color=ui.BAD)
        elif part is None and (d.get("sector") or 512) != 512:
            self.space.configure(text=text + "  ·  " + t("im_space_ok") + "\n" + t("im_4k"), text_color=ui.WARN)
        else:
            self.space.configure(text=text + "  ·  " + t("im_space_ok"), text_color=ui.GOOD)
        self.go_btn.configure(state="disabled" if error else "normal")
        return error

    def busy(self):
        return self.job is not None or self.mount_busy

    def start(self):
        item = self.selected()
        if item is None or self.check_space():
            return
        label, d, offset, size, _, part = item
        path = os.path.join(self.folder, safe_name(self.name_var.get()) + ".vhd")
        if os.path.exists(path):
            self.result.configure(text=t("im_exists", name=os.path.basename(path)), text_color=ui.BAD)
            return
        try:
            src = Source(d["path"], size=size, sector=d.get("sector") or 512, label=label, base=offset)
        except OSError as ex:
            self.result.configure(text=str(ex), text_color=ui.BAD)
            return
        prefix = mbr_prefix(size, part.get("filesystem")) if part is not None else b""
        self.job = {"stop": False}
        job = self.job
        self.go_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.bar.set(0)
        self.result.configure(text=" ", text_color=ui.TEXT)

        def work():
            try:
                state, sha, done = copy(src, path, job, lambda *a: self.post(self.progress, *a), prefix)
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
                    f.write("Benchwise disk image (fixed VHD: raw data%s, then a 512-byte footer)\nsource: %s\n"
                            "size: %d bytes\nunreadable: %d bytes (written as zeros)\nsha256 of the disk data: %s\n"
                            "created: %s\n" % (", after a 1 MiB partition table" if prefix else "", label.strip(), done,
                                               src.bad_bytes, sha, time.strftime("%Y-%m-%d %H:%M:%S")))
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
        self.stop_btn.configure(state="disabled")
        self.check_space()
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
            self.add_image(path, refresh=False)

    # -- restore (mount) ------------------------------------------------------------------------------
    def build_restore(self, parent):
        c = card(parent, t("im_restore"), padx=(0, 8))
        note(c, t("im_mount_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        self.add_btn = ui.button(row, t("im_add"), self.choose_image, 150, primary=True)
        self.add_btn.pack(side="left")
        self.ro_var = ctk.BooleanVar(value=settings.get("image_readonly", True))
        ctk.CTkCheckBox(row, text=t("im_readonly"), variable=self.ro_var, font=("Segoe UI", 12), text_color=ui.TEXT,
                        checkbox_width=18, checkbox_height=18, border_width=2, fg_color=ui.ACCENT, border_color=ui.MUTED,
                        command=lambda: settings.put("image_readonly", bool(self.ro_var.get()))).pack(side="left", padx=16)
        self.rows = ctk.CTkFrame(c, fg_color="transparent")
        self.rows.pack(fill="x", padx=18, pady=(0, 6))
        self.mount_msg = ctk.CTkLabel(c, text=" ", font=("Segoe UI Semibold", 12), text_color=ui.MUTED, anchor="w",
                                      justify="left", wraplength=760)
        self.mount_msg.pack(fill="x", padx=18, pady=(0, 14))
        self.letter_vars = {}
        self.draw_rows()

    def save_list(self):
        settings.put("image_mounts", [i["path"] for i in self.images])

    def choose_image(self):
        path = filedialog.askopenfilename(title=t("im_add"), initialdir=self.folder if os.path.isdir(self.folder) else None,
                                          filetypes=[("Disk image", "*.vhd *.vhdx *.iso"), ("*", "*.*")])
        if path:
            self.add_image(os.path.normpath(path))

    def add_image(self, path, refresh=True):
        if not path.lower().endswith(MOUNTABLE):
            self.mount_msg.configure(text=t("im_raw_img"), text_color=ui.WARN)
            return
        if not any(os.path.normcase(i["path"]) == os.path.normcase(path) for i in self.images):
            self.images.append({"path": path, "attached": False, "letters": []})
            self.save_list()
        self.draw_rows()
        if refresh:
            self.refresh_states()

    def refresh_states(self):
        paths = [i["path"] for i in self.images if os.path.exists(i["path"])]
        if paths:
            self.run(lambda: states(paths), self.got_states)

    def got_states(self, res):
        if isinstance(res, Exception):
            self.mount_msg.configure(text=str(res), text_color=ui.BAD)
            return
        for i in self.images:
            attached, letters = res.get(i["path"], (False, []))
            i["attached"], i["letters"] = attached, letters
        self.draw_rows()

    def free_for(self, image):
        """Letters this image can take: free ones, minus those other unmounted rows have picked."""
        taken = {self.letter_vars[p].get() for p in self.letter_vars if p != image["path"]}
        return [x for x in disklist.free_letters() if x not in taken]

    def draw_rows(self):
        old = {p: v.get() for p, v in self.letter_vars.items()}
        for w_ in self.rows.winfo_children():
            w_.destroy()
        self.letter_vars = {}
        if not self.images:
            ctk.CTkLabel(self.rows, text=t("im_empty"), font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w").pack(fill="x")
            return
        free = disklist.free_letters()
        for image in self.images:     # picked letters first, so the others leave them out
            if not image["attached"] and old.get(image["path"]) in free:
                self.letter_vars[image["path"]] = ctk.StringVar(value=old[image["path"]])
        for image in self.images:
            if not image["attached"] and image["path"] not in self.letter_vars:
                choices = [x for x in free if x not in {v.get() for v in self.letter_vars.values()}]
                self.letter_vars[image["path"]] = ctk.StringVar(value=choices[0] if choices else "")
        for image in self.images:
            self.draw_row(image)

    def draw_row(self, image):
        path = image["path"]
        exists = os.path.exists(path)
        row = ctk.CTkFrame(self.rows, fg_color=ui.BG, corner_radius=8)
        row.pack(fill="x", pady=3)
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=(12, 6), pady=6)
        ctk.CTkLabel(info, text=os.path.basename(path), font=("Segoe UI Semibold", 12), text_color=ui.TEXT,
                     anchor="w").pack(fill="x")
        if not exists:
            state, color = t("im_missing"), ui.BAD
        elif image["attached"]:
            state, color = t("im_mounted_on", letter=", ".join(image["letters"]) or "?"), ui.GOOD
        else:
            state, color = t("im_not_mounted"), ui.MUTED
        size = human(os.path.getsize(path)) if exists else ""
        ctk.CTkLabel(info, text="   ·   ".join(x for x in (size, state) if x), font=("Segoe UI", 11), text_color=color,
                     anchor="w").pack(fill="x")
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="right", padx=(0, 8))
        if not image["attached"]:
            icon_button(right, "trash", lambda: self.forget(image), ui.MUTED).pack(side="right", padx=(4, 0))
        icon_button(right, "folder", lambda: reveal(path), ui.MUTED).pack(side="right", padx=(4, 0))
        if image["attached"]:
            b = ui.button(right, t("im_eject"), lambda: self.do_eject(image), 90)
            b.pack(side="right", padx=(4, 0))
            if image["letters"]:
                letter = image["letters"][0]
                ui.button(right, t("im_open") + " " + letter + ":", lambda: os.startfile(letter + ":\\"), 70).pack(
                    side="right", padx=(4, 0))
            if self.mount_busy:
                b.configure(state="disabled")
        else:
            var = self.letter_vars[path]
            values = [x + ":" for x in self.free_for(image)]
            menu = ctk.CTkOptionMenu(right, values=values or [t("im_no_letter")], width=72, fg_color=ui.CARD,
                                     button_color=ui.BORDER, button_hover_color="#33405c", text_color=ui.TEXT,
                                     command=lambda v, p=path: self.pick_letter(p, v))
            menu.set((var.get() + ":") if var.get() else t("im_no_letter"))
            b = ui.button(right, t("im_mount"), lambda: self.do_mount(image), 90, primary=True)
            b.pack(side="right", padx=(4, 0))
            menu.pack(side="right", padx=(4, 0))
            if not exists or not var.get() or self.mount_busy:
                b.configure(state="disabled")
                menu.configure(state="disabled" if not exists or self.mount_busy else "normal")

    def pick_letter(self, path, value):
        self.letter_vars[path].set(value.rstrip(":")[:1])
        self.draw_rows()

    def forget(self, image):
        self.images = [i for i in self.images if i is not image]
        self.save_list()
        self.draw_rows()

    def do_mount(self, image):
        letter = self.letter_vars[image["path"]].get()
        if letter not in disklist.free_letters():
            self.mount_msg.configure(text=t("im_letter_taken", letter=letter), text_color=ui.BAD)
            self.draw_rows()
            return
        self.mount_busy = True
        self.draw_rows()
        readonly = bool(self.ro_var.get())
        self.run(lambda: (image, mount(image["path"], letter, readonly)), self.mounted)

    def mounted(self, res):
        self.mount_busy = False
        if isinstance(res, Exception):
            self.mount_msg.configure(text=str(res), text_color=ui.BAD)
        else:
            image, out = res
            name = os.path.basename(image["path"])
            if out.get("ok"):
                self.mount_msg.configure(text=t("im_mount_ok", name=name, letter=out.get("letter")), text_color=ui.GOOD)
            else:
                self.mount_msg.configure(text=name + ": " + mount_error(out.get("error") or "?"), text_color=ui.BAD)
        self.draw_rows()
        self.refresh_states()

    def do_eject(self, image):
        self.mount_busy = True
        self.draw_rows()
        self.run(lambda: (image, eject(image["path"])), self.ejected)

    def ejected(self, res):
        self.mount_busy = False
        if isinstance(res, Exception):
            self.mount_msg.configure(text=str(res), text_color=ui.BAD)
        else:
            image, out = res
            name = os.path.basename(image["path"])
            if out.get("ok"):
                self.mount_msg.configure(text=t("im_eject_ok", name=name), text_color=ui.MUTED)
            else:
                self.mount_msg.configure(text=name + ": " + (out.get("error") or "?"), text_color=ui.BAD)
        self.draw_rows()
        self.refresh_states()

    def destroy(self):
        if self.job:
            self.job["stop"] = True
        super().destroy()


def reveal(path):
    """Open Explorer at ``path`` with the file selected."""
    if os.path.exists(path):
        subprocess.Popen('explorer.exe /select,"%s"' % os.path.normpath(path))
    elif os.path.isdir(os.path.dirname(path)):
        subprocess.Popen(["explorer.exe", os.path.dirname(path)])
