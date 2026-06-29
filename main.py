"""
FastAPI Entry Point — AI Interviewer API with session management.
Persists sessions and responses to Postgres (graceful fallback to in-memory).
"""

import sys
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add backend to path so dialogue package can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from core.config import settings
from core.role_registry import DEFAULT_TARGET_ROLE, list_target_roles
from core.session_service import SessionNotFoundError, get_session_service
from dialogue import database as db
from dialogue.recruiter_report import (
    generate_hr_report,
    generate_candidate_summary,
    derive_hire_recommendation,
    rank_candidates,
)

app = FastAPI(
    title="AI Interviewer — API Layer",
    description=(
        "REST API for interview sessions and reports. "
        "Primary voice runtime: python backend/pipecat_integration/interview_bot.py"
    ),
    version="5.0.0",
)

# Dev-only text WebSocket simulation (not the product voice path)
if settings.enable_dev_text_voice_ws:
    from voice.websocket_router import router as voice_router

    app.include_router(voice_router)

# ── Unified Session Service ─────────────────────────────────────
sessions = get_session_service()


@app.on_event("startup")
def startup_event():
    """Create Postgres tables on startup (graceful if DB unavailable)."""
    db.create_tables()


# ── Request / Response Models ──────────────────────────────────
class StartRequest(BaseModel):
    """Session start — resume is optional; target_role defaults to Junior AI Engineer."""

    target_role: str = DEFAULT_TARGET_ROLE
    display_name: Optional[str] = None
    resume_text: Optional[str] = None
    resume_data: Optional[dict] = None

    class Config:
        json_schema_extra = {
            "example": {
                "target_role": "junior_ai_engineer",
                "display_name": "Alex",
                "resume_text": "3 years Python, TensorFlow, NLP projects...",
                "resume_data": {
                    "skills": ["Python", "TensorFlow", "NLP"],
                    "experience": "3 years",
                },
            }
        }


class StartResponse(BaseModel):
    session_id: str
    greeting: str
    profile_source: str
    target_role: str


class ChatRequest(BaseModel):
    session_id: str
    input_text: str


class StarBreakdown(BaseModel):
    situation_present: bool = False
    task_present: bool = False
    action_present: bool = False
    result_present: bool = False


class EvaluationResponse(BaseModel):
    clarity_score: int = 0
    clarity: int = 0
    structure_score: int = 0
    structure: int = 0
    confidence_score: int = 0
    confidence: int = 0
    ownership_score: int = 0
    ownership: int = 0
    leadership_score: int = 0
    leadership: int = 0
    result_score: int = 0
    result_orientation: int = 0
    strengths: list = []
    weaknesses: list = []
    overall_score: float = 0.0
    weighted_overall_score: float = 0.0
    weakest_dimension: str = "N/A"
    hire_signal: str = "N/A"
    star_breakdown: Optional[StarBreakdown] = None


class ChatResponse(BaseModel):
    question: str
    evaluation: Optional[EvaluationResponse] = None
    decision_type: Optional[str] = None
    status: dict


# ── Endpoints ──────────────────────────────────────────────────
@app.post("/start", response_model=StartResponse)
def start_interview(req: StartRequest):
    """
    Start a new interview session.

    Resume is optional. When omitted, the system uses the default profile for
    target_role (default: junior_ai_engineer).
    """
    session_start = req.model_dump(exclude_none=True)
    session_id, result = sessions.start_interview(session_start=session_start)
    stored = sessions.get(session_id)
    resume_data = stored.resume_data if stored else {}

    return StartResponse(
        session_id=session_id,
        greeting=result["question"],
        profile_source=resume_data.get("profile_source", "default"),
        target_role=resume_data.get("target_role", DEFAULT_TARGET_ROLE),
    )


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Send a candidate's answer and receive the next interview question
    along with evaluation of the previous answer.
    """
    try:
        result = sessions.process_turn(req.session_id, req.input_text)
        status = sessions.get_status(req.session_id)
    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Start a new interview with POST /start.",
        )

    # Build evaluation response if one was generated
    eval_data = None
    if result.get("evaluation"):
        eval_data = EvaluationResponse(**result["evaluation"])

    return ChatResponse(
        question=result["question"],
        evaluation=eval_data,
        decision_type=result.get("decision_type"),
        status=status,
    )


@app.get("/session/{session_id}")
def get_session_status(session_id: str):
    """
    Get the current status of an interview session, including
    aggregate evaluation scores.
    """
    try:
        return sessions.get_status(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")


@app.get("/roles")
def list_roles():
    """List available target interview roles."""
    return {"roles": list_target_roles(), "default": DEFAULT_TARGET_ROLE}


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "active_sessions": sessions.active_count(),
        "primary_runtime": "pipecat",
        "dev_text_voice_ws": settings.enable_dev_text_voice_ws,
    }


@app.get("/report/{session_id}")
def get_final_report(session_id: str):
    """
    Generate a full final interview report with:
    - Weighted score summary
    - STAR effectiveness analysis
    - Performance trend analysis
    - Consistency rating
    - Behavioral profile (5-axis)
    - Bias awareness section
    """
    try:
        return sessions.get_report(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")


# ── Recruiter Report Endpoints ─────────────────────────────────

@app.get("/report/hr/{session_id}")
def get_hr_report(session_id: str):
    """
    Generate a structured recruiter-facing report including:
    - Candidate summary
    - Per-dimension scores
    - Hire recommendation (STRONG_HIRE / HIRE / LEAN_HIRE / NO_HIRE)
    - Risk flags
    """
    try:
        dm = sessions.get_dialogue_manager(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")
    return generate_hr_report(dm)


@app.get("/sessions")
def get_all_sessions():
    """
    List all interview sessions with final metrics.
    Returns data from Postgres if available, otherwise from in-memory store.
    """
    # Try Postgres first
    db_sessions = db.list_sessions()
    if db_sessions:
        # Enrich with hire_recommendation if not already present
        for s in db_sessions:
            if not s.get("hire_recommendation"):
                s["hire_recommendation"] = derive_hire_recommendation(
                    s.get("final_weighted_score", 0) or 0,
                    s.get("consistency_rating", "N/A") or "N/A",
                    s.get("trend_label", "stable") or "stable",
                )
        return db_sessions

    # Fallback: build from in-memory sessions
    results = []
    for sid, dm in sessions.iter_active():
        summary = generate_candidate_summary(dm)
        results.append({
            "session_id": sid,
            "created_at": None,
            "final_weighted_score": summary.get("avg_weighted_score", 0),
            "hire_signal": summary.get("final_hire_signal", "N/A"),
            "trend_label": None,
            "consistency_rating": None,
            "hire_recommendation": None,
        })
    return results


@app.get("/sessions/rank")
def get_ranked_candidates():
    """
    Rank all candidates by composite score.
    Priority: weighted_score (desc) → consistency (High > Moderate > Low)
    → improving trend preferred.
    """
    # Try DB first
    db_sessions = db.list_sessions()
    if db_sessions:
        for s in db_sessions:
            s["hire_recommendation"] = derive_hire_recommendation(
                s.get("final_weighted_score", 0) or 0,
                s.get("consistency_rating", "N/A") or "N/A",
                s.get("trend_label", "stable") or "stable",
            )
        return rank_candidates(db_sessions)

    # Fallback: rank in-memory sessions
    data = []
    for sid, dm in sessions.iter_active():
        summary = generate_candidate_summary(dm)
        data.append({
            "session_id": sid,
            "final_weighted_score": summary.get("avg_weighted_score", 0),
            "consistency_rating": None,
            "trend_label": None,
            "hire_recommendation": None,
        })
    return rank_candidates(data)


@app.get("/sessions/{session_id}/summary")
def get_session_summary(session_id: str):
    """Return a compact candidate summary for a session."""
    try:
        dm = sessions.get_dialogue_manager(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")
    return generate_candidate_summary(dm)