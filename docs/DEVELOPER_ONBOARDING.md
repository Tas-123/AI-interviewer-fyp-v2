# Developer Onboarding

## Quick start

```bash
git clone <repo>
cd AI-interviewer-fyp-v2
cp .env.example .env   # add API keys
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-pipecat.txt
python backend/pipecat_integration/interview_bot.py
```

Open `backend/pipecat_integration/manual_client/index.html` in a browser.

## Project layout

```
backend/
  core/           config, session_service, logging, role_registry, interviewer_policy
  dialogue/       DialogueManager, guards, evaluator, LLM adapter
  evaluation/     rubric, human study export
  integration/    InterviewDialogueAdapter (Pipecat ↔ sessions)
  pipecat_integration/  interview_bot, interview_processor, manual_client
  voice/          VoiceTurnPolicy (Phase 5)
  tests/          phase tests + pytest harness
main.py           FastAPI REST entry
recruiter_dashboard/  Recruiter UI + API (:8001) — invites + Report v2 listing
docs/             phase reports and guides
scripts/          run_regression.sh
```

Recruiter Dashboard (separate from the voice engine):

```bash
cd recruiter_dashboard
uvicorn app:app --reload --port 8001
```

See `docs/RECRUITER_DASHBOARD.md` and `recruiter_dashboard/README.md`.

## Running tests

```bash
bash scripts/run_regression.sh
```

Or individual suites:

```bash
PYTHONPATH=backend python backend/tests/test_phase3_session_flow.py
PYTHONPATH=backend python backend/tests/test_phase4_evaluation.py
PYTHONPATH=backend python backend/test_pipecat_integration.py
```

With pytest (if installed):

```bash
pytest backend/tests/
```

## Making changes safely

1. **Voice timing** — edit `.env` or `VoiceTurnPolicy`; avoid hardcoding sleeps in processor.
2. **Spoken copy** — `core/interviewer_policy.py` (closing lines, fallbacks).
3. **Follow-up labels** — `dialogue/output_sanitizer.strip_followup_prefix()`.
4. **LLM models** — `GROQ_MODEL` / `GROQ_EVALUATOR_MODEL` in `.env`.
5. Run regression before opening a PR.

## Phase history

| Phase | Focus |
|-------|-------|
| 1 | Unified SessionService, config |
| 2 | Guard pipeline refactor |
| 3 | Optional resume, role registry, coverage engine |
| 4 | Lite ensemble evaluation (rethink) |
| 5 | Production hardening — config, logging, async voice, docs, tests |

See `docs/PHASE_*_COMPLETE.md` for detailed reports.
