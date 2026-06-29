"""
Central logging bootstrap for all runtimes (FastAPI, Pipecat bot, scripts).
"""

from __future__ import annotations

import logging
import sys

from core.config import settings


def setup_logging(level: str | None = None) -> None:
    """Configure root logging once per process."""
    log_level = (level or settings.log_level).upper()
    numeric = getattr(logging, log_level, logging.INFO)

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(numeric)
        return

    logging.basicConfig(
        level=numeric,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    # Quiet noisy third-party loggers in production demos
    if numeric >= logging.INFO:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
