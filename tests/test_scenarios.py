"""End-to-end tests on real filesystems created inside virtual disks (VHD).

Each scenario creates a small virtual disk with diskpart, formats it, fills it with known files,
then destroys the data the way users do (quick format to another filesystem, deleting files),
detaches the disk and runs the recovery engine on it.  The result is compared against the
SHA-256 of every original file.

The one property that must always hold:  a file reported as OK / REPAIRED is byte-identical
to the original.  A recovery tool may fail to get a file back, but it must never claim success
for a corrupt one.

Run from an elevated prompt (diskpart needs administrator rights):

    python tests\\test_scenarios.py            # all scenarios
    python tests\\test_scenarios.py fat32-ntfs # one scenario
"""

from __future__ import annotations

import csv
import hashlib
import os
import random
import shutil
import string
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recoverytool.engine import Options, run_recovery  # noqa: E402

SIZE_MB = 320
# name: (first filesystem, action, second filesystem)
SCENARIOS = {
    "fat32-ntfs": ("fat32", "format", "ntfs"),
    "fat32-fat32": ("fat32", "format", "fat32"),
    "fat32-exfat": ("fat32", "format", "exfat"),
    "exfat-exfat": ("exfat", "format", "exfat"),
    "exfat-ntfs": ("exfat", "format", "ntfs"),
    "ntfs-ntfs": ("ntfs", "format", "ntfs"),
    "ntfs-exfat": ("ntfs", "format", "exfat"),
    "fat32-delete": ("fat32", "delete", None),
    "exfat-delete": ("exfat", "delete", None),
    "ntfs-delete": ("ntfs", "delete", None),
}


def diskpart(script):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(script)
    try:
        p = subprocess.run(["diskpart", "/s", f.name], capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError("diskpart failed:\n%s\n%s" % (script, p.stdout))
        return p.stdout
    finally:
        os.unlink(f.name)


def free_letter():
    used = {d[0].upper() for d in os.popen("wmic logicaldisk get name 2>nul").read().split() if d.endswith(":")}
    for c in "ZYXWVUTSRQP":
        if c not in used and not os.path.exists(c + ":\\"):
            return c
    raise RuntimeError("no free drive letter")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def make_tree(root, rng):
    """Create a varied tree. Returns {basename: sha256}; every basename is unique."""
    manifest = {}
    counter = [0]
    dirs = ["", "Belgeler", "Belgeler\\ÇALIŞMA DOSYALARI ğüşiöç", "Belgeler\\ÇALIŞMA DOSYALARI ğüşiöç\\2024\\Ocak",
            "Fotoğraflar", "Fotoğraflar\\Tatil İzmir", "a\\b\\c\\d\\e\\f", "Proje Dosyaları (yedek)",
            ("Uzun " + "klasör adı " * 8).strip()]
    sizes = [0, 1, 100, 511, 512, 4095, 4096, 4097, 20000, 70000, 300000, 1500000, 6000000]

    def write(folder, ext, data):
        counter[0] += 1
        stem = "dosya %03d %s" % (counter[0], "".join(rng.choice("abcçdefgğhıijklmnoöprsştuüvyz ") for _ in range(rng.randint(3, 40))).strip())
        name = stem + ext
        d = os.path.join(root, folder)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)
        manifest[name] = hashlib.sha256(data).hexdigest()
        return os.path.join(d, name)

    # A new filesystem always overwrites the first part of the old one's metadata (NTFS wipes the
    # first 256 MFT records; its log file lands on the start of a FAT data area).  On a real disk
    # that is a small fraction; on a tiny test disk it would be everything.  This filler takes the
    # hit, so the scenarios measure the tool and not the size of the test disk.
    filler = os.path.join(root, "_dolgu")
    os.makedirs(filler, exist_ok=True)
    with open(os.path.join(filler, "buyuk.dat"), "wb") as f:
        f.write(rng.randbytes(24 << 20))
    for i in range(300):
        with open(os.path.join(filler, "kucuk%03d.dat" % i), "wb") as f:
            f.write(rng.randbytes(100))

    paths = []
    for i, size in enumerate(sizes * 5):
        folder = dirs[i % len(dirs)]
        kind = i % 4
        if kind == 0:
            paths.append(write(folder, ".bin", rng.randbytes(size)))
        elif kind == 1:
            paths.append(write(folder, ".jpg", b"\xff\xd8\xff\xe0" + rng.randbytes(size)))
        elif kind == 2:
            paths.append(write(folder, ".pdf", b"%PDF-1.7\n" + rng.randbytes(size)))
        else:
            tmp = os.path.join(tempfile.gettempdir(), "rt_zip_%d.zip" % os.getpid())
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("xl/workbook.xml", rng.randbytes(size))
                z.writestr("[Content_Types].xml", "<Types/>")
            with open(tmp, "rb") as f:
                paths.append(write(folder, ".xlsx", f.read()))
            os.unlink(tmp)
    # Force fragmentation: remove every third small file, then write files that fill the holes.
    removed = []
    for p in paths[::3]:
        if os.path.getsize(p) < 400000:
            os.remove(p)
            removed.append(os.path.basename(p))
            manifest.pop(os.path.basename(p))
    for i in range(6):
        write(dirs[(i * 2) % len(dirs)], ".bin", rng.randbytes(900000 + i * 77777))
    # identical copies in another folder, as real backups have
    twins = {}
    for p in [q for q in paths if os.path.exists(q)][:25]:
        d = os.path.join(root, "YEDEK KOPYA")
        os.makedirs(d, exist_ok=True)
        shutil.copy2(p, os.path.join(d, os.path.basename(p)))
        twins[os.path.basename(p)] = True
    return manifest, removed


def undo_trim(before, after):
    """Make the image behave like a USB stick or hard disk instead of an SSD.

    Virtual disks honour TRIM, so space released by a format or a delete is really zeroed.  Media
    without TRIM keep that data.  Every sector that is zero now, was not zero before, and is not
    in use by the current filesystem (so the filesystem did not write those zeros itself) is put
    back from the copy taken before the destructive step.
    """
    from recoverytool import allocation
    from recoverytool.source import Source
    src = Source(after)
    alloc = allocation.current_allocation(src)
    src.close()
    restored, step = 0, 1 << 20
    with open(before, "rb") as a, open(after, "r+b") as b:
        for off in range(0, os.path.getsize(after), step):
            old, new = a.read(step), b.read(step)
            if old == new:
                continue
            out = bytearray(new)
            for o in range(0, len(new), 512):
                if not any(new[o:o + 512]) and any(old[o:o + 512]) and not alloc.overlaps(off + o, 512):
                    out[o:o + 512] = old[o:o + 512]
                    restored += 512
            if out != new:
                b.seek(off)
                b.write(out)
                b.seek(off + len(new))
    return restored


def run_scenario(name, workdir, keep=False):
    fs1, action, fs2 = SCENARIOS[name]
    vhd = os.path.join(workdir, name + ".vhd")
    out = os.path.join(workdir, name + "-out")
    for p in (vhd,):
        if os.path.exists(p):
            os.remove(p)
    shutil.rmtree("\\\\?\\" + out, ignore_errors=True)
    letter = free_letter()
    rng = random.Random(1234)
    diskpart('create vdisk file="%s" maximum=%d type=fixed\nselect vdisk file="%s"\nattach vdisk\n'
             'create partition primary\nformat fs=%s quick label=ESKI\nassign letter=%s\n' % (vhd, SIZE_MB, vhd, fs1, letter))
    try:
        root = letter + ":\\"
        for _ in range(50):
            if os.path.exists(root):
                break
            time.sleep(0.2)
        manifest, _ = make_tree(root, rng)
        subprocess.run(["fsutil", "volume", "flush", letter + ":"], capture_output=True)
    finally:
        diskpart('select vdisk file="%s"\ndetach vdisk\n' % vhd)
    before = vhd + ".before"
    shutil.copyfile(vhd, before)                    # state just before the destructive step
    diskpart('select vdisk file="%s"\nattach vdisk\nselect partition 1\nremove all noerr\nassign letter=%s\n'
             % (vhd, letter))
    try:
        for _ in range(50):
            if os.path.exists(root):
                break
            time.sleep(0.2)
        deleted = {}
        if action == "delete":
            # delete a whole folder and a few single files
            victims = []
            for dp, _, fns in os.walk(root):
                if "System Volume" in dp or "$RECYCLE" in dp.upper():
                    continue
                for fn in fns:
                    if "Fotoğraflar" in dp or fn.endswith(".pdf"):
                        victims.append(os.path.join(dp, fn))
            for v in victims:
                if os.path.basename(v) in manifest and "YEDEK" not in v:
                    deleted[os.path.basename(v)] = manifest[os.path.basename(v)]
                os.remove(v)
            shutil.rmtree(os.path.join(root, "Fotoğraflar"), ignore_errors=True)
        subprocess.run(["fsutil", "volume", "flush", letter + ":"], capture_output=True)
        if action == "format":
            diskpart('select vdisk file="%s"\nselect partition 1\nformat fs=%s quick label=YENI\n' % (vhd, fs2))
    finally:
        diskpart('select vdisk file="%s"\ndetach vdisk\n' % vhd)
    restored = undo_trim(before, vhd)
    if keep:
        print("   undo_trim restored %d bytes" % restored)
    else:
        os.remove(before)

    logs = []
    summary = run_recovery({"image": vhd}, out, Options(), lambda kind, **kw: logs.append(kw.get("text", "")), threading.Event())
    expected = deleted if action == "delete" else manifest
    good = false_ok = wrong_flagged = 0
    found = set()
    with open(summary["report"], encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["status"] == "FOLDER":
                continue
            base = r["path"].rsplit("\\", 1)[-1]
            want = expected.get(base) or manifest.get(base)
            if want is None:
                continue
            if r["sha256"] == want:
                if r["status"] in ("OK", "REPAIRED", "FILLED_FROM_TWIN", "UNCERTAIN"):
                    if base in expected:
                        found.add(base)
                    good += 1
                else:
                    wrong_flagged += 1          # correct content reported as damaged: harmless, but noted
                    if base in expected:
                        found.add(base)
            elif r["status"] in ("OK", "REPAIRED"):
                false_ok += 1
                print("    FALSE OK:", r["status"], r["details"], r["path"])
    result = dict(name=name, expected=len(expected), recovered=len(found), false_ok=false_ok,
                  pessimistic=wrong_flagged, seconds=summary["elapsed"])
    if not keep:
        os.remove(vhd)
        shutil.rmtree("\\\\?\\" + out, ignore_errors=True)
    return result


def main():
    names = [a for a in sys.argv[1:] if not a.startswith("-")] or list(SCENARIOS)
    keep = "--keep" in sys.argv
    workdir = os.path.join(tempfile.gettempdir(), "recoverytool-tests")
    os.makedirs(workdir, exist_ok=True)
    results, failed = [], False
    for n in names:
        print("-- %s" % n, flush=True)
        r = run_scenario(n, workdir, keep)
        results.append(r)
        print("   expected=%(expected)d recovered=%(recovered)d false_ok=%(false_ok)d "
              "correct-but-flagged=%(pessimistic)d  %(seconds).1fs" % r, flush=True)
        failed |= r["false_ok"] > 0
    print("\n%-14s %9s %10s %6s %9s" % ("scenario", "expected", "recovered", "rate", "false OK"))
    for r in results:
        print("%-14s %9d %10d %5.0f%% %9d" % (r["name"], r["expected"], r["recovered"],
                                               100.0 * r["recovered"] / max(r["expected"], 1), r["false_ok"]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
