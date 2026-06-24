"""
simulate_interview.py — Mini End-to-End Adaptive Interview Simulation (STEP 9)

Runs a 3-turn automated interview with:
  - Postgres persistence (graceful fallback to in-memory)
  - Latency tracking per turn
  - STAR evaluation & weighted scoring
  - Adaptive follow-up logic (PROBE/ADVANCE)
  - Final report generation with trend, consistency, behavioral profile

Usage:
    python simulate_interview.py

Requires GEMINI_API_KEY in environment. DATABASE_URL optional.
Output: strict JSON to stdout.
"""

import json
import os
import sys
import time
import uuid

# Setup path and env
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from dialogue.dialogue_manager import DialogueManager
from dialogue import database as db
from dialogue.analytics import (
    detect_performance_trend,
    compute_consistency_rating,
)


# ====================================================================
#  Simulated Candidate Answers (progressively improving for trend test)
# ====================================================================

SIMULATED_ANSWERS = [
    # Turn 1 (EARLY) — Weak answer, missing result
    (
        "In my last role, there was a disagreement between two team members "
        "about the database design. I noticed it was affecting our sprint velocity. "
        "I talked to both of them separately to understand their perspectives."
    ),
    # Turn 2 (EARLY) — Better answer with more STAR components
    (
        "When I joined the startup, our deployment process was entirely manual "
        "and took 4 hours each time. I was tasked with automating this pipeline. "
        "I researched CI/CD tools, chose GitHub Actions, wrote the pipeline configs, "
        "and trained the team. We reduced deployment time from 4 hours to 15 minutes "
        "and went from bi-weekly releases to daily deployments."
    ),
    # Turn 3 (EARLY/MID) — Strong answer with full STAR
    (
        "As tech lead of a 6-person team at Acme Corp, our flagship product had "
        "a critical performance bottleneck — API response times exceeded 5 seconds "
        "for 30% of requests. I was responsible for diagnosing and resolving it. "
        "I profiled the application, identified N+1 query patterns, restructured the "
        "ORM layer with eager loading, added Redis caching for hot paths, and implemented "
        "connection pooling. The result was a 92% reduction in P95 latency (from 5.2s to "
        "0.4s), which directly recovered 15% of churning enterprise customers worth "
        "$280K ARR."
    ),
]

RESUME_DATA = {
    "skills": ["Python", "Django", "REST APIs"],
    "experience": "3 years",
    "role": "Backend Engineer",
}


# ====================================================================
#  Simulation Runner
# ====================================================================

def run_simulation() -> dict:
    """Execute a 3-turn automated interview end-to-end."""

    session_id = str(uuid.uuid4())
    simulation_log = {
        "session_id": session_id,
        "turns": [],
        "latencies_ms": [],
        "db_status": "unknown",
        "final_report": None,
    }

    # -- Step 1: Create session in Postgres --
    db_ok = db.create_tables()
    db.save_session(session_id, RESUME_DATA, role_applied="Backend Engineer")
    simulation_log["db_status"] = "postgres" if db.is_available() else "in_memory_fallback"

    # -- Initialize DialogueManager --
    dm = DialogueManager(RESUME_DATA, session_id=session_id)

    # -- Intro turn (no evaluation) --
    intro_result = dm.handle_turn("")
    simulation_log["intro_question"] = intro_result["question"]

    # -- Turns 1-3: Simulate candidate answers --
    for turn_idx, answer in enumerate(SIMULATED_ANSWERS, start=1):
        t_start = time.perf_counter()
        result = dm.handle_turn(answer)
        turn_latency = round((time.perf_counter() - t_start) * 1000, 2)

        evaluation = result.get("evaluation", {})
        llm_latency = result.get("latency_ms", 0)

        turn_record = {
            "turn": turn_idx,
            "stage": dm.context.interview_stage,
            "question": result.get("question", ""),
            "answer_snippet": answer[:80] + "..." if len(answer) > 80 else answer,
            "decision_type": result.get("decision_type", "N/A"),
            "weighted_score": evaluation.get("weighted_overall_score", 0),
            "raw_score": evaluation.get("overall_score", 0),
            "weakest_dimension": evaluation.get("weakest_dimension", "N/A"),
            "hire_signal": evaluation.get("hire_signal", "N/A"),
            "star_breakdown": evaluation.get("star_breakdown", {
                "situation_present": False, "task_present": False,
                "action_present": False, "result_present": False,
            }),
            "llm_latency_ms": llm_latency,
            "total_turn_latency_ms": turn_latency,
        }

        simulation_log["turns"].append(turn_record)
        simulation_log["latencies_ms"].append(llm_latency)

        # Persist response to DB
        db.save_response(
            session_id=session_id,
            turn_number=turn_idx,
            question_text=result.get("question", ""),
            answer_text=answer,
            weighted_score=evaluation.get("weighted_overall_score", 0),
            raw_score=evaluation.get("overall_score", 0),
            star_breakdown=evaluation.get("star_breakdown", {}),
            stage=dm.context.interview_stage,
            latency_ms=llm_latency,
            decision_type=result.get("decision_type", ""),
            weakest_dimension=evaluation.get("weakest_dimension", ""),
        )

    # -- Step 5: Generate final report --
    report = dm.get_final_report()
    simulation_log["final_report"] = report

    # -- Step 6: Update session finals in DB --
    weighted_summary = report.get("weighted_score_summary", {})
    trend_analysis = report.get("performance_trend_analysis", {})
    consistency = report.get("consistency_rating", {})

    db.update_session_finals(
        session_id=session_id,
        final_weighted_score=weighted_summary.get("avg_weighted_overall", 0),
        hire_signal=weighted_summary.get("final_hire_signal", "N/A"),
        trend_label=trend_analysis.get("performance_trend_label", "stable"),
        consistency_rating=consistency.get("consistency_rating", "N/A"),
    )

    # -- Step 7: Compute latency summary --
    latencies = [l for l in simulation_log["latencies_ms"] if l > 0]
    if latencies:
        sorted_l = sorted(latencies)
        n = len(sorted_l)
        simulation_log["latency_summary"] = {
            "avg_ms": round(sum(sorted_l) / n, 2),
            "p95_ms": round(sorted_l[min(int(n * 0.95), n - 1)], 2),
            "max_ms": round(max(sorted_l), 2),
            "total_llm_calls": n,
        }
    else:
        simulation_log["latency_summary"] = {
            "avg_ms": 0, "p95_ms": 0, "max_ms": 0, "total_llm_calls": 0,
        }

    # -- Step 8: Verification checks --
    verification = _verify_simulation(simulation_log)
    simulation_log["verification"] = verification

    return simulation_log


# ====================================================================
#  Verification
# ====================================================================

def _verify_simulation(log: dict) -> dict:
    """Verify simulation results for consistency and correctness."""
    checks = {}

    turns = log.get("turns", [])

    # Check 1: All turns have valid evaluations
    checks["all_turns_evaluated"] = all(
        t.get("raw_score", 0) > 0 for t in turns
    )

    # Check 2: Weighted scores are in valid range [0, 5]
    weighted = [t.get("weighted_score", 0) for t in turns]
    checks["weighted_scores_valid"] = all(0 <= w <= 5 for w in weighted)

    # Check 3: STAR breakdowns are valid JSON booleans
    checks["star_breakdowns_valid"] = all(
        isinstance(t.get("star_breakdown", {}), dict)
        and all(isinstance(v, bool) for v in t.get("star_breakdown", {}).values())
        for t in turns
    )

    # Check 4: Decision types are valid
    checks["decision_types_valid"] = all(
        t.get("decision_type") in ("PROBE", "ADVANCE", "LEGACY", None, "N/A")
        for t in turns
    )

    # Check 5: Latencies are non-negative
    checks["latencies_valid"] = all(
        t.get("llm_latency_ms", 0) >= 0 for t in turns
    )

    # Check 6: Trend detection present in report
    report = log.get("final_report", {})
    checks["trend_detected"] = (
        report.get("performance_trend_analysis", {})
        .get("performance_trend_label") in ("improving", "declining", "stable")
    )

    # Check 7: Consistency rating present
    checks["consistency_rated"] = (
        report.get("consistency_rating", {})
        .get("consistency_rating") in ("High", "Moderate", "Low")
    )

    # Check 8: Behavioral profile present
    profile = report.get("behavioral_profile", {})
    checks["behavioral_profile_present"] = (
        profile.get("ownership_pattern") != "N/A"
    )

    # Overall
    checks["all_passed"] = all(checks.values())

    return checks


# ====================================================================
#  Main
# ====================================================================

if __name__ == "__main__":
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        print(json.dumps({
            "error": "GEMINI_API_KEY not set. Please set it in .env file.",
            "hint": "Copy .env.example to .env and add your Gemini API key.",
        }, indent=2))
        sys.exit(1)

    print("=" * 60)
    print("AI INTERVIEWER — Mini E2E Simulation (v4.0)")
    print("=" * 60)
    print()

    result = run_simulation()

    # Output strict JSON
    print(json.dumps(result, indent=2, default=str))

    # Summary
    v = result.get("verification", {})
    print()
    print("=" * 60)
    if v.get("all_passed"):
        print("✓ ALL VERIFICATION CHECKS PASSED")
    else:
        failed = [k for k, v_val in v.items() if not v_val and k != "all_passed"]
        print(f"✗ VERIFICATION FAILED: {', '.join(failed)}")
    print("=" * 60)
