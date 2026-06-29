"""
Analytics Module -- Advanced intelligence layer for the AI Interviewer.

All pure-function helpers for:
  1. Weighted scoring
  2. Performance trend detection
  3. Consistency rating (stdev-based)
  4. Behavioral profile generation (5-axis)
  5. Final interview report generation

No external dependencies. No LLM calls. Fully testable.
"""

import math


# ====================================================================
#  Scoring Weights (sum = 1.0)
# ====================================================================

DIMENSION_WEIGHTS = {
    "structure": 0.25,
    "result_orientation": 0.20,
    "ownership": 0.20,
    "leadership": 0.15,
    "clarity": 0.10,
    "confidence": 0.10,
}


# ====================================================================
#  1. Weighted Scoring
# ====================================================================


def _is_star_relevant_domain(domain: str) -> bool:
    """
    STAR analysis is mainly meaningful for project overview and behavioral/ownership answers.
    Technical skill questions should be judged on technical correctness, structure, and specificity,
    not forced STAR storytelling.
    """
    d = (domain or "").strip().lower()
    return d in {
        "project_overview",
        "behavioral_ownership",
        "behavioral/ownership",
        "ownership",
        "behavioral",
    }


def _technical_report_concern_filter(concerns, trace_items=None):
    """
    Remove STAR-heavy concerns when the interview mostly contains technical domains.
    Keep them only when project/behavioral answers are actually present.
    """
    trace_items = trace_items or []
    star_relevant_count = 0
    technical_count = 0

    for item in trace_items:
        domain = (item.get("domain") or "").strip().lower()
        if _is_star_relevant_domain(domain):
            star_relevant_count += 1
        else:
            technical_count += 1

    filtered = []
    for c in concerns or []:
        lc = str(c).lower()

        star_heavy = (
            "star" in lc
            or "result/impact" in lc
            or "measurable results" in lc
            or "measurable project impact" in lc
        )

        # If interview is mostly technical, do not over-emphasize STAR/result-impact.
        if star_heavy and technical_count > star_relevant_count:
            continue

        filtered.append(c)

    return filtered


def _technical_report_followup_filter(items, trace_items=None):
    """
    Remove generic STAR/result-impact follow-ups when technical validation is more appropriate.
    """
    trace_items = trace_items or []
    star_relevant_count = 0
    technical_count = 0

    for item in trace_items:
        domain = (item.get("domain") or "").strip().lower()
        if _is_star_relevant_domain(domain):
            star_relevant_count += 1
        else:
            technical_count += 1

    filtered = []
    for item in items or []:
        li = str(item).lower()
        star_heavy = (
            "measurable project impact" in li
            or "outcomes" in li
            or "success metrics" in li
            or "result/impact" in li
        )

        if star_heavy and technical_count > star_relevant_count:
            continue

        filtered.append(item)

    return filtered


def compute_weighted_score(scores: dict) -> float:
    """
    Compute weighted overall score from 6-dimension scores.

    Args:
        scores: dict with keys matching DIMENSION_WEIGHTS
                (clarity, structure, confidence, ownership,
                 leadership, result_orientation)

    Returns:
        Weighted score rounded to 2 decimals.
    """
    total = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        total += scores.get(dim, 0) * weight
    return round(total, 2)


# ====================================================================
#  2. Performance Trend Detection
# ====================================================================

def detect_performance_trend(weighted_history: list) -> dict:
    """
    Analyze score trajectory across interview stages.

    Args:
        weighted_history: list of (turn_number, weighted_score) tuples

    Returns:
        {
            "early_avg": float | None,
            "mid_avg": float | None,
            "late_avg": float | None,
            "performance_trend_label": "improving" | "declining" | "stable",
            "score_history": [float, ...]
        }
    """
    early = [s for turn, s in weighted_history if turn <= 3]
    mid = [s for turn, s in weighted_history if 4 <= turn <= 7]
    late = [s for turn, s in weighted_history if turn >= 8]

    early_avg = round(sum(early) / len(early), 2) if early else None
    mid_avg = round(sum(mid) / len(mid), 2) if mid else None
    late_avg = round(sum(late) / len(late), 2) if late else None

    # Determine trend from available stage averages
    available = [v for v in [early_avg, mid_avg, late_avg] if v is not None]

    if len(available) < 2:
        label = "stable"
    else:
        # Compare first and last available averages
        first = available[0]
        last = available[-1]
        diff = last - first

        if diff > 0.3:
            label = "improving"
        elif diff < -0.3:
            label = "declining"
        else:
            label = "stable"

    return {
        "early_avg": early_avg,
        "mid_avg": mid_avg,
        "late_avg": late_avg,
        "performance_trend_label": label,
        "score_history": [s for _, s in weighted_history],
    }


# ====================================================================
#  3. Consistency Rating
# ====================================================================

def compute_consistency_rating(weighted_history: list) -> dict:
    """
    Calculate standard deviation of weighted scores and classify.

    Args:
        weighted_history: list of (turn_number, weighted_score) tuples

    Returns:
        {
            "stdev": float,
            "consistency_rating": "High" | "Moderate" | "Low"
        }
    """
    scores = [s for _, s in weighted_history]

    if len(scores) < 2:
        return {"stdev": 0.0, "consistency_rating": "High"}

    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    stdev = round(math.sqrt(variance), 2)

    if stdev < 0.5:
        rating = "High"
    elif stdev <= 1.0:
        rating = "Moderate"
    else:
        rating = "Low"

    return {"stdev": stdev, "consistency_rating": rating}


# ====================================================================
#  4. Behavioral Profile Generator (5-Axis)
# ====================================================================

def generate_behavioral_profile(evaluations: list) -> dict:
    """
    Derive a 5-axis behavioral profile from aggregated evaluation metrics.

    Args:
        evaluations: list of evaluation dicts (filtered, no errors)

    Returns:
        {
            "risk_orientation": "Risk-Taker" | "Balanced" | "Risk-Averse",
            "thinking_style": "Structured" | "Semi-Structured" | "Unstructured",
            "data_orientation": "Data-Driven" | "Example-Based" | "Vague",
            "ownership_pattern": "Strong" | "Moderate" | "Weak",
            "leadership_presence": "Strong" | "Situational" | "Minimal"
        }
    """
    if not evaluations:
        return {
            "risk_orientation": "N/A",
            "thinking_style": "N/A",
            "data_orientation": "N/A",
            "ownership_pattern": "N/A",
            "leadership_presence": "N/A",
        }

    def avg_field(field):
        vals = [e.get(field, 0) for e in evaluations]
        return sum(vals) / len(vals) if vals else 0

    def avg_with_fallback(primary, fallback):
        """Use primary field if any evaluation has it, else fallback."""
        has_primary = any(primary in e for e in evaluations)
        if has_primary:
            return avg_field(primary)
        return avg_field(fallback)

    # Adaptive field resolution: check field existence, not truthiness
    ownership_avg = avg_with_fallback("ownership", "ownership_score")
    leadership_avg = avg_with_fallback("leadership", "leadership_score")
    structure_avg = avg_with_fallback("structure", "structure_score")
    result_avg = avg_with_fallback("result_orientation", "result_score")

    # Count STAR completeness
    star_evals = [e for e in evaluations if "star_breakdown" in e]
    star_complete_ratio = 0.0
    if star_evals:
        complete = sum(
            1 for e in star_evals
            if all(e["star_breakdown"].get(k, False)
                   for k in ["situation_present", "task_present",
                              "action_present", "result_present"])
        )
        star_complete_ratio = complete / len(star_evals)

    # --- Axis 1: Risk Orientation (ownership + leadership) ---
    risk_score = (ownership_avg + leadership_avg) / 2
    if risk_score >= 4.0:
        risk_orientation = "Risk-Taker"
    elif risk_score >= 2.5:
        risk_orientation = "Balanced"
    else:
        risk_orientation = "Risk-Averse"

    # --- Axis 2: Thinking Style (structure + STAR completeness) ---
    thinking_score = structure_avg * 0.6 + star_complete_ratio * 5 * 0.4
    if thinking_score >= 3.5:
        thinking_style = "Structured"
    elif thinking_score >= 2.0:
        thinking_style = "Semi-Structured"
    else:
        thinking_style = "Unstructured"

    # --- Axis 3: Data Orientation (result_orientation scores) ---
    if result_avg >= 4.0:
        data_orientation = "Data-Driven"
    elif result_avg >= 2.5:
        data_orientation = "Example-Based"
    else:
        data_orientation = "Vague"

    # --- Axis 4: Ownership Pattern ---
    if ownership_avg >= 4.0:
        ownership_pattern = "Strong"
    elif ownership_avg >= 2.5:
        ownership_pattern = "Moderate"
    else:
        ownership_pattern = "Weak"

    # --- Axis 5: Leadership Presence ---
    if leadership_avg >= 4.0:
        leadership_presence = "Strong"
    elif leadership_avg >= 2.5:
        leadership_presence = "Situational"
    else:
        leadership_presence = "Minimal"

    return {
        "risk_orientation": risk_orientation,
        "thinking_style": thinking_style,
        "data_orientation": data_orientation,
        "ownership_pattern": ownership_pattern,
        "leadership_presence": leadership_presence,
    }





def _canonical_skill_name(skill: str) -> str:
    """Normalize aliases/domains into one stable skill key."""
    skill = (skill or "").lower().strip()

    aliases = {
        "machine_learning": "machine learning",
        "data_preprocessing": "data preprocessing",
        "model_evaluation": "model evaluation",
        "nlp_speech_ai": "nlp",
        "apis_backend": "apis",
        "debugging_problem_solving": "debugging/problem solving",
        "behavioral_ownership": "behavioral/ownership",
        "project_overview": "project overview",
    }

    return aliases.get(skill, skill.replace("_", " "))


def _skill_evidence_keywords(skill: str) -> list:
    """
    Return evidence keywords for skill/domain coverage validation.
    Coverage should be based on actual answer/question evidence, not only guessed skill_focus.
    """
    skill = (skill or "").lower().strip()

    keyword_map = {
        "python": [
            "python", "pandas", "numpy", "sklearn", "scikit", "function", "class",
            "module", "decorator", "context manager", "exception", "debug", "script"
        ],
        "machine learning": [
            "machine learning", "ml", "model", "training", "train", "validation",
            "overfitting", "underfitting", "regularization", "cross validation",
            "classification", "regression", "random forest", "logistic regression",
            "feature", "label", "dataset"
        ],
        "data preprocessing": [
            "preprocessing", "missing values", "missing", "imputation", "impute",
            "categorical", "encoding", "one hot", "scaling", "normalize",
            "standardize", "clean data", "data cleaning", "outlier"
        ],
        "model evaluation": [
            "evaluation", "evaluate", "accuracy", "precision", "recall", "f1",
            "f1-score", "confusion matrix", "roc", "auc", "false positive",
            "false negative", "metric", "metrics"
        ],
        "nlp": [
            "nlp", "natural language", "text", "tokenization", "tokenize",
            "embedding", "embeddings", "transformer", "bert", "language model",
            "prompt", "transcript", "speech", "asr", "stt", "tts"
        ],
        "deep learning": [
            "deep learning", "neural network", "cnn", "rnn", "lstm", "transformer",
            "pytorch", "tensorflow", "keras", "layers", "activation", "backpropagation"
        ],
        "apis": [
            "api", "apis", "rest", "endpoint", "request", "response", "json",
            "fastapi", "flask", "backend", "http", "validation", "status code"
        ],
        "deployment": [
            "deploy", "deployment", "production", "latency", "monitor", "monitoring",
            "logging", "docker", "server", "cloud", "performance", "error rate"
        ],
        "project_overview": [
            "project", "built", "problem", "solution", "result", "impact", "worked",
            "implemented", "developed", "system", "pipeline"
        ],
        "nlp_speech_ai": [
            "nlp", "speech", "asr", "stt", "tts", "transcript", "audio",
            "tokenization", "text", "language model", "embedding", "prompt"
        ],
        "apis_backend": [
            "api", "backend", "endpoint", "request", "response", "json",
            "fastapi", "flask", "rest", "validation", "error handling"
        ],
        "debugging_problem_solving": [
            "debug", "debugging", "logs", "error", "issue", "fix", "pipeline",
            "problem", "trace", "testing", "root cause"
        ],
        "behavioral_ownership": [
            "ownership", "owned", "responsible", "led", "handled", "team",
            "decision", "conflict", "outcome", "result"
        ],
    }

    if skill in keyword_map:
        return keyword_map[skill]

    # Fallback: use skill phrase and individual words
    parts = [p for p in skill.replace("/", " ").replace("_", " ").split() if len(p) > 2]
    return [skill] + parts


def _has_skill_evidence(skill: str, question: str, answer: str) -> bool:
    """
    Validate that a skill/domain was actually discussed.
    Candidate answer has more weight than question, but question evidence also counts
    because the system may ask a domain-specific question and the answer may use synonyms.
    """
    text = f"{question or ''} {answer or ''}".lower()
    keywords = _skill_evidence_keywords(skill)

    for kw in keywords:
        kw = (kw or "").lower().strip()
        if kw and kw in text:
            return True

    return False



def generate_recruiter_summary(weighted_summary: dict, star_analysis: dict, profile: dict,
                               adaptive_trace: list, skill_coverage_map: dict) -> dict:
    """
    Generate a recruiter-friendly readable summary from analytics.
    This does not use an LLM; it is rule-based and explainable.
    """
    final_signal = weighted_summary.get("final_hire_signal", "N/A")
    avg_score = weighted_summary.get("avg_weighted_overall", 0)
    total_evaluated = weighted_summary.get("total_evaluated", 0)

    strengths = []
    concerns = []
    follow_up_areas = []

    # Strengths from score/profile
    if avg_score >= 3.5:
        strengths.append("Candidate showed strong overall interview performance.")
    elif avg_score >= 2.5:
        strengths.append("Candidate showed moderate potential but needs deeper explanation.")
    elif total_evaluated > 0:
        concerns.append("Candidate responses were weak or underdeveloped across evaluated turns.")

    if profile.get("ownership_pattern") in ["Strong", "Moderate"]:
        strengths.append("Candidate showed some ownership of the discussed work.")
    else:
        concerns.append("Candidate did not clearly demonstrate personal ownership or contribution.")

    if profile.get("thinking_style") == "Structured":
        strengths.append("Candidate communicated in a structured way.")
    else:
        concerns.append("Candidate answers lacked structure and step-by-step explanation.")

    if profile.get("data_orientation") == "Data-Driven":
        strengths.append("Candidate used measurable or data-backed explanation.")
    else:
        concerns.append("Candidate did not provide enough measurable results or evidence.")

    # STAR concerns
    if star_analysis.get("missing_result_count", 0) > 0:
        concerns.append("Candidate repeatedly missed result/impact in STAR-style answers.")
        follow_up_areas.append("Ask for measurable project impact, outcomes, or success metrics.")

    if star_analysis.get("weak_action_count", 0) > 0:
        concerns.append("Candidate did not clearly explain actions taken to solve problems.")
        follow_up_areas.append("Ask candidate to explain exact implementation steps and decisions.")

    # Skill coverage concerns
    # Avoid overwhelming the recruiter in very short/early interviews.
    not_covered_skills = []
    weak_skills = []

    for skill, data in skill_coverage_map.items():
        status = data.get("status", "")
        if status == "not_covered":
            not_covered_skills.append(skill)
        elif status == "covered_weak":
            weak_skills.append(skill)

    for skill in weak_skills[:3]:
        follow_up_areas.append(f"Re-check {skill} with a deeper technical follow-up.")

    for skill in not_covered_skills[:3]:
        follow_up_areas.append(f"Assess {skill} because it was not covered.")

    if total_evaluated <= 2 and len(not_covered_skills) > 3:
        follow_up_areas.append(
            "Only early interview data is available; remaining unassessed skills should be covered in later turns."
        )

    # Adaptive trace-based follow-up areas
    for item in adaptive_trace[-3:]:
        weakest = item.get("weakest_dimension", "")
        if weakest == "structure":
            follow_up_areas.append("Ask candidate to answer using a clear step-by-step structure.")
        elif weakest == "result_orientation":
            follow_up_areas.append("Ask candidate to quantify the result or business/user impact.")
        elif weakest == "ownership":
            follow_up_areas.append("Ask what the candidate personally built or owned.")

    # Deduplicate while preserving order
    def unique(items):
        seen = set()
        result = []
        for x in items:
            if x and x not in seen:
                result.append(x)
                seen.add(x)
        return result

    strengths = unique(strengths)[:5]
    concerns = unique(concerns)[:6]
    follow_up_areas = unique(follow_up_areas)[:6]

    if total_evaluated == 0:
        overall = "No evaluated candidate answers were available, so no reliable hiring assessment can be made."
    elif avg_score >= 4:
        overall = "Candidate performed strongly and gave convincing evidence across key interview dimensions."
    elif avg_score >= 3:
        overall = "Candidate showed potential, but some areas still require deeper technical and behavioral validation."
    elif avg_score >= 2:
        overall = "Candidate showed limited evidence of readiness and needs stronger, more structured answers."
    else:
        overall = "Candidate performance was weak in this interview segment, mainly due to unclear structure, limited ownership evidence, and missing measurable results."

    decision_note = (
        f"Final recommendation signal is {final_signal} based on an average weighted score of {avg_score}. "
        "This should be treated as a decision-support signal, not a final hiring decision."
    )

    return {
        "overall_observation": overall,
        "final_signal": final_signal,
        "average_weighted_score": avg_score,
        "main_strengths": strengths,
        "main_concerns": concerns,
        "recommended_follow_up_areas": follow_up_areas,
        "interview_decision_note": decision_note,
    }



# ====================================================================
#  5. Final Report Generator
# ====================================================================

def generate_final_report(context) -> dict:
    """
    Generate the full structured final report.

    Sections:
        A. Weighted Score Summary
        B. Technical Evidence Analysis
        C. Performance Trend Analysis
        D. Consistency Rating
        E. Behavioral Profile
        F. Bias Awareness & System Limitations

    Args:
        context: InterviewContext instance

    Returns:
        Complete report dict.
    """
    scored = [e for e in context.evaluations
              if e.get("overall_score", 0) > 0 and not e.get("is_error")]

    # --- A. Weighted Score Summary ---
    raw_fields = ["clarity", "structure", "confidence",
                  "ownership", "leadership", "result_orientation"]
    weighted_summary = {}
    if scored:
        for f in raw_fields:
            vals = [e.get(f, 0) for e in scored]
            weighted_summary[f"avg_{f}"] = round(sum(vals) / len(vals), 2)

        all_weighted = [s for _, s in context.weighted_score_history]
        weighted_summary["avg_weighted_overall"] = (
            round(sum(all_weighted) / len(all_weighted), 2) if all_weighted else 0.0
        )
        weighted_summary["total_evaluated"] = len(scored)

        avg_w = weighted_summary["avg_weighted_overall"]
        if avg_w >= 4.0:
            weighted_summary["final_hire_signal"] = "Strong Hire"
        elif avg_w >= 3.0:
            weighted_summary["final_hire_signal"] = "Hire"
        elif avg_w >= 2.0:
            weighted_summary["final_hire_signal"] = "Borderline"
        else:
            weighted_summary["final_hire_signal"] = "No Hire"
    else:
        weighted_summary = {"total_evaluated": 0, "final_hire_signal": "N/A"}

    # --- B. Technical Evidence Analysis ---
    # Junior AI Engineer evaluation should focus on beginner-to-intermediate technical evidence,
    # not senior-level architecture or STAR-style storytelling.
    technical_evidence_analysis = {
        "framework": "Evidence-Based Junior AI Engineer Technical Competency Rubric",
        "expected_level": "Beginner-to-intermediate practical understanding, not expert-level production mastery.",
        "evaluation_basis": {
            "technical_correctness": {
                "description": "Checks whether the candidate understands the basic technical concept correctly.",
                "junior_expectation": "Core idea should be correct; deep expert-level detail is not required.",
                "importance": "High"
            },
            "implementation_thinking": {
                "description": "Checks whether the candidate can explain simple practical steps such as loading data, preprocessing, training, evaluating, exposing an API, or deploying.",
                "junior_expectation": "A clear basic workflow is enough; complex MLOps architecture is not required.",
                "importance": "High"
            },
            "tool_and_framework_understanding": {
                "description": "Checks whether the candidate has basic practical familiarity with tools such as Python, scikit-learn, FastAPI, Docker, logging, monitoring, or NLP/speech tools.",
                "junior_expectation": "Basic usage and purpose should be clear; advanced optimization is not required.",
                "importance": "Medium-High"
            },
            "validation_and_testing": {
                "description": "Checks whether the candidate can explain simple ways to verify results using train/validation split, accuracy, precision, recall, F1-score, confusion matrix, API testing, logs, or latency/error checks.",
                "junior_expectation": "Basic validation sense is expected; advanced statistical evaluation is not required.",
                "importance": "High"
            },
            "debugging_approach": {
                "description": "Checks whether the candidate can isolate common issues in data, preprocessing, model behavior, evaluation, API, or deployment.",
                "junior_expectation": "Candidate should know how to check problems step by step.",
                "importance": "High"
            },
            "communication_clarity": {
                "description": "Checks whether the answer is understandable, structured, and clear in a live interview.",
                "junior_expectation": "Simple clear wording is preferred over complex terminology.",
                "importance": "Medium"
            },
            "ownership_evidence": {
                "description": "Checks whether the candidate can explain what they personally built, tested, fixed, or improved.",
                "junior_expectation": "Individual contribution should be visible, even if the project was small.",
                "importance": "Medium"
            }
        },
        "focus_areas": [
            "technical_correctness",
            "implementation_thinking",
            "tool_and_framework_understanding",
            "validation_and_testing",
            "debugging_approach",
            "communication_clarity",
            "ownership_evidence",
        ],
        "technical_turns_evaluated": len(scored),
        "note": (
            "This report uses an evidence-based Junior AI Engineer technical competency rubric. "
            "It does not expect senior-level production mastery. The candidate is evaluated on core AI/ML understanding, "
            "practical implementation steps, basic tool usage, validation/testing, debugging approach, communication clarity, "
            "and evidence of personal contribution."
        ),
    }

    # --- C. Performance Trend Analysis ---
    trend = detect_performance_trend(context.weighted_score_history)

    # --- D. Consistency Rating ---
    consistency = compute_consistency_rating(context.weighted_score_history)

    # --- E. Behavioral Profile ---
    profile = generate_behavioral_profile(scored)

    # --- F. Bias Awareness & System Limitations ---
    bias_awareness = {
        "language_fluency_bias": (
            "Scores may be influenced by the candidate's English language "
            "fluency rather than actual competency. Non-native speakers may "
            "receive lower clarity and structure scores despite strong "
            "technical or behavioral substance."
        ),
        "cultural_storytelling_differences": (
            "Structured interview response conventions vary across cultures. "
            "Candidates from different cultural backgrounds may organize "
            "their answers differently without implying weaker thinking "
            "or ownership."
        ),
        "llm_subjectivity_limitations": (
            "All scores are generated by an LLM and are inherently subjective. "
            "They should be treated as directional signals, not definitive "
            "assessments. Human interviewer review is strongly recommended "
            "before any hiring decision."
        ),
    }

    # --- G. Adaptive Trace + Evidence-Based Skill Coverage ---
    adaptive_trace = (
        context.get_adaptive_trace()
        if hasattr(context, "get_adaptive_trace")
        else getattr(context, "adaptive_trace", [])
    )

    skill_coverage_map = {}
    skills = list(getattr(context, "skills", []))
    trace_text_items = []

    for item in adaptive_trace:
        combined_text = " ".join([
            str(item.get("question_answered", "")),
            str(item.get("candidate_answer", "")),
            str(item.get("next_question", "")),
            str(item.get("skill_focus", "")),
        ]).lower()
        trace_text_items.append((item, combined_text))

    for skill in skills:
        skill_key = _canonical_skill_name(skill)
        evidence_turns = []
        scores = []
        evidence_snippets = []

        for item, combined_text in trace_text_items:
            item_domain = _canonical_skill_name(str(item.get("domain", "")).lower().strip())
            question_text = str(item.get("question_answered", ""))
            answer_text = str(item.get("candidate_answer", ""))

            # Primary rule:
            # Count a skill/domain only when the interview turn was actually assigned to that domain.
            # This prevents broad ML words like "model" or "training" from inflating every skill.
            domain_match = item_domain == skill_key

            # Secondary fallback:
            # If domain is missing, count only when the candidate answer itself has explicit evidence.
            fallback_answer_evidence = (
                not item_domain
                and _has_skill_evidence(skill_key, "", answer_text)
            )

            if domain_match or fallback_answer_evidence:
                evidence_turns.append(item.get("turn"))
                score = item.get("scores", {}).get("weighted_overall_score", 0)
                if score:
                    scores.append(score)

                snippet = answer_text.strip()
                if snippet:
                    evidence_snippets.append(snippet[:160])

        avg_score = round(sum(scores) / len(scores), 2) if scores else 0

        if not evidence_turns:
            status = "not_covered"
            coverage_reason = "This skill/domain was not reached as a dedicated interview domain."
        elif avg_score >= 3.5:
            status = "covered_strong"
            coverage_reason = "Skill/domain was assessed in its dedicated domain with strong performance."
        elif avg_score >= 2.5:
            status = "covered_moderate"
            coverage_reason = "Skill/domain was assessed in its dedicated domain with moderate performance."
        else:
            status = "covered_weak"
            coverage_reason = "Skill/domain was assessed in its dedicated domain, but performance was weak."

        skill_coverage_map[skill_key] = {
            "mentions": len(evidence_turns),
            "avg_score": avg_score,
            "status": status,
            "evidence_turns": evidence_turns,
            "coverage_reason": coverage_reason,
            "evidence_snippets": evidence_snippets[:3],
        }

    # Add non-resume inferred skills/domains only when real evidence exists.
    for item in adaptive_trace:
        raw_inferred = str(
            item.get("domain", "") or item.get("skill_focus", "")
        ).lower().strip()

        inferred = _canonical_skill_name(raw_inferred)

        if not inferred or inferred in ["general", "intro", "technical", "behavioral"]:
            continue

        question_text = str(item.get("question_answered", ""))
        answer_text = str(item.get("candidate_answer", ""))

        # For inferred blueprint domains, the assigned domain itself is the evidence.
        # Only require some candidate answer text so empty/failed turns are not counted.
        if not answer_text.strip():
            continue

        score = item.get("scores", {}).get("weighted_overall_score", 0)

        # If canonical skill already exists, merge evidence instead of creating duplicate key.
        if inferred in skill_coverage_map:
            existing = skill_coverage_map[inferred]
            turn = item.get("turn")
            if turn not in existing.get("evidence_turns", []):
                existing["evidence_turns"].append(turn)
                existing["mentions"] = len(existing["evidence_turns"])
                if answer_text:
                    existing.setdefault("evidence_snippets", [])
                    if len(existing["evidence_snippets"]) < 3:
                        existing["evidence_snippets"].append(answer_text[:160])
            continue

        if score >= 3.5:
            status = "covered_strong"
        elif score >= 2.5:
            status = "covered_moderate"
        else:
            status = "covered_weak"

        skill_coverage_map[inferred] = {
            "mentions": 1,
            "avg_score": score,
            "status": status,
            "evidence_turns": [item.get("turn")],
            "coverage_reason": "Inferred domain/skill had evidence in the interview trace.",
            "evidence_snippets": [answer_text[:160]] if answer_text else [],
        }

    star_analysis = getattr(context, "star_stats", {}) or {}

    recruiter_summary = generate_recruiter_summary(
        weighted_summary=weighted_summary,
        star_analysis=star_analysis,
        profile=profile,
        adaptive_trace=adaptive_trace,
        skill_coverage_map=skill_coverage_map,
    )

    star_effectiveness_analysis = {
        "missing_result_count": star_analysis.get("missing_result_count", 0),
        "weak_action_count": star_analysis.get("weak_action_count", 0),
        "incomplete_star_count": star_analysis.get("incomplete_star_count", 0),
        "note": (
            "STAR-style storytelling is a Western corporate convention and is not the "
            "primary evaluation criterion for technical interviews. This data is provided "
            "for reference only."
        ),
    }

    return {
        "weighted_score_summary": weighted_summary,
        "technical_evidence_analysis": technical_evidence_analysis,
        "star_effectiveness_analysis": star_effectiveness_analysis,
        "performance_trend_analysis": trend,
        "consistency_rating": consistency,
        "behavioral_profile": profile,
        "recruiter_summary": recruiter_summary,
        "bias_awareness": bias_awareness,
        "adaptive_questioning_trace": adaptive_trace,
        "skill_coverage_map": skill_coverage_map,
        "interview_metadata": {
            "total_turns": context.turn_count,
            "final_state": context.state.value,
            "interview_stage": context.interview_stage,
            "skills_assessed": context.skills,
            "behavioral_categories_covered": context.behavioral_categories_used,
            "target_role": getattr(context, "target_role", "junior_ai_engineer"),
            "profile_source": getattr(context, "profile_source", "default"),
            "role_title": context.resume_data.get("role", "Junior AI Engineer"),
            "domain_coverage": context.get_domain_summary(),
        },
    }



def sanitize_recruiter_summary_for_technical_interview(final_report: dict) -> dict:
    """
    Final safety sanitizer for reports:
    Keeps STAR concerns only when project/behavioral turns justify them.
    """
    if not isinstance(final_report, dict):
        return final_report

    trace = final_report.get("adaptive_questioning_trace", []) or []
    summary = final_report.get("recruiter_summary", {}) or {}

    if isinstance(summary, dict):
        if "main_concerns" in summary:
            summary["main_concerns"] = _technical_report_concern_filter(
                summary.get("main_concerns", []), trace
            )
        if "recommended_follow_up_areas" in summary:
            summary["recommended_follow_up_areas"] = _technical_report_followup_filter(
                summary.get("recommended_follow_up_areas", []), trace
            )

    final_report["recruiter_summary"] = summary
    return final_report

