"""Invite / interview link API."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import invite_store
from services.roles import list_roles, normalize_role

router = APIRouter(prefix="/api", tags=["interviews"])


def _candidate_origin() -> str:
    return os.getenv("CANDIDATE_ORIGIN", "http://localhost:3000").rstrip("/")


class CreateInterviewBody(BaseModel):
    target_role: str = Field(default="junior_ai_engineer")
    label: str | None = None


class BindSessionBody(BaseModel):
    session_id: str


@router.get("/roles")
def get_roles() -> dict[str, Any]:
    return {"roles": list_roles()}


@router.get("/interviews")
def list_interviews() -> dict[str, Any]:
    return {"invites": invite_store.list_invites()}


@router.post("/interviews")
def create_interview(body: CreateInterviewBody) -> dict[str, Any]:
    role = normalize_role(body.target_role)
    invite = invite_store.create_invite(
        target_role=role,
        label=body.label,
        candidate_origin=_candidate_origin(),
    )
    return invite


@router.get("/interviews/{token}")
def get_interview(token: str) -> dict[str, Any]:
    invite = invite_store.get_invite(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Interview invite not found.")
    # Public resolve payload for the Candidate client
    return {
        "invite_token": invite["invite_token"],
        "target_role": invite["target_role"],
        "label": invite.get("label"),
        "status": invite.get("status"),
        "session_id": invite.get("session_id"),
    }


@router.post("/interviews/{token}/bind")
def bind_interview(token: str, body: BindSessionBody) -> dict[str, Any]:
    invite = invite_store.bind_session(token, body.session_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Interview invite not found.")
    return invite
