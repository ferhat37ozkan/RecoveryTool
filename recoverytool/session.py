"""Saved scans.

A scan of a large disk takes hours, and its result rarely fits into the free space at hand in
one go.  So the catalogue of everything that was found is kept in a small SQLite file, together
with what has been recovered so far.  The user can recover a part, move it away, and come back
for the rest - today or next week - without scanning again.

Two kinds of files live in the data folder (``%LOCALAPPDATA%\\RecoveryTool``):
  * ``scans\\*.rtscan``    a finished scan: catalogue + recovery state of every file,
  * ``partial\\*.rtpart``  the position and findings of a scan that was stopped half-way.
Neither is ever written to the disk that is being recovered.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time

from .model import RECOVERED, Item, Node
from .scanner import ScanResult

VERSION = 1
EXT = ".rtscan"
_MAX = (1 << 63) - 1

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE items (
    id INTEGER PRIMARY KEY, vol INTEGER, cat TEXT, top TEXT, rel TEXT, name TEXT, is_dir INTEGER,
    size INTEGER, ctime INTEGER, atime INTEGER, mtime INTEGER, attrs INTEGER, deleted INTEGER, live INTEGER,
    flags TEXT, extents TEXT, resident BLOB, notes TEXT, bad TEXT,
    status TEXT, details TEXT, sha TEXT, path TEXT);
"""
_COLUMNS = ("id, vol, cat, top, rel, name, is_dir, size, ctime, atime, mtime, attrs, deleted, live, "
            "flags, extents, resident, notes, bad, status, details, sha, path")


def data_dir():
    base = os.environ.get("RECOVERYTOOL_DATA")
    return base or os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "RecoveryTool")


def sessions_dir(base=None):
    return os.path.join(base or data_dir(), "scans")


class VolInfo:
    """What is left of a Volume once the scan is over: its name in the output and its type."""

    def __init__(self, title, fs):
        self.title, self.fs = title, fs


def _int(v):
    return v if isinstance(v, int) and 0 <= v <= _MAX else None


class Session:
    def __init__(self, path=None):
        self.path = path
        self.db = sqlite3.connect(path or ":memory:", check_same_thread=False)
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.lock = threading.Lock()
        self.meta, self.items, self.volumes = {}, [], []

    # -- writing --------------------------------------------------------------------------------
    @classmethod
    def create(cls, path, meta, items, volumes):
        """Store a fresh catalogue.  ``path`` None keeps it in memory only (nowhere safe to write)."""
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.exists(path):
                os.remove(path)
        s = cls(path)
        s.db.executescript(_SCHEMA)
        index = {id(v): i for i, v in enumerate(volumes)}

        def rows():
            for i, it in enumerate(items):
                it.id = i
                n = it.node
                yield (i, index[id(it.volume)], it.category, it.top, "\\".join(it.rel), n.name, int(n.is_dir),
                       min(max(int(n.size), 0), _MAX), _int(n.ctime), _int(n.atime), _int(n.mtime),
                       int(n.attrs) & 0xFFFFFFFF, int(bool(n.deleted)), int(bool(n.live)),
                       json.dumps(list(n.flags)), json.dumps(n.extents),
                       None if n.resident is None else bytes(n.resident),
                       json.dumps(it.notes), json.dumps(it.bad), it.status, json.dumps(it.details), it.sha, it.path)

        s.db.executemany("INSERT INTO items (%s) VALUES (%s)" % (_COLUMNS, ",".join("?" * 23)), rows())
        s.meta = dict(meta, version=VERSION, created=time.time(), volumes=[[v.title, v.fs] for v in volumes])
        s.db.executemany("INSERT INTO meta VALUES (?, ?)", [(k, json.dumps(v)) for k, v in s.meta.items()])
        s.db.commit()
        s.items, s.volumes = items, [VolInfo(v.title, v.fs) for v in volumes]
        return s

    def save(self, it):
        """Record the outcome of one file.  Call ``flush`` now and then to make it durable."""
        with self.lock:
            self.db.execute("UPDATE items SET status=?, details=?, sha=?, path=? WHERE id=?",
                            (it.status, json.dumps(it.details), it.sha, it.path, it.id))

    def flush(self):
        with self.lock:
            self.db.commit()

    def set_meta(self, key, value):
        self.meta[key] = value
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))
            self.db.commit()

    def close(self):
        with self.lock:
            try:
                self.db.commit()
                self.db.close()
            except sqlite3.Error:
                pass

    # -- reading --------------------------------------------------------------------------------
    @classmethod
    def open(cls, path):
        if not os.path.isfile(path):
            raise ValueError("not found: %s" % path)
        s = cls(path)
        try:
            s.meta = {k: json.loads(v) for k, v in s.db.execute("SELECT key, value FROM meta")}
            if s.meta.get("version") != VERSION:
                raise ValueError("unsupported scan file version")
            s.volumes = [VolInfo(title, fs) for title, fs in s.meta["volumes"]]
            for (i, vol, cat, top, rel, name, is_dir, size, ctime, atime, mtime, attrs, deleted, live, flags,
                 extents, resident, notes, bad, status, details, sha, path_) in s.db.execute(
                    "SELECT %s FROM items ORDER BY id" % _COLUMNS):
                n = Node(name, bool(is_dir), size)
                n.ctime, n.atime, n.mtime, n.attrs = ctime, atime, mtime, attrs
                n.deleted, n.live = bool(deleted), bool(live)
                n.flags = json.loads(flags)
                n.extents = [(a, b) for a, b in json.loads(extents)]
                n.resident = resident
                it = Item(n, s.volumes[vol], cat, top, rel.split("\\"), path_ or "")
                it.id, it.status, it.sha = i, status or "", sha or ""
                it.notes, it.details = json.loads(notes), json.loads(details)
                it.bad = [(a, b) for a, b in json.loads(bad)]
                s.items.append(it)
        except (sqlite3.Error, KeyError, TypeError) as ex:
            s.close()
            raise ValueError("not a valid scan file: %s" % ex) from None
        return s


def describe(path):
    """Summary of a saved scan for the list, without loading the catalogue."""
    db = sqlite3.connect(path)
    try:
        meta = {k: json.loads(v) for k, v in db.execute("SELECT key, value FROM meta WHERE key IN "
                                                        "('version', 'created', 'label', 'source')")}
        if meta.get("version") != VERSION:
            return None
        marks = ",".join("'%s'" % s for s in RECOVERED)
        files, size, done, done_size = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(size), 0), COALESCE(SUM(status IN (%s)), 0), "
            "COALESCE(SUM(CASE WHEN status IN (%s) THEN size ELSE 0 END), 0) "
            "FROM items WHERE is_dir = 0 AND status NOT IN ('SKIPPED', 'UNSUPPORTED')" % (marks, marks)).fetchone()
        return dict(path=path, created=meta.get("created") or 0, label=meta.get("label") or "",
                    files=files, size=size, recovered=done, recovered_size=done_size)
    except (sqlite3.Error, ValueError, TypeError):
        return None
    finally:
        db.close()


def list_sessions(base=None):
    folder, out = sessions_dir(base), []
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.endswith(EXT):
                info = describe(os.path.join(folder, name))
                if info:
                    out.append(info)
    return sorted(out, key=lambda x: x["created"], reverse=True)


def delete_session(path):
    for p in (path, path + "-journal"):
        try:
            os.remove(p)
        except OSError:
            pass


# -- interrupted scans --------------------------------------------------------------------------
def source_key(source):
    """Identifies "the same thing being scanned": the disk (by serial number) or image, and the region."""
    region = source.get("region") or {}
    if "image" in source:
        p = os.path.abspath(source["image"])
        ident = "image|%s|%d" % (os.path.normcase(p), os.path.getsize(p) if os.path.exists(p) else 0)
    else:
        ident = "disk|%s|%s|%d" % (source.get("serial") or "", source.get("name") or "", source.get("size") or 0)
    return "%s|%d|%d" % (ident, region.get("offset", 0), region.get("size", 0))


def checkpoint_path(key, base=None):
    return os.path.join(base or data_dir(), "partial", hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".rtpart")


def save_checkpoint(path, key, res):
    head = dict(key=key, pos=res.pos, nonzero=res.nonzero_bytes, bad=res.bad_bytes, boot=res.boot, saved=time.time(),
                counts=[len(res.fat_dirs), len(res.mft), len(res.exfat_sets)])
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "wb") as f:
            f.write(json.dumps(head).encode("utf-8") + b"\n")
            for arr in (res.fat_dirs, res.mft, res.exfat_sets):
                f.write(arr.tobytes())
        os.replace(path + ".tmp", path)
    except OSError:
        pass                                    # a checkpoint is a convenience, never a reason to fail


def peek_checkpoint(path, key):
    """(position, time saved) of an interrupted scan of this source, or None."""
    try:
        with open(path, "rb") as f:
            head = json.loads(f.readline().decode("utf-8"))
        return (head["pos"], head["saved"]) if head.get("key") == key and head["pos"] > 0 else None
    except (OSError, ValueError, KeyError):
        return None


def load_checkpoint(path, key):
    try:
        with open(path, "rb") as f:
            head = json.loads(f.readline().decode("utf-8"))
            if head.get("key") != key:
                return None
            res = ScanResult()
            res.pos, res.nonzero_bytes, res.bad_bytes = head["pos"], head["nonzero"], head["bad"]
            res.boot = {k: list(v) for k, v in head["boot"].items()}
            for arr, n in zip((res.fat_dirs, res.mft, res.exfat_sets), head["counts"]):
                raw = f.read(n * arr.itemsize)
                if len(raw) != n * arr.itemsize:
                    return None
                arr.frombytes(raw)
            return res
    except (OSError, ValueError, KeyError, TypeError):
        return None


def drop_checkpoint(path):
    for p in (path, path + ".tmp"):
        try:
            os.remove(p)
        except OSError:
            pass
