"""
VAD Simulator — Simulates Voice Activity Detection for text-based sessions.

Processes incoming WebSocket messages and determines whether the candidate
has finished speaking. Designed as a drop-in replaceable module — a real
audio-based VAD can swap this class without changing the rest of the system.
"""


class VADSimulator:
    """
    Simulates voice activity detection using message types.

    In text simulation mode, end-of-turn is signaled explicitly via
    a 'speech_end' message. When a real VAD is integrated, this class
    will be replaced by one that detects silence in audio streams.
    """

    def __init__(self, silence_threshold_ms: int = 1500):
        # Future: silence_threshold_ms will control how long silence
        # must persist before triggering end-of-turn in audio mode.
        self.silence_threshold_ms = silence_threshold_ms

    def process_message(self, message: dict) -> dict:
        """
        Analyze an incoming message to determine turn status.

        Args:
            message: parsed WebSocket message dict

        Returns:
            {
                "is_end_of_turn": bool,
                "is_speech": bool,
                "text": str (extracted text if speech)
            }
        """
        msg_type = message.get("type", "")

        if msg_type == "speech_end":
            return {
                "is_end_of_turn": True,
                "is_speech": False,
                "text": "",
            }

        if msg_type == "speech_chunk":
            return {
                "is_end_of_turn": False,
                "is_speech": True,
                "text": message.get("text", ""),
            }

        # Unknown message type — not speech
        return {
            "is_end_of_turn": False,
            "is_speech": False,
            "text": "",
        }

    def reset(self):
        """Reset internal state (no-op in simulation mode)."""
        pass
