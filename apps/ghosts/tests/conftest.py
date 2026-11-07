"""Shared test configuration for the Ghosts app.

The same hypothesis profile as the skeleton: 100 examples per property; under ``CI`` the examples are derandomized and
the example database is off. The deadline is off because it is measured with the real clock.
"""

from __future__ import annotations

import os

from hypothesis import settings

settings.register_profile("ghosts", max_examples=100, deadline=None, print_blob=True)
settings.register_profile("ghosts-ci", max_examples=100, deadline=None, print_blob=True, derandomize=True,
                          database=None)
settings.load_profile("ghosts-ci" if os.environ.get("CI") else "ghosts")
