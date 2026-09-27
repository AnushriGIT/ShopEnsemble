"""Tests for the agent-call retry wrapper (ports test_persistence.py's shape)."""

from dataclasses import dataclass
from decimal import Decimal

import httpx
import openai
import pytest

from app.agents.retry import call_with_retry

_REQUEST = httpx.Request("POST", "https://api.openai.com/v1/responses")


@dataclass(frozen=True)
class _FakeUsage:
    """Stands in for PydanticAI's real ``RunUsage`` — only the fields
    ``call_with_retry``'s usage-logging path actually reads."""

    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: Decimal | None


@dataclass(frozen=True)
class _FakeAgentRunResult:
    """Stands in for a PydanticAI ``AgentRunResult`` — has a ``.usage``
    property, same shape ``call_with_retry`` reads via ``getattr``."""

    usage: _FakeUsage


async def test_call_with_retry_recovers_after_transient_failures():
    calls = {"count": 0}

    async def flaky_call():
        calls["count"] += 1
        if calls["count"] <= 2:
            raise openai.APITimeoutError(request=_REQUEST)
        return "ok"

    result, stats = await call_with_retry(
        flaky_call, max_retries=3, backoff_base_seconds=0.01, backoff_max_seconds=0.05
    )

    assert result == "ok"
    assert calls["count"] == 3
    assert stats.retries == 2
    assert stats.latency_seconds >= 0


async def test_call_with_retry_fails_after_exhausting_retries():
    calls = {"count": 0}

    async def always_fails():
        calls["count"] += 1
        raise openai.APITimeoutError(request=_REQUEST)

    with pytest.raises(openai.APITimeoutError):
        await call_with_retry(always_fails, max_retries=2, backoff_base_seconds=0.01, backoff_max_seconds=0.02)

    # 1 initial attempt + 2 retries = 3 total calls.
    assert calls["count"] == 3


async def test_call_with_retry_does_not_retry_non_transient_errors():
    calls = {"count": 0}

    async def raises_value_error():
        calls["count"] += 1
        raise ValueError("not a transient OpenAI failure")

    with pytest.raises(ValueError):
        await call_with_retry(raises_value_error, max_retries=5)

    # A non-transient error must fail immediately with zero retries/backoff.
    assert calls["count"] == 1


async def test_call_with_retry_logs_usage_when_the_result_has_a_usage_property(caplog: pytest.LogCaptureFixture):
    """Phase 4b: closes Section 11's 'Token cost per turn' gap — one shared
    hook point covering every LLM call site, using PydanticAI's own
    AgentRunResult.usage rather than a hand-rolled pricing table."""

    fake_result = _FakeAgentRunResult(
        usage=_FakeUsage(requests=1, input_tokens=42, output_tokens=8, total_tokens=50, cost=Decimal("0.0001"))
    )

    with caplog.at_level("INFO", logger="app.agents.retry"):
        result, _ = await call_with_retry(lambda: _return(fake_result), label="review_summary_agent")

    assert result is fake_result
    [record] = [r for r in caplog.records if r.message.startswith("llm_usage")]
    assert "label=review_summary_agent" in record.message
    assert "input_tokens=42" in record.message
    assert "output_tokens=8" in record.message
    assert "total_tokens=50" in record.message
    assert "cost_usd=0.0001" in record.message


async def test_call_with_retry_does_not_log_usage_when_the_result_has_none(caplog: pytest.LogCaptureFixture):
    """A plain, non-AgentRunResult return value (e.g. a bare ``str``, as the
    other tests in this file use) must not crash — ``call_with_retry`` stays
    generic, not hard-coupled to PydanticAI's result shape."""

    with caplog.at_level("INFO", logger="app.agents.retry"):
        result, _ = await call_with_retry(lambda: _return("ok"))

    assert result == "ok"
    assert not [r for r in caplog.records if r.message.startswith("llm_usage")]


async def _return(value):
    return value
