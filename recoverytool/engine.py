"""The recovery pipeline: lock -> (image) -> scan -> rebuild -> extract -> verify/repair -> report -> unlock."""

from __future__ import annotations

import contextlib
import csv
import ctypes
import errno
import hashlib
import os
import shutil
import time
import zipfile
from collections import Counter, defaultdict
from ctypes import wintypes

from . import APP_NAME, __version__, allocation, disks, exfat, fat32, ntfs, scanner, session
from .i18n import t
from .model import (DAMAGED, FILLED_FROM_TWIN, OK, RECOVERED, REPAIRED, SKIPPED, UNCERTAIN, UNSUPPORTED, Cancelled,
                    Intervals, Item, filetime_to_text, human_size, is_pending)
from .signatures import ARCHIVE_EXT as _ARCHIVE_EXT, magic_matches
from .source import Source, SourceLost

REPORT_DIR = "RecoveryTool-Report"
IO_CHUNK = 4 * 1024 * 1024
RESERVE = 64 << 20          # free space that is never used up in the destination
ANALYZE_STEPS = 3                 # counted steps of the "rebuilding folder structure" phase
NOT_RECOVERED = "NOT_RECOVERED"   # report only: selected, but the destination was full

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


class _NoSpace(Exception):
    """The destination filled up while a file was being written."""


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
        self.titles = None          # [(title, fs)] when the catalogue comes from a saved scan
        self.session = None         # saved scan to keep up to date while recovering
        self.top_names = {}         # top folder of the catalogue -> its name inside this destination
        self.scan_state = None      # ScanResult of an interrupted scan to continue
        self.checkpoint = None      # called with the ScanResult now and then during the scan
        self.free_bytes = lambda: shutil.disk_usage(self.dest).free
        self._dirmap = None
        self._step_t = 0.0

    def step(self, key, done=0, total=0, n=None):
        """Progress of one step of rebuilding the folder structure, counted in records/files.

        ``n`` numbers the steps that have a counter; the others only say what is going on."""
        now = time.monotonic()
        if total and 0 < done < total and now - self._step_t < 0.25:
            return
        self._step_t = now
        text = t("st_count", n=n, of=ANALYZE_STEPS, what=t(key)) if n else t(key)
        self.emit("progress", done=done, total=total, unit="records", stage=key, text=text)

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
        """Scan and recover everything that fits, in one go."""
        self.analyze()
        return self.recover()

    def analyze(self):
        """Scan, rebuild the volumes and build the catalogue of what can be recovered. Writes nothing.

        Returns the number of bytes a recovery of everything would need in the destination.
        """
        self.phase("ph_scan")
        res = self.scan_state or scanner.ScanResult()
        self.src.bad_bytes += res.bad_bytes

        def progress(done, total):
            self.emit("progress", done=done, total=total, unit="bytes", stats=dict(
                mft=len(res.mft), fat=len(res.fat_dirs), exfat=len(res.exfat_sets),
                boot=sum(len(v) for v in res.boot.values()), bad=self.src.bad_bytes))
        scanner.scan(self.src, progress, self.cancel, res, self.checkpoint)
        self.log(t("log_scan_done", mft=len(res.mft), fat=len(res.fat_dirs), exfat=len(res.exfat_sets),
                   boot=sum(len(v) for v in res.boot.values())))

        self.phase("ph_analyze")
        self.step("st_fat")
        dbg = lambda m: self.emit("debug", text=m)
        for finder in (fat32.find_volumes, exfat.find_volumes):
            self.check()
            self.volumes += finder(self.src, res, dbg)
        self.step("st_records", 0, max(len(res.mft), 1), n=1)
        self.volumes += ntfs.find_volumes(self.src, res, dbg, self.cancel,
                                          lambda done, total: self.step("st_records", done, total, n=1))
        self.check()
        self.step("st_alloc")
        alloc, unknown = allocation.current_allocation(self.src, dbg)
        accessible = self.accessible if self.accessible is not None else allocation.accessible_starts(self.src)
        found, nodes = [], 0
        for v in self.volumes:
            if v.start not in accessible:
                # A filesystem nobody can open any more (lost partition, damaged boot sector):
                # none of its files are "still accessible", however healthy it looks inside.
                unlive(v)
            files, dirs = v.count()
            found.append((v.fs, v.label, files, dirs))
            nodes += files + dirs
            self.log(t("log_volume", fs=v.fs, files=files, dirs=dirs))
        self.emit("volumes", found=found)

        self.plan(nodes)
        self.mark_overlaps(alloc, unknown)
        hopeless = 0
        for it in self.items:
            if not it.node.is_dir:
                why = self.unrecoverable(it.node)
                if why:                                 # known now: do not count it, do not offer it
                    it.status, it.details = why[0], list(it.node.flags) + it.notes + why[1]
                    hopeless += 1
        if not self.items:
            self.log(t("log_nothing"))
        todo = [i for i in self.items if not i.node.is_dir and not i.status]
        total = sum(i.node.size for i in todo)
        self.log(t("log_plan", n=len(todo), size=human_size(total)))
        if hopeless:
            self.log(t("log_hopeless", n=hopeless))
        if total > self.src.size:
            # More data than the source can hold: say where the excess comes from, so that the
            # user can decide what to leave out instead of looking for that much free space.
            ranges = [(off, off + ln) for i in todo for off, ln in i.node.extents if off is not None]
            mapped = sum(e - s for s, e in ranges)
            unique = Intervals(ranges).total()
            self.log(t("log_oversize", total=human_size(total), src=human_size(self.src.size),
                       unique=human_size(unique), shared=human_size(max(mapped - unique, 0)),
                       deleted=human_size(sum(i.node.size for i in todo if i.category == "deleted"))))
        return total

    def unrecoverable(self, n):
        """(status, [detail]) for a file that cannot be read back at all, else None."""
        if "COMPRESSED" in n.flags:
            return UNSUPPORTED, []
        if n.size > self.src.size:
            return SKIPPED, ["INVALID_SIZE"]
        if n.size and n.resident is None and not any(off is not None for off, _ in n.extents):
            return SKIPPED, ["NO_DATA_LOCATION"]
        return None

    # -- planning -------------------------------------------------------------------------------
    def plan(self, nodes=0):
        """``nodes``: files and folders in all volumes, only used to show how far along it is."""
        used_top = set()
        visited = [0]
        self.step("st_plan", 0, max(nodes, 1), n=2)

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

            def top_of(category):
                if category not in tops:
                    suffix = {"main": "", "deleted": " (deleted)", "orphaned": " (orphaned)"}[category]
                    tops[category] = unique_top(title + suffix)
                return tops[category]

            def walk(node, parts, orphan, seen, depth):
                # Names are made unique per output tree; live entries are handled first so that
                # a deleted namesake can never push an existing file off its real name.
                dir_names, file_names = set(), {"main": set(), "deleted": set(), "orphaned": set()}
                for ch in sorted(node.children, key=lambda c: c.deleted):
                    if id(ch) in seen or depth > 200:
                        continue
                    seen.add(id(ch))
                    visited[0] += 1
                    if visited[0] & 1023 == 0:
                        self.step("st_plan", visited[0], max(nodes, visited[0]), n=2)
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
                            self.items.append(Item(ch, vol, cat, top_of(cat), rel))
                        walk(ch, rel, orphan, seen, depth + 1)
                        continue
                    if ch.live and not self.opt.include_live:
                        self.skipped_live += 1
                        continue
                    if ch.deleted and not self.opt.include_deleted:
                        continue
                    cat = "deleted" if ch.deleted else "orphaned" if orphan else "main"
                    key = (cat, "\\".join(rel).lower())
                    if key in taken:
                        continue
                    taken.add(key)
                    self.items.append(Item(ch, vol, cat, top_of(cat), rel))

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
        for i, it in enumerate(self.items):
            it.id = i
        self.step("st_plan", max(nodes, visited[0], 1), max(nodes, visited[0], 1), n=2)

    # -- extraction -----------------------------------------------------------------------------
    def mark_overlaps(self, alloc, unknown):
        """Which bytes of each lost file does something newer sit on?"""
        total = len(self.items)
        for k, it in enumerate(self.items):
            if k & 1023 == 0:
                self.step("st_check", k, max(total, 1), n=3)
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
        self.step("st_check", total, max(total, 1), n=3)

    def recover(self, items=None):
        """Write catalogue files into the destination; by default everything not recovered yet.

        Lack of space is not an error: every file is finished (written, verified, recorded) on
        its own, and a file that does not fit simply stays pending.  The caller can free some
        space, or pick another destination, and call this again for the rest.
        """
        t0, paused = time.time(), getattr(self.cancel, "paused_seconds", 0.0)
        os.makedirs(self.dest, exist_ok=True)
        everything = items is None
        if everything:
            files = [i for i in self.items if not i.node.is_dir and is_pending(i)]
            dirs = [i for i in self.items if i.node.is_dir]
        else:
            files = [i for i in items if not i.node.is_dir]
            dirs = self.parents_of(files)
        self.name_tops(files + dirs)

        self.phase("ph_recover")
        done, waiting, stopped = self.extract(files, dirs, everything)
        if not stopped and self.opt.twin_repair:
            self.phase("ph_verify")
            changed = self.repair_from_twins(done)
            if self.session:
                for it in changed:
                    self.session.save(it)
            if changed:
                self.emit("items", items=changed)
        self.phase("ph_report")
        elapsed = time.time() - t0 - (getattr(self.cancel, "paused_seconds", 0.0) - paused)
        summary = self.report(elapsed, done, dirs, waiting, stopped)
        if self.session:
            self.session.flush()
        if waiting:
            self.log(t("log_no_space", n=len(waiting), size=human_size(summary["no_space_size"])))
        if self.src.bad_bytes:
            self.log(t("log_bad", size=human_size(self.src.bad_bytes)))
        return summary

    def parents_of(self, files):
        """The catalogue folders above the given files, parents first."""
        if self._dirmap is None:
            self._dirmap = {(i.top, tuple(i.rel)): i for i in self.items if i.node.is_dir}
        seen, out = set(), []
        for f in files:
            rel = tuple(f.rel[:-1])
            while rel and (f.top, rel) not in seen:
                seen.add((f.top, rel))
                d = self._dirmap.get((f.top, rel))
                if d is not None:
                    out.append(d)
                rel = rel[:-1]
        out.sort(key=lambda i: len(i.rel))
        return out

    def name_tops(self, items):
        """Give each top folder a name that does not collide with what is already in the destination.

        Names used before in this destination (``top_names``) are kept, so that a later run adds
        to the same folders instead of starting "Volume 1 (2)".
        """
        used = {n.lower() for n in os.listdir(self.dest)} | {v.lower() for v in self.top_names.values()}
        for it in items:
            if it.top not in self.top_names:
                name, k = it.top, 2
                while name.lower() in used:
                    name = "%s (%d)" % (it.top, k)
                    k += 1
                used.add(name.lower())
                self.top_names[it.top] = name

    def out_path(self, it):
        return os.path.join(self.dest, self.top_names[it.top], *it.rel)

    def extract(self, files, dirs, make_dirs):
        """Returns (files handled, files that did not fit, stopped by the user)."""
        total = sum(i.node.size for i in files)
        for it in dirs:
            it.path, it.details = self.out_path(it), []
            if make_dirs:                               # otherwise folders appear with their first file
                try:
                    os.makedirs(long_path(it.path), exist_ok=True)
                except OSError as ex:
                    it.details.append("MKDIR_FAILED:%s" % ex)
        done, waiting, batch, counts = [], [], [], Counter()
        pos = seen = waiting_size = 0
        free, checked, last, flushed = self.free_bytes(), time.time(), 0.0, time.time()
        stopped = False

        def tell(name):
            self.emit("progress", done=pos, total=total, unit="bytes", text=name, stats=dict(
                files=seen, files_total=len(files), counts=dict(counts), waiting=len(waiting),
                waiting_size=waiting_size, free=free, bad=self.src.bad_bytes))
            if batch:
                self.emit("items", items=batch[:])
                del batch[:]

        try:
            for it in files:
                self.check()
                n = it.node
                now = time.time()
                if n.size + RESERVE > free or now - checked > 2:
                    free, checked = self.free_bytes(), now
                if n.size + RESERVE > free and not self.unrecoverable(n):
                    waiting.append(it)                  # stays pending; smaller files may still fit
                    waiting_size += n.size
                else:
                    it.path = self.out_path(it)
                    try:
                        self.extract_one(it)
                        if not it.status:
                            self.settle(it)
                    except _NoSpace:
                        it.path = ""
                        waiting.append(it)
                        waiting_size += n.size
                        free, checked = self.free_bytes(), time.time()
                    except Cancelled:
                        self.discard(it.path)           # never leave half a file behind
                        it.path = it.status = ""
                        raise
                    else:
                        if it.status in RECOVERED:
                            free -= n.size
                        else:
                            it.path = ""
                        done.append(it)
                        batch.append(it)
                        counts[it.status] += 1
                        if self.session:
                            self.session.save(it)
                pos += n.size
                seen += 1
                now = time.time()
                if now - last > 0.1:
                    last = now
                    tell(it.rel[-1])
                    if self.session and now - flushed > 3:
                        self.session.flush()
                        flushed = now
        except Cancelled:
            stopped = True
        if not stopped:
            pos = total
        tell("")
        for it in reversed(dirs):                       # directory times last, children would bump them
            n, p = it.node, long_path(it.path)
            if os.path.isdir(p):
                set_metadata(p, n.ctime, n.atime, n.mtime, n.attrs, True)
        return done, waiting, stopped

    @staticmethod
    def discard(path):
        if path:
            try:
                _k32.SetFileAttributesW(long_path(path), 0x80)
                os.remove(long_path(path))
            except OSError:
                pass

    @staticmethod
    def _create(path):
        try:
            return open(path, "wb")
        except PermissionError:                         # a read-only copy from an earlier run
            _k32.SetFileAttributesW(path, 0x80)
            return open(path, "wb")

    def extract_one(self, it):
        """Write one file.  Leaves ``status`` empty on success; ``settle`` decides it afterwards."""
        n, src = it.node, self.src
        it.status, it.sha, it.proven, it.magic = "", "", False, None
        it.details = list(n.flags) + it.notes
        why = self.unrecoverable(n)
        if why:
            it.status = why[0]
            it.details += why[1]
            return
        sha, head, written, bad_before = hashlib.sha256(), b"", 0, src.bad_bytes
        try:
            os.makedirs(long_path(os.path.dirname(it.path)), exist_ok=True)
            with self._create(long_path(it.path)) as f:
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
        except OSError as ex:
            self.discard(it.path)
            if ex.errno == errno.ENOSPC or getattr(ex, "winerror", 0) in (39, 112):
                raise _NoSpace() from None
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
    def settle(self, it):
        """Read the written file back, test what can be tested, and decide its final status."""
        p = long_path(it.path)
        if self.opt.verify:
            h = hashlib.sha256()
            try:
                with open(p, "rb") as f:
                    for b in iter(lambda: f.read(IO_CHUNK), b""):
                        h.update(b)
                        if self.cancel.is_set():
                            raise Cancelled()
                if h.hexdigest() != it.sha:
                    it.details.append("WRITE_VERIFY_FAILED")
            except OSError:
                it.details.append("WRITE_VERIFY_FAILED")
            ext = it.node.name.rsplit(".", 1)[-1].lower()
            if ext in _ARCHIVE_EXT and it.node.size and not it.node.name.startswith("~$") and it.magic is not False:
                try:
                    with zipfile.ZipFile(p) as z:
                        if z.testzip() is None:
                            it.proven = True
                        else:
                            it.details.append("ARCHIVE_CRC_ERROR")
                except Cancelled:
                    raise
                except Exception:
                    it.details.append("ARCHIVE_CRC_ERROR")
        flags = {d.split(":")[0] for d in it.details}
        proven = it.proven or (it.magic is True and "CHAIN_GUESSED" not in flags)
        if flags & _DAMAGE_FLAGS:
            it.status = DAMAGED
        elif (it.node.deleted or "CHAIN_GUESSED" in flags) and not proven and it.node.size:
            it.status = UNCERTAIN
        elif "MAYBE_OVERWRITTEN" in flags and not it.proven:
            it.status = UNCERTAIN           # under a partition we cannot inspect; a header check is not proof
        else:
            it.status = OK

    def repair_from_twins(self, files):
        """Refill damaged files from identical intact copies.  Returns the files that changed."""
        wanted = {it.node.size for it in files if it.status == DAMAGED and it.bad and it.node.size}
        good, changed = defaultdict(list), []
        if not wanted:
            return changed
        for it in self.items:
            if it.status == OK and it.path and it.node.size in wanted and not it.node.is_dir:
                good[it.node.size].append(it)
        block = 65536
        for it in files:
            if it.status != DAMAGED or not it.bad or not it.node.size:
                continue
            if self.cancel.is_set():
                break
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
            changed.append(it)
        return changed

    # -- report ---------------------------------------------------------------------------------
    def report(self, elapsed, files, dirs, waiting, stopped):
        """Write the report of this run: ``files`` were handled, ``waiting`` did not fit."""
        rdir = os.path.join(self.dest, REPORT_DIR)
        if os.path.exists(rdir):
            rdir += time.strftime(" %Y-%m-%d %H-%M-%S")
        os.makedirs(rdir, exist_ok=True)
        counts = Counter(i.status for i in files)
        held = {id(i) for i in waiting}
        rows = sorted(dirs + files + waiting, key=lambda i: i.id)
        with open(os.path.join(rdir, "report.csv"), "w", newline="", encoding="utf-8-sig") as fo:
            w = csv.writer(fo, delimiter=";")
            w.writerow(["volume", "category", "path", "size", "modified", "status", "details", "sha256"])
            for it in rows:
                n = it.node
                status, details, sha = ("FOLDER" if n.is_dir else it.status), " ".join(it.details), it.sha
                if id(it) in held:
                    status, details, sha = NOT_RECOVERED, "NO_SPACE", ""
                w.writerow([it.volume.title, it.category, "\\".join(it.rel) + ("\\" if n.is_dir else ""),
                            "" if n.is_dir else n.size, filetime_to_text(n.mtime), status, details, sha])
        attention = [i for i in files if i.status not in (OK,)]
        with open(os.path.join(rdir, "needs-attention.txt"), "w", encoding="utf-8") as fo:
            for it in attention:
                fo.write("%s\t%s\t%s\\%s\n" % (it.status, " ".join(it.details), it.volume.title, "\\".join(it.rel)))
            for it in waiting:
                fo.write("%s\tNO_SPACE\t%s\\%s\n" % (NOT_RECOVERED, it.volume.title, "\\".join(it.rel)))
        recovered = sum(counts[s] for s in RECOVERED)
        size = sum(i.node.size for i in files if i.status in RECOVERED)
        left = [i for i in self.items if not i.node.is_dir and is_pending(i)]
        summary = dict(recovered=recovered, ok=counts[OK], repaired=counts[REPAIRED] + counts[FILLED_FROM_TWIN],
                       uncertain=counts[UNCERTAIN], damaged=counts[DAMAGED],
                       skipped=counts[SKIPPED] + counts[UNSUPPORTED], live_skipped=self.skipped_live,
                       size=size, elapsed=elapsed, dest=self.dest, report_dir=rdir,
                       report=os.path.join(rdir, "report.csv"), bad_bytes=self.src.bad_bytes,
                       no_space=len(waiting), no_space_size=sum(i.node.size for i in waiting), stopped=stopped,
                       pending=len(left), pending_size=sum(i.node.size for i in left),
                       session=self.session.path if self.session else None,
                       volumes=self.titles or [(v.title, v.fs) for v in self.volumes if hasattr(v, "title")],
                       categories={c: dict(Counter(i.status for i in files if i.category == c))
                                   for c in ("main", "orphaned", "deleted")})
        lines = ["%s %s" % (APP_NAME, __version__), time.strftime("%Y-%m-%d %H:%M:%S"), "",
                 "Source: %s" % self.src.label, ""]
        for key, field in (("sum_recovered", "recovered"), ("sum_ok", "ok"), ("sum_repaired", "repaired"),
                           ("sum_uncertain", "uncertain"), ("sum_damaged", "damaged"), ("sum_skipped", "skipped"),
                           ("sum_live_skipped", "live_skipped"), ("sum_no_space", "no_space"),
                           ("sum_pending", "pending")):
            lines.append("%-48s %d" % (t(key) + ":", summary[field]))
        if stopped:
            lines.append(t("sum_stopped"))
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
                  "  SKIPPED           could not be recovered / kurtarılamadı",
                  "  NOT_RECOVERED     selected, but the destination was full; still in the saved scan /",
                  "                    seçildi ama hedefte yer kalmadı; kayıtlı taramada bekliyor"]
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


@contextlib.contextmanager
def opened(source, dest, options, emit, cancel, imaging=True):
    """Write-protect and open the source for one piece of work; both are always undone again.

    ``source`` is a disk dict from ``disks.list_disks()`` or ``{"image": path}``.  A disk dict may
    carry ``"region": {"offset", "size", "label", "filesystem"}`` to restrict the work to one
    partition or one stretch of unallocated space.  Only that window is read, which is much
    faster than scanning the whole disk.

    Yields ``(src, accessible, used)``; ``used`` is what was really opened: the source itself, or
    the image that was made of it first.
    """
    is_disk = "number" in source
    region = source.get("region")
    if is_disk and disks.fake_mode():
        raise RecoveryError(t("err_demo"))
    if dest:
        os.makedirs(dest, exist_ok=True)
        if is_disk and disks.disk_of_path(dest, disks.list_disks()) == source["number"]:
            raise RecoveryError(t("err_same_disk"))
    locked, src, used = False, None, source
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
        if options.image_first and is_disk and imaging:
            if not dest:
                raise RecoveryError(t("err_select_dest"))
            free = shutil.disk_usage(dest).free
            if src.size + RESERVE > free:
                raise RecoveryError(t("err_space", need=human_size(src.size), free=human_size(free)))
            emit("phase", key="ph_image", text=t("ph_image"))
            image = create_image(src, os.path.join(dest, "disk-%d%s.img" % (
                source["number"], "-part" if region else "")), emit, cancel)
            bad = src.bad_bytes
            src.close()
            src = Source(image, label=label)
            src.bad_bytes = bad
            used = {"image": image, "accessible": sorted(accessible)}
        yield src, accessible, used
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


def run_recovery(source, dest, options, emit, cancel):
    """Scan and recover in one go, without keeping the scan.  Returns the summary."""
    with opened(source, dest, options, emit, cancel) as (src, accessible, _):
        return Engine(src, dest, options, emit, cancel, accessible).run()


def _data_base(source, dest, all_disks=None):
    """Where scan files may be written: the data folder, but never on the disk being recovered."""
    base = session.data_dir()
    if "number" in source:
        try:
            on_source = disks.disk_of_path(base, all_disks or disks.list_disks()) == source["number"]
        except Exception:
            on_source = bool(source.get("system"))
        if on_source:
            base = os.path.join(dest, REPORT_DIR) if dest else None
    return base


def _describe(source):
    """The part of a source that is needed to find and open it again later."""
    keep = ("image", "accessible", "number", "name", "serial", "size", "sector", "system", "bus", "region")
    out = {k: source[k] for k in keep if k in source}
    if "image" in out:
        out["image"] = os.path.abspath(out["image"])
    return out


def interrupted_scan(source, dest=None, all_disks=None):
    """(position, time) of a stopped scan of this source that can be continued, or None."""
    base = _data_base(source, dest, all_disks)
    if not base:
        return None
    key = session.source_key(source)
    return session.peek_checkpoint(session.checkpoint_path(key, base), key)


def scan_source(source, options, emit, cancel, dest=None, resume=True):
    """Scan a source and store the catalogue of what was found.  Returns the ``Session``.

    Nothing is recovered here, so no destination is needed (except for "image first").  A scan
    that is stopped leaves a checkpoint behind and continues from there next time.
    """
    base = _data_base(source, dest)
    key = session.source_key(source)
    with opened(source, dest, options, emit, cancel) as (src, accessible, used):
        eng = Engine(src, dest, options, emit, cancel, accessible)
        mark = None
        if base and used is source:                     # an image made first is scanned in one piece
            mark = session.checkpoint_path(key, base)
            if resume:
                eng.scan_state = session.load_checkpoint(mark, key)
                if eng.scan_state:
                    emit("log", text=t("log_resume_scan", pos=human_size(eng.scan_state.pos)))
            eng.checkpoint = lambda res: session.save_checkpoint(mark, key, res)
        eng.analyze()
        if mark:
            session.drop_checkpoint(mark)
        emit("phase", key="ph_save", text=t("ph_save"))
        meta = dict(source=_describe(used), label=src.label, src_size=src.size, bad_bytes=src.bad_bytes,
                    skipped_live=eng.skipped_live)
        path = None
        if base:
            path = os.path.join(session.sessions_dir(base), time.strftime("%Y%m%d-%H%M%S") + session.EXT)
        try:
            return session.Session.create(path, meta, eng.items, [v for v in eng.volumes if hasattr(v, "title")])
        except (OSError, session.sqlite3.Error) as ex:
            emit("log", text=t("log_not_saved", err=ex))
            return session.Session.create(None, meta, eng.items, [v for v in eng.volumes if hasattr(v, "title")])


def resolve_source(desc):
    """Find the source of a saved scan again.  Disk numbers change between boots; serial numbers do not."""
    if "image" in desc:
        if not os.path.isfile(desc["image"]):
            raise RecoveryError(t("err_image_missing", path=desc["image"]))
        return desc
    if disks.fake_mode():
        raise RecoveryError(t("err_demo"))
    all_disks = disks.list_disks()
    serial = desc.get("serial")
    match = [d for d in all_disks if d["size"] == desc.get("size") and (
        d.get("serial") == serial if serial else d["number"] == desc.get("number") and d.get("name") == desc.get("name"))]
    if not match:
        raise RecoveryError(t("err_disk_missing", name=desc.get("name") or "?", size=human_size(desc.get("size") or 0)))
    found = dict(match[0])
    if desc.get("region"):
        found["region"] = desc["region"]
    return found


def recover_session(sess, items, dest, options, emit, cancel):
    """Recover files of a saved scan (``items`` None: everything still pending).  Returns the summary.

    Can be called again and again, with other files or another destination; the scan file
    remembers what has been recovered.
    """
    source = resolve_source(sess.meta["source"])
    with opened(source, dest, options, emit, cancel, imaging=False) as (src, accessible, _):
        eng = Engine(src, dest, options, emit, cancel, accessible)
        eng.items, eng.session = sess.items, sess
        eng.titles = [(v.title, v.fs) for v in sess.volumes]
        eng.skipped_live = sess.meta.get("skipped_live", 0)
        where = os.path.normcase(os.path.abspath(dest))
        eng.top_names = dict(sess.meta.get("dests", {}).get(where, {}))
        try:
            return eng.recover(items)
        finally:
            sess.flush()
            sess.set_meta("dests", dict(sess.meta.get("dests", {}), **{where: eng.top_names}))
