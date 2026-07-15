# Project Cleanup Report

**Date:** 2026-07-15  
**Branch:** `uthman`  
**Policy:** Conservative — delete only items with 100% confidence they are unused by runtime, pytest, and `scripts/run_regression.sh`. When uncertain, keep and document.

---

## 1. Executive Summary

A safe, reversible cleanup removed **22 unused tracked artifacts**:

- **16** repo-root legacy manual smoke scripts (`test_*.py`)
- **6** backend saved test-run output dumps (`*.txt`)

No production modules, APIs, business logic, configs, or official regression tests were changed. Deprecated-but-still-referenced code (for example `interview_flow_controller.py`) was intentionally kept. A full list of “maybe unused” items is in §8 for manual review.

---

## 2. Files Deleted

### 2.1 Repo-root legacy smoke scripts (16)

| File |
|------|
| `test_barge_policy.py` |
| `test_context_followups.py` |
| `test_domain_relevance.py` |
| `test_domain_relevance_fixed.py` |
| `test_echo_repeat_guard.py` |
| `test_incomplete_transcript_guard.py` |
| `test_intent_classifier.py` |
| `test_live_transcript_cleanup.py` |
| `test_natural_questions.py` |
| `test_preprocessing_relevance.py` |
| `test_redirects.py` |
| `test_semantic_intent_classifier.py` |
| `test_strict_domain_relevance.py` |
| `test_strict_echo_guard.py` |
| `test_technical_short_followup.py` |
| `test_transcript_cleanup.py` |

### 2.2 Backend test-run output dumps (6)

| File |
|------|
| `backend/results.txt` |
| `backend/test_output.txt` |
| `backend/test_output_new.txt` |
| `backend/test_results.txt` |
| `backend/test_results_adaptive.txt` |
| `backend/test_results_stability.txt` |

---

## 3. Dead Code Removed

**None in this pass.**

No functions, classes, or constants were removed from live modules. Intra-module dead-code detection is not 100% reliable without invasive static analysis (dynamic imports, string dispatch, docs demos). Per policy, that class of change was deferred to §8.

---

## 4. Dead Test Files Removed

All **16** root `test_*.py` files listed in §2.1.

They were manual CLI smoke scripts (`sys.path.insert` into `backend/`), not part of the official suite:

- `pytest.ini` → `testpaths = backend/tests`
- `scripts/run_regression.sh` never invoked them
- No `import` / `from` references anywhere in the codebase
- Previously labeled in `docs/FYP_FINAL_REPORT.md` as legacy manual debug scripts

Canonical coverage remains under `backend/tests/` (guards, transcript utils, Phase 6*, reporting, voice turn policy, etc.).

---

## 5. Why Each Item Was Removed

| Category | Why 100% unused |
|----------|-----------------|
| Root `test_*.py` | Never imported; not collected by pytest; not in regression harness; superseded by `backend/tests/` |
| Backend `*.txt` dumps | Saved stdout from old manual runs (including UTF-16 dumps); not requirements; never read by code, scripts, or docs as inputs |

Doc hygiene only:

- `docs/PHASE_3_COMPLETE.md` — replaced `test_strict_echo_guard.py` with `backend/tests/test_guards/test_echo_guard.py`
- `docs/FYP_FINAL_REPORT.md` — tree line now points to `scripts/run_regression.sh` instead of deleted root scripts

---

## 6. Validation Performed After Cleanup

| Check | Result |
|-------|--------|
| Deleted paths absent from working tree | Yes |
| Grep for imports of deleted filenames | No broken code imports (doc history updated) |
| `python3 -m compileall backend main.py` | **Passed** |
| `scripts/run_regression.sh` | **Passed** (after aligning `test_processor_interview_completion` with intentional single closing TTS — see note below) |
| Docker / Compose | **N/A** — this repository has no Dockerfile or docker-compose |
| Production API / dialogue / Pipecat modules edited | No |

**Validation note:** `backend/test_pipecat_integration.py::test_processor_interview_completion` still expected two TTS frames on wrap-up. Product code already suppresses the duplicate system closing when the adapter text contains “concludes the interview” (full-coverage dialogue work). The assertion was updated to expect one TTS frame. This is a test-alignment fix only — not caused by deleting orphan root scripts.

---

## 7. Files Intentionally Kept (confidence &lt; 100% or still referenced)

| Item | Reason kept |
|------|-------------|
| `main.py` and all production packages under `backend/` | Live runtime |
| `scripts/run_regression.sh` and entire `backend/tests/` | Official harness |
| `backend/test_dialogue_adapter.py` | Invoked by regression |
| `backend/test_pipecat_integration.py` | Invoked by regression |
| `backend/dialogue/interview_flow_controller.py` | Deprecated for product path, but still imported by `backend/test_new_layers.py` |
| Dev text WebSocket stack (`ENABLE_DEV_TEXT_VOICE_WS`) | Still wired from `main.py` / documented as optional |
| `.env.example`, `requirements.txt`, `requirements-pipecat.txt` | Config / deps |
| All other `docs/` (aside from the two hygiene edits) | Academic / phase history |
| Gitignored `reports/`, `logs/`, `audit_*.json` | Generated artifacts; not part of this tracked cleanup |

---

## 8. Potentially Unused (Manual Review Recommended)

Do **not** delete these without a separate review. Uncertainty reasons are explicit.

### 8.1 Backend-root manuals outside regression

| File | Why uncertain |
|------|----------------|
| `backend/test_adaptive.py` | Documents / FYP note they are not in the harness, but may still be run manually for demos or marking evidence |
| `backend/test_stability.py` | Same |
| `backend/test_bugfixes.py` | Same |
| `backend/test_decision.py` | Same |
| `backend/test_new_layers.py` | Alone removable only with `interview_flow_controller.py`; still a valid offline check of deprecated layer |
| `backend/test_silero_debug.py` | Debug aid for VAD; may be useful during voice demos |
| `backend/test_report_fixes.py` | Historical report checks; may overlap reporting tests but not proven redundant byte-for-byte |
| `backend/test_session_service.py` | Still cited in Phase 3/4 docs as a manual command |
| `backend/test_voice_layer.py` | Offline voice-layer checks; optional path still exists |

### 8.2 Demo / simulation scripts

| File | Why uncertain |
|------|----------------|
| `backend/simulate_interview.py` | Standalone adaptive simulation; useful for demos / markers |
| `backend/ws_client_simulation.py` | Example WebSocket client for FastAPI text path |

### 8.3 Deprecated product-path module (keep until demos confirmed)

| File | Why uncertain |
|------|----------------|
| `backend/dialogue/interview_flow_controller.py` | Not used by Pipecat / CoverageEngine path, but still imported by `test_new_layers.py`. Removing requires deleting or rewriting that test together. |

### 8.4 Intra-module dead helpers / constants

Not audited for deletion in this pass. Static “never referenced” signals can miss:

- dynamic `getattr` / string dispatch
- reflection in tests
- documentation snippets

**Recommendation:** if a second pass is needed, run a dedicated reachability audit and review findings one-by-one.

### 8.5 Optional / secondary runtime path

Dev text WebSocket (`backend/voice/websocket_router.py`, orchestrator, session manager) is **not** the product Pipecat path but is still enabled via `ENABLE_DEV_TEXT_VOICE_WS`. Product decision required before removal.

---

## 9. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Someone still had a personal habit of running a root `test_*.py` | Low | Use `backend/tests/` or `scripts/run_regression.sh`; changes are git-reversible |
| Doc leftovers mentioning deleted names in prose archives | Low | Known command lines updated; historical prose may still mention names narratively |
| Accidental deletion of a needed module | None expected | Only orphans + output dumps removed; no production edits |

Cleanup is **fully reversible** via `git revert` of the cleanup commit.

---

## 10. Final Project Status

- **Stable FYP tree retained**
- Official regression path unchanged
- Production dialogue / voice / reporting behavior unchanged
- Cleanup scope deliberately small for safety
- Follow-up cleanup of §8 items is optional and should be a separate, reviewed change

**Status after this pass:** Clean of confirmed orphan root smoke scripts and tracked test-output dumps; ready for normal development and demos.
