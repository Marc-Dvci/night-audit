"""Shared test configuration for the own-build app.

The same hypothesis profile as the skeleton: 100 examples per property; under ``CI`` the examples are derandomized and
the example database is off. The deadline is off because it is measured with the real clock.

The browser tests use the skeleton's harness as it is: ``e2e.browser_kit`` (page set-up, page opener, axe check). Its
folder is put on the import path here, so the skeleton itself needs no change.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from hypothesis import settings

SKELETON_TESTS = Path(__file__).resolve().parents[3] / "skeleton" / "tests"
if str(SKELETON_TESTS) not in sys.path:
    sys.path.append(str(SKELETON_TESTS))

settings.register_profile("own-build", max_examples=100, deadline=None, print_blob=True)
settings.register_profile(
    "own-build-ci", max_examples=100, deadline=None, print_blob=True, derandomize=True, database=None
)
settings.load_profile("own-build-ci" if os.environ.get("CI") else "own-build")
