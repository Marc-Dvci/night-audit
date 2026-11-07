"""``scripts/ui_check.py``'s script-payload check: a check with nothing to check says so and does not fail."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _ui_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ui_check", ROOT / "scripts" / "ui_check.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_regression_a_night_with_no_payload_is_not_applicable_rather_than_a_failure() -> None:
    """Bug: on the live lab night, which plants no script tag, the check printed ``RESULT: FAIL ['xss']`` because
    ``script payload shown as text: 0 place(s)``."""
    ok, line = _ui_check().xss_verdict(payload_in_data=0, shown=0, dialogs=0)
    assert ok
    assert line == "xss: not applicable, no payload on this night"


@pytest.mark.parametrize(
    ("in_data", "shown", "dialogs", "ok"),
    [
        (1, 1, 0, True),
        (3, 2, 0, True),
        (1, 0, 0, False),  # a payload in the data that the page does not show as text
        (1, 1, 1, False),  # shown as text, but a dialog opened too
        (0, 0, 1, False),  # no payload in the data, and still a dialog
    ],
)
def test_a_payload_must_be_shown_as_text_and_no_dialog_may_open(
    in_data: int, shown: int, dialogs: int, ok: bool
) -> None:
    verdict, line = _ui_check().xss_verdict(payload_in_data=in_data, shown=shown, dialogs=dialogs)
    assert verdict is ok
    assert line.startswith("xss: ")


def test_the_payload_is_found_in_a_json_response_however_it_is_escaped() -> None:
    check = _ui_check()
    assert check.payload_count('{"name": "<img src=x onerror=alert(1)>"}') == 1
    assert check.payload_count('{"name": "\\u003cimg src=x onerror=alert(1)\\u003e"}') == 1
    assert check.payload_count('{"name": "i-0c8b3995db6d57788"}') == 0


def test_regression_a_json_redirect_is_not_read_for_the_payload() -> None:
    """Bug: on the deployed URL a JSON response was a redirect, and reading its body printed a Playwright traceback
    (``Response body is unavailable for redirect responses``) before ``RESULT: PASS``."""
    check = _ui_check()
    assert not check.has_json_body(307, "application/json")
    assert not check.has_json_body(301, "application/json")
    assert check.has_json_body(200, "application/json; charset=utf-8")
    assert not check.has_json_body(200, "text/html")
