# Changelog

## Unreleased

Added

- **Live disk temperatures next to the clock.** Tick "By the clock" on a disk in Disk Health and its
  temperature appears in the notification area as its own icon (green / amber / red by the same limits
  as the verdict), refreshed every 30 seconds. Hovering shows the model, degrees, which disk and link,
  and health; a click opens Benchwise on that disk; right-click has Open and Quit. With disks watched,
  closing the window keeps Benchwise running next to the clock. Windows 11 would hide new icons behind
  the "^"; Benchwise shows its own there unless the user hid them on purpose.
- **Live monitoring mode (always administrator).** Windows gives temperatures only to administrators.
  With one consent a Task Scheduler task runs Benchwise elevated without further UAC prompts, also when
  it is opened normally; optionally it starts with Windows in the background (no window, only the icons).
  Can be switched off in Disk Health, which deletes the task.
- **In-app update.** "Download and install" in the update panel downloads the release's Benchwise.exe
  with a progress bar, checks its size and SHA-256 against the release, replaces the running exe and
  restarts.
- **Temperatures every 15 seconds** by default (5 / 15 / 30 / 60 s to choose in Disk Health; Hard Disk
  Sentinel's default is 5 minutes). Two readers stay open instead of starting a process each time: one
  PowerShell for the disks Windows sees and the AMD RAID helper, which keeps the library loaded. Both end
  by themselves when Benchwise ends (the helper is never killed). The full health reading runs every
  5 minutes.
- **Health percentage** in Disk Health and in the clock tooltips ("Healthy · 94 %"): SSDs from the wear
  they report and their spare blocks, hard disks from reallocated, pending and uncorrectable sectors;
  never higher than the verdict allows. An array shows its worst member.
- Ticking an AMD RAID array for the clock ticks every disk inside it (unticking removes them all).
- **Icon colours.** Disk Health > Icon colours: a background and a digit colour for each level (ideal,
  warm, risky) with a live preview; applied next to the clock at once. Better-contrast defaults
  (dark green / white, amber / black, red / white).
- One Benchwise at a time: a second start brings the running window to the front.
- Ticking a disk that reports no temperature (most USB enclosures) warns that it would show "?" and asks first.
- Ticking an AMD RAID array for the clock first offers to set up AMD_RC2t7 (the array reports no
  temperature itself); the disks inside it are then ticked one by one.
- **Every category now has working tools** (until now most cards said "Coming soon"):
  - *Display & input:* dead-pixel test (full-screen colours and a flashing pattern), keyboard test
    (Turkish-Q layout, every key lights up), mouse test (buttons, wheel, double-click fault detection),
    speaker and microphone test (left / right / sweep tones, live level meter), camera check (devices,
    privacy setting, opens the Camera app).
  - *System:* system information (save / copy), memory test (quick in-app test plus Windows Memory
    Diagnostic and its last result), crash analysis (blue screens with their codes explained, unexpected
    shutdowns, hardware errors, minidumps), CPU stress test with temperature cut-off.
  - *Power:* battery health (design vs. full capacity, wear, powercfg report), wake & sleep diagnosis
    (what woke the PC, wake timers, what keeps it awake, devices allowed to wake it).
  - *Network:* step-by-step connection diagnosis (adapter, address, gateway, DNS, internet, captive
    portal), speed test (Cloudflare; download, upload, latency, route), Wi-Fi analysis (networks,
    channels, best 2.4 GHz channel, saved profiles), network reset (DNS flush, renew, Winsock, TCP/IP;
    restore point first).
  - *Windows repair:* SFC and DISM with progress, Windows Update repair (recent failures explained,
    component reset), driver problems (problem codes, old third-party drivers, driver backup),
    startup programs and services (turn on / off).
  - *Cleanup & privacy:* junk files by category (you choose what is deleted; the Recycle Bin is never
    ticked by default; links and junctions are never followed), duplicate finder (byte-identical files;
    removed copies go to the Recycle Bin, one copy of each group is always kept), space analyzer.
  - *Disk:* surface scan (reads every sector and maps slow and unreadable areas), speed test (uncached
    sequential and 4 KB random), disk repair checks (both GPT copies, boot sector backups, read-only
    chkdsk), image to file (with SHA-256 and a report), partitions (layout and partition table backup),
    secure erase preview.
  - Everything that would write to a disk directly - repairing, cloning or restoring to a disk,
    creating / deleting / formatting partitions, erasing, the fake-capacity fill and wiping free space -
    is shown but locked in this version.

Fixed

- Start-up no longer flickers: the window appears fully drawn in one go. It used to be drawn piece by
  piece, and the category pages built in the background flashed over the home page one after another.
  The window also comes to the front reliably.

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
- **Disk Health** (Disk > Disk Health). Every disk with a plain verdict: Healthy, Watch it, At risk or
  No data, and the reasons in everyday words (what it means, what to do). Tiles for temperature,
  power-on time, wear, reallocated and pending sectors, uncorrected errors and power cycles; disk
  details; and the full ATA SMART table with the attributes that matter coloured. Unknown values are
  shown as "not reported", never as 0. USB enclosures and RAID arrays that hide health data get an
  explanation instead of a guess. "Recover files from this disk" opens File Recovery with the disk
  selected. Demo data: `BENCHWISE_FAKE_HEALTH=docs\demo-health.json`; tests: `tests\test_diskhealth.py`.
- **Disks inside AMD RAID arrays.** Windows only sees the array; the disks in it are now listed one by
  one with their own verdict (temperature, wear, spare, data written, media errors, unexpected
  shutdowns for NVMe; the SMART table for SATA). This uses AMD_RC2t7, a third-party library by Gakuto
  Matsumura that CrystalDiskInfo also uses. It is not shipped: on request it is downloaded from its
  official site with a progress bar, accepted only if its SHA-256 matches the pinned release and its
  signature is valid, and run in a separate process that is never killed. Source, developer and a
  disclaimer are shown wherever it is used. NVMe health checks (critical warning bits, spare below
  threshold, media errors, time above critical temperature) apply to every NVMe disk.
- **New version notice.** A card with a blinking amber frame at the bottom right when GitHub has a
  newer release; it opens a panel with the release notes in the interface language, tool by tool
  (format: `docs/release-notes/`). `BENCHWISE_NO_UPDATE_CHECK=1` turns it off.

Fixed

- **A command-line exe that works.** `RecoveryTool.exe --list` and the other options printed
  nothing, because the exe is a window application with no console. The command line now ships
  as `Benchwise-cli.exe`, a console program that runs inside the terminal it is started from:
  it prints there, the terminal waits for it and Ctrl+C stops it. It does not demand
  administrator rights up front (that would make Windows open a separate window that closes at
  the end); commands that read a disk ask for an administrator terminal. `RecoveryTool.exe`
  stays the desktop app and, given arguments, points to the cli exe.
- The log box at the bottom of File Recovery cut its top line in half: its height was not a whole
  number of lines, and when the window was short it was squeezed below the requested size. It now
  shows exactly 3 lines (5 on the results page), keeps the last line in view, and a short window
  shrinks the disk and file lists (they scroll) instead of the log or the options.
- Benchwise opens in the middle of the screen; the title reads Benchwise@idlepose.com.
- Switching pages no longer redraws them: pages and tools stay laid out and are only raised, category
  pages are built in the background, and Disk Health swaps its detail in one go.

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
