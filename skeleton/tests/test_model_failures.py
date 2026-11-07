"""When the model fails, the finding keeps its deterministic template (Req 7.2, 7.3, audit rule 1).

The Bedrock client is stubbed at the network edge only: ``boto3.client`` returns an object whose ``converse`` raises or
answers as a recorded response would.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError, ReadTimeoutError
from nightaudit.control import ControlConfig
from nightaudit.explain import ModelConfig, ModelUnavailable, _extract_converse_text, explain_finding
from nightaudit.models import Finding, LedgerName, Record

TEMPLATE = "Exists and is paid for, but nobody approved it. On the bill: $41.20."


def _vampire() -> Finding:
    record = Record(
        ledger=LedgerName.billed,
        source="cur",
        row_id="b2",
        raw_key="i-0f3e",
        key="i-0f3e",
        amount=Decimal("41.20"),
        timestamp=datetime(2026, 11, 2, 21, 14, tzinfo=UTC),
    )
    return Finding(
        key="i-0f3e",
        region_code="OB",
        name="Vampire",
        severity="high",
        meaning="Exists and is paid for, but nobody approved it.",
        informational=False,
        records=[record],
        billed_amount=Decimal("41.20"),
    )


def _explain(call: Any, cfg: ModelConfig | None = None) -> Any:
    return explain_finding(_vampire(), cfg or ModelConfig(enabled=True), ControlConfig(), model_call=call)


def _raises(exc: BaseException) -> Any:
    def call(prompt: str) -> str:
        raise exc

    return call


def test_a_disabled_model_is_never_called() -> None:
    explanation = explain_finding(_vampire(), ModelConfig(), ControlConfig(), model_call=_raises(AssertionError()))
    assert (explanation.source, explanation.text) == ("template", TEMPLATE)


@pytest.mark.parametrize(
    "exc",
    [TimeoutError("read timed out"), ModelUnavailable("throttled"), ConnectionError("refused"), ImportError("boto3")],
    ids=["timeout", "unavailable", "connection", "no-sdk"],
)
def test_a_model_that_fails_leaves_the_template_and_is_not_a_rejection(exc: BaseException) -> None:
    explanation = _explain(_raises(exc))
    assert (explanation.source, explanation.text, explanation.rejected) == ("template", TEMPLATE, False)


@pytest.mark.parametrize("garbage", ["", "   \n\t", "\n"])
def test_an_empty_answer_leaves_the_template(garbage: str) -> None:
    assert _explain(lambda prompt: garbage).text == TEMPLATE


@pytest.mark.parametrize(
    ("garbage", "offending"),
    [
        ("Costs 41.21.", "41.21"),
        ("Costs -41.20.", "-41.20"),
        ("{'amount': 99, 'region': 'IOB'}", "99"),
        ("Seen 7 times since 1999.", "1999, 7"),
    ],
)
def test_an_answer_citing_a_number_outside_the_evidence_is_rejected_and_named(garbage: str, offending: str) -> None:
    explanation = _explain(lambda prompt: garbage)
    assert (explanation.source, explanation.text, explanation.rejected) == ("template", TEMPLATE, True)
    assert explanation.rejection_reason == f"number(s) not in evidence: {offending}"


def test_an_answer_of_words_and_evidence_numbers_is_kept() -> None:
    text = "Instance i-0f3e is on the bill at 41.20 and appears in no approved template."
    explanation = _explain(lambda prompt: text)
    assert (explanation.source, explanation.text) == ("model", text)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"output": None},
        {"output": {}},
        {"output": {"message": {}}},
        {"output": {"message": {"content": None}}},
        {"output": {"message": {"content": [{"image": "..."}]}}},
        {"output": {"message": {"content": ["text without a block"]}}},
    ],
    ids=["no-output", "null-output", "no-message", "no-content", "null-content", "no-text-block", "bare-string"],
)
def test_a_converse_response_missing_its_text_reads_as_empty(response: dict[str, Any]) -> None:
    assert _extract_converse_text(response) == ""


def test_a_converse_response_joins_its_text_blocks() -> None:
    response = {
        "output": {"message": {"content": [{"text": "Billed 41.20."}, {"image": "x"}, {"text": "Unapproved."}]}}
    }
    assert _extract_converse_text(response) == "Billed 41.20. Unapproved."


class _Bedrock:
    """A Bedrock runtime client: ``converse`` raises *error* or returns *response*."""

    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.response, self.error = response, error

    def converse(self, **_: Any) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.response or {}


@pytest.fixture()
def bedrock(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(client: _Bedrock) -> list[dict[str, Any]]:
        made: list[dict[str, Any]] = []

        def make(service: str, **kwargs: Any) -> _Bedrock:
            made.append({"service": service, **kwargs})
            return client

        monkeypatch.setattr(boto3, "client", make)
        return made

    return install


CFG = ModelConfig(enabled=True, model_id="amazon.nova-micro-v1:0", region="us-east-1", timeout=3)


@pytest.mark.parametrize(
    "error",
    [
        ReadTimeoutError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"),
        ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse"),
        ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Converse"),
    ],
    ids=["timeout", "throttled", "denied"],
)
def test_a_bedrock_error_leaves_the_template(bedrock: Any, error: Exception) -> None:
    bedrock(_Bedrock(error=error))
    explanation = explain_finding(_vampire(), CFG, ControlConfig())
    assert (explanation.source, explanation.text) == ("template", TEMPLATE)


def test_a_bedrock_answer_without_text_leaves_the_template(bedrock: Any) -> None:
    bedrock(_Bedrock(response={"output": {"message": {"content": []}}, "stopReason": "max_tokens"}))
    assert explain_finding(_vampire(), CFG, ControlConfig()).source == "template"


def test_the_bedrock_client_gets_the_configured_region_and_timeout(bedrock: Any) -> None:
    made = bedrock(_Bedrock(response={"output": {"message": {"content": [{"text": "Billed 41.20."}]}}}))
    explanation = explain_finding(_vampire(), CFG, ControlConfig())
    assert explanation.text == "Billed 41.20."
    assert [(m["service"], m["region_name"]) for m in made] == [("bedrock-runtime", "us-east-1")]
    config = made[0]["config"]
    assert (config.read_timeout, config.connect_timeout) == (3, 3)


def test_an_enabled_model_with_no_model_id_is_never_called(bedrock: Any) -> None:
    made = bedrock(_Bedrock(error=AssertionError("called")))
    explanation = explain_finding(_vampire(), ModelConfig(enabled=True, model_id=""), ControlConfig())
    assert (explanation.source, made) == ("template", [])
