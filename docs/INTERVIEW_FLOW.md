# Phase 3 — Structured Interview Flow & Optional Resume

## Overview

Phase 3 adds **structured domain coverage** with **optional resume personalization**:

- **target_role** selects interview structure (blueprint)
- **resume** (optional) personalizes intro and project-overview questions
- **No resume** → default Junior AI Engineer profile

## Session start contract

```json
{
  "target_role": "junior_ai_engineer",
  "display_name": "Alex",
  "resume_text": "Python, TensorFlow, 2 years, built NLP chatbot...",
  "resume_data": {
    "skills": ["Python", "TensorFlow"],
    "experience": "2 years"
  }
}
```

All fields except `target_role` are optional. Default role: `junior_ai_engineer`.

## Architecture

```
Client (REST / Pipecat / dev WS)
    ↓ session_start payload
session_bootstrap.build_candidate_profile()
    ↓ CandidateProfile.to_resume_data()
SessionService.create()
    ↓
DialogueManager → InterviewContext
    ├── CoverageEngine (blueprint domains)
    └── QuestionSelector (resume questions → bank → LLM)
```

## Blueprint domains (Junior AI Engineer)

1. project_overview  
2. python  
3. machine_learning  
4. data_preprocessing  
5. model_evaluation  
6. nlp_speech_ai  
7. apis_backend  
8. deployment  
9. debugging_problem_solving  
10. behavioral_ownership  

## Key modules

| Module | Role |
|--------|------|
| `core/role_registry.py` | Role → blueprint + default profile |
| `dialogue/session_bootstrap.py` | Normalize optional resume input |
| `dialogue/coverage_engine.py` | Domain coverage, probes, advance |
| `dialogue/question_selector.py` | Resume questions + question bank |
| `dialogue/resume_context_parser.py` | Parse resume text (no LLM) |

## Deprecated

`InterviewFlowController` — replaced by `CoverageEngine` + `InterviewContext`.
Dev text WebSocket now reports blueprint `current_domain` as stage.

## API

- `POST /start` — optional resume; returns `profile_source`, `target_role`
- `GET /roles` — list available target roles
- Pipecat WS `{type:"start", resume_text?, display_name?, target_role?}`

## Report metadata

Final reports include:

```json
"interview_metadata": {
  "profile_source": "resume" | "default",
  "target_role": "junior_ai_engineer",
  "domain_coverage": { "blueprint": [...], "coverage": {...}, ... }
}
```
