"""Command-line interface.

    python -m recoverytool.cli --list
    python -m recoverytool.cli --disk 1 --dest E:\\Recovered
    python -m recoverytool.cli --image usb.img --dest E:\\Recovered

The scan is saved.  If the destination fills up, whatever fitted is kept and the rest can be
fetched later without scanning again:

    python -m recoverytool.cli --scans
    python -m recoverytool.cli --resume <scan file> --dest F:\\More
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

from . import APP_NAME, __version__, disks, i18n, session
from .engine import Options, RecoveryError, format_duration, recover_session, scan_source
from .model import Cancelled, human_size


HELP = {
    "en": r"""
{app} {ver} - command line

Usage:  Benchwise-cli.exe <options>
        (from a source checkout: python -m benchwise <options>)

Reading a disk needs an administrator terminal. Listing, saved scans, image files and this
help work in any terminal.

INFORMATION (prints and exits)
  --list                 All disks: number, model, bus, size, MBR/GPT, partitions, drive
                         letters and unallocated space. Disk and partition numbers come from here.
  --scans                Saved scans: date, source, files found and recovered, scan file path.
  --unlock-pending       Release disks left write-protected by an interrupted run. (admin)
  help, -h, --help, /?   This help.

SOURCE (exactly one)
  --disk N               Recover from physical disk N (see --list). (admin)
  --image FILE           Recover from a disk image file (.img, .vhd, ...).
  --resume SCAN          Recover what is still waiting in a saved scan, without scanning
                         again (see --scans). Takes --dest, no --disk / --image.

DESTINATION
  --dest FOLDER          Where recovered files go. Required. Must be on another disk.

NARROW THE SCAN
  --partition N          With --disk: only this partition. Much faster than the whole disk.
  --offset X --length Y  Only this region, in bytes (for example a lost partition or the
                         unallocated space --list shows). Always together.

BEHAVIOUR
  --no-deleted           Skip deleted files; take only lost and orphaned ones.
  --include-live         Also copy files Windows can still open normally (skipped by default).
  --no-twin-repair       Do not repair a damaged file from an identical copy elsewhere.
  --no-verify            Skip reading each written file back. Faster, not recommended.
  --no-lock              Do not write-protect the source disk while working. Not recommended.
  --image-first          Image the whole disk first, then work on the image. Safest for a
                         dying disk; needs free space the size of the disk at the destination.

OTHER
  --lang en|tr           Message language (default: the Windows language).
  --debug                Also print technical detail (where each volume starts, and so on).

NOTE
  Unlike the desktop app, the command line does not stop after the scan: it recovers everything
  it finds. If the destination fills up, what fitted is kept; get the rest later with --resume.

EXAMPLES
  Benchwise-cli.exe --list
  Benchwise-cli.exe --disk 2 --partition 1 --dest E:\Recovered
  Benchwise-cli.exe --disk 2 --partition 1 --dest E:\Recovered --debug > scan.log
  Benchwise-cli.exe --image stick.img --dest E:\Recovered
  Benchwise-cli.exe --scans
  Benchwise-cli.exe --resume "C:\...\scan.rtscan" --dest F:\More
""",
    "tr": r"""
{app} {ver} - komut satırı

Kullanım:  Benchwise-cli.exe <seçenekler>
           (kaynak koddan: python -m benchwise <seçenekler>)

Disk okumak için terminal yönetici olarak açılmalı. Listeleme, kayıtlı taramalar, imaj
dosyaları ve bu yardım her terminalde çalışır.

BİLGİ (yazar ve çıkar)
  --list                 Tüm diskler: numara, model, bağlantı, boyut, MBR/GPT, bölümler,
                         sürücü harfleri ve ayrılmamış alan. Disk/bölüm numaraları buradan.
  --scans                Kayıtlı taramalar: tarih, kaynak, bulunan/kurtarılan, dosya yolu.
  --unlock-pending       Yarıda kalan bir işlemden yazma korumalı kalan diskleri serbest bırakır.
                         (yönetici)
  help, -h, --help, /?   Bu yardım.

KAYNAK (yalnızca biri)
  --disk N               N numaralı fiziksel diskten kurtarır (--list'e bakın). (yönetici)
  --image DOSYA          Bir disk imajı dosyasından kurtarır (.img, .vhd, ...).
  --resume TARAMA        Kayıtlı bir taramada bekleyenleri yeniden taramadan kurtarır
                         (--scans'e bakın). --dest ister, --disk / --image ile kullanılmaz.

HEDEF
  --dest KLASÖR          Kurtarılan dosyaların yazılacağı yer. Zorunlu. Başka bir diskte olmalı.

TARAMAYI DARALTMA
  --partition N          --disk ile: sadece bu bölüm. Bütün diskten çok daha hızlı.
  --offset X --length Y  Sadece bu alan, bayt cinsinden (örneğin kayıp bir bölüm ya da
                         --list'in gösterdiği ayrılmamış alan). İkisi birlikte verilir.

DAVRANIŞ
  --no-deleted           Silinmiş dosyaları atlar; sadece kayıp ve sahipsiz olanları alır.
  --include-live         Windows'un hâlâ açabildiği dosyaları da kopyalar (varsayılan: atlanır).
  --no-twin-repair       Hasarlı dosyayı başka yerdeki aynı kopyasından onarmaz.
  --no-verify            Yazılan dosyayı geri okuyup doğrulamaz. Daha hızlı, önerilmez.
  --no-lock              Çalışırken kaynak diski yazmaya karşı kilitlemez. Önerilmez.
  --image-first          Önce diskin tam imajını çıkarır, sonra imaj üzerinde çalışır. Ölmek
                         üzere olan disk için en güvenlisi; hedefte disk boyutu kadar yer ister.

DİĞER
  --lang en|tr           Mesaj dili (varsayılan: Windows dili).
  --debug                Teknik ayrıntıları da yazar (her bölümün nerede başladığı vb.).

NOT
  Masaüstü uygulamasından farklı olarak komut satırı taramadan sonra durmaz, bulduğu her şeyi
  kurtarır. Hedef dolarsa sığanlar kalır; gerisini sonra --resume ile alırsınız.

ÖRNEKLER
  Benchwise-cli.exe --list
  Benchwise-cli.exe --disk 2 --partition 1 --dest E:\Kurtarilan
  Benchwise-cli.exe --disk 2 --partition 1 --dest E:\Kurtarilan --debug > tarama.log
  Benchwise-cli.exe --image usb.img --dest E:\Kurtarilan
  Benchwise-cli.exe --scans
  Benchwise-cli.exe --resume "C:\...\tarama.rtscan" --dest F:\Devami
""",
}


def print_help():
    print(HELP[i18n.language()].replace("{app}", APP_NAME).replace("{ver}", __version__).strip("\n"))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if "--lang" in argv[:-1]:
        i18n.set_language(argv[argv.index("--lang") + 1])
    else:
        i18n.detect()
    if "--hideme" in argv:                      # Passage (Geçit): opens sites blocked in Turkey, in the background
        from benchwise.passage_cli import cli_entry
        return cli_entry(argv[argv.index("--hideme") + 1:])
    rest = [a for a in argv if a not in ("--lang", "en", "tr")]
    if not rest or any(a in ("help", "-h", "--help", "/?", "-?", "/h") for a in argv):
        print_help()
        return 0
    ap = argparse.ArgumentParser(prog="Benchwise-cli", description="%s %s" % (APP_NAME, __version__),
                                 add_help=False, epilog="help: Benchwise-cli.exe --help")
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
    ap.add_argument("--scans", action="store_true", help="list saved scans and exit")
    ap.add_argument("--resume", metavar="SCAN", help="recover what is still waiting in a saved scan (needs --dest)")
    ap.add_argument("--unlock-pending", action="store_true",
                    help="release disks left write-protected by an interrupted run and exit")
    ap.add_argument("--lang", choices=["en", "tr"], help="message language")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)
    i18n.set_language(args.lang) if args.lang else i18n.detect()

    if args.unlock_pending:
        if not disks.is_admin():
            print(i18n.t("admin_needed"), file=sys.stderr)
            return 2
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
    if args.scans:
        for info in session.list_sessions():
            print("%s  %s\n    %d files (%s), %d recovered (%s)\n    %s" % (
                time.strftime("%Y-%m-%d %H:%M", time.localtime(info["created"])), info["label"], info["files"],
                human_size(info["size"]), info["recovered"], human_size(info["recovered_size"]), info["path"]))
        return 0
    if args.resume:
        if not args.dest or args.disk is not None or args.image:
            ap.error("--resume takes --dest and no --disk / --image")
    elif (args.disk is None) == (args.image is None) or not args.dest:
        ap.error("give --dest and exactly one of --disk / --image")
    if args.resume:
        source = {}
    elif args.disk is not None:
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
        if args.resume:
            try:
                scan = session.Session.open(args.resume)
            except ValueError as ex:
                raise RecoveryError(i18n.t("err_scan_file", err=ex)) from None
            if not scan.meta["source"].get("image") and not disks.is_admin():
                scan.close()
                print(i18n.t("admin_needed"), file=sys.stderr)
                return 2
        else:
            scan = scan_source(source, opts, emit, threading.Event(), args.dest)
        s = recover_session(scan, None, args.dest, opts, emit, threading.Event())
        scan.close()
    except Cancelled:
        print(i18n.t("cancelled"))
        return 1
    except RecoveryError as ex:
        print("ERROR: %s" % ex, file=sys.stderr)
        return 2
    print()
    for key, field in (("sum_recovered", "recovered"), ("sum_ok", "ok"), ("sum_repaired", "repaired"),
                       ("sum_uncertain", "uncertain"), ("sum_damaged", "damaged"), ("sum_skipped", "skipped"),
                       ("sum_live_skipped", "live_skipped"), ("sum_no_space", "no_space"),
                       ("sum_pending", "pending")):
        print("%-48s %d" % (i18n.t(key) + ":", s[field]))
    print("%-48s %s" % (i18n.t("sum_size") + ":", human_size(s["size"])))
    print("%-48s %s" % (i18n.t("sum_time") + ":", format_duration(s["elapsed"])))
    print("%-48s %s" % (i18n.t("sum_report") + ":", s["report"]))
    if s["pending"] and s["session"]:
        print("\n" + i18n.t("cli_resume", path=s["session"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
