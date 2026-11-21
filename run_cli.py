"""Entry point of the command-line executable (dist\\Benchwise-cli.exe).

A console program, so it runs inside the terminal it is started from: output appears there, the
terminal waits for it and Ctrl+C stops it.  It does not demand administrator rights in its
manifest, because Windows would then run it in a new window that closes when it ends; the
commands that read a disk ask for an administrator terminal instead.
"""

import sys

from recoverytool.cli import main

sys.exit(main())
