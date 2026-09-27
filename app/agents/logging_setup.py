"""Shared logging configuration for this project's 2 process entry points
(``app.agents.cli``, ``app.api.main``).

Phase 4b wired up ``logging.basicConfig`` at each entry point so ``.info()``
calls (``llm_usage``, ``routing_decision``) were actually visible at all —
before that, they were silently dropped project-wide (root logger defaults
to WARNING). That fixed *visibility* but not *persistence*: those calls
only pointed at a console ``StreamHandler``, so the lines existed only in
whatever terminal ran the process and vanished with its scrollback.

This module adds a ``RotatingFileHandler`` alongside the console handler —
both entry points call ``configure_logging(...)`` with their own filename
rather than duplicating handler-construction logic in both places (the
same "one shared constant/helper, not two copies" reasoning as
``TRANSIENT_OPENAI_ERRORS``/``LLM_CALL_TIMEOUT_SECONDS`` in ``retry.py``).

Rotation caps are deliberately small (5 MB x 3 backups = 15 MB max per
entry point) — proportionate to a capstone with no long-running production
deployment target, not a production log-retention policy. No structured
(JSON) logging, no external log shipping/aggregation — not triggered by
any measured need, matching this project's established minimalism
elsewhere (e.g. Appendix B's stance on vector semantic caching).
"""

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file before rotating
BACKUP_COUNT = 3  # keep 3 rotated backups on top of the active file


def configure_logging(log_filename: str) -> None:
    """Set up console + rotating-file logging for the current process.

    ``log_filename`` is entry-point-specific (``"cli.log"``, ``"api.log"``)
    so the 2 processes never interleave into one file — each gets its own,
    written under ``LOG_DIR`` (created if missing).
    """

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / log_filename, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    console_handler = logging.StreamHandler()
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=[console_handler, file_handler])
