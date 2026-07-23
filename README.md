# AI Voice Interviewer

Real-time AI voice interviewer for structured junior technical interviews. Candidates speak in a browser; the system transcribes speech, runs a guided multi-domain dialogue, scores answers with an LLM-based rubric, and produces a recruiter-facing assessment report.

This repository is the Final Year Project implementation on branch `uthman`.

## What you get

- **Live voice interviews** — microphone streaming, speech-to-text, text-to-speech, and turn-taking
- **Pre-interview lobby** — role-aware welcome, spoken instructions, then start when ready
- **Role templates** — configurable junior tracks (for example AI Engineer, Frontend Developer, Backend Developer), each with its own domain blueprint
- **Guarded dialogue pipeline** — intent handling, incomplete answers, repeats, coverage-driven progression, adaptive follow-ups
- **Automated evaluation** — multi-dimension rubric scoring with hire-style summary signals
- **Structured reports** — Report v2 JSON + HTML (`complete` / `partial` / `incomplete` / `aborted`)
- **Recruiter workspace** — session login, create invite links, optional invitation email, browse and download reports
- **Optional text/API path** — REST endpoints for testing without a microphone

## System map

| Piece | Default ports | Purpose |
|-------|---------------|---------|
| **Voice bot** | WebSocket `8765`, report HTTP `8766` | Primary interview engine and latest-report endpoints |
| **Candidate UI** | `3000` | Browser client: lobby, mic, live transcript |
| **Recruiter dashboard** | `8001` | Invites, auth, report browser (separate FastAPI app) |
| **Optional REST API** | `8000` | Text chat / report testing via `main.py` |

Recommended demo order: voice bot → candidate UI → recruiter dashboard.

## Tech stack

| Layer | Technology |
|-------|------------|
| Language / APIs | Python, FastAPI, Uvicorn |
| Voice runtime | Pipecat (WebSocket), Silero VAD |
| Speech-to-text | Deepgram |
| Text-to-speech | Cartesia |
| LLM (questions + evaluation) | Groq |
| Candidate / recruiter UIs | HTML, CSS, JavaScript |
| Optional persistence | PostgreSQL (falls back when unset) |

## Repository layout

```text
backend/
  core/                 # Config, sessions, roles, domain packs
  dialogue/             # Guards, evaluator, decision engine, DialogueManager
  evaluation/           # Rubric helpers, human-study export
  reporting/            # Report v2 builders, persistence, HTML renderer
  integration/          # Adapter between voice path and dialogue
  pipecat_integration/  # Voice bot, processor, candidate UI (manual_client/)
  voice/                # Turn policy and related voice helpers
  tests/                # Pytest suite
recruiter_dashboard/    # Invite + report UI/API on :8001
docs/                   # Architecture, pipeline, FYP, recruiter guides
reports/                # Generated Report v2 JSON/HTML (aborted/ for early exits)
logs/                   # Optional live debug traces
scripts/                # Regression helpers
main.py                 # Optional FastAPI text/API entry
requirements.txt
requirements-pipecat.txt
.env.example
pytest.ini
```

## Quick start

### 1. Clone and virtual environment

```powershell
git clone https://github.com/Tas-123/AI-interviewer-fyp-v2.git
cd AI-interviewer-fyp-v2
python -m venv venv
venv\Scripts\activate
```

On macOS/Linux: `source venv/bin/activate`.

### 2. Install dependencies

```powershell
pip install -r requirements.txt
pip install -r requirements-pipecat.txt
```

For the recruiter dashboard:

```powershell
pip install -r recruiter_dashboard\requirements.txt
```

### 3. Environment

```powershell
copy .env.example .env
```

Set at least:

- `GROQ_API_KEY` — question generation and evaluation
- `DEEPGRAM_API_KEY` — speech-to-text
- `CARTESIA_API_KEY` — text-to-speech

For the recruiter workspace, also set `RECRUITER_PASSWORD` (and optionally SMTP variables). See [`.env.example`](.env.example) and [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

**Do not commit `.env`.** Only `.env.example` belongs in version control.

## Running a full demo

### Voice bot (primary)

```powershell
venv\Scripts\activate
python backend\pipecat_integration\interview_bot.py
```

- Interview WebSocket: `ws://localhost:8765`
- Report HTTP: `http://localhost:8766` (for example `/latest-report`)

### Candidate UI

```powershell
cd backend\pipecat_integration\manual_client
python -m http.server 3000
```

Open `http://localhost:3000` and allow microphone access.

With an invite link from the recruiter dashboard, use `http://localhost:3000?invite=TOKEN`.

### Recruiter dashboard

```powershell
cd recruiter_dashboard
uvicorn app:app --reload --host 0.0.0.0 --port 8001
```

Open `http://localhost:8001` → sign in → create an interview invite → **Copy link** (always available). Optionally enter a candidate email and **Send invitation** when SMTP is configured.

After the interview, use **Candidate Reports** to view, open the full HTML assessment, or download it.

### Optional REST API (no microphone)

```powershell
uvicorn main:app --reload
```

Useful for `POST /start`, `POST /chat`, and report retrieval during development. This is not the product voice path.

## Configuration (overview)

All settings load from the root `.env`. Groups you may tune:

| Area | Examples |
|------|----------|
| LLM / STT / TTS | `GROQ_*`, `DEEPGRAM_*`, `CARTESIA_*` |
| Voice ports | `PIPECAT_WS_PORT`, `REPORT_HTTP_PORT` |
| Turn timing / VAD | debounce, echo cooldown, `VAD_STOP_SECS` (raise in noisy rooms) |
| Logging | `LOG_LEVEL`, `DEBUG_LIVE_LOGGING` |
| Recruiter | `CANDIDATE_ORIGIN`, `RECRUITER_AUTH_*`, `RECRUITER_USERNAME` / `PASSWORD` |
| Optional email | `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `COMPANY_NAME` |
| Optional DB | `DATABASE_URL` |

Full reference: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

## Architecture (short)

```text
Browser mic
  → WebSocket voice bot
  → Speech-to-text
  → DialogueManager (guards → evaluate → decide → generate)
  → Text-to-speech
  → Browser speaker

Role template + coverage blueprint drive topics.
Evaluations feed Report v2 under reports/ (and reports/aborted/ when needed).
Recruiter dashboard indexes those files; it does not run the interview engine.
```

Deeper detail:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/DIALOGUE_PIPELINE.md`](docs/DIALOGUE_PIPELINE.md)
- [`docs/INTERVIEW_FLOW.md`](docs/INTERVIEW_FLOW.md)
- [`docs/PRE_INTERVIEW_LOBBY_AND_CARTESIA.md`](docs/PRE_INTERVIEW_LOBBY_AND_CARTESIA.md)

## Recruiter workspace and reporting

| Concern | Notes |
|---------|--------|
| Auth | Env-based recruiter login; invite links stay public (token only, no candidate password) |
| Invites | Stored locally (JSON); candidate UI resolves role from the token |
| Delivery | **Copy link** is primary; SMTP send is optional and never blocks create/copy |
| Reports | Report v2 contract; HTML for presentation; JSON as structured source |

See:

- [`docs/RECRUITER_DASHBOARD.md`](docs/RECRUITER_DASHBOARD.md)
- [`docs/RECRUITER_REPORT_CONTRACT.md`](docs/RECRUITER_REPORT_CONTRACT.md)
- [`recruiter_dashboard/README.md`](recruiter_dashboard/README.md)

## Testing

From the repository root (see `pytest.ini`):

```powershell
venv\Scripts\activate
pytest
```

Or target the package path explicitly:

```powershell
$env:PYTHONPATH="backend"
pytest backend\tests
```

Regression helper (where available): `scripts/run_regression.sh`.

Legacy smoke scripts under `backend/test_*.py` may still be useful for quick checks; the primary suite lives in `backend/tests/`.

## Scope and limitations

Designed as an academic MVP, not a multi-tenant production SaaS:

- **One concurrent live voice session** on the Pipecat bot
- **File-based** invite store and report files on disk
- **Demo-grade** recruiter authentication (environment credentials + session cookie)
- **LLM-as-judge** evaluation — scores depend on model quality and transcript quality
- **Speech recognition noise** can affect follow-ups and scores in noisy rooms
- **No separate speech-emotion or facial analysis** — behavioural dimensions come from the text rubric only
- Optional PostgreSQL; the interview path works without it

## Documentation index

| Doc | Topic |
|-----|--------|
| [`docs/FYP_FINAL_REPORT_V03.md`](docs/FYP_FINAL_REPORT_V03.md) | Master technical FYP report |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Runtimes and module map |
| [`docs/DIALOGUE_PIPELINE.md`](docs/DIALOGUE_PIPELINE.md) | Guard order and turn flow |
| [`docs/INTERVIEW_FLOW.md`](docs/INTERVIEW_FLOW.md) | Bootstrap, coverage, roles |
| [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) | Environment variables |
| [`docs/PRE_INTERVIEW_LOBBY_AND_CARTESIA.md`](docs/PRE_INTERVIEW_LOBBY_AND_CARTESIA.md) | Lobby and spoken instructions |
| [`docs/RECRUITER_DASHBOARD.md`](docs/RECRUITER_DASHBOARD.md) | Recruiter product flow |
| [`docs/RECRUITER_REPORT_CONTRACT.md`](docs/RECRUITER_REPORT_CONTRACT.md) | Report fields and APIs |
| [`docs/DEVELOPER_ONBOARDING.md`](docs/DEVELOPER_ONBOARDING.md) | Getting productive in the repo |
| [`docs/MANUAL_TEST_GUIDE.md`](docs/MANUAL_TEST_GUIDE.md) | Manual verification checklist |
| [`docs/EVALUATION_CALIBRATION.md`](docs/EVALUATION_CALIBRATION.md) | Scoring calibration notes |

Older `docs/PHASE_*_COMPLETE.md` files are historical project notes, not the current status source.

## Team notes

Before a live run:

1. Activate the virtual environment and confirm dependencies are installed.
2. Ensure `.env` has valid LLM, STT, and TTS keys.
3. Start the voice bot before opening the candidate UI.
4. Allow microphone permission in the browser.
5. Prefer a quiet room; raise `VAD_STOP_SECS` if mid-sentence cutoffs are common.
6. For dashboard demos, set recruiter credentials and `CANDIDATE_ORIGIN` to match the candidate UI origin.

Optional live turn traces: set `DEBUG_LIVE_LOGGING=true` and inspect `logs/live_interview_debug.log`.

## Repository

```text
https://github.com/Tas-123/AI-interviewer-fyp-v2
```

Authoritative development branch: `uthman`.
