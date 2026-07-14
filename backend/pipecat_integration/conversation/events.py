"""Versioned conversation event payloads (wire contract for the live chat UI)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = 1

# Wire envelope type (existing clients ignore unknown types safely).
WIRE_TYPE = "conversation_event"

Role = str  # "assistant" | "user" | "system"
Phase = str  # "listening" | "thinking" | "speaking"
MessageStatus = str  # "final" (v1); "interim" reserved for captions later


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_message_event(
    *,
    role: Role,
    text: str,
    session_id: str = "",
    message_id: str | None = None,
    turn_id: str | None = None,
    status: MessageStatus = "final",
) -> dict[str, Any]:
    """Build a finalized (or later interim) chat message event."""
    return {
        "type": WIRE_TYPE,
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid4()),
        "session_id": session_id or "",
        "ts": _utc_now_iso(),
        "kind": "message",
        "role": role,
        "text": text,
        "message_id": message_id or str(uuid4()),
        "turn_id": turn_id or "",
        "status": status,
    }


def make_phase_event(
    *,
    phase: Phase,
    session_id: str = "",
) -> dict[str, Any]:
    """UI-only interview phase (does not affect dialogue / scoring)."""
    return {
        "type": WIRE_TYPE,
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid4()),
        "session_id": session_id or "",
        "ts": _utc_now_iso(),
        "kind": "phase",
        "phase": phase,
    }


def make_session_event(
    *,
    action: str,
    session_id: str = "",
) -> dict[str, Any]:
    """Session lifecycle marker (started / ended)."""
    return {
        "type": WIRE_TYPE,
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid4()),
        "session_id": session_id or "",
        "ts": _utc_now_iso(),
        "kind": "session",
        "action": action,
    }
