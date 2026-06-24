"""
FastAPI Entry Point — AI Interviewer API with session management.
Persists sessions and responses to Postgres (graceful fallback to in-memory).
"""

import uuid
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

from dialogue.dialogue_manager import DialogueManager
from dialogue import database as db
from dialogue.recruiter_report import (
    generate_hr_report,
    generate_candidate_summary,
    derive_hire_recommendation,
    rank_candidates,
)
from voice.websocket_router import router as voice_router

app = FastAPI(
    title="AI Interviewer — Dialogue Manager",
    description="Conducts AI-powered interviews with technical and behavioral questions, with LLM-based answer evaluation.",
    version="4.0.0",
)

# ── Register Voice WebSocket Router ─────────────────────────────
app.include_router(voice_router)


# ── Session Storage ─────────────────────────────────────────────
# In-memory session store: session_id → DialogueManager instance
sessions: dict[str, DialogueManager] = {}


@app.on_event("startup")
def startup_event():
    """Create Postgres tables on startup (graceful if DB unavailable)."""
    db.create_tables()


# ── Request / Response Models ──────────────────────────────────
class StartRequest(BaseModel):
    resume_data: dict

    class Config:
        json_schema_extra = {
            "example": {
                "resume_data": {
                    "experience": "3 years",
                    "skills": ["Python", "Django", "REST APIs"],
                }
            }
        }


class StartResponse(BaseModel):
    session_id: str
    greeting: str


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
    Accepts resume data and returns a session ID + intro greeting.
    Persists session to Postgres (graceful fallback to in-memory).
    """
    session_id = str(uuid.uuid4())
    dm = DialogueManager(req.resume_data, session_id=session_id)
    sessions[session_id] = dm

    # Persist session to Postgres
    db.save_session(
        session_id=session_id,
        resume_data=req.resume_data,
        role_applied=req.resume_data.get("role", ""),
    )

    # Generate intro greeting (first turn with empty transcript)
    result = dm.handle_turn("")

    return StartResponse(session_id=session_id, greeting=result["question"])


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Send a candidate's answer and receive the next interview question
    along with evaluation of the previous answer.
    """
    dm = sessions.get(req.session_id)
    if dm is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Start a new interview with POST /start.",
        )

    result = dm.handle_turn(req.input_text)
    status = dm.get_status()

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
    dm = sessions.get(session_id)
    if dm is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return dm.get_status()


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "active_sessions": len(sessions)}


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
    dm = sessions.get(session_id)
    if dm is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return dm.get_final_report()


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
    dm = sessions.get(session_id)
    if dm is None:
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
    for sid, dm in sessions.items():
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
    for sid, dm in sessions.items():
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
    dm = sessions.get(session_id)
    if dm is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return generate_candidate_summary(dm)