"""
Dialogue Manager Adapter — Bridges any voice/text pipeline to the dialogue engine.
Provides a clean, plain text interface suitable for future integrations like Pipecat.
"""

import sys
import os
import uuid
import logging

# Ensure backend directory is in path for robust module imports
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.dialogue_manager import DialogueManager
from dialogue import database as db

logger = logging.getLogger("InterviewDialogueAdapter")

class InterviewDialogueAdapter:
    """
    Adapter class to interface between raw audio/text streams (such as Pipecat)
    and the core Interview Dialogue Manager.
    """
    def __init__(self):
        # Local session registry: session_id -> DialogueManager instance
        self.sessions = {}

    def start_interview(self, candidate_profile: dict) -> dict:
        """
        Start/initialize an interview session using the existing Dialogue Manager.
        
        Args:
            candidate_profile (dict): Dict containing candidate resume data (e.g. skills, experience).
            
        Returns:
            dict: Interview session start status and intro greeting suitable for TTS.
        """
        try:
            session_id = str(uuid.uuid4())
            
            # Initialize DialogueManager
            dm = DialogueManager(candidate_profile, session_id=session_id)
            self.sessions[session_id] = dm
            
            # Persist session to database (graceful fallback internally)
            db.save_session(
                session_id=session_id,
                resume_data=candidate_profile,
                role_applied=candidate_profile.get("role", "")
            )
            
            # Generate intro greeting (first turn with empty transcript)
            result = dm.handle_turn("")
            ai_response_text = result.get("question", "")
            
            # Determine if state is wrapup (highly unlikely on turn 0, but good for consistency)
            status = dm.get_status()
            current_state = status.get("state", "intro")
            turn_count = status.get("turn_count", 0)
            
            return {
                "session_id": session_id,
                "ai_response_text": ai_response_text,
                "current_state": current_state,
                "turn_count": turn_count,
                "is_complete": current_state == "wrapup",
                "evaluation_summary": status.get("evaluation_summary"),
                "error": None
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
                "error": str(e)
            }

    def process_user_text(self, session_id: str, text: str) -> dict:
        """
        Pass a candidate transcript/answer into the Dialogue Manager and get the next question.
        
        Args:
            session_id (str): Session UUID identifier.
            text (str): Candidate's answer text transcript.
            
        Returns:
            dict: response object containing session state and next question suitable for TTS.
        """
        if not session_id or session_id not in self.sessions:
            return {
                "session_id": session_id or "",
                "ai_response_text": "",
                "current_state": "unknown",
                "turn_count": 0,
                "is_complete": True,
                "evaluation_summary": None,
                "error": f"Session ID '{session_id}' not found."
            }
            
        dm = self.sessions[session_id]
        
        try:
            # Handle empty/whitespace transcript safely
            user_text = (text or "").strip()
            
            # Process the turn
            result = dm.handle_turn(user_text)
            
            status = dm.get_status()
            ai_response_text = result.get("question", "")
            current_state = status.get("state", "unknown")
            turn_count = status.get("turn_count", 0)
            
            # Extract latest turn evaluation summary
            last_eval = result.get("evaluation")
            evaluation_summary = None
            if last_eval:
                evaluation_summary = {
                    "overall_score": last_eval.get("overall_score", 0),
                    "weighted_score": last_eval.get("weighted_overall_score", 0),
                    "weakest_dimension": last_eval.get("weakest_dimension", "N/A"),
                    "hire_signal": last_eval.get("hire_signal", "N/A")
                }
                
            return {
                "session_id": session_id,
                "ai_response_text": ai_response_text,
                "current_state": current_state,
                "turn_count": turn_count,
                "is_complete": current_state == "wrapup",
                "evaluation_summary": evaluation_summary,
                "error": None
            }
        except Exception as e:
            logger.exception(f"Error processing text for session {session_id}")
            return {
                "session_id": session_id,
                "ai_response_text": "",
                "current_state": dm.context.state.value if hasattr(dm, "context") and hasattr(dm.context, "state") else "unknown",
                "turn_count": dm.context.turn_count if hasattr(dm, "context") else 0,
                "is_complete": False,
                "evaluation_summary": None,
                "error": str(e)
            }

    def get_report(self, session_id: str) -> dict:
        """
        Retrieve the final evaluation report for an interview session.
        
        Args:
            session_id (str): Session UUID identifier.
            
        Returns:
            dict: Full structured report or error dict.
        """
        if not session_id or session_id not in self.sessions:
            return {
                "error": f"Session ID '{session_id}' not found."
            }
            
        try:
            dm = self.sessions[session_id]
            return dm.get_final_report()
        except Exception as e:
            logger.exception(f"Failed to generate report for session {session_id}")
            return {
                "error": str(e)
            }

    def end_interview(self, session_id: str) -> dict:
        """
        Concludes the interview session, saving final scores to database and cleaning up.
        
        Args:
            session_id (str): Session UUID identifier.
            
        Returns:
            dict: Status summary.
        """
        if not session_id or session_id not in self.sessions:
            return {
                "session_id": session_id or "",
                "status": "not_found",
                "error": f"Session ID '{session_id}' not found."
            }
            
        try:
            dm = self.sessions[session_id]
            
            # This automatically computes finals, generates the report,
            # and persists scores (weighted score, consistency, trend) to database.
            final_report = dm.get_final_report()
            
            # Clean up session from active memory store to prevent leaks
            self.sessions.pop(session_id)
            
            return {
                "session_id": session_id,
                "status": "ended",
                "final_report": final_report,
                "error": None
            }
        except Exception as e:
            logger.exception(f"Error ending interview for session {session_id}")
            return {
                "session_id": session_id,
                "status": "error",
                "error": str(e)
            }
