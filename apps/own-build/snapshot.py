"""Record the tracked files and the spec promises of one commit: ``uv run python apps/own-build/snapshot.py``.

The work is in ``own_build.snapshot``; this file is the command. It writes apps/own-build/data/tracked-files.csv and
apps/own-build/data/spec-files.csv for HEAD (or ``--commit``), and runs only read commands of git.
"""

from __future__ import annotations

import sys

from own_build.snapshot import main

if __name__ == "__main__":
    sys.exit(main())
