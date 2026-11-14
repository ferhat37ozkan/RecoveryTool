"""The recovery pipeline: lock -> (image) -> scan -> rebuild -> extract -> verify/repair -> report -> unlock."""

from __future__ import annotations

import csv
import ctypes
import hashlib
import os
import shutil
import time
import zipfile
from collections import Counter, defaultdict
from ctypes import wintypes

from . import APP_NAME, __version__, allocation, disks, exfat, fat32, ntfs, scanner
from .i18n import t
from .model import (DAMAGED, FILLED_FROM_TWIN, OK, REPAIRED, SKIPPED, UNCERTAIN, UNSUPPORTED, Cancelled,
                    filetime_to_text, human_size)
from .signatures import ARCHIVE_EXT as _ARCHIVE_EXT, magic_matches
from .source import Source, SourceLost

REPORT_DIR = "RecoveryTool-Report"
IO_CHUNK = 4 * 1024 * 1024

_DAMAGE_FLAGS = {"CHAIN_BROKEN", "RUNLIST_INCOMPLETE", "RUN_OUT_OF_RANGE", "TRUNCATED", "READ_ERROR",
                 "OVERWRITTEN", "CONTENT_MISMATCH", "ARCHIVE_CRC_ERROR", "WRITE_VERIFY_FAILED"}
_BAD_CHARS = dict.fromkeys(map(ord, '<>:"/\\|?*'), "_")
_BAD_CHARS.update({i: "_" for i in range(32)})
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


class Options:
    def __init__(self, include_deleted=True, include_live=False, twin_repair=True, lock=True, verify=True,
                 image_first=False):
        self.include_deleted, self.include_live, self.twin_repair = include_deleted, include_live, twin_repair
        self.lock, self.verify, self.image_first = lock, verify, image_first


class RecoveryError(Exception):
    pass


class _Item:
    __slots__ = ("node", "volume", "category", "rel", "path", "status", "details", "sha", "bad", "magic", "notes")

    def __init__(self, node, volume, category, rel, path):
        self.node, self.volume, self.category, self.rel, self.path = node, volume, category, rel, path
        self.status, self.details, self.sha, self.bad, self.magic, self.notes = "", [], "", [], None, []


def long_path(p):
    p = os.path.abspath(p)
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def safe_name(name):
    name = name.translate(_BAD_CHARS).rstrip(" .")
    if not name:
        return "_"
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name[:240]


# -- Windows metadata -----------------------------------------------------------------------
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_k32.SetFileTime.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 3
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
_INVALID = wintypes.HANDLE(-1).value


def set_metadata(path, ctime, atime, mtime, attrs, is_dir=False):
    h = _k32.CreateFileW(path, 0x100, 7, None, 3, 0x02000000, None)
    if h and h != _INVALID:
        fts = [wintypes.FILETIME(v & 0xFFFFFFFF, v >> 32) if v and 0 < v < (1 << 63) else None
               for v in (ctime, atime, mtime)]
        _k32.SetFileTime(h, *[ctypes.byref(x) if x is not None else None for x in fts])
        _k32.CloseHandle(h)
    if attrs & 0x07:
        _k32.SetFileAttributesW(path, (attrs & 0x07) | (0x10 if is_dir else 0))


class Engine:
    def __init__(self, src, dest, options, emit, cancel, accessible=None):
        """``accessible``: offsets of the volumes Windows can open right now.  None means "work
        it out from the partition table", which is what an image file needs."""
        self.src, self.dest, self.opt, self.emit, self.cancel = src, dest, options, emit, cancel
        self.accessible = accessible
        self.items = []
        self.skipped_live = 0
        self.volumes = []

    # -- helpers --------------------------------------------------------------------------------
    def log(self, text):
        self.emit("log", text=text)

    def phase(self, key):
        self.emit("phase", key=key, text=t(key))

    def check(self):
        if self.cancel.is_set():
            raise Cancelled()

    # -- pipeline -------------------------------------------------------------------------------
    def run(self):
        t0 = time.time()
        total = self.analyze()
        free = shutil.disk_usage(self.dest).free
        if total + (64 << 20) > free:
            raise RecoveryError(t("err_space", need=human_size(total), free=human_size(free)))

        self.phase("ph_recover")
        self.extract(total)
        self.phase("ph_verify")
        self.verify()
        self.phase("ph_report")
        summary = self.report(time.time() - t0)
        if self.src.bad_bytes:
            self.log(t("log_bad", size=human_size(self.src.bad_bytes)))
        return summary

    def analyze(self):
        """Scan, rebuild the volumes and decide what will be recovered. Writes nothing.

        Returns the number of bytes the recovery will need in the destination.
        """
        self.phase("ph_scan")
        res = scanner.scan(self.src, lambda d, tot: self.emit("progress", done=d, total=tot, unit="bytes"), self.cancel)
        self.log(t("log_scan_done", mft=len(res.mft), fat=len(res.fat_dirs), exfat=len(res.exfat_sets),
                   boot=sum(len(v) for v in res.boot.values())))

        self.phase("ph_analyze")
        self.emit("progress", done=0, total=0, unit="")
        dbg = lambda m: self.emit("debug", text=m)
        for finder in (fat32.find_volumes, exfat.find_volumes):
            self.check()
            self.volumes += finder(self.src, res, dbg)
        self.volumes += ntfs.find_volumes(self.src, res, dbg, self.cancel)
        self.check()
        alloc, unknown = allocation.current_allocation(self.src, dbg)
        accessible = self.accessible if self.accessible is not None else allocation.accessible_starts(self.src)
        for v in self.volumes:
            if v.start not in accessible:
                # A filesystem nobody can open any more (lost partition, damaged boot sector):
                # none of its files are "still accessible", however healthy it looks inside.
                unlive(v)
            files, dirs = v.count()
            self.log(t("log_volume", fs=v.fs, files=files, dirs=dirs))

        self.plan()
        self.mark_overlaps(alloc, unknown)
        if not self.items:
            self.log(t("log_nothing"))
        total = sum(i.node.size for i in self.items if not i.node.is_dir)
        self.log(t("log_plan", n=sum(1 for i in self.items if not i.node.is_dir), size=human_size(total)))
        return total

    # -- planning -------------------------------------------------------------------------------
    def plan(self):
        used_top = {n.lower() for n in os.listdir(self.dest)} if os.path.isdir(self.dest) else set()

        def unique_top(name):
            base, k = name, 2
            while name.lower() in used_top:
                name = "%s (%d)" % (base, k)
                k += 1
            used_top.add(name.lower())
            return name

        index = 0
        for vol in self.volumes:
            before = len(self.items)
            title = "Volume %d - %s%s" % (index + 1, vol.fs, (" - " + safe_name(vol.label)) if vol.label else "")
            tops = {}
            taken = set()

            def out_path(category, rel_parts):
                if category not in tops:
                    suffix = {"main": "", "deleted": " (deleted)", "orphaned": " (orphaned)"}[category]
                    tops[category] = unique_top(title + suffix)
                return os.path.join(self.dest, tops[category], *rel_parts)

            def walk(node, parts, orphan, seen, depth):
                # Names are made unique per output tree; live entries are handled first so that
                # a deleted namesake can never push an existing file off its real name.
                dir_names, file_names = set(), {"main": set(), "deleted": set(), "orphaned": set()}
                for ch in sorted(node.children, key=lambda c: c.deleted):
                    if id(ch) in seen or depth > 200:
                        continue
                    seen.add(id(ch))
                    kind = "deleted" if ch.deleted else "orphaned" if orphan else "main"
                    name = safe_name(ch.name)
                    base, k = name, 2
                    while name.lower() in dir_names or (not ch.is_dir and name.lower() in file_names[kind]):
                        stem, dot, ext = base.rpartition(".")
                        name = "%s (%d).%s" % (stem, k, ext) if dot and not ch.is_dir else "%s (%d)" % (base, k)
                        k += 1
                    (dir_names if ch.is_dir else file_names[kind]).add(name.lower())
                    rel = parts + [name]
                    if ch.is_dir:
                        if not ch.deleted and not (ch.live and not self.opt.include_live):
                            cat = "orphaned" if orphan else "main"
                            self.items.append(_Item(ch, vol, cat, rel, out_path(cat, rel)))
                        walk(ch, rel, orphan, seen, depth + 1)
                        continue
                    if ch.live and not self.opt.include_live:
                        self.skipped_live += 1
                        continue
                    if ch.deleted and not self.opt.include_deleted:
                        continue
                    cat = "deleted" if ch.deleted else "orphaned" if orphan else "main"
                    path = out_path(cat, rel)
                    key = path.lower()
                    if key in taken:
                        continue
                    taken.add(key)
                    self.items.append(_Item(ch, vol, cat, rel, path))

            seen = set()
            walk(vol.root, [], False, seen, 0)
            walk(vol.orphans, [], True, seen, 0)
            if any(not i.node.is_dir for i in self.items[before:]):
                vol.title = title
                index += 1
            else:
                del self.items[before:]                 # nothing to recover from this volume
                for name in tops.values():
                    used_top.discard(name.lower())

    # -- extraction -----------------------------------------------------------------------------
    def mark_overlaps(self, alloc, unknown):
        """Which bytes of each lost file does something newer sit on?"""
        for it in self.items:
            n = it.node
            if n.is_dir or n.live:
                continue
            pos, maybe = 0, 0
            for off, ln in n.extents:
                if off is not None:
                    if alloc:
                        it.bad += [(pos + s - off, pos + e - off) for s, e in alloc.overlaps(off, ln)]
                    if unknown:
                        maybe += sum(e - s for s, e in unknown.overlaps(off, ln))
                pos += ln
            if it.bad:
                it.notes.append("OVERWRITTEN:%d/%d" % (sum(e - s for s, e in it.bad), n.size))
            if maybe:
                it.notes.append("MAYBE_OVERWRITTEN:%d/%d" % (maybe, n.size))

    def extract(self, total):
        done = 0
        dirs = [i for i in self.items if i.node.is_dir]
        for it in dirs:
            try:
                os.makedirs(long_path(it.path), exist_ok=True)
            except OSError as ex:
                it.details.append("MKDIR_FAILED:%s" % ex)
        last = 0.0
        for it in self.items:
            n = it.node
            if n.is_dir:
                continue
            self.check()
            self.extract_one(it)
            done += n.size
            now = time.time()
            if now - last > 0.1:
                last = now
                self.emit("progress", done=done, total=total, unit="bytes", text=it.rel[-1])
        self.emit("progress", done=total, total=total, unit="bytes")
        for it in reversed(dirs):                       # directory times last, children would bump them
            n = it.node
            set_metadata(long_path(it.path), n.ctime, n.atime, n.mtime, n.attrs, True)

    def extract_one(self, it):
        n, src = it.node, self.src
        it.details = list(n.flags) + it.notes
        if "COMPRESSED" in n.flags:
            it.status = UNSUPPORTED
            return
        if n.size > src.size:
            it.status = SKIPPED
            it.details.append("INVALID_SIZE")
            return
        if n.size and n.resident is None and not any(off is not None for off, _ in n.extents):
            it.status = SKIPPED
            it.details.append("NO_DATA_LOCATION")
            return
        sha, head, written, bad_before = hashlib.sha256(), b"", 0, src.bad_bytes
        try:
            os.makedirs(long_path(os.path.dirname(it.path)), exist_ok=True)
            with open(long_path(it.path), "wb") as f:
                if n.resident is not None:
                    data = n.resident[:n.size]
                    f.write(data)
                    sha.update(data)
                    head, written = data[:16], len(data)
                else:
                    for off, ln in n.extents:
                        left = min(ln, n.size - written)
                        while left > 0:
                            step = min(left, IO_CHUNK)
                            data = b"\0" * step if off is None else src.read_raw(off, step)
                            if len(data) < step:
                                data += b"\0" * (step - len(data))
                            f.write(data)
                            sha.update(data)
                            if not head:
                                head = data[:16]
                            written += step
                            left -= step
                            if off is not None:
                                off += step
                            if self.cancel.is_set():
                                raise Cancelled()
                    if written < n.size:
                        it.details.append("TRUNCATED")
                        pad = n.size - written
                        f.seek(n.size - 1)
                        f.write(b"\0")
                        for _ in range(pad // IO_CHUNK):
                            sha.update(b"\0" * IO_CHUNK)
                        sha.update(b"\0" * (pad % IO_CHUNK))
            set_metadata(long_path(it.path), n.ctime, n.atime, n.mtime, n.attrs)
        except Cancelled:
            raise
        except OSError as ex:
            it.status = SKIPPED
            it.details.append("WRITE_FAILED:%s" % ex)
            return
        if src.bad_bytes != bad_before:
            it.details.append("READ_ERROR")
        it.sha = sha.hexdigest()
        it.magic = magic_matches(n.name, head) if n.size else None
        if it.magic is False:
            it.details.append("CONTENT_MISMATCH")

    # -- verification and repair ----------------------------------------------------------------
    def verify(self):
        files = [i for i in self.items if not i.node.is_dir and not i.status]
        total = sum(i.node.size for i in files) or 1
        done, last = 0, 0.0
        archive_ok = set()
        for it in files:
            self.check()
            p = long_path(it.path)
            if self.opt.verify:
                h = hashlib.sha256()
                try:
                    with open(p, "rb") as f:
                        for b in iter(lambda: f.read(IO_CHUNK), b""):
                            h.update(b)
                    if h.hexdigest() != it.sha:
                        it.details.append("WRITE_VERIFY_FAILED")
                except OSError:
                    it.details.append("WRITE_VERIFY_FAILED")
                ext = it.node.name.rsplit(".", 1)[-1].lower()
                if ext in _ARCHIVE_EXT and it.node.size and not it.node.name.startswith("~$") and it.magic is not False:
                    try:
                        with zipfile.ZipFile(p) as z:
                            if z.testzip() is None:
                                archive_ok.add(id(it))
                            else:
                                it.details.append("ARCHIVE_CRC_ERROR")
                    except Cancelled:
                        raise
                    except Exception:
                        it.details.append("ARCHIVE_CRC_ERROR")
            done += it.node.size
            now = time.time()
            if now - last > 0.1:
                last = now
                self.emit("progress", done=done, total=total, unit="bytes", text=it.rel[-1])

        for it in files:
            flags = {d.split(":")[0] for d in it.details}
            proven = id(it) in archive_ok or (it.magic is True and "CHAIN_GUESSED" not in flags)
            if flags & _DAMAGE_FLAGS:
                it.status = DAMAGED
            elif (it.node.deleted or "CHAIN_GUESSED" in flags) and not proven and it.node.size:
                it.status = UNCERTAIN
            elif "MAYBE_OVERWRITTEN" in flags and id(it) not in archive_ok:
                it.status = UNCERTAIN       # under a partition we cannot inspect; a header check is not proof
            else:
                it.status = OK
        if self.opt.twin_repair:
            self.repair_from_twins(files)
        self.emit("progress", done=total, total=total, unit="bytes")

    def repair_from_twins(self, files):
        good = defaultdict(list)
        for it in files:
            if it.status == OK and it.node.size:
                good[it.node.size].append(it)
        block = 65536
        for it in files:
            if it.status != DAMAGED or not it.bad or not it.node.size:
                continue
            self.check()
            size, name = it.node.size, it.node.name.lower()
            cands = sorted(good.get(size, ()), key=lambda c: c.node.name.lower() != name)
            bad_blocks = set()
            for s, e in it.bad:
                bad_blocks.update(range(s // block, (e - 1) // block + 1))
            total_blocks = -(-size // block)
            twin, how = None, None
            if len(bad_blocks) < total_blocks:              # compare everything that was not overwritten
                for c in cands[:50]:
                    try:
                        with open(long_path(it.path), "rb") as a, open(long_path(c.path), "rb") as b:
                            same, i = True, 0
                            while same:
                                x, y = a.read(block), b.read(block)
                                if not x:
                                    break
                                if i not in bad_blocks and x != y:
                                    same = False
                                i += 1
                    except OSError:
                        continue
                    if same:
                        twin, how = c, REPAIRED
                        break
            else:                                           # nothing left to compare: name + size + time
                for c in cands:
                    if c.node.name.lower() == name and c.node.mtime == it.node.mtime and it.node.mtime:
                        twin, how = c, FILLED_FROM_TWIN
                        break
            if twin is None:
                continue
            try:
                p = long_path(it.path)
                _k32.SetFileAttributesW(p, 0x80)
                shutil.copyfile(long_path(twin.path), p)
                n = it.node
                set_metadata(p, n.ctime, n.atime, n.mtime, n.attrs)
                it.sha, it.status = twin.sha, how
                it.details.append("TWIN:" + os.path.join(twin.volume.title, *twin.rel))
            except OSError as ex:
                it.details.append("TWIN_COPY_FAILED:%s" % ex)

    # -- report ---------------------------------------------------------------------------------
    def report(self, elapsed):
        rdir = os.path.join(self.dest, REPORT_DIR)
        if os.path.exists(rdir):
            rdir += time.strftime(" %Y-%m-%d %H-%M-%S")
        os.makedirs(rdir, exist_ok=True)
        files = [i for i in self.items if not i.node.is_dir]
        counts = Counter(i.status for i in files)
        with open(os.path.join(rdir, "report.csv"), "w", newline="", encoding="utf-8-sig") as fo:
            w = csv.writer(fo, delimiter=";")
            w.writerow(["volume", "category", "path", "size", "modified", "status", "details", "sha256"])
            for it in self.items:
                n = it.node
                w.writerow([it.volume.title, it.category, "\\".join(it.rel) + ("\\" if n.is_dir else ""),
                            "" if n.is_dir else n.size, filetime_to_text(n.mtime),
                            "FOLDER" if n.is_dir else it.status, " ".join(it.details), it.sha])
        attention = [i for i in files if i.status not in (OK,)]
        with open(os.path.join(rdir, "needs-attention.txt"), "w", encoding="utf-8") as fo:
            for it in attention:
                fo.write("%s\t%s\t%s\\%s\n" % (it.status, " ".join(it.details), it.volume.title, "\\".join(it.rel)))
        recovered = sum(counts[s] for s in (OK, REPAIRED, FILLED_FROM_TWIN, UNCERTAIN, DAMAGED))
        size = sum(i.node.size for i in files if i.status not in (SKIPPED, UNSUPPORTED))
        summary = dict(recovered=recovered, ok=counts[OK], repaired=counts[REPAIRED] + counts[FILLED_FROM_TWIN],
                       uncertain=counts[UNCERTAIN], damaged=counts[DAMAGED],
                       skipped=counts[SKIPPED] + counts[UNSUPPORTED], live_skipped=self.skipped_live,
                       size=size, elapsed=elapsed, dest=self.dest, report_dir=rdir,
                       report=os.path.join(rdir, "report.csv"), bad_bytes=self.src.bad_bytes,
                       volumes=[(v.title, v.fs) for v in self.volumes if hasattr(v, "title")],
                       categories={c: dict(Counter(i.status for i in files if i.category == c))
                                   for c in ("main", "orphaned", "deleted")})
        lines = ["%s %s" % (APP_NAME, __version__), time.strftime("%Y-%m-%d %H:%M:%S"), "",
                 "Source: %s" % self.src.label, ""]
        for key, field in (("sum_recovered", "recovered"), ("sum_ok", "ok"), ("sum_repaired", "repaired"),
                           ("sum_uncertain", "uncertain"), ("sum_damaged", "damaged"), ("sum_skipped", "skipped"),
                           ("sum_live_skipped", "live_skipped")):
            lines.append("%-48s %d" % (t(key) + ":", summary[field]))
        lines += ["%-48s %s" % (t("sum_size") + ":", human_size(size)),
                  "%-48s %s" % (t("sum_time") + ":", format_duration(elapsed)), "",
                  "Status codes / Durum kodları",
                  "  OK                intact / sorunsuz",
                  "  REPAIRED          damaged blocks refilled from a byte-verified identical copy /",
                  "                    hasarlı bloklar, bayt bayt doğrulanmış özdeş kopyadan dolduruldu",
                  "  FILLED_FROM_TWIN  fully overwritten; replaced by a copy with the same name, size and time /",
                  "                    tamamen ezilmiş; adı, boyutu ve tarihi aynı kopya yerine kondu",
                  "  UNCERTAIN         recovered, integrity cannot be proven (deleted or guessed layout) /",
                  "                    kurtarıldı, bütünlük kanıtlanamıyor (silinmiş ya da tahmini yerleşim)",
                  "  DAMAGED           evidence of corruption, see details / bozulma kanıtı var, ayrıntılara bakın",
                  "  UNSUPPORTED       NTFS-compressed file / NTFS sıkıştırılmış dosya",
                  "  SKIPPED           could not be recovered / kurtarılamadı"]
        with open(os.path.join(rdir, "summary.txt"), "w", encoding="utf-8") as fo:
            fo.write("\n".join(lines) + "\n")
        return summary


def unlive(volume):
    """Mark every node of a volume as not belonging to an accessible filesystem."""
    stack, seen = [volume.root, volume.orphans], set()
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        n.live = False
        if n.is_dir:
            stack.extend(n.children)


def format_duration(sec):
    sec = int(sec)
    return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


def create_image(src, path, emit, cancel):
    """Sector-by-sector copy of the source into a file."""
    done, last = 0, 0.0
    with open(long_path(path), "wb") as out:
        while done < src.size:
            if cancel.is_set():
                raise Cancelled()
            data = src.read_raw(done, min(IO_CHUNK * 4, src.size - done))
            if not data:
                break
            out.write(data)
            done += len(data)
            if time.time() - last > 0.1:
                last = time.time()
                emit("progress", done=done, total=src.size, unit="bytes")
    return path


def run_recovery(source, dest, options, emit, cancel):
    """Top-level entry used by both the GUI and the command line.

    ``source`` is a disk dict from ``disks.list_disks()`` or ``{"image": path}``.
    The disk is write-protected for the duration and the protection is always released again.

    A disk dict may carry ``"region": {"offset", "size", "label", "filesystem"}`` to restrict
    the work to one partition or one stretch of unallocated space.  Only that window is
    scanned, which is much faster than scanning the whole disk.
    """
    is_disk = "number" in source
    region = source.get("region")
    if is_disk and disks.fake_mode():
        raise RecoveryError(t("err_demo"))
    os.makedirs(dest, exist_ok=True)
    if is_disk:
        all_disks = disks.list_disks()
        if disks.disk_of_path(dest, all_disks) == source["number"]:
            raise RecoveryError(t("err_same_disk"))
    locked, src = False, None
    try:
        if is_disk and options.lock:
            if source.get("system"):
                emit("log", text=t("log_no_lock_system"))
            else:
                emit("phase", key="ph_lock", text=t("ph_lock"))
                locked, err = disks.lock_disk(source)
                if locked:
                    emit("log", text=t("log_locked", n=source["number"]))
                elif err:
                    emit("log", text=t("log_lock_failed", err=err))
        if is_disk:
            label = "Disk %d - %s (%s)" % (source["number"], source.get("name", ""), human_size(source["size"]))
            if region:
                label += " / %s (%s)" % (region.get("label", ""), human_size(region["size"]))
                src = Source(source["path"], region["size"], source.get("sector") or 512, label, base=region["offset"])
                # the window starts at the partition: it is accessible only if Windows reads it
                accessible = {0} if region.get("filesystem") else set()
            else:
                src = Source(source["path"], source["size"], source.get("sector") or 512, label)
                accessible = {p["offset"] for p in source.get("partitions", ()) if p.get("filesystem")}
        elif region:
            src = Source(source["image"], region["size"], label="%s @ %d" % (source["image"], region["offset"]),
                         base=region["offset"])
            accessible = None
        else:
            src = Source(source["image"], label=source["image"])
            accessible = None
        if options.image_first and is_disk:
            free = shutil.disk_usage(dest).free
            if src.size + (64 << 20) > free:
                raise RecoveryError(t("err_space", need=human_size(src.size), free=human_size(free)))
            emit("phase", key="ph_image", text=t("ph_image"))
            image = create_image(src, os.path.join(dest, "disk-%d%s.img" % (
                source["number"], "-part" if region else "")), emit, cancel)
            bad = src.bad_bytes
            src.close()
            src = Source(image, label=label)
            src.bad_bytes = bad
        return Engine(src, dest, options, emit, cancel, accessible).run()
    except SourceLost:
        raise RecoveryError(t("err_source_lost")) from None
    finally:
        if src is not None:
            src.close()
        if locked:
            emit("phase", key="ph_unlock", text=t("ph_unlock"))
            # If the disk is gone this fails; the record stays and the next start offers to unlock it.
            ok, err = disks.unlock_disk(source["number"], source.get("serial"))
            emit("log", text=t("log_unlocked", n=source["number"]) if ok
                 else t("log_unlock_failed", n=source["number"], err=err))
