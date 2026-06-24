"""
Voice Session Manager — Manages active voice interview sessions.

Tracks per-session conversation state, transcript buffers, and
DialogueManager references. Supports automatic expiry of inactive sessions.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from dialogue.dialogue_manager import DialogueManager
from dialogue.interview_flow_controller import InterviewFlowController


# Sessions expire after 30 minutes of inactivity
SESSION_TIMEOUT_SECONDS = 30 * 60


@dataclass
class VoiceSession:
    """State container for one active voice interview session."""

    session_id: str
    dialogue_manager: DialogueManager
    flow_controller: InterviewFlowController
    candidate_role: str = ""
    candidate_skills: list = field(default_factory=list)
    current_stage: str = "init"
    turn_count: int = 0
    transcript_buffer: str = ""
    conversation_history: list = field(default_factory=list)
    last_activity: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    is_closed: bool = False


class VoiceSessionManager:
    """
    Manages the pool of active voice interview sessions.

    Handles creation, retrieval, expiry, and cleanup of VoiceSessions.
    Thread-safe for single-process async usage.
    """

    def __init__(self):
        self._sessions: dict[str, VoiceSession] = {}

    def create_session(
        self,
        resume_data: dict,
        session_id: str = None,
    ) -> VoiceSession:
        """
        Create a new voice interview session.

        Args:
            resume_data: candidate resume data dict
            session_id: optional pre-assigned session ID

        Returns:
            New VoiceSession instance.
        """
        sid = session_id or str(uuid.uuid4())
        role = resume_data.get("role", "")
        skills = resume_data.get("skills", [])

        dm = DialogueManager(resume_data, session_id=sid)
        fc = InterviewFlowController(sid, candidate_role=role,
                                     candidate_skills=skills)

        session = VoiceSession(
            session_id=sid,
            dialogue_manager=dm,
            flow_controller=fc,
            candidate_role=role,
            candidate_skills=skills,
        )
        self._sessions[sid] = session
        return session

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Retrieve an active session by ID, or None if not found/expired."""
        session = self._sessions.get(session_id)
        if session and not session.is_closed:
            return session
        return None

    def touch_session(self, session_id: str):
        """Update the last activity timestamp for a session."""
        session = self._sessions.get(session_id)
        if session:
            session.last_activity = time.time()

    def close_session(self, session_id: str) -> bool:
        """Mark a session as closed."""
        session = self._sessions.get(session_id)
        if session:
            session.is_closed = True
            return True
        return False

    def remove_session(self, session_id: str):
        """Remove a session from the manager entirely."""
        self._sessions.pop(session_id, None)

    def cleanup_expired(self) -> int:
        """
        Remove sessions that have been inactive beyond the timeout.

        Returns:
            Number of sessions removed.
        """
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if (now - s.last_activity) > SESSION_TIMEOUT_SECONDS or s.is_closed
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def get_active_count(self) -> int:
        """Return count of non-closed sessions."""
        return sum(1 for s in self._sessions.values() if not s.is_closed)

    def list_sessions(self) -> list[dict]:
        """Return summary of all active sessions."""
        return [
            {
                "session_id": s.session_id,
                "current_stage": s.current_stage,
                "turn_count": s.turn_count,
                "candidate_role": s.candidate_role,
                "is_closed": s.is_closed,
                "idle_seconds": round(time.time() - s.last_activity, 1),
            }
            for s in self._sessions.values()
        ]

    def append_transcript_chunk(self, session_id: str, text: str):
        """Append a speech chunk to the session's transcript buffer."""
        session = self._sessions.get(session_id)
        if session:
            if session.transcript_buffer:
                session.transcript_buffer += " " + text.strip()
            else:
                session.transcript_buffer = text.strip()
            session.last_activity = time.time()

    def flush_transcript(self, session_id: str) -> str:
        """Flush and return the accumulated transcript buffer."""
        session = self._sessions.get(session_id)
        if not session:
            return ""
        transcript = session.transcript_buffer.strip()
        session.transcript_buffer = ""
        return transcript
