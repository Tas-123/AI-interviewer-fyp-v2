"""
Thin recruiter auth for the Recruiter Dashboard (FYP demo-grade).

Uses env username/password + Starlette session cookie.
Candidate invite resolve/bind stays public (no session required).
"""

from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request


SESSION_KEY = "recruiter"


def auth_enabled() -> bool:
    raw = (os.getenv("RECRUITER_AUTH_ENABLED") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def session_secret() -> str:
    secret = (os.getenv("RECRUITER_SESSION_SECRET") or "").strip()
    if secret:
        return secret
    # Demo fallback so the app still boots; document that production must set this.
    return "fyp-recruiter-dev-session-secret-change-me"


def expected_username() -> str:
    return (os.getenv("RECRUITER_USERNAME") or "recruiter").strip() or "recruiter"


def expected_password() -> str:
    return os.getenv("RECRUITER_PASSWORD") or ""


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time compare against env credentials (demo-grade, not hashed)."""
    user_ok = hmac.compare_digest(
        (username or "").strip(),
        expected_username(),
    )
    expected = expected_password()
    if not expected:
        # Misconfigured: refuse login when auth is on and password is empty.
        return False
    pass_ok = hmac.compare_digest(password or "", expected)
    return user_ok and pass_ok


def is_logged_in(request: Request) -> bool:
    if not auth_enabled():
        return True
    return bool(request.session.get(SESSION_KEY))


def login_session(request: Request, username: str) -> None:
    request.session[SESSION_KEY] = {
        "username": username.strip() or expected_username(),
    }


def logout_session(request: Request) -> None:
    request.session.pop(SESSION_KEY, None)


def current_username(request: Request) -> str | None:
    data = request.session.get(SESSION_KEY)
    if isinstance(data, dict):
        return data.get("username")
    return None


def require_recruiter(request: Request) -> None:
    """FastAPI dependency: 401 unless session is valid (or auth disabled)."""
    if not auth_enabled():
        return
    if not is_logged_in(request):
        raise HTTPException(status_code=401, detail="Recruiter login required.")


RequireRecruiter = Annotated[None, Depends(require_recruiter)]
