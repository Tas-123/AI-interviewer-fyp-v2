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

Set in project root `.env` (loaded automatically) or `recruiter_dashboard/.env`.

## Demo flow

1. Start voice bot (`:8765` / `:8766`).
2. Start Candidate UI (`:3000`).
3. Start Recruiter Dashboard (`:8001`) and sign in.
4. In **AI Interview**, select role → **Generate interview link** → copy.
5. Open the link (includes `?invite=TOKEN`). Candidate resolves role from this API **without** recruiter login, then runs lobby → voice interview.
6. After the interview ends, open **Candidate Reports** (while logged in) and refresh.

## Authentication

| Surface | Auth |
|---------|------|
| `/`, create/list invites, `/api/reports*` | Session cookie after `/login` |
| `GET /api/interviews/{token}`, `POST .../bind` | **Public** (candidate) |
| `POST /api/auth/login`, `logout`, `GET /api/auth/me` | Public auth endpoints |

**Non-goals:** candidate passwords; SMTP invite email (future).

## Candidate Reports UI

Each row has a compact action group:

| Button | Behavior |
|--------|----------|
| **View** (primary) | Centered **summary modal** — scores, hire signal, narratives; close with Close / backdrop / Esc |
| **Full Report** | HTML assessment in a new browser tab |
| **Download** | Save the HTML file (`/html?download=1`) |

Modal footer repeats Full Report / Download for convenience. Summary is never injected under the table.

Key UI files:

- `static/login.html` / `static/js/login.js` — recruiter sign-in
- `static/js/reportsView.js` — table + modal open/close
- `static/css/main.css` — `.action-group`, `.modal*` styles
- `static/index.html` — `#report-modal` markup + Logout

## Limitations (FYP)

- **One live voice session** at a time on the Pipecat bot.
- Invite store is a local JSON file (`data/interviews.json`) — fine for demos, not multi-user production.
- Recruiter auth is env-based (demo-grade), not OAuth/multi-tenant.
- Interview engine (`DialogueManager` / Pipecat) is not imported or modified by this module.

## API (summary)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/api/auth/login` | Public | Set session cookie |
| `POST` | `/api/auth/logout` | Public | Clear session |
| `GET` | `/api/auth/me` | Public | Auth status |
| `GET` | `/api/roles` | Recruiter | Role dropdown |
| `GET` | `/api/interviews` | Recruiter | List invites |
| `POST` | `/api/interviews` | Recruiter | Create invite |
| `GET` | `/api/interviews/{token}` | Public | Resolve invite (Candidate) |
| `POST` | `/api/interviews/{token}/bind` | Public | Bind `{ session_id }` |
| `GET` | `/api/reports` | Recruiter | List Report v2 cards |
| `GET` | `/api/reports/{session_id}` | Recruiter | Full Report v2 JSON |
| `GET` | `/api/reports/{session_id}/html` | Recruiter | Sibling HTML (inline) |
| `GET` | `/api/reports/{session_id}/html?download=1` | Recruiter | HTML download |
