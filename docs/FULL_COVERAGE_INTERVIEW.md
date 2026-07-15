# Full-Topic Interview Coverage and Dialogue Fixes

**Date:** 2026-07-15  
**Branch:** `uthman`  
**Status:** Implemented + unit tests green  
**Scope:** Coverage-first wrap-up, report completeness, skip/intent policy, incomplete STT fragments, barge-in TTS settle

---

## Why this push

Live Junior AI Engineer interviews were ending after covering only part of the role blueprint (often ~50%). Closing was driven mainly by a hard turn cap of **12**, while the blueprint has **10 domains** plus intro, probes, skips, and incomplete redirects that burn turns. Reports could still be marked **`complete`** at only 50% coverage. Soft phrases like “next question” also skipped domains instantly, and tiny STT fragments (e.g. `"Started."`) created bad incomplete redirects.

---

## Problems Fixed

| # | Symptom | Root cause |
|---|---------|------------|
| 1 | Interview ends before NLP / APIs / deployment / debugging / behavioral | `MAX_TOTAL_INTERVIEW_TURNS = 12` forced WRAPUP regardless of uncovered domains |
| 2 | Report type `complete` with many `not_assessed` domains | `complete_min_coverage_percent = 50` |
| 3 | “Move to the next question” instantly skips a domain | Soft advance phrases classified as skip / `CHANGE_TOPIC` |
| 4 | Skip-heavy path burns topics / ends early | No per-interview skip budget |
| 5 | “Ask previous question” could derail toward close | No dedicated previous-question → replay mapping |
| 6 | Incomplete redirect quotes orphan `"Started."` after a good answer | Tiny trailing STT merged/scored as the turn |
| 7 | Duplicate org question TTS after barge-in; double closing line | No settle / duplicate suppress; closing spoken twice |

---

## Policy Changes (concrete)

1. **Never wrap while blueprint domains remain**, unless safety ceiling or explicit end.
2. **Safety ceiling** `MAX_TOTAL_INTERVIEW_TURNS = 28` (intro + 10 domains + probes + guard buffer).
3. **Report `complete`** requires ~**100%** visited blueprint coverage (assessed or explicitly skipped).
4. **Skip budget** `MAX_SKIPS_PER_INTERVIEW = 2`; soft “next question” does **not** skip.

Junior AI Engineer blueprint order (unchanged):

1. `project_overview`
2. `python`
3. `machine_learning`
4. `data_preprocessing`
5. `model_evaluation`
6. `nlp_speech_ai`
7. `apis_backend`
8. `deployment`
9. `debugging_problem_solving`
10. `behavioral_ownership`

---

## Changes Made

### 1. Coverage-first wrap-up — `interviewer_policy.py`, `decision_engine.py`, `role_registry.py`, `coverage_engine.py`

- Raised `MAX_TOTAL_INTERVIEW_TURNS` from **12 → 28**.
- Added `MAX_SKIPS_PER_INTERVIEW = 2` on role config / coverage engine.
- Closing from adaptive decide / technical handler only when:
  - all domains covered, **or**
  - turn count ≥ safety ceiling (**28**).
- Mid-interview at turn 12 with open domains now **ADVANCE**s instead of CLOSING.
- When the blueprint is exhausted, wrap immediately (no extra multi-turn behavioral loop after the blueprint’s own `behavioral_ownership` domain).

### 2. Skip budget and stay-on-question — `dialogue_manager.py`, `context.py`

- `InterviewContext.skips_used` / `can_skip_domain()` / `record_skip()`.
- `_guard_skip_domain`: if budget exhausted, **stay on current question** (`SKIP_BUDGET_EXCEEDED`) instead of advancing.
- Successful skips still advance through remaining domains; a single skip alone does not close the interview.

### 3. Intent / meta conversation — `intent_guard.py`, `meta_conversation_guard.py`

- Soft advance (`next question`, `move to the next…`) → `STAY_ON_QUESTION` / `stay_on_question` (replay current question).
- Hard skip (`skip this question`, `don't have an answer`, `change the question`, `let's move on`) → `SKIP_REQUEST` / `CHANGE_TOPIC` with `skip_domain`.
- Previous question phrases → `REPEAT_REQUEST` / `PREVIOUS_QUESTION` (never CLOSING).

### 4. Incomplete / STT fragments — `incomplete_guard.py`, `transcript_utils.py`, `interview_processor.py`

- `merge_stt_hypothesis`: do not append ≤2-word fragments onto a substantial (≥6 word) utterance.
- Incomplete redirect: do not quote micro-fragments; prefer a clear “continue your answer” prompt when prior substantial speech exists.
- Processor quietly discards tiny trailing STT fragments before dialogue.

### 5. Report completeness — `completion_policy.py`, `analytics.py`

- `complete_min_coverage_percent` raised to **100**.
- `coverage_percent` for completion uses **visited** domains (assessed **or** coverage turns **or** explicitly skipped), not assessed-only.
- Sessions that wrap at ~50% classify as **`partial`**, not `complete`.

### 6. Barge-in / VAD — `interview_processor.py`, `interview_bot.py`

- Post–barge-in settle window; suppress duplicate TTS of the interrupted assistant line.
- Avoid double closing TTS when adapter text already contains “concludes the interview”.
- Silero VAD `stop_secs` **0.80 → 0.90** to reduce mid-sentence cuts.

---

## Tests

New: `backend/tests/test_full_coverage_policy.py`

- Does **not** close at turn 12 with uncovered domains.
- Closes when blueprint exhausted or safety ceiling hit.
- Soft next / previous / hard skip intent checks.
- Skip budget, merge drop of `"Started."`, incomplete non-quote of micro-fragments.
- 50% wrap → `partial`; 100% → `complete`.

Updated: reporting v2 tiers, phase 6A meta guard, interview flow fixes.

Run (from `backend`, with venv):

```bash
PYTHONPATH=. python3 tests/test_full_coverage_policy.py
PYTHONPATH=. python3 tests/test_reporting_v2.py
PYTHONPATH=. python3 tests/test_phase6a_interview_flow.py
PYTHONPATH=. python3 tests/test_guards/test_interview_flow_fixes.py
```

---

## Acceptance (manual voice smoke)

A normal JR AI voice run should ask through:

`nlp_speech_ai` → `apis_backend` → `deployment` → `debugging_problem_solving` → `behavioral_ownership`

**before** the closing TTS, and the report should show ~100% visited coverage when the candidate finishes (or exhausted skips still leaving remaining domains until covered).

---

## Out of scope (unchanged)

- Cartesia / Deepgram account billing or socket instability
- Resume PDF / session-scoped report API redesign

---

## Key files touched

| Area | Files |
|------|--------|
| Policy | `backend/core/interviewer_policy.py`, `backend/core/role_registry.py` |
| Decide / flow | `backend/dialogue/decision_engine.py`, `dialogue_manager.py`, `context.py`, `coverage_engine.py` |
| Guards | `intent_guard.py`, `meta_conversation_guard.py`, `incomplete_guard.py` |
| Voice | `interview_processor.py`, `interview_bot.py` |
| Reporting | `completion_policy.py`, `analytics.py` |
| Tests | `test_full_coverage_policy.py` + related updates |
| Doc | `docs/FULL_COVERAGE_INTERVIEW.md` (this file) |
