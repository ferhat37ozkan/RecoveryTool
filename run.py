"""Entry point of the Benchwise window (dist\\Benchwise.exe) and for running from a source checkout.

The exe is a window application: no console window flashes up on a double click.  It starts
without administrator rights; a tool that needs them restarts it elevated with
``--open=<tool id>``.  A window application cannot print to a terminal, so the command line
ships as its own console executable, Benchwise-cli.exe (see run_cli.py).
"""

import os
import sys

# Copies of ourselves (the AMD RAID helper, the elevated restart, the restart after an update)
# must unpack into their own _MEI folder.  Otherwise PyInstaller 6 lets them share ours, they keep
# it in use, and our bootloader shows "Failed to remove temporary directory" when we close.
os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

args = sys.argv[1:]
if len(args) in (3, 5) and args[0] == "--amdrc2-helper":     # Disk Health: reads AMD RAID members
    from benchwise.diskhealth.amdraid import helper_main
    helper_main(*args[1:])
    sys.exit(0)
if args and (args[0].startswith("--passage=") or args[0] == "--hideme"):   # Passage, no window
    from benchwise.passage_cli import window_entry
    sys.exit(window_entry(args))
from benchwise.launch import is_window_start  # noqa: E402

if is_window_start(args):
    from benchwise.launch import run_window
    sys.exit(run_window(args))
elif sys.stdout is None:
    # The window build has no console, so command-line output would vanish without a trace.
    import ctypes
    ctypes.windll.user32.MessageBoxW(
        None,
        "Benchwise.exe is the desktop app and cannot print to a terminal.\n"
        "For the command line use Benchwise-cli.exe from the same folder, e.g.\n\n"
        "    .\\Benchwise-cli.exe --list\n\n"
        "Benchwise.exe masaüstü uygulamasıdır, terminale yazı yazamaz.\n"
        "Komut satırı için aynı klasördeki Benchwise-cli.exe dosyasını kullanın.",
        "Benchwise", 0x40)
    sys.exit(2)
else:
    from recoverytool.cli import main
    sys.exit(main())
