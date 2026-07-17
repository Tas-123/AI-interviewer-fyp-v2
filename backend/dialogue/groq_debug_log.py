"""Optional Groq prompt/reply logging for live interview debugging."""

from __future__ import annotations

import datetime
import logging

logger = logging.getLogger(__name__)

_MAX_CHARS = 4000


def log_groq_exchange(label: str, value: str, *, max_chars: int = _MAX_CHARS) -> None:
    """Append prompt/reply to live_interview_debug.log when DEBUG_LIVE_LOGGING is on."""
    try:
        from core.config import settings

        if not settings.debug_live_logging:
            return

        log_file = settings.live_debug_log
        log_file.parent.mkdir(parents=True, exist_ok=True)

        text = str(value or "")
        if max_chars > 0 and len(text) > max_chars:
            text = text[: max_chars - 3].rstrip() + "..."

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"\n[{ts}] {label}\n")
            f.write(text.strip() + "\n")
            f.write("-" * 80 + "\n")
    except Exception as exc:
        logger.warning("Groq debug log failed: %s", exc)
