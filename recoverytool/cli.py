"""Command-line interface.

    python -m recoverytool.cli --list
    python -m recoverytool.cli --disk 1 --dest E:\\Recovered
    python -m recoverytool.cli --image usb.img --dest E:\\Recovered
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

from . import APP_NAME, __version__, disks, i18n
from .engine import Options, RecoveryError, format_duration, run_recovery
from .model import Cancelled, human_size


def main(argv=None):
    ap = argparse.ArgumentParser(prog="recoverytool", description="%s %s" % (APP_NAME, __version__))
    ap.add_argument("--list", action="store_true", help="list all disks and exit")
    ap.add_argument("--disk", type=int, help="physical disk number to recover from")
    ap.add_argument("--image", help="disk image file to recover from")
    ap.add_argument("--dest", help="destination folder (must be on a different disk)")
    ap.add_argument("--partition", type=int, help="with --disk: recover only this partition number (faster)")
    ap.add_argument("--offset", type=int, help="recover only a region: start in bytes")
    ap.add_argument("--length", type=int, help="recover only a region: size in bytes")
    ap.add_argument("--no-lock", action="store_true", help="do not write-protect the disk")
    ap.add_argument("--no-deleted", action="store_true", help="skip deleted files")
    ap.add_argument("--include-live", action="store_true", help="also copy files that are still accessible")
    ap.add_argument("--no-twin-repair", action="store_true", help="do not repair from identical copies")
    ap.add_argument("--no-verify", action="store_true", help="skip read-back verification")
    ap.add_argument("--image-first", action="store_true", help="image the disk first, then work on the image")
    ap.add_argument("--unlock-pending", action="store_true",
                    help="release disks left write-protected by an interrupted run and exit")
    ap.add_argument("--lang", choices=["en", "tr"], help="message language")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    i18n.set_language(args.lang) if args.lang else i18n.detect()

    if args.unlock_pending:
        for d in disks.resolve_pending(disks.list_disks()):
            ok, err = disks.unlock_disk(d["number"], d.get("serial"))
            print(i18n.t("log_unlocked", n=d["number"]) if ok else i18n.t("log_unlock_failed", n=d["number"], err=err))
        left = disks.pending_locks()
        if left:
            print("Not connected, still recorded: %s" % ", ".join("%s (%s)" % (x.get("name"), x.get("serial")) for x in left))
        return 0
    if args.list:
        for d in disks.list_disks():
            vols = ", ".join("%s%s %s" % ((p["letter"] + ": ") if p["letter"] else "", p["filesystem"] or "RAW",
                                          human_size(p["size"])) for p in d["partitions"]) or "-"
            print("Disk %d  %-28s %-6s %10s  %-4s%s%s%s" % (
                d["number"], d["name"][:28], d["bus"], human_size(d["size"]), d["style"],
                "  [system]" if d["system"] else "", "  [offline]" if d["offline"] else "",
                "  [read-only]" if d["readonly"] else ""))
            for row in disks.layout(d):
                if row["kind"] == "gap":
                    print("    %-14s %10s  offset %d" % ("unallocated", human_size(row["size"]), row["offset"]))
                else:
                    p = row["part"]
                    print("    partition %-4d %10s  %-6s %-3s %s" % (
                        p["number"], human_size(p["size"]), p["filesystem"] or "RAW",
                        (p["letter"] + ":") if p["letter"] else "", p.get("label") or ""))
        return 0
    if (args.disk is None) == (args.image is None) or not args.dest:
        ap.error("give --dest and exactly one of --disk / --image")
    if args.disk is not None:
        if not disks.is_admin():
            print(i18n.t("admin_needed"), file=sys.stderr)
            return 2
        match = [d for d in disks.list_disks() if d["number"] == args.disk]
        if not match:
            print("Disk %d not found" % args.disk, file=sys.stderr)
            return 2
        source = match[0]
    else:
        source = {"image": args.image}
    if args.partition is not None:
        match = [p for p in source.get("partitions", ()) if p["number"] == args.partition]
        if not match:
            ap.error("--partition needs --disk and an existing partition number (see --list)")
        p = match[0]
        source["region"] = {"offset": p["offset"], "size": p["size"], "filesystem": p.get("filesystem") or "",
                            "label": "partition %d" % p["number"]}
    elif args.offset is not None or args.length is not None:
        if args.offset is None or not args.length:
            ap.error("--offset and --length go together")
        source["region"] = {"offset": args.offset, "size": args.length, "filesystem": "", "label": "region"}

    state = {"t": 0.0}

    def emit(kind, **kw):
        if kind == "phase":
            print("\n== %s" % kw["text"], flush=True)
        elif kind == "log" or (kind == "debug" and args.debug):
            print("   " + kw["text"], flush=True)
        elif kind == "progress" and kw.get("total") and time.time() - state["t"] > 2:
            state["t"] = time.time()
            print("   %5.1f%%" % (100.0 * kw["done"] / kw["total"]), flush=True)

    opts = Options(include_deleted=not args.no_deleted, include_live=args.include_live,
                   twin_repair=not args.no_twin_repair, lock=not args.no_lock, verify=not args.no_verify,
                   image_first=args.image_first)
    try:
        s = run_recovery(source, args.dest, opts, emit, threading.Event())
    except Cancelled:
        print(i18n.t("cancelled"))
        return 1
    except RecoveryError as ex:
        print("ERROR: %s" % ex, file=sys.stderr)
        return 2
    print()
    for key, field in (("sum_recovered", "recovered"), ("sum_ok", "ok"), ("sum_repaired", "repaired"),
                       ("sum_uncertain", "uncertain"), ("sum_damaged", "damaged"), ("sum_skipped", "skipped"),
                       ("sum_live_skipped", "live_skipped")):
        print("%-48s %d" % (i18n.t(key) + ":", s[field]))
    print("%-48s %s" % (i18n.t("sum_size") + ":", human_size(s["size"])))
    print("%-48s %s" % (i18n.t("sum_time") + ":", format_duration(s["elapsed"])))
    print("%-48s %s" % (i18n.t("sum_report") + ":", s["report"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
