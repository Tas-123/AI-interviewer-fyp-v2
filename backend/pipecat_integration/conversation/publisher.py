"""ConversationEventPublisher — shapes turn facts into transport frames."""

from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from pipecat_integration.conversation.events import (
    make_message_event,
    make_phase_event,
    make_session_event,
)


def wrap_transport_message(message: dict[str, Any]) -> Any:
    """Wrap a JSON-serializable dict as an output transport message frame.

    Uses Pipecat's OutputTransportMessageFrame when available so the frame
    passes through TTS and is written by the WebSocket transport. Falls back
    to a simple attribute object for dry-run / unit tests without Pipecat.
    """
    try:
        from pipecat.frames.frames import OutputTransportMessageFrame

        return OutputTransportMessageFrame(message=message)
    except ImportError:

        class _MockTransportMessage:
            def __init__(self, message: dict[str, Any]):
                self.message = message

        return _MockTransportMessage(message)


class ConversationEventPublisher:
    """Builds versioned conversation events bound to the active session id."""

    def __init__(self, session_id_getter: Callable[[], str] | None = None):
        self._session_id_getter = session_id_getter or (lambda: "")

    @property
    def session_id(self) -> str:
        try:
            return self._session_id_getter() or ""
        except Exception:
            return ""

    def new_turn_id(self) -> str:
        return str(uuid4())

    def message(
        self,
        *,
        role: str,
        text: str,
        turn_id: str | None = None,
        message_id: str | None = None,
        status: str = "final",
    ) -> dict[str, Any]:
        return make_message_event(
            role=role,
            text=text,
            session_id=self.session_id,
            turn_id=turn_id,
            message_id=message_id,
            status=status,
        )

    def phase(self, phase: str) -> dict[str, Any]:
        return make_phase_event(phase=phase, session_id=self.session_id)

    def session(self, action: str) -> dict[str, Any]:
        return make_session_event(action=action, session_id=self.session_id)

    def frame_for(self, event: dict[str, Any]) -> Any:
        return wrap_transport_message(event)
