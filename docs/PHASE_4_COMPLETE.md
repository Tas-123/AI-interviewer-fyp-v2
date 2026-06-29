# Phase 4 — Evaluation Engine (Complete)

**Status:** Implemented and tested  
**Method:** `llm_rubric_ensemble_lite_v1` — primary LLM score + optional rethink on borderline answers

---

## 1. Objective

### Goal
Make scoring **fair, stable, and thesis-defensible** via:
- Central **rubric** (weights + hire thresholds)
- **Lite ensemble** (rethink pass on borderline scores)
- **Human-study export** for κ agreement validation

### Why after Phase 3?
Structured interview flow (Phase 3) defines *what* to ask. Phase 4 ensures *how* answers are judged is reliable enough for reports and hire signals.

### New capabilities
| Capability | Module |
|------------|--------|
| Central rubric | `evaluation/rubric.py` |
| Ensemble pipeline | `dialogue/evaluation_pipeline.py` |
| Rethink prompt | `dialogue/prompts.py` |
| Human study CSV/JSON | `evaluation/human_study_export.py` |
| Report methodology block | `analytics.py`, `recruiter_report.py` |

### Problems solved
- Weights/thresholds scattered across files → single rubric
- Single LLM score swings → rethink on borderline band (2.2–3.5)
- No thesis export path → CSV/JSON with empty human_rating columns
- Reports lacked evaluation method metadata → now included

---

## 2. Task Breakdown (all done)

| # | Task | File |
|---|------|------|
| 4.1 | Central rubric | `evaluation/rubric.py` |
| 4.2 | Evaluation pipeline | `dialogue/evaluation_pipeline.py` |
| 4.3 | Rethink prompt | `prompts.py` |
| 4.4 | Refactor evaluator | `evaluator.py` |
| 4.5 | Analytics uses rubric | `analytics.py` |
| 4.6 | Recruiter methodology | `recruiter_report.py` |
| 4.7 | Trace metadata | `dialogue_manager.py` |
| 4.8 | Human study export | `human_study_export.py` |
| 4.9 | REST export endpoint | `main.py` |
| 4.10 | Tests | `tests/test_phase4_evaluation.py` |

---

## 3. Architecture

```
DialogueManager.handle_turn()
    → Evaluator.adaptive_evaluate()
        → EvaluationPipeline.evaluate_turn()
            1. _run_primary_adaptive()     # score + decision (1 LLM call)
            2. rethink_evaluation()        # only if borderline (2nd call)
            3. merge_evaluations()         # dimension average
    → DecisionEngine (unchanged contract)
```

**Latency:** Clear scores = 1 call. Borderline = 2 calls.

---

## 4. Implementation Order (executed)

1. `rubric.py` → 2. `evaluation_pipeline.py` → 3. `evaluator.py` refactor  
4. `analytics` + `recruiter_report` → 5. `dialogue_manager` metadata  
6. `human_study_export` + REST → 7. Tests

---

## 5. Best Practices

- Single source of truth for weights/thresholds
- Ensemble only when needed (not 2× on every turn)
- Conservative merge (dimension average)
- Backward-compatible `adaptive_evaluate()` response shape
- Offline export separate from runtime path

---

## 6. Deliverables

**New:** `evaluation/rubric.py`, `evaluation/human_study_export.py`, `dialogue/evaluation_pipeline.py`, `tests/test_phase4_evaluation.py`

**Updated:** `evaluator.py`, `prompts.py`, `analytics.py`, `recruiter_report.py`, `dialogue_manager.py`, `main.py`

**Tests:** 10/10 Phase 4 tests pass

---

## 7. Completion Checklist

- [x] `DIMENSION_WEIGHTS` in one module
- [x] Rethink triggers on borderline weighted score or high dimension spread
- [x] `evaluation_methodology` in final report
- [x] `rethink_applied` in adaptive trace
- [x] Human study CSV/JSON export
- [x] `GET /export/human-study/{session_id}`
- [x] Phase 1–3 tests still pass

---

## 8. Validation

### Manual
1. Complete 3+ scored turns → check report for `evaluation_methodology`
2. Borderline answer → logs may show rethink; trace has `rethink_applied: true`
3. `GET /export/human-study/{session_id}` → rows with empty `human_rating_overall`

### Commands
```bash
./venv/bin/python backend/tests/test_phase4_evaluation.py
curl http://localhost:8000/export/human-study/{session_id}
```

### Edge cases
| Case | Expected |
|------|----------|
| Weighted 4.5 | No rethink |
| Weighted 3.0 | Rethink applied |
| High spread (5 vs 2) | Rethink applied |
| Short answer | No LLM call, empty eval |

### Phase 3 regression
```bash
./venv/bin/python backend/tests/test_phase3_session_flow.py
./venv/bin/python backend/test_session_service.py
```

---

## Rubric summary

| Dimension | Weight |
|-----------|--------|
| structure | 0.25 |
| result_orientation | 0.20 |
| ownership | 0.20 |
| leadership | 0.15 |
| clarity | 0.10 |
| confidence | 0.10 |

**Hire signals (per answer):** Strong Hire ≥4.2 · Hire ≥3.4 · Borderline ≥2.5 · else No Hire
