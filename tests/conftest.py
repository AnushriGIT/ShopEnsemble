"""Shared fixtures for the ShopEnsemble pipeline test suite."""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.pipeline.persistence import (
    Base,
    DATABASE_URL_ENV,
    DEFAULT_DATABASE_URL,
    create_engine,
    create_session_factory,
)

# Same env-var-override-with-default idiom as app/main.py's REPORT_ROOT_ENV.
TEST_REPORT_ROOT_ENV = "SHOPENSEMBLE_TEST_REPORT_ROOT"
DEFAULT_TEST_REPORT_ROOT = "reports/test-results"


def _suite_label(markexpr: str) -> str | None:
    """Classify a run's ``-m`` expression as one of this project's 3 named
    suites, so ``latest.json`` being overwritten by whichever suite ran most
    recently doesn't bury an older suite's own last result. Only recognizes
    this project's actual mark expressions (``eval``, ``integration``,
    ``not integration and not eval``) — an ad hoc run with no ``-m`` flag (or
    an unrecognized expression) gets no suite label, only the unconditional
    timestamped file + ``latest.json`` below.
    """

    tokens = markexpr.split()

    def _positively_selected(name: str) -> bool:
        if name not in tokens:
            return False
        index = tokens.index(name)
        return index == 0 or tokens[index - 1] != "not"

    if _positively_selected("eval"):
        return "eval"
    if _positively_selected("integration"):
        return "integration"
    if "eval" in tokens and "integration" in tokens and not _positively_selected("eval") and not _positively_selected("integration"):
        return "fast"
    return None


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Write a small durable JSON results file after every pytest run (Rule 4).

    Root-level, so this fires for *any* invocation — the fast suite, an
    `integration` run, the real-API `eval` suite, or a mix — not just eval.
    Writes a timestamped file (history), ``latest.json`` (whatever ran most
    recently, of any kind), and — when the run's ``-m`` expression matches
    one of this project's named suites — a suite-specific
    ``latest-<suite>.json`` too, so a later fast-suite run doesn't bury the
    eval suite's own last result behind ``latest.json``. All under
    ``reports/test-results/`` (already-gitignored, same convention as the
    pipeline's run reports in ``app/main.py``); each payload also carries the
    actual CLI args pytest was invoked with.
    """

    reports = [
        report
        for outcome in ("passed", "failed", "skipped")
        for report in terminalreporter.stats.get(outcome, [])
        if report.when == "call"
    ]
    if not reports:
        return

    results = []
    for report in reports:
        entry: dict[str, str] = {"test": report.nodeid, "outcome": report.outcome}
        if report.outcome != "passed":
            try:
                entry["detail"] = str(report.longrepr.reprcrash.message)
            except AttributeError:
                entry["detail"] = str(report.longrepr)
        results.append(entry)

    markexpr = terminalreporter.config.getoption("markexpr", "") or ""
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "pytest_args": list(terminalreporter.config.invocation_params.args),
        "suite": _suite_label(markexpr),
        "total": len(results),
        "passed": sum(1 for r in results if r["outcome"] == "passed"),
        "failed": sum(1 for r in results if r["outcome"] == "failed"),
        "skipped": sum(1 for r in results if r["outcome"] == "skipped"),
        "results": results,
    }

    report_root = Path(os.getenv(TEST_REPORT_ROOT_ENV, DEFAULT_TEST_REPORT_ROOT))
    report_root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    serialized = json.dumps(payload, indent=2)
    (report_root / f"{run_id}.json").write_text(serialized)
    (report_root / "latest.json").write_text(serialized)
    if payload["suite"] is not None:
        (report_root / f"latest-{payload['suite']}.json").write_text(serialized)


def _postgres_reachable(url: str) -> bool:
    """Cheap TCP probe so DB-dependent tests skip cleanly instead of hanging."""

    parsed = make_url(url)
    try:
        with socket.create_connection((parsed.host, parsed.port or 5432), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def database_url() -> str:
    """Resolve the integration-test database URL the same way persistence.py does."""

    return os.getenv(DATABASE_URL_ENV, DEFAULT_DATABASE_URL)


@pytest.fixture(scope="session")
def postgres_available(database_url: str) -> bool:
    return _postgres_reachable(database_url)


@pytest_asyncio.fixture
async def db_engine(database_url: str, postgres_available: bool) -> AsyncEngine:
    # Skipping (rather than failing) keeps `pytest -q` usable on a machine
    # without `docker compose up -d postgres` running; only tests marked
    # `integration` depend on this fixture.
    if not postgres_available:
        pytest.skip("PostgreSQL not reachable; run `docker compose up -d postgres` first.")

    engine = create_engine(database_url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def clean_schema(db_engine: AsyncEngine):
    """Drop-and-recreate all tables so each test starts from an empty schema."""

    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with db_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session_factory(
    db_engine: AsyncEngine, clean_schema: None
) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(db_engine)
