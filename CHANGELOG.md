# Changelog

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
