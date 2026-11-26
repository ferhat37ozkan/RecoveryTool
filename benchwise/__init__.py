"""Benchwise - an open-source workbench of disk, hardware and Windows tools.

The window (``benchwise.shell``) shows categories as big cards; each category holds tool cards.
The tools live in their own packages: File Recovery is ``recoverytool``.

Only constants here, so that every package can import the identity without pulling in the UI.
"""

__version__ = "1.6.0"
NAME = "Benchwise"
DOMAIN = "idlepose.com"
APP_NAME = "%s@%s" % (NAME, DOMAIN)       # window title, message boxes, reports, command-line help
REPO = "ferhat37ozkan/RecoveryTool"       # GitHub repository whose releases the update check reads
