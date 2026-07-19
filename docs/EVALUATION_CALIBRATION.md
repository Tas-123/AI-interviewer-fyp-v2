# Evaluation Calibration (Junior Voice Interviews)

**Date:** 2026-07-19  
**Branch:** `uthman`  
**Status:** Implemented  

---

## Why

Live voice answers were scored with a **strict senior HR** persona and a **higher per-turn Hire bar (3.4)** than the final interview aggregate (**3.0**). That stacked bias made solid junior answers look weaker than they should for FYP demos and viva defence.

This update is a **calibration** change only — not a scoring-engine rewrite.

---

## What changed

### 1. Fairer eval persona (prompts + Groq system)

| Before | After |
|--------|--------|
| “strict senior HR interviewer” | Fair senior engineer evaluating a Junior AI Engineer in a **live voice** interview |
| “Be strict and analytical in scoring…” | Fair and evidence-based; reward concrete practice; do not punish natural spoken delivery when meaning is clear |

Files: `backend/dialogue/prompts.py` (`ADAPTIVE_EVALUATION_PROMPT`, `RETHINK_EVALUATION_PROMPT`), `backend/dialogue/evaluator.py` (system message).

Rethink still forbids unfounded inflation, but may **raise** scores that were too harsh when evidence supports it.

### 2. Aligned per-answer hire thresholds

In `backend/evaluation/rubric.py` → `HIRE_SIGNAL_THRESHOLDS`:

| Signal | Before | After (matches interview aggregates) |
|--------|--------|--------------------------------------|
| Strong Hire | ≥ 4.2 | ≥ **4.0** |
| Hire | ≥ 3.4 | ≥ **3.0** |
| Borderline | ≥ 2.5 | ≥ 2.5 (unchanged) |

Interview-level analytics and `RECRUITER_HIRE_THRESHOLDS` were already 4.0 / 3.0 — left unchanged.

### Unchanged (intentionally)

- Six dimensions and default **weights** (structure 0.25, etc.)
- EvaluationPipeline / rethink merge math
- Guards, DecisionEngine, probe budgets
- 3-word empty-answer cliff
- Report v2 / completion policy
- Domain-aware weight maps (out of scope)

---

## How to defend in viva

> We kept the same deterministic rubric and ensemble pipeline. We recalibrated the LLM persona and hire thresholds for **junior voice interviews** so per-turn Hire labels match the final report bands (3.0 / 4.0), without redesigning the architecture.

---

## Re-test

```bash
PYTHONPATH=backend python backend/tests/test_phase4_evaluation.py
```

Live: a concrete junior technical answer with weighted ~3.1–3.3 should more often show **Hire** than **Borderline**.
