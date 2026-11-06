"""Shared test configuration for Night Audit tests.

Hypothesis profile: 100 examples per property. When the environment variable ``CI`` is set, examples are derandomized
(the same examples on every run) and the example database is off, so a CI result does not depend on earlier runs.
The per-example deadline is off because it is measured with the real clock; the tests themselves never read the clock.
"""

from __future__ import annotations

import os

import pytest
from hypothesis import settings

settings.register_profile("nightaudit", max_examples=100, deadline=None, print_blob=True)
settings.register_profile("nightaudit-ci", max_examples=100, deadline=None, print_blob=True, derandomize=True,
                          database=None)
settings.load_profile("nightaudit-ci" if os.environ.get("CI") else "nightaudit")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-parity-fixture",
        action="store_true",
        help="rewrite skeleton/web/test/fixtures/parity.json from the current Python code",
    )
