"""Entry point used by PyInstaller and for running from a source checkout."""

import sys

if len(sys.argv) > 1:
    from recoverytool.cli import main
    sys.exit(main())
else:
    from recoverytool.gui import main
    main()
