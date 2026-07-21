"""
Recruiter Dashboard — FastAPI entry point.

Run from this directory:
  uvicorn app:app --reload --port 8001

Or from project root:
  uvicorn recruiter_dashboard.app:app --reload --port 8001
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

# Ensure local imports work when launched as `uvicorn app:app` from this folder
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Load project .env if present (CANDIDATE_ORIGIN, etc.)
_PROJECT_ENV = _ROOT.parent / ".env"
if _PROJECT_ENV.exists():
    load_dotenv(_PROJECT_ENV)
load_dotenv(_ROOT / ".env")

from api.auth import router as auth_router  # noqa: E402
from api.invites import router as invites_router  # noqa: E402
from api.reports import router as reports_router  # noqa: E402
from services import auth as auth_service  # noqa: E402

STATIC_DIR = _ROOT / "static"

app = FastAPI(
    title="Recruiter Dashboard",
    description="Interview invite links + Report v2 listing (separate from voice engine).",
    version="1.0.0",
)

# Session must be added so request.session works in routes.
app.add_middleware(
    SessionMiddleware,
    secret_key=auth_service.session_secret(),
    session_cookie="recruiter_session",
    same_site="lax",
    https_only=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(invites_router)
app.include_router(reports_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "recruiter_dashboard",
        "candidate_origin": os.getenv("CANDIDATE_ORIGIN", "http://localhost:3000"),
        "auth_enabled": auth_service.auth_enabled(),
    }


@app.get("/login")
def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/")
def index_page(request: Request):
    if auth_service.auth_enabled() and not auth_service.is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
