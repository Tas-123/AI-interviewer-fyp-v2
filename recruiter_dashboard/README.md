# Recruiter Dashboard

Separate management UI for creating interview invite links and viewing Report v2 files.
Does **not** run the voice interview engine.

## Ports

| Service | Port | Command |
|---------|------|---------|
| **Recruiter Dashboard** | **8001** | See below |
| Candidate UI | 3000 | `python -m http.server 3000` in `backend/pipecat_integration/manual_client/` |
| Voice bot (WS) | 8765 | `python backend/pipecat_integration/interview_bot.py` |
| Report HTTP (voice) | 8766 | started with the voice bot |
| FastAPI text API (optional) | 8000 | `uvicorn main:app --reload` |

## Run

From this directory:

```bash
cd recruiter_dashboard
pip install -r requirements.txt   # fastapi, uvicorn, python-dotenv, itsdangerous
uvicorn app:app --reload --host 0.0.0.0 --port 8001
```

Open [http://localhost:8001](http://localhost:8001) → **login** → dashboard.

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `CANDIDATE_ORIGIN` | `http://localhost:3000` | Base URL baked into invite links |
| `RECRUITER_AUTH_ENABLED` | `true` | Gate dashboard + protected APIs |
| `RECRUITER_USERNAME` | `recruiter` | Login username |
| `RECRUITER_PASSWORD` | _(empty)_ | Required when auth enabled |
| `RECRUITER_SESSION_SECRET` | demo fallback | Signs the session cookie |
| `SMTP_HOST` / `SMTP_PORT` | _(empty)_ / `587` | Optional invite email |
| `SMTP_USER` / `SMTP_PASSWORD` | | SMTP credentials (e.g. Gmail App Password) |
| `EMAIL_FROM` | | From address |
| `COMPANY_NAME` | `AI Interviewer` | Name in invitation email |

Set in project root `.env` (loaded automatically) or `recruiter_dashboard/.env`.

## Demo flow

1. Start voice bot (`:8765` / `:8766`).
2. Start Candidate UI (`:3000`).
3. Start Recruiter Dashboard (`:8001`) and sign in.
4. Generate interview link → **Copy link** (always works).
5. Optionally enter candidate email → **Send invitation** (only if SMTP is configured).
6. Candidate opens `?invite=TOKEN` (no recruiter login) → lobby → voice interview.
7. After the interview ends, open **Candidate Reports**.

## Invite delivery

| Path | When |
|------|------|
| **Copy link** | Always — primary, reliable for FYP demos |
| **Send invitation** | Optional — needs candidate email + SMTP env |

Email body: company name, interview title, optional candidate name, invite link, instructions. **No password** (token link only).

## Authentication

| Surface | Auth |
|---------|------|
| `/`, create/list invites, `/api/reports*`, send email | Session cookie after `/login` |
| `GET /api/interviews/{token}`, `POST .../bind` | **Public** (candidate) |
| `POST /api/auth/login`, `logout`, `GET /api/auth/me` | Public auth endpoints |

**Non-goals:** candidate passwords.

## Candidate Reports UI

Each row has a compact action group:

| Button | Behavior |
|--------|----------|
| **View** (primary) | Centered **summary modal** |
| **Full Report** | HTML assessment in a new browser tab |
| **Download** | Save the HTML file (`/html?download=1`) |

## Limitations (FYP)

- **One live voice session** at a time on the Pipecat bot.
- Invite store is a local JSON file (`data/interviews.json`).
- Recruiter auth is env-based (demo-grade).
- SMTP is optional; misconfigured SMTP never blocks Copy link.
- Interview engine is not imported or modified by this module.

## API (summary)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/api/auth/login` | Public | Set session cookie |
| `POST` | `/api/auth/logout` | Public | Clear session |
| `GET` | `/api/auth/me` | Public | Auth status |
| `GET` | `/api/email/status` | Recruiter | SMTP configured? |
| `GET` | `/api/roles` | Recruiter | Role dropdown |
| `GET` | `/api/interviews` | Recruiter | List invites |
| `POST` | `/api/interviews` | Recruiter | Create invite (optional email/name) |
| `POST` | `/api/interviews/{token}/send` | Recruiter | Send invitation email |
| `GET` | `/api/interviews/{token}` | Public | Resolve invite (Candidate) |
| `POST` | `/api/interviews/{token}/bind` | Public | Bind `{ session_id }` |
| `GET` | `/api/reports` | Recruiter | List Report v2 cards |
| `GET` | `/api/reports/{session_id}` | Recruiter | Full Report v2 JSON |
| `GET` | `/api/reports/{session_id}/html` | Recruiter | Sibling HTML (inline) |
| `GET` | `/api/reports/{session_id}/html?download=1` | Recruiter | HTML download |
