"""P15: the shipped browser verifier and the Python verifier agree on every pack (ui-kit Req 6.1, 6.4).

One Chromium page is reused for every example. It imports the exact shipped module, ``assets/verify.js``, and is fed
packs generated here from hostile ledger values, untouched or with one character changed anywhere.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from hostile import RUN_TIME, controls, ledger_snapshots
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from nightaudit.control import ControlConfig
from nightaudit.evidence import verify_evidence_pack, write_evidence_pack
from nightaudit.matcher import match
from nightaudit.models import LedgerSnapshot

from e2e.browser_kit import Nights, new_page

pytestmark = [pytest.mark.e2e, pytest.mark.property]

HOSTILE_TEXT = st.one_of(
    st.sampled_from(
        [
            "\u202eevil\u202c",
            "\u2066x\u2069",
            "\U0001f9db\U0001f47b",
            '"quoted" \\ back',
            "\x7f\x00\x1f",
            "\ud800 lone",
            "\uffff\U00010000",
        ]
    ),
    st.text(max_size=12),
)
#: Replacement characters: printable ASCII, a quote, a backslash and two non-ASCII characters. Never a newline.
REPLACEMENTS = st.sampled_from(list('x0f}{:,"\\ ') + ["\u00e9", "\u202e"])

BROWSER_VERIFY = """async ([jsonl, manifest]) => {
  const m = await import("./assets/verify.js");
  return await m.verifyPack(jsonl, manifest);
}"""


@pytest.fixture(scope="module")
def verifier(browser: Any, base_url: str, nights: tuple[Path, Nights]) -> Iterator[Any]:
    page = new_page(browser)
    page.goto(f"{base_url}/")
    page.wait_for_selector("#headline")
    yield page
    page.context.close()


def _pack(snapshots: list[LedgerSnapshot], control: ControlConfig, extra: dict[str, str]) -> tuple[str, str]:
    for snapshot in snapshots:
        snapshot.records = [r.model_copy(update={"attrs": {**r.attrs, **extra}}) for r in snapshot.records]
    result = match(snapshots, control, RUN_TIME)
    with tempfile.TemporaryDirectory() as tmp:
        write_evidence_pack(result, Path(tmp))
        return (Path(tmp) / "evidence.jsonl").read_text("utf-8"), (Path(tmp) / "manifest.json").read_text("utf-8")


def _python(jsonl: str, manifest: str) -> Any:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "evidence.jsonl").write_bytes(jsonl.encode("utf-8", "surrogatepass"))
        (Path(tmp) / "manifest.json").write_text(manifest, "utf-8")
        return verify_evidence_pack(Path(tmp))


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    ledger_snapshots(max_size=4),
    controls(),
    st.dictionaries(st.sampled_from(["Name", "note"]), HOSTILE_TEXT),
    st.booleans(),
    st.data(),
)
def test_property_browser_and_python_verdicts_agree(
    verifier: Any,
    snapshots: list[LedgerSnapshot],
    control: ControlConfig,
    extra: dict[str, str],
    change: bool,
    data: st.DataObject,
) -> None:
    jsonl, manifest = _pack(snapshots, control, extra)
    if change and jsonl:
        at = data.draw(st.integers(0, len(jsonl) - 2), label="position")
        if jsonl[at] != "\n":
            new = data.draw(REPLACEMENTS.filter(lambda c: c != jsonl[at]), label="replacement")
            jsonl = jsonl[:at] + new + jsonl[at + 1 :]
    expected = _python(jsonl, manifest)
    actual = verifier.evaluate(BROWSER_VERIFY, [jsonl, json.loads(manifest)])
    assert (actual["ok"], actual["failedRow"]) == (expected.ok, expected.failed_row), (actual, expected)
    if expected.ok:
        assert actual["finalHash"] == expected.final_hash
        assert (actual["rows"], actual["findings"]) == (expected.rows, expected.findings)
