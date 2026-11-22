"""``python -m benchwise`` starts the window (flags: see benchwise.launch); any other arguments run
the command line (``python -m benchwise --list``)."""

import sys

from benchwise.launch import is_window_start, run_window

args = sys.argv[1:]
if is_window_start(args):
    sys.exit(run_window(args))
else:
    from recoverytool.cli import main
    sys.exit(main())
