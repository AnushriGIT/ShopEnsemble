"""Retry-with-backoff for agent LLM calls.

Mirrors ``app.pipeline.persistence.persist_batch_with_retry``'s exact
``tenacity`` idiom: retry only on a known transient-error class, exponential
backoff with jitter, ``reraise=True`` so the final failure surfaces
unmodified, and a small stats dataclass reporting how many retries happened.
Per spec Section 9, a schema/validation failure is never retried — only
transient OpenAI errors are.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import TypeVar

import openai
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

T = TypeVar("T")

logger = logging.getLogger(__name__)

# Transient failures worth retrying: rate limiting and connectivity blips.
# Anything else (bad request, schema/validation errors, auth failures) is a
# data or programming error and must fail immediately with zero backoff.
TRANSIENT_OPENAI_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
)

# Phase 4b: closes a gap found during that plan's own research — spec
# Section 9's "Phase 1 minimum" per-call timeout was written down but never
# actually implemented anywhere. Applied via ModelSettings(timeout=...) at
# each build_*_agent() call site, not here — this constant is just the one
# shared source of truth both this module's docstring and every builder
# reference, matching TRANSIENT_OPENAI_ERRORS' role as a shared constant.
LLM_CALL_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class RetryStats:
    retries: int
    latency_seconds: float


async def call_with_retry(
    call: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    backoff_base_seconds: float = 0.5,
    backoff_max_seconds: float = 8.0,
    label: str | None = None,
) -> tuple[T, RetryStats]:
    """Run ``call()``, retrying on a transient OpenAI error only.

    ``call`` is a zero-argument callable so a fresh call (fresh request) is
    made per attempt, matching ``persist_batch_with_retry``'s "fresh
    session/transaction per attempt" rationale.

    ``label`` identifies the caller (e.g. ``"coordinator"``,
    ``"review_summary_agent"``) in the usage log line below — every call
    site in this codebase happens to wrap a PydanticAI ``agent.run(...)``,
    so this one hook point gives Section 11's "Token cost per turn"
    real data for free, without touching each of the 6 call sites'
    dispatch logic. Kept optional and looked up via ``getattr`` (not a type
    check) so this function stays generic — it doesn't hard-depend on
    PydanticAI's ``AgentRunResult`` shape.
    """

    started = monotonic()
    attempts = 0
    result: T | None = None

    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(TRANSIENT_OPENAI_ERRORS),
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential_jitter(initial=backoff_base_seconds, max=backoff_max_seconds),
        reraise=True,
    ):
        with attempt:
            attempts += 1
            result = await call()

    assert result is not None  # AsyncRetrying always executes at least once on success
    stats = RetryStats(retries=attempts - 1, latency_seconds=monotonic() - started)

    usage = getattr(result, "usage", None)
    if usage is not None:
        logger.info(
            "llm_usage label=%s requests=%s input_tokens=%s output_tokens=%s total_tokens=%s "
            "cost_usd=%s retries=%s latency_seconds=%.3f",
            label,
            usage.requests,
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
            usage.cost,
            stats.retries,
            stats.latency_seconds,
        )

    return result, stats
