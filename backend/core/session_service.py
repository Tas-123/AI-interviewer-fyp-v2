"""
Unified session service — single source of truth for interview sessions.

All runtimes (Pipecat voice, FastAPI REST, dev text WebSocket) delegate here.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterator, Optional

from dialogue.dialogue_manager import DialogueManager
from dialogue import database as db
from dialogue.session_bootstrap import bootstrap_from_request, build_candidate_profile

logger = logging.getLogger(__name__)

# Module-level singleton (one process, one store)
_service: Optional["SessionService"] = None


@dataclass
class InterviewSession:
    """In-memory record for one active interview."""

    session_id: str
    dialogue_manager: DialogueManager
    resume_data: dict
    created_at: float = field(default_factory=time.time)
    ended: bool = False


class SessionNotFoundError(KeyError):
    """Raised when a session_id is not in the active store."""


class SessionService:
    """
    Create, retrieve, process, and end interview sessions.

    Thread-safe enough for single-process async (FastAPI + Pipecat in separate
    processes each get their own singleton — Phase 1 target is unified within
    one process; cross-process sharing is out of scope).
    """

    def __init__(self) -> None:
        self._sessions: dict[str, InterviewSession] = {}

    # ── CRUD ───────────────────────────────────────────────────────

    def create(
        self,
        resume_data: dict | None = None,
        session_id: Optional[str] = None,
        *,
        session_start: dict | None = None,
    ) -> InterviewSession:
        """
        Create a new session or return an existing active one for session_id.

        Reuse supports REST /start followed by dev WS attach on the same id.

        Args:
            resume_data: Legacy flat resume dict (bootstrapped automatically).
            session_start: Full session-start payload (target_role, resume_text, etc.).
        """
        sid = session_id or str(uuid.uuid4())
        existing = self._sessions.get(sid)
        if existing and not existing.ended:
            return existing

        if session_start is not None:
            profile = bootstrap_from_request(session_start)
        elif resume_data is not None:
            profile = build_candidate_profile(resume_data=resume_data)
        else:
            profile = build_candidate_profile()

        normalized = profile.to_resume_data()
        dm = DialogueManager(normalized, session_id=sid)
        db.save_session(
            session_id=sid,
            resume_data=normalized,
            role_applied=normalized.get("role", ""),
        )
        session = InterviewSession(
            session_id=sid,
            dialogue_manager=dm,
            resume_data=normalized,
        )
        self._sessions[sid] = session
        logger.info(
            "Session created: %s (source=%s, role=%s)",
            sid,
            profile.profile_source,
            profile.target_role,
        )
        return session

    def get(self, session_id: str) -> Optional[InterviewSession]:
        """Return active session or None if missing/ended."""
        session = self._sessions.get(session_id)
        if session and not session.ended:
            return session
        return None

    def get_dialogue_manager(self, session_id: str) -> DialogueManager:
        """Return DialogueManager or raise SessionNotFoundError."""
        session = self.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session.dialogue_manager

    def has(self, session_id: str) -> bool:
        return self.get(session_id) is not None

    # ── Interview operations ───────────────────────────────────────

    def start_interview(
        self,
        resume_data: dict | None = None,
        session_id: Optional[str] = None,
        *,
        session_start: dict | None = None,
    ) -> tuple[str, dict]:
        """
        Create session and run the intro turn (empty transcript).

        Returns:
            (session_id, handle_turn result dict)
        """
        session = self.create(
            resume_data=resume_data,
            session_id=session_id,
            session_start=session_start,
        )
        result = session.dialogue_manager.handle_turn("")
        return session.session_id, result

    def process_turn(self, session_id: str, text: str) -> dict:
        """Process a candidate answer and return the next interviewer turn."""
        dm = self.get_dialogue_manager(session_id)
        return dm.handle_turn((text or "").strip())

    def get_status(self, session_id: str) -> dict:
        dm = self.get_dialogue_manager(session_id)
        return dm.get_status()

    def get_report(self, session_id: str) -> dict:
        dm = self.get_dialogue_manager(session_id)
        return dm.get_final_report()

    def end_session(self, session_id: str, *, remove: bool = True) -> dict:
        """
        Generate final report and optionally remove from active store.

        Args:
            session_id: Session to end.
            remove: If True, drop from memory after report (voice disconnect path).

        Returns:
            Dict with session_id, status, final_report, error.
        """
        session = self.get(session_id)
        if session is None:
            return {
                "session_id": session_id,
                "status": "not_found",
                "final_report": None,
                "error": f"Session ID '{session_id}' not found.",
            }

        try:
            final_report = session.dialogue_manager.get_final_report()
            session.ended = True
            if remove:
                self._sessions.pop(session_id, None)
            logger.info("Session ended: %s", session_id)
            return {
                "session_id": session_id,
                "status": "ended",
                "final_report": final_report,
                "error": None,
            }
        except Exception as exc:
            logger.exception("Error ending session %s", session_id)
            return {
                "session_id": session_id,
                "status": "error",
                "final_report": None,
                "error": str(exc),
            }

    # ── Introspection ──────────────────────────────────────────────

    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if not s.ended)

    def list_active_ids(self) -> list[str]:
        return [s.session_id for s in self._sessions.values() if not s.ended]

    def iter_active(self) -> Iterator[tuple[str, DialogueManager]]:
        for session in self._sessions.values():
            if not session.ended:
                yield session.session_id, session.dialogue_manager


def get_session_service() -> SessionService:
    """Return the process-wide SessionService singleton."""
    global _service
    if _service is None:
        _service = SessionService()
    return _service


def reset_session_service() -> None:
    """Clear singleton — for tests only."""
    global _service
    _service = None
