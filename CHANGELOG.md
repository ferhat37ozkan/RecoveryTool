# Changelog

## Unreleased

Added

- **Disk Health** (Disk > Disk Health). Every disk with a plain verdict: Healthy, Watch it, At risk or
  No data, and the reasons in everyday words (what it means, what to do). Tiles for temperature,
  power-on time, wear, reallocated and pending sectors, uncorrected errors and power cycles; disk
  details; and the full ATA SMART table with the attributes that matter coloured. Unknown values are
  shown as "not reported", never as 0. USB enclosures and RAID arrays that hide health data get an
  explanation instead of a guess. "Recover files from this disk" opens File Recovery with the disk
  selected. Demo data: `BENCHWISE_FAKE_HEALTH=docs\demo-health.json`; tests: `tests\test_diskhealth.py`.

Fixed

- The log box at the bottom of File Recovery cut its top line in half: its height was not a whole
  number of lines, and when the window was short it was squeezed below the requested size. It now
  shows exactly 3 lines (5 on the results page), keeps the last line in view, and a short window
  shrinks the disk and file lists (they scroll) instead of the log or the options.
- Benchwise opens in the middle of the screen; the title reads Benchwise@idlepose.com.

## 1.1.0

The app is now **Benchwise**, a workbench of tools. RecoveryTool lives on as its first tool,
File Recovery.

Added

- **Benchwise window.** Categories as big cards (Disk, System & Memory, Battery & Power, Display &
  Input, Network, Windows Repair, Cleanup & Privacy), each with its tool cards, and a path bar at the
  top to go back. Tools that are not built yet show "Coming soon". A tool keeps running while you
  look around, so a scan goes on when you go back to the home page.
- **Administrator rights per tool.** Benchwise starts without them. A tool marked with a shield
  asks to restart as administrator and the elevated copy opens that tool straight away. The top bar
  shows "Administrator" or "Standard mode".
- `Benchwise.exe` and `Benchwise-cli.exe` replace `RecoveryTool.exe`; `python -m benchwise` runs it
  from source. Saved scans stay where they were (`%LOCALAPPDATA%\RecoveryTool`).
- **Progress while rebuilding the folder structure.** After the scan, this phase used to show
  only a still bar, and on a large disk it can take many minutes. It now runs in three counted
  steps (reading and linking the file records, building the list of files, checking for
  overwritten data). The live panel shows the current step, the remaining time, the speed in
  records per second and how many records are done.
- **Full command-line help.** `help`, `-h`, `--help`, `/?` or no arguments list every option
  in groups, with what it does and examples, in Turkish or English.

Fixed

- **A command-line exe that works.** `RecoveryTool.exe --list` and the other options printed
  nothing, because the exe is a window application with no console. The command line now ships
  as `RecoveryTool-cli.exe`, a console program that runs inside the terminal it is started from:
  it prints there, the terminal waits for it and Ctrl+C stops it. It does not demand
  administrator rights up front (that would make Windows open a separate window that closes at
  the end); commands that read a disk ask for an administrator terminal. `RecoveryTool.exe`
  stays the desktop app and, given arguments, points to the cli exe.

## 1.0.2

Changed

- **Scan first, recover what you choose.** A recovery used to stop before it began when the
  destination had less free space than everything the scan had found, which could be several
  times the size of the disk (deleted files whose space was reused, and old copies of the same
  file, each count in full). The scan now writes nothing and ends in a list of what was found: a
  folder tree with tick boxes, sizes, dates and a search box. Recovery writes what is ticked.
- **Running out of space is no longer an error.** Each file is written, verified and recorded on
  its own. A file that does not fit is left for later and smaller ones are still tried. What was
  not recovered stays ticked; free some space or choose another folder and press the button again.
- Verification happens right after each file instead of in a pass at the end, so a run that is
  stopped keeps everything it finished. A file being written when the run is stopped is removed,
  never left half-written.
- Entries that cannot be read back at all (no data location, impossible size, NTFS-compressed) are
  recognised during the scan and no longer counted in the total.

Added

- **Saved scans.** Every finished scan is stored with the state of each file. "Saved scans" opens
  one again later, without scanning the disk, to recover more from it. The disk is found again by
  its serial number.
- **Green check mark** on recovered files, **grey ring** on files not recovered yet, amber for
  recovered-but-unproven, red for damaged. Folders show "recovered / total".
- **Pause and Continue**, during the scan and during recovery.
- **A stopped scan continues** where it was (checkpoint every 20 seconds), also after the program
  was closed or the computer crashed.
- **Live panel** on the right, opened when work starts and hidden or shown with a button: percent,
  elapsed and remaining time, current and average speed with a graph, unreadable bytes, what the
  scan has found so far, files per status, files waiting for space, free space in the
  destination, the last files written.
- Right-click a recovered file: open it, show it in its folder, see its details.
- Command line: `--scans` lists saved scans, `--resume <scan> --dest <folder>` recovers what is
  still waiting in one.
- When the files found add up to more than the source, the log says how much disk space they
  really occupy and how much of it is claimed by more than one entry.

## 1.0.1

Fixed

- Files of a lost partition were skipped. A partition that had vanished from the partition table
  but still had an intact boot sector was treated as "still accessible" and left out unless the
  "also copy accessible files" option was ticked. Accessibility is now decided by whether Windows
  actually recognises the partition (for image files: whether the partition table lists it).
- Files under an image written over the disk could be reported `OK`. Overwrite detection only
  understood NTFS, FAT32 and exFAT as the new occupant. An ISO 9660 image at the start of the disk
  is now measured and everything under it is marked `DAMAGED`. Old files lying under a partition
  that holds ext2/3/4, XFS, btrfs, HFS+, APFS, LUKS, swap or FAT12/16 are marked `UNCERTAIN`
  unless a checksum proves them intact.
- A disk that stops answering mid-run (unplugged, dying) now ends the run with a clear message
  instead of "reading" zeros to the end. Unreadable areas are skipped faster.
- A disk left write-protected by an interrupted run is now found again by serial number, not by
  disk number, which changes between boots.

Added

- Partitions and unallocated space are listed under each disk.
- Recovery from a single partition or a stretch of unallocated space (`--partition`, `--offset`,
  `--length` on the command line). Only that region is scanned.
- Right-click menu: assign, change or remove a drive letter; bring online or take offline; set or
  clear read-only; read-only filesystem check; filesystem repair; open in Explorer; properties.
- Troubleshooter: explains what is wrong with a disk, fixes what can be fixed, and says so when
  nothing can be done.
- Demo mode (`RECOVERYTOOL_FAKE_DISKS`) to run the interface against a made-up disk list.

Not yet tested on real hardware: the disk operations and the troubleshooter's fixes, and recovery
from a multi-partition physical disk. They were developed against image files.

## 1.0.0

First public release.
