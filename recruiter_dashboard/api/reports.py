"""Read-only Report v2 listing and fetch APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services import invite_store
from services import report_index

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/reports")
def list_reports(include_aborted: bool = True) -> dict[str, Any]:
    cards = report_index.list_report_cards(include_aborted=include_aborted)
    # Soft-complete invites that now have matching reports
    for card in cards:
        sid = card.get("session_id")
        if sid:
            invite_store.mark_completed_for_session(sid)
            invite = invite_store.find_by_session_id(sid)
            if invite:
                card["invite_token"] = invite.get("invite_token")
                card["invite_label"] = invite.get("label")
    return {"reports": cards}


@router.get("/reports/{session_id}")
def get_report(session_id: str) -> dict[str, Any]:
    result = report_index.get_report(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Report not found for session.")
    invite = invite_store.find_by_session_id(session_id)
    if invite:
        invite_store.mark_completed_for_session(session_id)
        result["invite"] = {
            "invite_token": invite.get("invite_token"),
            "label": invite.get("label"),
            "status": invite.get("status"),
        }
    return result


@router.get("/reports/{session_id}/html")
def get_report_html(session_id: str, download: bool = False):
    """
    Serve the sibling HTML assessment.
    - Default: inline (open in browser tab).
    - download=true: Content-Disposition attachment (save locally).
    """
    html_path = report_index.get_html_path(session_id)
    if not html_path:
        raise HTTPException(
            status_code=404,
            detail="HTML report not found for session (may be aborted or missing).",
        )
    # Do not pass filename= unless downloading — Starlette treats filename as attachment.
    if download:
        return FileResponse(
            path=str(html_path),
            media_type="text/html",
            filename=html_path.name,
            content_disposition_type="attachment",
        )
    return FileResponse(
        path=str(html_path),
        media_type="text/html",
        headers={
            "Content-Disposition": f'inline; filename="{html_path.name}"',
        },
    )
