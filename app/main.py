"""CLI entry point: run the full ShopEnsemble pipeline and record its outcome on disk."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

from app.pipeline.orchestrator import PipelineRunReport, run_full_pipeline

load_dotenv()  # No-op if .env is absent; makes local SHOPENSEMBLE_* values usable.

REPORT_ROOT_ENV = "SHOPENSEMBLE_REPORT_ROOT"
QUARANTINE_ROOT_ENV = "SHOPENSEMBLE_QUARANTINE_ROOT"
BATCH_SIZE_ENV = "SHOPENSEMBLE_BATCH_SIZE"
MAX_INVALID_ROWS_ENV = "SHOPENSEMBLE_MAX_INVALID_ROWS"

# SHOPENSEMBLE_DATA_ROOT and SHOPENSEMBLE_DATABASE_URL are intentionally not read
# here: app.pipeline.paths and app.pipeline.persistence already read those
# two env vars internally when their corresponding parameters are left
# ``None``. Re-reading them here would create a second source of truth for
# the same configuration.


def _json_default(value):
    """Serialize the date/datetime fields that ``dataclasses.asdict`` leaves as-is."""

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _write_report(report: PipelineRunReport, report_root: Path, quarantine_root: Path) -> None:
    """Write one JSON run-report file and one JSON quarantine file per run.

    Resolves the governing spec's open decision on run-report/quarantine
    storage location: one file per run, named by ``run_id``, under the two
    directories the project's .env.example already anticipates (and that
    .gitignore already excludes).
    """

    report_root.mkdir(parents=True, exist_ok=True)
    quarantine_root.mkdir(parents=True, exist_ok=True)

    payload = asdict(report)
    payload.pop("quarantine")  # Written separately so operators can grep it independently.
    (report_root / f"{report.run_id}.json").write_text(
        json.dumps(payload, indent=2, default=_json_default), encoding="utf-8"
    )
    (quarantine_root / f"{report.run_id}.json").write_text(
        json.dumps([asdict(record) for record in report.quarantine], indent=2, default=_json_default),
        encoding="utf-8",
    )


async def _run() -> PipelineRunReport:
    batch_size = int(os.getenv(BATCH_SIZE_ENV, "500"))
    max_invalid_rows = int(os.getenv(MAX_INVALID_ROWS_ENV, "0"))
    report_root = Path(os.getenv(REPORT_ROOT_ENV, "reports"))
    quarantine_root = Path(os.getenv(QUARANTINE_ROOT_ENV, "quarantine"))

    try:
        report = await run_full_pipeline(batch_size=batch_size, max_invalid_rows=max_invalid_rows)
    except Exception as error:
        # A fail-fast validation error still carries the partial report
        # (see orchestrator.py's `error.pipeline_report` handoff), so the
        # quarantine detail is written even though persistence never started.
        failed_report = getattr(error, "pipeline_report", None)
        if failed_report is not None:
            _write_report(failed_report, report_root, quarantine_root)
        raise

    _write_report(report, report_root, quarantine_root)
    return report


def main() -> int:
    try:
        report = asyncio.run(_run())
    except Exception as error:
        print(f"Pipeline run failed: {error}")
        return 1

    print(f"Run {report.run_id} finished with status={report.status}")
    print(f"rows_persisted={report.rows_persisted} retries={report.retries}")
    return 0 if report.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
