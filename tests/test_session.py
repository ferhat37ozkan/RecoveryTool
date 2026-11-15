"""Tests for pausing, interrupted scans, saved scans and recovering in several goes.

    python tests\\test_session.py

No hardware or administrator rights are needed.  The last part works on a real disk image and
runs when RECOVERYTOOL_TEST_IMAGE points to one (any image the tool finds files in, for example
a VHD kept by ``test_scenarios.py --keep``).
"""

from __future__ import annotations

import csv
import os
import random
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recoverytool import catalog, scanner, session  # noqa: E402
from recoverytool.engine import RESERVE, Engine, Options, recover_session, run_recovery, scan_source  # noqa: E402
from recoverytool.model import RECOVERED, Cancelled, Control, Item, Node, is_pending  # noqa: E402
from recoverytool.source import Source  # noqa: E402


def test_control():
    c = Control()
    assert not c.is_set() and not c.paused
    c.pause()
    seen = []
    worker = threading.Thread(target=lambda: seen.append(c.is_set()))
    worker.start()
    time.sleep(0.3)
    assert c.paused and worker.is_alive() and not seen, "a paused worker must wait inside is_set()"
    c.resume()
    worker.join(2)
    assert seen == [False] and c.paused_seconds >= 0.25
    c.pause()
    worker = threading.Thread(target=lambda: seen.append(c.is_set()))
    worker.start()
    c.set()                                             # stopping also ends the pause
    worker.join(2)
    assert seen == [False, True] and c.stopping and not c.paused
    c.clear()
    assert not c.is_set() and c.paused_seconds == 0
    print("pause / stop control passed")


class StopAfter:
    """A cancel flag that trips after a number of polls."""

    def __init__(self, n):
        self.n = n

    def is_set(self):
        self.n -= 1
        return self.n < 0


def test_interrupted_scan():
    work = tempfile.mkdtemp(prefix="rt_scan_")
    path = os.path.join(work, "disk.bin")
    rng = random.Random(7)
    data = bytearray(rng.randbytes(8 << 20))
    for i in range(0, len(data), 37 * 512):             # things the scanner looks for, all over the file
        data[i:i + 6] = b"FILE0\x00"
    for i in range(5 * 512, len(data), 91 * 512):
        data[i:i + 11] = b".          "
        data[i + 11] = 0x10
        data[i + 32:i + 43] = b"..         "
        data[i + 43] = 0x10
    with open(path, "wb") as f:
        f.write(data)
    old = scanner.CHUNK
    scanner.CHUNK = 1 << 20
    try:
        src = Source(path)
        whole = scanner.scan(src)
        key = session.source_key({"image": path})
        mark = session.checkpoint_path(key, work)
        try:
            scanner.scan(src, cancel=StopAfter(3), checkpoint=lambda r: session.save_checkpoint(mark, key, r))
            raise AssertionError("the scan should have been stopped")
        except Cancelled:
            pass
        pos, _ = session.peek_checkpoint(mark, key)
        assert pos == 3 << 20, pos
        assert session.load_checkpoint(mark, "another disk") is None
        state = session.load_checkpoint(mark, key)
        calls = []
        rest = scanner.scan(src, lambda done, total: calls.append(done), state=state)
        assert calls[0] == 4 << 20, "a continued scan must not read the first part again"
        assert list(rest.mft) == list(whole.mft) and list(rest.fat_dirs) == list(whole.fat_dirs)
        assert rest.nonzero_bytes == whole.nonzero_bytes and rest.pos == src.size
        assert len(whole.mft) > 400 and len(whole.fat_dirs) > 100
        src.close()
    finally:
        scanner.CHUNK = old
        shutil.rmtree(work, ignore_errors=True)
    print("interrupted scan passed: %d + %d findings identical after continuing" % (len(whole.mft), len(whole.fat_dirs)))


def fake_items():
    vol = session.VolInfo("Volume 1 - NTFS", "NTFS")
    items = []

    def add(top, rel, size=None, cat="main"):
        n = Node(rel[-1], size is None, size or 0)
        if size:
            n.extents = [(4096 * len(items), size)]
        it = Item(n, vol, cat, top, rel)
        it.id = len(items)
        items.append(it)
        return it
    add("Volume 1 - NTFS", ["Belgeler"])
    add("Volume 1 - NTFS", ["Belgeler", "a.txt"], 100)
    add("Volume 1 - NTFS", ["Belgeler", "b.txt"], 200)
    add("Volume 1 - NTFS", ["Belgeler", "Alt"])
    add("Volume 1 - NTFS", ["Belgeler", "Alt", "c.bin"], 1000)
    add("Volume 1 - NTFS", ["kök.dat"], 50)
    add("Volume 1 - NTFS (deleted)", ["Silinen klasör", "d.jpg"], 7, "deleted")      # its folder has no entry
    bad = add("Volume 1 - NTFS", ["Belgeler", "bozuk.bin"], 5)
    bad.status, bad.details = "SKIPPED", ["NO_DATA_LOCATION"]
    return vol, items


def test_catalog():
    vol, items = fake_items()
    cat = catalog.Catalog(items)
    r = cat.root
    assert (r.files, r.size, r.pend, r.pend_size, r.done) == (6, 1362, 5, 1357, 0)
    docs = next(e for e in r.children[0].children if e.name == "Belgeler")
    assert (docs.files, docs.pend, docs.tick(), docs.mark()) == (4, 3, 0, "pending")
    cat.set_checked(docs, True)
    assert (docs.tick(), docs.sel, docs.sel_size, r.sel, r.children[0].tick()) == (1, 3, 1300, 3, 2)
    assert [i.rel[-1] for i in cat.selected()] == ["a.txt", "b.txt", "c.bin"]
    broken = cat.by_id[7]
    cat.toggle(broken)
    assert not broken.checked and broken.state == "fail", "a file that cannot be recovered cannot be ticked"

    items[1].status, items[1].path = "OK", "X:\\a.txt"   # a.txt was recovered
    changed = cat.update(items[1])
    assert docs in changed and r in changed
    assert (docs.done, docs.pend, docs.sel, docs.mark(), r.done_size, r.sel_size) == (1, 2, 2, "part", 100, 1200)
    assert cat.by_id[1].state == "ok" and not cat.by_id[1].checked
    for i in (2, 4):
        items[i].status = "UNCERTAIN" if i == 4 else "OK"
        cat.update(items[i])
    assert (docs.mark(), docs.tick(), r.sel, r.pend) == ("ok", 0, 0, 2), "folder with only a hopeless file left is done"
    assert cat.by_id[4].state == "warn"
    cat.set_checked(r, True)
    assert r.sel == 2 and r.tick() == 1, "ticking everything takes only what is still to be recovered"
    cat.toggle(cat.by_id[1])                            # a recovered file can be ticked by hand, to write it again
    assert r.sel == 3 and cat.by_id[1].checked
    cat.set_checked(r, False)
    assert r.sel == 0 and r.sel_size == 0
    found, n = cat.find("B.TXT")
    assert n == 1 and found[0].path() == "Volume 1 - NTFS\\Belgeler\\b.txt"
    assert cat.by_id[6].path() == "Volume 1 - NTFS (deleted)\\Silinen klasör\\d.jpg"

    # the same catalogue through a scan file: states survive, hopeless and pending are told apart
    work = tempfile.mkdtemp(prefix="rt_sess_")
    try:
        path = os.path.join(session.sessions_dir(work), "t" + session.EXT)
        s = session.Session.create(path, dict(label="test", source={"image": "x"}), items, [vol])
        items[5].status, items[5].details, items[5].sha, items[5].path = "DAMAGED", ["READ_ERROR"], "ab", "X:\\k"
        s.save(items[5])
        s.set_meta("dests", {"x:\\out": {"Volume 1 - NTFS": "Volume 1 - NTFS (2)"}})
        s.close()
        info = session.list_sessions(work)
        assert len(info) == 1 and (info[0]["files"], info[0]["recovered"], info[0]["recovered_size"]) == (5, 4, 1350)
        s = session.Session.open(path)
        assert [i.status for i in s.items] == ["", "OK", "OK", "", "UNCERTAIN", "DAMAGED", "", "SKIPPED"]
        assert s.items[5].details == ["READ_ERROR"] and s.items[5].path == "X:\\k" and s.items[4].node.extents == [(16384, 1000)]
        assert s.items[6].rel == ["Silinen klasör", "d.jpg"] and s.items[6].category == "deleted" and s.items[0].node.is_dir
        assert s.meta["dests"]["x:\\out"]["Volume 1 - NTFS"] == "Volume 1 - NTFS (2)"
        assert [i.id for i in s.items if is_pending(i) and not i.node.is_dir] == [6]
        s.close()
        session.delete_session(path)
        assert not session.list_sessions(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("catalogue and scan file passed")


def report_rows(summary):
    with open(summary["report"], encoding="utf-8-sig") as f:
        return {(r["volume"], r["path"]): r for r in csv.DictReader(f, delimiter=";") if r["status"] != "FOLDER"}


def test_image(image):
    work = tempfile.mkdtemp(prefix="rt_parts_")
    os.environ["RECOVERYTOOL_DATA"] = os.path.join(work, "data")
    quiet = lambda kind, **kw: None
    try:
        # reference: everything in one go
        ref = run_recovery({"image": image}, os.path.join(work, "ref"), Options(), quiet, threading.Event())
        want = {k: r for k, r in report_rows(ref).items() if r["status"] in RECOVERED}
        assert want, "the test image needs recoverable files"

        # 1) scan only: a catalogue, nothing written
        scan = scan_source({"image": image}, Options(), quiet, threading.Event())
        files = [i for i in scan.items if not i.node.is_dir and is_pending(i)]
        assert scan.path and os.path.isfile(scan.path) and len(files) == len(want)
        assert not os.path.exists(os.path.join(work, "out1"))
        total = sum(i.node.size for i in files)

        # 2) a destination with room for about a third: what fits is recovered, the rest waits
        out1, out2 = os.path.join(work, "out1"), os.path.join(work, "out2")
        os.makedirs(out1)
        used = lambda: sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(out1) for f in fs
                           if "RecoveryTool-Report" not in d)
        room = total // 3 + RESERVE
        src = Source(image)
        eng = Engine(src, out1, Options(), quiet, threading.Event())
        eng.items, eng.session = scan.items, scan
        eng.titles = [(v.title, v.fs) for v in scan.volumes]
        eng.free_bytes = lambda: room - used()
        first = eng.recover(files)
        src.close()
        assert first["no_space"] > 0 and first["recovered"] > 0 and not first["stopped"]
        assert first["pending"] == first["no_space"] == len(files) - first["recovered"] - first["skipped"]
        assert used() <= total // 3, "the reserve must not be eaten into"
        rows1 = report_rows(first)
        assert sum(r["status"] == "NOT_RECOVERED" for r in rows1.values()) == first["no_space"]
        scan.close()

        # 3) later, from the scan file alone: only the rest is written, into another folder
        again = session.Session.open(scan.path)
        left = [i for i in again.items if not i.node.is_dir and is_pending(i)]
        assert len(left) == first["pending"]
        assert all(os.path.isfile(i.path) for i in again.items if i.status in RECOVERED)
        second = recover_session(again, None, out2, Options(), quiet, threading.Event())
        assert second["no_space"] == 0 and second["pending"] == 0
        assert second["recovered"] + second["skipped"] == len(left)
        rows2 = report_rows(second)
        got = {k: r for k, r in list(rows1.items()) + list(rows2.items()) if r["status"] in RECOVERED}
        assert set(got) == set(want), "both runs together must cover exactly what one run recovers"
        wrong = [k for k in want if got[k]["sha256"] != want[k]["sha256"]]
        assert not wrong, "content differs from a recovery in one go: %s" % wrong[:3]
        # twin repair may turn DAMAGED into REPAIRED only when the intact copy is at hand; never the reverse
        worse = [k for k in want if want[k]["status"] == "OK" and got[k]["status"] != "OK"]
        assert not worse, worse[:3]

        # 4) a third run finds nothing to do; ticking a recovered file writes it again
        third = recover_session(again, None, out2, Options(), quiet, threading.Event())
        assert third["recovered"] == 0 and third["pending"] == 0
        one = next(i for i in again.items if i.status == "OK" and i.node.size)
        sha, where = one.sha, one.path
        os.remove(where) if os.path.dirname(where).startswith(out2) else None
        redo = recover_session(again, [one], out2, Options(), quiet, threading.Event())
        assert redo["recovered"] == 1 and one.sha == sha and os.path.isfile(one.path)
        again.close()

        # 5) stopping in the middle keeps what is finished and leaves no half-written file
        scan3 = scan_source({"image": image}, Options(), quiet, threading.Event())
        todo = [i for i in scan3.items if not i.node.is_dir and is_pending(i)]
        out3 = os.path.join(work, "out3")
        stopped = recover_session(scan3, None, out3, Options(), quiet, StopAfter(len(todo) // 2))
        assert stopped["stopped"] and 0 < stopped["recovered"] < len(want)
        on_disk = sum(len(fs) for d, _, fs in os.walk(out3) if "RecoveryTool-Report" not in d)
        assert on_disk == stopped["recovered"], (on_disk, stopped["recovered"])
        assert stopped["pending"] == len(todo) - stopped["recovered"] - stopped["skipped"]
        scan3.close()
        print("image: %d files; %d fitted first, %d later; stopped run kept %d" % (
            len(want), first["recovered"], second["recovered"], stopped["recovered"]))
    finally:
        os.environ.pop("RECOVERYTOOL_DATA", None)
        shutil.rmtree("\\\\?\\" + work, ignore_errors=True)
    print("recovering in several goes passed")


if __name__ == "__main__":
    test_control()
    test_interrupted_scan()
    test_catalog()
    image = os.environ.get("RECOVERYTOOL_TEST_IMAGE")
    if image:
        test_image(image)
    else:
        print("RECOVERYTOOL_TEST_IMAGE not set: image tests skipped")
