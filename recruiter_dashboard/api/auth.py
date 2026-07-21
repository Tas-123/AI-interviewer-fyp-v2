"""Recruiter login / logout / me endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(default="")
    password: str = Field(default="")


@router.post("/login")
def login(body: LoginBody, request: Request) -> dict[str, Any]:
    if not auth_service.auth_enabled():
        auth_service.login_session(request, auth_service.expected_username())
        return {
            "ok": True,
            "username": auth_service.expected_username(),
            "auth_enabled": False,
        }
    if not auth_service.verify_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    auth_service.login_session(request, body.username)
    return {
        "ok": True,
        "username": auth_service.current_username(request),
        "auth_enabled": True,
    }


@router.post("/logout")
def logout(request: Request) -> dict[str, Any]:
    auth_service.logout_session(request)
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict[str, Any]:
    enabled = auth_service.auth_enabled()
    logged_in = auth_service.is_logged_in(request)
    return {
        "auth_enabled": enabled,
        "authenticated": logged_in,
        "username": auth_service.current_username(request) if logged_in else None,
    }
