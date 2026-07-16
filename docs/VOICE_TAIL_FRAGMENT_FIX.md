# Voice Tail Fragment Fix — July 15 & 16 QA Plan

**Date:** 2026-07-16  
**Branch:** `uthman`  
**Commit:** `f69dd6c` — *Fix voice turn tail fragmentation (July 15/16 QA plan)*  
**Status:** Implemented + unit tests green  
**Scope:** Turn finalization, dialogue guard safety net, session-scoped report UI

---

## Why this change

Live interviews on **July 15** and **July 16** showed the same failure pattern:

1. Deepgram/STT captured the **full answer** in the browser transcript.
2. The backend **finalized too early** on a pause boundary.
3. A **short tail** (3–6 words) became a **separate dialogue turn**.
4. That tail triggered:
   - `INCOMPLETE_TRANSCRIPT_REDIRECT` — *"I only caught part of your answer"*
   - `DOMAIN_RELEVANCE_REDIRECT` / off-topic redirects
   - Sometimes **scoring and ADVANCE** on junk evidence

**Example tails from logs:**

| Session | Tail fragment | Problem |
|---------|---------------|---------|
| July 16 | `"the model generalized well."` | Incomplete redirect after full answer already submitted |
| July 15 | `"database for that."` | Scored/advanced as new turn |
| July 15 | `"deal with using the neighbor values."` | Domain redirect on tail |
| July 15 | `"Yes. That's what I'm saying."` | Fragment evaluated separately |

A second issue: the manual browser client loaded `/latest-report` without checking `session_id`, so back-to-back runs could show **stale reports** in the UI.

---

## Fix strategy (three layers)

| Layer | Goal |
|-------|------|
| **Processor** | Merge or suppress short tails shortly after a substantial answer is submitted |
| **Dialogue** | Never score/advance/redirect harshly on likely tail fragments |
| **UI** | Load report only when `report_meta.session_id` matches the active voice session |

---

## Changes made

### 1. Processor resume window — `interview_processor.py`

After `_submit_turn()`:

- Opens a **resume window** (`TURN_RESUME_WINDOW_SECONDS`, default **0.75s**).
- Stores `_last_submitted_transcript` and `_last_submitted_word_count`.

During the resume window:

- **Short tails** (≤ `TURN_TAIL_MAX_WORDS`, default **6**) following a **substantial answer** (≥ `TURN_TAIL_MIN_WORDS_FOR_SUSPICION`, default **10**) are **discarded** in `_prepare_transcript_for_turn()`.
- Final STT arrivals defer debounce so tails can merge before submit.
- **Extended debounce** for substantial buffered answers (waits through resume window).
- **Interim silence fallback** is skipped while resume window is active.

### 2. New config knobs — `config.py` / `voice_turn_policy.py`

| Variable | Default | Purpose |
|----------|---------|---------|
| `TURN_RESUME_WINDOW_SECONDS` | `0.75` | Window after submit to absorb/suppress tails |
| `TURN_TAIL_MAX_WORDS` | `6` | Max word count for a suspicious tail |
| `TURN_TAIL_MIN_WORDS_FOR_SUSPICION` | `10` | Prior answer must be at least this long |

These flow into `VoiceTurnPolicy` via `VoiceTurnPolicy.from_settings(settings)`.

### 3. Transcript quality flag — `transcript_quality.py`

New field: **`is_likely_tail_fragment`**

Heuristic (≤ 6 cleaned words):

- Noisy STT (`is_noisy`, high repetition, high cleanup reduction), or
- Any micro utterance ≤ 6 words (matches live pause-boundary tails)

Exposed in `TranscriptQuality.to_dict()` as `is_likely_tail_fragment`.

### 4. Guard pipeline — `incomplete_guard.py`, `domain_guard.py`

**IncompleteGuard**

- If `is_likely_tail_fragment` and a prior substantial answer exists → **`TAIL_FRAGMENT_CONTINUE`**
- Soft prompt: *"Please continue clearly from where you left off"* — **no quoting** of junk tails.

**DomainGuard**

- If `is_likely_tail_fragment` → **`STAY_ON_QUESTION`** instead of `DOMAIN_RELEVANCE_REDIRECT`.

`GuardContext` now accepts optional `transcript_quality` dict (passed from `dialogue_manager.py`).

### 5. DecisionEngine safety net — `decision_engine.py`

Before ADVANCE/PROBE:

- Blocks scoring when answer ≤ 3 words, or
- `is_likely_tail_fragment` with ≤ 8 words, or
- Tail fragment + noisy transcript

Returns **`STAY_ON_QUESTION`** with reason `tail_fragment_scoring_blocked`.

### 6. Session-scoped report UI — manual client

**`reportClient.js`**

- New `fetchLatestReportMatched(reportUrl, expectedSessionId)` — polls `/latest-report` (up to ~3.2s) until `report_meta.session_id` matches.
- Falls back to latest report if match fails (same as pre-fix behavior).

**`voiceSession.js`**

- Tracks `activeSessionId` from `conversation_event` (`session.started` or first message with `session_id`).
- Passes session id to `onSessionEnded(sessionId)`.

**`app.js`**

- Clears report panel on **Connect**.
- Loads report with session match on session end.

---

## Files changed

| File | Change |
|------|--------|
| `backend/core/config.py` | Three new env vars |
| `backend/voice/voice_turn_policy.py` | Policy fields + `from_settings` wiring |
| `backend/pipecat_integration/interview_processor.py` | Resume window, tail suppression, extended debounce |
| `backend/dialogue/transcript_quality.py` | `is_likely_tail_fragment` |
| `backend/dialogue/guards/types.py` | `transcript_quality` on `GuardContext` |
| `backend/dialogue/guards/incomplete_guard.py` | Tail fragment continue path |
| `backend/dialogue/guards/domain_guard.py` | Stay-on-question for tails |
| `backend/dialogue/decision_engine.py` | Fragment scoring block |
| `backend/dialogue/dialogue_manager.py` | Pass quality into guards + engine |
| `manual_client/js/app.js` | Session-scoped report load, clear on connect |
| `manual_client/js/network/reportClient.js` | `fetchLatestReportMatched` |
| `manual_client/js/network/voiceSession.js` | Session id tracking |
| `backend/tests/test_voice_tail_fragment_resume_window.py` | **New** processor regression tests |
| `backend/tests/test_tail_fragment_guarding.py` | **New** guard + engine tests |
| `scripts/run_regression.sh` | Includes new test modules |

---

## How to test

### 1. Automated regression

From repo root (with venv active and dependencies installed):

```bash
export PYTHONPATH="${PWD}/backend${PYTHONPATH:+:$PYTHONPATH}"
bash scripts/run_regression.sh
```

Run only the new tail-fragment tests:

```bash
python3 backend/tests/test_voice_tail_fragment_resume_window.py
python3 backend/tests/test_tail_fragment_guarding.py
```

**Expected:** `[PASS] test_voice_tail_fragment_resume_window` and `[PASS] test_tail_fragment_guarding`.

### 2. Manual voice interview

1. Start the voice server and manual client (see `docs/MANUAL_TEST_GUIDE.md`).
2. Give **long answers with a natural pause**, then a short closing phrase (e.g. *"…and the model generalized well."*).
3. Confirm the bot does **not** say *"I only caught part of your answer"* for the tail.
4. Confirm interview **coverage and flow** remain normal (no skipped domains).

### 3. Report session match

1. Run **two interviews back-to-back** without restarting the server.
2. After each session ends, check the report panel debug log:  
   `Final interview report loaded (session <uuid>).`
3. Confirm `report_meta.session_id` in the JSON matches the conversation session.

### 4. Optional tuning

If tails still slip through on slow networks, increase:

```bash
TURN_RESUME_WINDOW_SECONDS=1.0
TURN_TAIL_MAX_WORDS=8
```

If legitimate short answers are suppressed, decrease `TURN_TAIL_MAX_WORDS` or raise `TURN_TAIL_MIN_WORDS_FOR_SUSPICION`.

---

## Success criteria (from QA plan)

| Criterion | Target |
|-----------|--------|
| Tail fragments | Do not create extra dialogue turns |
| `INCOMPLETE_TRANSCRIPT_REDIRECT` | Sharp drop for post-answer tails |
| `DOMAIN_RELEVANCE_REDIRECT` on tails | Suppressed → `STAY_ON_QUESTION` |
| Report UI | `session_id` matches active session |
| Full coverage | Unchanged — all blueprint domains still required |

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Tail merged into wrong turn | Conservative word-count + resume window only |
| Legitimate short answer suppressed | Skip/repeat intents still pass; resume window expires |
| Report match timeout | Falls back to `/latest-report` (previous behavior) |
| Over-aggressive fragment flag | DecisionEngine only blocks ADVANCE/PROBE, not all turns |

---

## Related docs

- `docs/VOICE_TURN_TAKING_FIXES.md` — earlier barge-in / interim / echo fixes
- `docs/FULL_COVERAGE_INTERVIEW.md` — blueprint coverage before wrap-up
- `docs/CONFIGURATION.md` — general env reference (add tail vars here if extended)
- `docs/MANUAL_TEST_GUIDE.md` — end-to-end voice test steps

---

## Pull / deploy checklist

```bash
git checkout uthman
git pull origin uthman
# activate venv, install deps if needed
bash scripts/run_regression.sh
# start voice bot + manual client, run one full interview
```
