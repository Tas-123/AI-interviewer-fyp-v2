"""Outbound live conversation event projection for the Pipecat voice client.

Dialogue / evaluation stay unaware of this module. InterviewProcessor (and the
bot greeting path) emit finalized turn facts; the WebSocket serializer ships
them as versioned JSON events for the manual client's conversation UI.
"""

from pipecat_integration.conversation.events import (
    SCHEMA_VERSION,
    make_message_event,
    make_phase_event,
    make_session_event,
)
from pipecat_integration.conversation.publisher import ConversationEventPublisher

__all__ = [
    "SCHEMA_VERSION",
    "ConversationEventPublisher",
    "make_message_event",
    "make_phase_event",
    "make_session_event",
]
