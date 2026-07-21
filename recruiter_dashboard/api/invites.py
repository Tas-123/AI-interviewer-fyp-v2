"""Invite / interview link API."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import invite_store
from services.roles import get_role_meta, list_roles, normalize_role

router = APIRouter(prefix="/api", tags=["interviews"])


def _candidate_origin() -> str:
    return os.getenv("CANDIDATE_ORIGIN", "http://localhost:3000").rstrip("/")


class CreateInterviewBody(BaseModel):
    target_role: str = Field(default="junior_ai_engineer")
    label: str | None = None


class BindSessionBody(BaseModel):
    session_id: str


def _public_invite_payload(invite: dict[str, Any]) -> dict[str, Any]:
    """Candidate-facing resolve payload with role-aware lobby fields."""
    role_meta = get_role_meta(invite.get("target_role"))
    display_title = (
        invite.get("display_title")
        or invite.get("label")
        or role_meta.get("display_title")
    )
    description = invite.get("description") or role_meta.get("description")
    skills = invite.get("suggested_skills") or role_meta.get("suggested_skills") or []
    return {
        "invite_token": invite["invite_token"],
        "target_role": invite["target_role"],
        "label": invite.get("label"),
        "status": invite.get("status"),
        "session_id": invite.get("session_id"),
        "display_title": display_title,
        "description": description,
        "suggested_skills": list(skills),
    }


@router.get("/roles")
def get_roles() -> dict[str, Any]:
    return {"roles": list_roles()}


@router.get("/interviews")
def list_interviews() -> dict[str, Any]:
    return {"invites": invite_store.list_invites()}


@router.post("/interviews")
def create_interview(body: CreateInterviewBody) -> dict[str, Any]:
    target_role = normalize_role(body.target_role)
    role_meta = get_role_meta(target_role)
    display_title = role_meta.get("display_title")
    description = role_meta.get("description")
    suggested_skills = list(role_meta.get("suggested_skills") or [])

    invite = invite_store.create_invite(
        target_role=target_role,
        label=body.label or display_title,
        candidate_origin=_candidate_origin(),
        display_title=display_title,
        description=description,
        suggested_skills=suggested_skills,
    )
    return invite


@router.get("/interviews/{token}")
def get_interview(token: str) -> dict[str, Any]:
    invite = invite_store.get_invite(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Interview invite not found.")
    return _public_invite_payload(invite)


@router.post("/interviews/{token}/bind")
def bind_interview(token: str, body: BindSessionBody) -> dict[str, Any]:
    invite = invite_store.bind_session(token, body.session_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Interview invite not found.")
    return invite
