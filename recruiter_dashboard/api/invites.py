"""Invite / interview link API + optional invitation email."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import email_service
from services import invite_store
from services.auth import require_recruiter
from services.roles import get_role_meta, list_roles, normalize_role

router = APIRouter(prefix="/api", tags=["interviews"])


def _candidate_origin() -> str:
    return os.getenv("CANDIDATE_ORIGIN", "http://localhost:3000").rstrip("/")


class CreateInterviewBody(BaseModel):
    target_role: str = Field(default="junior_ai_engineer")
    label: str | None = None
    candidate_email: str | None = None
    candidate_name: str | None = None


class BindSessionBody(BaseModel):
    session_id: str


class SendInviteBody(BaseModel):
    candidate_email: str | None = None
    candidate_name: str | None = None


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


@router.get("/email/status")
def get_email_status(_auth: None = Depends(require_recruiter)) -> dict[str, Any]:
    return email_service.email_status()


@router.get("/roles")
def get_roles(_auth: None = Depends(require_recruiter)) -> dict[str, Any]:
    """Role dropdown for the dashboard (protected). Candidate gets role via invite resolve."""
    return {"roles": list_roles()}


@router.get("/interviews")
def list_interviews(_auth: None = Depends(require_recruiter)) -> dict[str, Any]:
    return {"invites": invite_store.list_invites()}


@router.post("/interviews")
def create_interview(
    body: CreateInterviewBody,
    _auth: None = Depends(require_recruiter),
) -> dict[str, Any]:
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
        candidate_email=body.candidate_email,
        candidate_name=body.candidate_name,
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


@router.post("/interviews/{token}/send")
def send_invitation(
    token: str,
    body: SendInviteBody | None = None,
    _auth: None = Depends(require_recruiter),
) -> dict[str, Any]:
    """Send optional invitation email (SMTP). Copy-link path never depends on this."""
    invite = invite_store.get_invite(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Interview invite not found.")

    body = body or SendInviteBody()
    if body.candidate_email is not None or body.candidate_name is not None:
        updated = invite_store.update_invite_contact(
            token,
            candidate_email=body.candidate_email
            if body.candidate_email is not None
            else invite.get("candidate_email"),
            candidate_name=body.candidate_name
            if body.candidate_name is not None
            else invite.get("candidate_name"),
        )
        if updated:
            invite = updated

    to_addr = (invite.get("candidate_email") or "").strip()
    if body.candidate_email:
        to_addr = body.candidate_email.strip()

    if not to_addr:
        raise HTTPException(
            status_code=400,
            detail="Candidate email is required to send an invitation.",
        )
    if not email_service.smtp_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "SMTP is not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, "
                "and EMAIL_FROM — or use Copy link instead."
            ),
        )

    # Ensure name override applied for template
    if body.candidate_name:
        invite = dict(invite)
        invite["candidate_name"] = body.candidate_name.strip()

    try:
        result = email_service.send_invite_email(invite, to_override=to_addr)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    invite_store.mark_email_sent(token)
    refreshed = invite_store.get_invite(token) or invite
    return {
        "ok": True,
        "to": result["to"],
        "subject": result["subject"],
        "email_sent_at": refreshed.get("email_sent_at"),
        "invite_token": token,
    }
