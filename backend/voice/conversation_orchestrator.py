"""
Conversation Orchestrator — Bridges voice layer to the interview engine.

Takes a completed candidate transcript, processes it through DialogueManager,
and returns a structured response for the WebSocket layer.

Phase 3: Uses blueprint domain stage from InterviewContext (no InterviewFlowController).
"""


class ConversationOrchestrator:
    """
    Connects the voice conversation layer to the core interview engine.

    Handles the full turn cycle:
        candidate transcript → evaluation → next question → response
    """

    def get_intro(self, session) -> dict:
        """
        Generate the initial interview greeting.

        Args:
            session: VoiceSession instance

        Returns:
            Structured response dict with intro question.
        """
        dm = session.dialogue_manager

        # Generate intro through DialogueManager (empty transcript)
        result = dm.handle_turn("")
        session.turn_count = dm.context.turn_count
        session.current_stage = dm.context.get_domain_summary().get("current_domain", "intro")

        question = result.get("question", "")

        # Record in conversation history
        session.conversation_history.append({
            "turn": session.turn_count,
            "stage": session.current_stage,
            "speaker": "ai",
            "text": question,
        })

        return {
            "type": "ai_response",
            "text": question,
            "stage": session.current_stage,
            "turn": session.turn_count,
            "profile_source": session.profile_source,
            "target_role": session.target_role,
        }

    def process_turn(self, session, transcript: str) -> dict:
        """
        Process a completed candidate turn and generate the AI response.

        Args:
            session: VoiceSession instance
            transcript: the candidate's full answer text

        Returns:
            Structured response dict with next question + evaluation.
        """
        dm = session.dialogue_manager

        # Record candidate answer in history
        session.conversation_history.append({
            "turn": session.turn_count + 1,
            "stage": session.current_stage,
            "speaker": "candidate",
            "text": transcript,
        })

        # Process through DialogueManager (handles evaluation internally)
        result = dm.handle_turn(transcript)

        session.turn_count = dm.context.turn_count
        session.current_stage = dm.context.get_domain_summary().get("current_domain", session.current_stage)

        question = result.get("question", "")
        decision_type = result.get("decision_type")
        latency_ms = result.get("latency_ms", 0)
        is_complete = dm.context.state.value == "wrapup"

        if is_complete and not question:
            question = "Thank you for your time. This concludes the interview."

        # Record AI response in history
        session.conversation_history.append({
            "turn": session.turn_count,
            "stage": session.current_stage,
            "speaker": "ai",
            "text": question,
        })

        last_eval = result.get("evaluation")

        return {
            "type": "ai_response",
            "text": question,
            "stage": session.current_stage,
            "turn": session.turn_count,
            "decision_type": decision_type,
            "latency_ms": latency_ms,
            "evaluation_summary": _compact_eval(last_eval),
            "is_complete": is_complete,
            "domain_coverage": dm.context.get_domain_summary(),
        }

    def get_report(self, session) -> dict:
        """
        Generate the final interview report for a session.

        Args:
            session: VoiceSession instance

        Returns:
            Full report dict from the DialogueManager.
        """
        return session.dialogue_manager.get_final_report()


def _compact_eval(evaluation: dict | None) -> dict | None:
    """Extract compact evaluation summary for the voice response."""
    if not evaluation:
        return None
    return {
        "overall_score": evaluation.get("overall_score", 0),
        "weighted_score": evaluation.get("weighted_overall_score", 0),
        "weakest_dimension": evaluation.get("weakest_dimension", "N/A"),
        "hire_signal": evaluation.get("hire_signal", "N/A"),
    }
