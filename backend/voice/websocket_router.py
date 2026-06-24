"""
WebSocket Router — Real-time interview conversation endpoint.

Provides a WebSocket endpoint at /ws/interview/{session_id} for streaming
candidate speech, processing turns, and delivering AI responses.

Integrates with VoiceSessionManager, VADSimulator, ConversationOrchestrator,
InterruptionManager, and StreamingResponseHandler.
"""

import json
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from voice.voice_session_manager import VoiceSessionManager
from voice.vad_simulator import VADSimulator
from voice.conversation_orchestrator import ConversationOrchestrator
from voice.interruption_manager import InterruptionManager
from voice.streaming_response_handler import stream_response


# ── Shared instances ─────────────────────────────────────────────
voice_manager = VoiceSessionManager()
vad = VADSimulator()
orchestrator = ConversationOrchestrator()

router = APIRouter(tags=["Voice Interview"])


# ── Background cleanup task ──────────────────────────────────────
_cleanup_task = None


async def _session_cleanup_loop():
    """Periodically clean expired voice sessions."""
    while True:
        await asyncio.sleep(60)
        removed = voice_manager.cleanup_expired()
        if removed > 0:
            print(f"[Voice] Cleaned up {removed} expired session(s)")


# ── WebSocket Endpoint ───────────────────────────────────────────

@router.websocket("/ws/interview/{session_id}")
async def voice_interview(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time voice interview sessions.

    Message types from client:
        - start_interview: {type, resume_data}
        - speech_chunk: {type, text}
        - speech_end: {type}
        - get_report: {type}
        - close: {type}

    Response types to client:
        - ai_response: {type, text, stage, turn}
        - ai_response_chunk: {type, text, is_final}
        - interruption: {type, reason, message}
        - error: {type, message}
        - session_closed: {type, message}
    """
    await websocket.accept()

    # Start cleanup background task if not running
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_session_cleanup_loop())

    interruption_mgr = InterruptionManager()
    last_question = ""

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, "Invalid JSON message")
                continue

            msg_type = message.get("type", "")

            # ── START INTERVIEW ──────────────────────────────────
            if msg_type == "start_interview":
                resume_data = message.get("resume_data", {})
                session = voice_manager.create_session(
                    resume_data=resume_data,
                    session_id=session_id,
                )

                # Generate intro greeting
                intro = orchestrator.get_intro(session)
                last_question = intro.get("text", "")

                # Stream the intro response
                async for chunk in stream_response(last_question):
                    await websocket.send_json(chunk)

                # Also send the full response
                await websocket.send_json(intro)
                continue

            # ── Get session (all other messages require it) ──────
            session = voice_manager.get_session(session_id)
            if not session:
                await _send_error(
                    websocket,
                    "Session not found. Send start_interview first."
                )
                continue

            voice_manager.touch_session(session_id)

            # ── SPEECH CHUNK ─────────────────────────────────────
            if msg_type == "speech_chunk":
                vad_result = vad.process_message(message)

                if vad_result["is_speech"]:
                    voice_manager.append_transcript_chunk(
                        session_id, vad_result["text"]
                    )

                    # Check barge-in on accumulated buffer
                    barge_in = interruption_mgr.check_barge_in(
                        session.transcript_buffer
                    )
                    if barge_in:
                        await websocket.send_json(barge_in)
                        # Force end of turn on barge-in
                        transcript = voice_manager.flush_transcript(session_id)
                        if transcript:
                            response = orchestrator.process_turn(
                                session, transcript
                            )
                            last_question = response.get("text", "")
                            async for chunk in stream_response(last_question):
                                await websocket.send_json(chunk)
                            await websocket.send_json(response)
                continue

            # ── SPEECH END ───────────────────────────────────────
            if msg_type == "speech_end":
                transcript = voice_manager.flush_transcript(session_id)

                if not transcript:
                    await _send_error(websocket, "No speech received")
                    continue

                # Check context guard
                if last_question:
                    guard = interruption_mgr.check_context_guard(
                        last_question, transcript
                    )
                    if guard:
                        await websocket.send_json(guard)
                        # Still process the turn but flag it

                # Process the turn through the interview engine
                response = orchestrator.process_turn(session, transcript)
                last_question = response.get("text", "")

                # Stream the response
                async for chunk in stream_response(last_question):
                    await websocket.send_json(chunk)

                # Send full response
                await websocket.send_json(response)

                # Check if interview is complete
                if response.get("is_complete"):
                    report = orchestrator.get_report(session)
                    await websocket.send_json({
                        "type": "report",
                        "data": report,
                    })
                continue

            # ── GET REPORT ───────────────────────────────────────
            if msg_type == "get_report":
                report = orchestrator.get_report(session)
                await websocket.send_json({
                    "type": "report",
                    "data": report,
                })
                continue

            # ── CLOSE ────────────────────────────────────────────
            if msg_type == "close":
                voice_manager.close_session(session_id)
                await websocket.send_json({
                    "type": "session_closed",
                    "message": "Interview session closed.",
                })
                break

            # ── UNKNOWN MESSAGE ──────────────────────────────────
            await _send_error(
                websocket,
                f"Unknown message type: {msg_type}"
            )

    except WebSocketDisconnect:
        print(f"[Voice] Client disconnected: {session_id}")
        voice_manager.close_session(session_id)
    except Exception as e:
        print(f"[Voice] WebSocket error for {session_id}: {e}")
        try:
            await _send_error(websocket, f"Internal error: {str(e)}")
        except Exception:
            pass
        voice_manager.close_session(session_id)


# ── Voice session info endpoint (REST) ───────────────────────────

@router.get("/voice/sessions")
async def get_voice_sessions():
    """Return list of active voice sessions."""
    return {
        "active_sessions": voice_manager.get_active_count(),
        "sessions": voice_manager.list_sessions(),
    }


# ── Helper ───────────────────────────────────────────────────────

async def _send_error(websocket: WebSocket, message: str):
    """Send an error message over WebSocket."""
    await websocket.send_json({
        "type": "error",
        "message": message,
    })
