"""``python -m benchwise`` starts the window; ``--open=<tool id>`` opens a tool straight away.
Any other arguments run the command line (``python -m benchwise --list``)."""

import sys

args = sys.argv[1:]
if not args or (len(args) == 1 and args[0].startswith("--open=")):
    from benchwise.shell import main
    main(open_tool=args[0].split("=", 1)[1] if args else None)
else:
    from recoverytool.cli import main
    sys.exit(main())
