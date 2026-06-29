"""
Dialogue Manager Adapter — Bridges any voice/text pipeline to the dialogue engine.
Provides a clean, plain text interface suitable for Pipecat and other integrations.
"""

import logging
import sys
import os

# Ensure backend directory is in path for robust module imports
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.session_service import SessionNotFoundError, get_session_service

logger = logging.getLogger("InterviewDialogueAdapter")


class InterviewDialogueAdapter:
    """
    Adapter between raw audio/text streams and the core interview engine.

    All session state is delegated to SessionService (single source of truth).
    """

    def __init__(self, session_service=None):
        self._sessions = get_session_service() if session_service is None else session_service

    def start_interview(self, candidate_profile: dict) -> dict:
        """
        Start/initialize an interview session.

        Args:
            candidate_profile: Dict with candidate resume data (skills, experience).

        Returns:
            dict: Session start status and intro greeting suitable for TTS.
        """
        try:
            session_id, result = self._sessions.start_interview(candidate_profile)
            dm = self._sessions.get_dialogue_manager(session_id)
            status = dm.get_status()
            current_state = status.get("state", "intro")
            turn_count = status.get("turn_count", 0)

            return {
                "session_id": session_id,
                "ai_response_text": result.get("question", ""),
                "current_state": current_state,
                "turn_count": turn_count,
                "is_complete": current_state == "wrapup",
                "evaluation_summary": status.get("evaluation_summary"),
                "error": None,
            }
        except Exception as e:
            logger.exception("Failed to start interview")
            return {
                "session_id": "",
                "ai_response_text": "",
                "current_state": "unknown",
                "turn_count": 0,
                "is_complete": True,
                "evaluation_summary": None,
                "error": str(e),
            }

    def process_user_text(self, session_id: str, text: str) -> dict:
        """
        Pass a candidate transcript into the dialogue engine and get the next question.

        Args:
            session_id: Session UUID.
            text: Candidate answer transcript.

        Returns:
            dict: Response with session state and next question for TTS.
        """
        if not session_id or not self._sessions.has(session_id):
            return {
                "session_id": session_id or "",
                "ai_response_text": "",
                "current_state": "unknown",
                "turn_count": 0,
                "is_complete": True,
                "evaluation_summary": None,
                "error": f"Session ID '{session_id}' not found.",
            }

        try:
            result = self._sessions.process_turn(session_id, text)
            status = self._sessions.get_status(session_id)
            current_state = status.get("state", "unknown")
            turn_count = status.get("turn_count", 0)

            last_eval = result.get("evaluation")
            evaluation_summary = None
            if last_eval:
                evaluation_summary = {
                    "overall_score": last_eval.get("overall_score", 0),
                    "weighted_score": last_eval.get("weighted_overall_score", 0),
                    "weakest_dimension": last_eval.get("weakest_dimension", "N/A"),
                    "hire_signal": last_eval.get("hire_signal", "N/A"),
                }

            return {
                "session_id": session_id,
                "ai_response_text": result.get("question", ""),
                "current_state": current_state,
                "turn_count": turn_count,
                "is_complete": current_state == "wrapup",
                "evaluation_summary": evaluation_summary,
                "error": None,
            }
        except SessionNotFoundError:
            return {
                "session_id": session_id,
                "ai_response_text": "",
                "current_state": "unknown",
                "turn_count": 0,
                "is_complete": True,
                "evaluation_summary": None,
                "error": f"Session ID '{session_id}' not found.",
            }
        except Exception as e:
            logger.exception("Error processing text for session %s", session_id)
            dm = self._sessions.get(session_id)
            ctx = dm.dialogue_manager.context if dm else None
            return {
                "session_id": session_id,
                "ai_response_text": "",
                "current_state": ctx.state.value if ctx else "unknown",
                "turn_count": ctx.turn_count if ctx else 0,
                "is_complete": False,
                "evaluation_summary": None,
                "error": str(e),
            }

    def get_report(self, session_id: str) -> dict:
        """Retrieve the final evaluation report for a session."""
        if not session_id or not self._sessions.has(session_id):
            return {"error": f"Session ID '{session_id}' not found."}

        try:
            return self._sessions.get_report(session_id)
        except SessionNotFoundError:
            return {"error": f"Session ID '{session_id}' not found."}
        except Exception as e:
            logger.exception("Failed to generate report for session %s", session_id)
            return {"error": str(e)}

    def end_interview(self, session_id: str) -> dict:
        """
        Conclude the interview, persist final scores, and remove from active store.
        """
        end_result = self._sessions.end_session(session_id, remove=True)
        return {
            "session_id": end_result["session_id"],
            "status": end_result["status"],
            "final_report": end_result.get("final_report"),
            "error": end_result.get("error"),
        }
