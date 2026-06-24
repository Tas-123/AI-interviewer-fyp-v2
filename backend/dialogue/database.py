"""
Database Layer -- Postgres persistence for interview sessions and responses.

Provides graceful fallback to in-memory storage if Postgres is unavailable.
All functions are safe to call regardless of DB availability.
"""

import json
import os
import time
from datetime import datetime


# ====================================================================
#  Connection Management
# ====================================================================

_pg_available = None  # None = not checked yet, True/False after check


def _get_connection():
    """Get a Postgres connection. Returns None if unavailable."""
    try:
        import psycopg2
        url = os.getenv("DATABASE_URL")
        if not url:
            return None
        conn = psycopg2.connect(url)
        return conn
    except Exception as e:
        print(f"[Database] Connection failed: {e}")
        return None


def is_available() -> bool:
    """Check if Postgres is reachable."""
    global _pg_available
    if _pg_available is None:
        conn = _get_connection()
        if conn:
            conn.close()
            _pg_available = True
        else:
            _pg_available = False
    return _pg_available


# ====================================================================
#  Schema Creation
# ====================================================================

def create_tables():
    """Create sessions and responses tables if they don't exist."""
    conn = _get_connection()
    if not conn:
        print("[Database] Postgres unavailable. Using in-memory storage only.")
        return False

    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT NOW(),
                role_applied TEXT DEFAULT '',
                resume_data JSONB,
                final_weighted_score FLOAT,
                hire_signal TEXT,
                trend_label TEXT,
                consistency_rating TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id SERIAL PRIMARY KEY,
                session_id TEXT REFERENCES sessions(session_id),
                turn_number INTEGER,
                question_text TEXT,
                answer_text TEXT,
                weighted_score FLOAT,
                raw_score FLOAT,
                star_breakdown JSONB,
                stage TEXT,
                latency_ms FLOAT,
                decision_type TEXT,
                weakest_dimension TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("[Database] Tables created successfully.")
        return True
    except Exception as e:
        print(f"[Database] Table creation error: {e}")
        conn.close()
        return False


# ====================================================================
#  Session CRUD
# ====================================================================

def save_session(session_id: str, resume_data: dict, role_applied: str = ""):
    """Insert a new session record."""
    if not is_available():
        return False
    conn = _get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO sessions (session_id, resume_data, role_applied)
               VALUES (%s, %s, %s)
               ON CONFLICT (session_id) DO NOTHING""",
            (session_id, json.dumps(resume_data), role_applied)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[Database] save_session error: {e}")
        conn.close()
        return False


def update_session_finals(
    session_id: str,
    final_weighted_score: float,
    hire_signal: str,
    trend_label: str,
    consistency_rating: str,
):
    """Update a session with final analytics after interview ends."""
    if not is_available():
        return False
    conn = _get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE sessions
               SET final_weighted_score = %s,
                   hire_signal = %s,
                   trend_label = %s,
                   consistency_rating = %s
               WHERE session_id = %s""",
            (final_weighted_score, hire_signal, trend_label,
             consistency_rating, session_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[Database] update_session_finals error: {e}")
        conn.close()
        return False


# ====================================================================
#  Response Storage
# ====================================================================

def save_response(
    session_id: str,
    turn_number: int,
    question_text: str,
    answer_text: str,
    weighted_score: float,
    raw_score: float,
    star_breakdown: dict,
    stage: str,
    latency_ms: float,
    decision_type: str = "",
    weakest_dimension: str = "",
):
    """Insert a per-turn response record."""
    if not is_available():
        return False
    conn = _get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO responses
               (session_id, turn_number, question_text, answer_text,
                weighted_score, raw_score, star_breakdown, stage,
                latency_ms, decision_type, weakest_dimension)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (session_id, turn_number, question_text, answer_text,
             weighted_score, raw_score,
             json.dumps(star_breakdown) if star_breakdown else "{}",
             stage, latency_ms, decision_type, weakest_dimension)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[Database] save_response error: {e}")
        conn.close()
        return False


# ====================================================================
#  Latency Metrics
# ====================================================================

def get_latency_metrics(session_id: str) -> dict:
    """
    Compute avg, P95, and max latency from responses for a session.
    Returns computed metrics or defaults if DB unavailable.
    """
    if not is_available():
        return {"avg_ms": 0, "p95_ms": 0, "max_ms": 0, "source": "unavailable"}

    conn = _get_connection()
    if not conn:
        return {"avg_ms": 0, "p95_ms": 0, "max_ms": 0, "source": "unavailable"}

    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT latency_ms FROM responses
               WHERE session_id = %s AND latency_ms > 0
               ORDER BY latency_ms""",
            (session_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return {"avg_ms": 0, "p95_ms": 0, "max_ms": 0, "source": "no_data"}

        latencies = [r[0] for r in rows]
        n = len(latencies)
        avg = round(sum(latencies) / n, 2)
        p95_idx = min(int(n * 0.95), n - 1)
        p95 = round(latencies[p95_idx], 2)
        max_l = round(max(latencies), 2)

        return {"avg_ms": avg, "p95_ms": p95, "max_ms": max_l, "source": "postgres"}

    except Exception as e:
        print(f"[Database] get_latency_metrics error: {e}")
        conn.close()
        return {"avg_ms": 0, "p95_ms": 0, "max_ms": 0, "source": "error"}


def get_session_responses(session_id: str) -> list:
    """Load all responses for a session from DB."""
    if not is_available():
        return []
    conn = _get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT turn_number, question_text, answer_text,
                      weighted_score, raw_score, star_breakdown,
                      stage, latency_ms, decision_type, weakest_dimension
               FROM responses WHERE session_id = %s
               ORDER BY turn_number""",
            (session_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        results = []
        for r in rows:
            results.append({
                "turn_number": r[0], "question_text": r[1],
                "answer_text": r[2], "weighted_score": r[3],
                "raw_score": r[4],
                "star_breakdown": json.loads(r[5]) if r[5] else {},
                "stage": r[6], "latency_ms": r[7],
                "decision_type": r[8], "weakest_dimension": r[9],
            })
        return results
    except Exception as e:
        print(f"[Database] get_session_responses error: {e}")
        conn.close()
        return []


# ====================================================================
#  Session Queries (read-only)
# ====================================================================

def list_sessions() -> list:
    """Return all sessions with their final metrics."""
    if not is_available():
        return []
    conn = _get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT session_id, created_at, final_weighted_score,
                      hire_signal, trend_label, consistency_rating,
                      role_applied
               FROM sessions ORDER BY created_at DESC"""
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        results = []
        for r in rows:
            results.append({
                "session_id": r[0],
                "created_at": r[1].isoformat() if r[1] else None,
                "final_weighted_score": r[2],
                "hire_signal": r[3],
                "trend_label": r[4],
                "consistency_rating": r[5],
                "role_applied": r[6],
            })
        return results
    except Exception as e:
        print(f"[Database] list_sessions error: {e}")
        conn.close()
        return []


def get_session(session_id: str) -> dict | None:
    """Retrieve a single session record by ID."""
    if not is_available():
        return None
    conn = _get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT session_id, created_at, final_weighted_score,
                      hire_signal, trend_label, consistency_rating,
                      role_applied, resume_data
               FROM sessions WHERE session_id = %s""",
            (session_id,)
        )
        r = cur.fetchone()
        cur.close()
        conn.close()
        if not r:
            return None
        return {
            "session_id": r[0],
            "created_at": r[1].isoformat() if r[1] else None,
            "final_weighted_score": r[2],
            "hire_signal": r[3],
            "trend_label": r[4],
            "consistency_rating": r[5],
            "role_applied": r[6],
            "resume_data": json.loads(r[7]) if r[7] else {},
        }
    except Exception as e:
        print(f"[Database] get_session error: {e}")
        conn.close()
        return None
