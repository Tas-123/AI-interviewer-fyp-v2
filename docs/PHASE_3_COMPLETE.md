# Phase 3 — Structured Interview Flow & Optional Resume (Complete)

**Status:** Implemented and tested  
**Design:** Optional resume + `target_role` defaulting to `junior_ai_engineer`

---

## 1. Objective

### Goal
Deliver a **structured, resume-aware interview flow** where:
- **target_role** selects blueprint structure (10 Junior AI Engineer domains)
- **Optional resume** personalizes intro and project-overview questions
- **No resume** falls back to `DEFAULT_CANDIDATE_PROFILE`

### Why after Phase 1–2?
Phase 1 unified sessions; Phase 2 extracted guards and interviewer persona. Phase 3 adds **what to ask and when to advance** — the structured plan the FYP proposal promises — without reopening session or guard architecture.

### New capabilities
| Capability | Description |
|------------|-------------|
| **Session bootstrap** | Normalize REST/Pipecat/WS payloads → `CandidateProfile` |
| **Role registry** | Extensible map: role → blueprint + default profile |
| **Coverage engine** | Single module for domain coverage, probes, advance |
| **Resume wiring** | `parse_resume` + `QuestionSelector` in live path |
| **Optional resume UX** | Pipecat client form + REST `/start` fields |

### Problems solved
| Before | After |
|--------|-------|
| Hardcoded profile on Pipecat connect | Client can send `resume_text` / skip for default |
| Blueprint logic scattered in `context.py` | `CoverageEngine` owns coverage state |
| Orphaned `resume_context_parser`, `question_selector` | Wired at session start + `project_overview` |
| Parallel `InterviewFlowController` on dev WS | Deprecated; blueprint domain = stage |
| REST required `resume_data` dict | All resume fields optional |

### Closer to FYP vision
Structured domain coverage (Q-matrix practical version) + personalized questions when resume provided — thesis-defensible without IRT/CAT.

---

## 2. Detailed Task Breakdown

| # | Task | Files | Type | Status |
|---|------|-------|------|--------|
| 3.1 | Role registry | `backend/core/role_registry.py` | New | Done |
| 3.2 | Session bootstrap | `backend/dialogue/session_bootstrap.py` | New | Done |
| 3.3 | Coverage engine | `backend/dialogue/coverage_engine.py` | New | Done |
| 3.4 | Context delegates to coverage | `dialogue/context.py` | Modify | Done |
| 3.5 | SessionService bootstrap | `core/session_service.py` | Modify | Done |
| 3.6 | QuestionSelector domain API | `dialogue/question_selector.py` | Modify | Done |
| 3.7 | DM + LLM resume wiring | `dialogue_manager.py`, `llm_adapter.py` | Modify | Done |
| 3.8 | REST optional resume | `main.py` | Modify | Done |
| 3.9 | Adapter session_start kwargs | `integration/dialogue_adapter.py` | Modify | Done |
| 3.10 | Pipecat start payload | `pipecat_integration/interview_bot.py` | Modify | Done |
| 3.11 | Manual client profile form | `manual_client/index.html`, `client.js` | Modify | Done |
| 3.12 | Deprecate flow controller path | `voice/voice_session_manager.py`, `conversation_orchestrator.py` | Modify | Done |
| 3.13 | Report metadata | `dialogue/analytics.py`, `dialogue_manager.get_status` | Modify | Done |
| 3.14 | Phase 3 tests | `backend/tests/test_phase3_session_flow.py` | New | Done |
| 3.15 | Documentation | `docs/INTERVIEW_FLOW.md`, README | New/Modify | Done |

---

## 3. Architecture Impact

```
SessionStartRequest (optional resume, target_role)
        ↓
session_bootstrap.build_candidate_profile()
        ↓
SessionService.create() → DialogueManager
        ↓
InterviewContext
   ├── CoverageEngine (blueprint progression)
   └── QuestionSelector (resume Qs → bank → LLM fallback)
        ↓
DecisionEngine + LLMAdapter (unchanged contract)
```

| Module | Coupling | Prepares for |
|--------|----------|--------------|
| `role_registry` | Low | Phase 3+ roles (Backend, DS) |
| `session_bootstrap` | Low | Phase 4 eval baseline metadata |
| `coverage_engine` | Medium | Phase 5 turn manager hooks |
| `QuestionSelector` | Low | Phase 4 question quality |

---

## 4. Implementation Order (executed)

1. `role_registry` + `coverage_engine` + `session_bootstrap`
2. `context.py` delegation
3. `SessionService` + adapter + REST
4. `QuestionSelector` + `LLMAdapter` + `DialogueManager`
5. Pipecat + manual client
6. Dev voice layer (remove flow controller)
7. Tests + docs

---

## 5. Best Practices Applied

- **Separation of concerns:** bootstrap (input) / coverage (structure) / selector (questions)
- **Role wins for blueprint; resume wins for personalization**
- **Backward compatible:** `create(resume_data={...})` still works
- **Type hints + dataclasses** on new modules
- **Structured logging** on session create (`profile_source`, `target_role`)
- **Deprecated** `InterviewFlowController` documented, not deleted (tests)

---

## 6. Deliverables

### New modules
- `backend/core/role_registry.py`
- `backend/dialogue/session_bootstrap.py`
- `backend/dialogue/coverage_engine.py`
- `backend/tests/test_phase3_session_flow.py`
- `docs/INTERVIEW_FLOW.md`

### Updated modules
- `context.py`, `session_service.py`, `dialogue_manager.py`, `llm_adapter.py`
- `question_selector.py`, `main.py`, `dialogue_adapter.py`
- `interview_bot.py`, `manual_client/*`
- `voice/voice_session_manager.py`, `voice/conversation_orchestrator.py`
- `analytics.py`, `README.md`

### Tests passing
- `backend/tests/test_phase3_session_flow.py` (8 tests)
- Phase 1–2: session_service, dialogue_adapter, guards
- Voice layer (11), Pipecat integration (6), new_layers (12)

---

## 7. Completion Checklist

### Functional
- [x] No resume → default Junior AI Engineer profile
- [x] Resume text/data → `profile_source: resume`, personalized skills + questions
- [x] `target_role` selects blueprint (default `junior_ai_engineer`)
- [x] Coverage engine drives domain advance
- [x] Resume questions used for `project_overview`
- [x] Pipecat accepts `{type:"start", resume_text?, display_name?}`
- [x] REST `POST /start` with optional fields
- [x] `GET /roles` lists available roles
- [x] Report includes `profile_source`, `domain_coverage`

### Code quality
- [x] No duplicate coverage logic in `context.py`
- [x] `InterviewFlowController` removed from dev voice path
- [x] Phase 1 SessionService contract preserved

### Integration
- [x] Pipecat default path unchanged when no resume sent
- [x] REST backward compatible via `resume_data` in body

---

## 8. Validation Before Phase 4

### Manual tests
1. **No resume:** Pipecat connect (empty form) → default intro
2. **With resume:** Paste skills in client → intro references skills
3. **REST:** `POST /start` with `{}` vs `{resume_text: "..."}`
4. **Report:** Check `interview_metadata.profile_source` and `domain_coverage`

### Edge cases
| Case | Expected |
|------|----------|
| Empty `{}` resume_data | `profile_source: default` |
| Resume says "Frontend" | Blueprint still Junior AI Engineer |
| Partial skills only | Merged with default skills |
| Unknown target_role | Falls back to junior_ai_engineer |

### Logs
- Session create: `Session created: <id> (source=resume, role=junior_ai_engineer)`
- Pipecat: `Starting interview with client profile` vs `default profile`

### Phase 1–2 regression
```bash
./venv/bin/python backend/test_session_service.py
./venv/bin/python backend/test_dialogue_adapter.py
./venv/bin/python backend/tests/test_guards/test_echo_guard.py
./venv/bin/python backend/tests/test_phase3_session_flow.py
```

---

## API Quick Reference

```bash
# Default interview (no resume)
curl -X POST http://localhost:8000/start -H "Content-Type: application/json" -d '{}'

# With resume
curl -X POST http://localhost:8000/start -H "Content-Type: application/json" -d '{
  "display_name": "Alex",
  "resume_text": "Python, TensorFlow, 2 years, built NLP chatbot"
}'

# List roles
curl http://localhost:8000/roles
```

Pipecat WS start:
```json
{
  "type": "start",
  "target_role": "junior_ai_engineer",
  "display_name": "Alex",
  "resume_text": "Python, PyTorch, NLP projects..."
}
```
