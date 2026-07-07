# Phase 6A — Interview Flow (Complete)

**Status:** Implemented and tested  
**Scope:** Duplicate questions, domain tracking, meta-conversation, IDK handling — **no Phase 6B/6C changes**

---

## Executive Summary

Phase 6A fixes the interview flow problems observed in the live voice test (question loops, advancing on "I don't know", meta-requests scored as answers). The root cause of repeated Python/overfitting/preprocessing questions was **`current_domain` resetting to the wrong blueprint domain** after `mark_domain_probe()` synced coverage state. Meta utterances and IDK responses now bypass evaluation via new guards and explicit flow actions.

---

## Problems Addressed

| Problem | Fix |
|---------|-----|
| Same domain question asked twice | `set_current_domain()` + `domain_primary_already_asked()` + `question_dedup` |
| `current_domain` lost after probe | `CoverageEngine.set_current_domain()`; `mark_domain_covered` no longer overwrites active domain |
| "I don't know" scored & advanced | `IdkGuard` + `idk_policy` (rephrase → hint → skip) |
| "Change question" / "I already answered" scored | `MetaConversationGuard` with `skip_domain` flow |
| Repeat/clarify scored | Existing `IntentGuard` (unchanged); guards now record turns via `_response_from_guard` |

---

## Files Modified / Added

### Added
| File | Purpose |
|------|---------|
| `backend/dialogue/question_dedup.py` | Semantic duplicate detection; domain primary signatures |
| `backend/dialogue/idk_policy.py` | IDK phrase detection; rephrase/hint/skip responses |
| `backend/dialogue/guards/meta_conversation_guard.py` | Already-answered & change-topic without scoring |
| `backend/dialogue/guards/idk_guard.py` | Routes IDK through policy before evaluator |
| `backend/tests/test_phase6a_interview_flow.py` | 10 unit tests for Phase 6A |

### Modified
| File | Why |
|------|-----|
| `backend/dialogue/coverage_engine.py` | `set_current_domain()`; decouple cover vs active domain |
| `backend/dialogue/context.py` | `set_current_domain()`, `record_idk_attempt()`, `domain_idk_counts` |
| `backend/dialogue/decision_engine.py` | `_advance_to_next_domain()` skips duplicate primaries; uses `set_current_domain` |
| `backend/dialogue/dialogue_manager.py` | `_handle_guard_hit`, `_guard_skip_domain`, `_ensure_unique_question` |
| `backend/dialogue/guards/pipeline.py` | Insert Meta + IDK guards after Echo |
| `backend/dialogue/guards/intent_guard.py` | Clarification phrase; logging fix |
| `backend/dialogue/llm_adapter.py` | Skip static question if duplicate in history |
| `scripts/run_regression.sh` | Include Phase 6A test suite |

---

## Architecture Impact

```
handle_turn()
  → GuardPipeline
      EchoGuard
      MetaConversationGuard   ← NEW (skip_domain, no eval)
      IdkGuard                ← NEW (rephrase / hint / skip_domain)
      IntentGuard
      IncompleteGuard
      DomainGuard
  → [if flow_action=skip_domain] _guard_skip_domain → mark covered → advance → LLM
  → [else if guard] _response_from_guard (no eval, add_turn)
  → adaptive_evaluate → decide_from_adaptive → _ensure_unique_question → LLM
```

**Modularity preserved:** New guards follow existing `Guard` protocol. Policy logic lives in `idk_policy.py` and `question_dedup.py`. Phase 5 voice/config/logging untouched.

**Coverage engine contract change:** `mark_domain_covered()` increments coverage only; callers must use `set_current_domain()` when advancing.

---

## Testing Performed

### Phase 6A unit tests (10/10 PASS)
- `test_set_current_domain_survives_probe_sync`
- `test_domain_primary_already_asked`
- `test_is_semantic_duplicate`
- `test_advance_skips_duplicate_primary_domain`
- `test_meta_already_answered_intent`
- `test_meta_guard_skips_evaluation`
- `test_idk_detection`
- `test_idk_guard_first_attempt_rephrase`
- `test_idk_third_attempt_skips_domain`
- `test_coverage_engine_set_current_domain`

### Regression (PASS)
- Phase 3 session flow (8/8)
- Phase 4 evaluation (10/10)
- Guard pipeline smoke test

**Command:** `bash scripts/run_regression.sh`

### Not run in CI (requires venv + Groq)
- Full `test_pipecat_integration.py` — processor contract unchanged; recommend manual voice retest.

---

## Results

| Area | Result |
|------|--------|
| Domain tracking after probe | Fixed |
| Duplicate primary questions on advance | Prevented |
| Meta-conversation scoring | Blocked |
| IDK three-strike policy | Implemented |
| Phase 3–5 regressions | No failures |

---

## Remaining Issues (Phase 6B scope)

- STT repetition/fragmentation still degrades transcripts before guards run
- Evaluator may still score noisy long answers harshly
- `IntentGuard` vs `MetaConversationGuard` overlap on some phrases (low risk; meta runs first)
- Live voice retest needed to confirm UX improvement end-to-end

---

## Recommendations (within Phase 6)

1. **Proceed to Phase 6B** — transcript dedupe + noisy-transcript detection before evaluation
2. **Manual voice test** — verify no question loops on a full 10+ turn interview
3. **Do not** expand turn limits until 6B improves answer quality input

---

**Phase 6A complete. Do not start 6B until approved.**
