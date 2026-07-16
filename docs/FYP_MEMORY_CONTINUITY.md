# FYP Memory Continuity Upgrade (Recent Q&A)

**Date:** 2026-07-16  
**Branch:** `uthman`  
**Status:** Implemented (incremental)  
**Scope:** Small continuity + token-safety upgrades only — no Memory Manager redesign

---

## What we changed

### 1. Answer-aware recent memory

[`backend/dialogue/context.py`](../backend/dialogue/context.py)

- `InterviewContext.get_recent_qa_pairs(n=3)` — last few completed Q&A pairs
- Includes in-flight answer from `latest_answer_for_decision` when present
- `format_recent_qa_for_prompt(...)` — compact prompt block with soft char cap

[`backend/dialogue/llm_adapter.py`](../backend/dialogue/llm_adapter.py)

Injects recent Q&A into:

- `_generate_technical`
- `_generate_behavioral`
- `_generate_followup`

So the question LLM can reference what the candidate actually said (e.g. FastAPI, Docker).

### 2. Sliding question-history window

Same file: `_build_history_text` now keeps only the **last 6 questions** (not the full interview list), with a soft character cap (~1800).

### 3. Adaptive evaluator (light touch)

[`backend/dialogue/evaluator.py`](../backend/dialogue/evaluator.py) + [`dialogue_manager.py`](../backend/dialogue/dialogue_manager.py)

Optional prior Q&A memory is appended to the adaptive evaluation prompt so PROBE follow-ups can stay continuous. Current Q/A remain the primary inputs.

---

## Postgres note

Postgres (`database.save_session` / `save_response`) is **persistence for reports and recovery metadata only**. It is **not** read back into LLM prompts at runtime. Live memory remains in-process `InterviewContext` via `SessionService`.

---

## In scope for FYP

| Item | Status |
|------|--------|
| Last 2–3 Q&A in question/follow-up prompts | Done |
| Sliding window on previous questions | Done |
| Soft char caps on history/memory blocks | Done |
| Docs of what we reject | This file |

---

## Explicitly out of scope (do not implement now)

| Idea | Why rejected at FYP stage |
|------|---------------------------|
| Full Memory Manager / knowledge graph | Redesigns `InterviewContext`; sync bugs |
| Candidate fact extraction after every turn | Extra LLM call → latency + parse failures |
| PromptAssembler mega-refactor | High regression risk on working prompts |
| Token Budget Manager + compress loops | Overkill under 28-turn ceiling; soft caps enough |
| Semantic / vector / topic retrieval | Infra + heuristics for little gain |
| Redis / RAG / full chat `messages[]` | Wrong scale / wrong problem |
| Contradiction detection agent | False positives hurt UX |

---

## How to test

```bash
export PYTHONPATH="${PWD}/backend${PYTHONPATH:+:$PYTHONPATH}"
python3 backend/tests/test_recent_qa_memory.py
```

Expected: `[PASS] test_recent_qa_memory`

Manual: in a voice interview, after mentioning a tool (e.g. FastAPI), a later follow-up or domain question may briefly reference that detail.

---

## Related

- Architecture review notes: project root `memory.md` (if present)
- Context flow overview: dialogue pipeline docs under `docs/`
