"""
JSON-file invite store for recruiter-created interview links.

File: recruiter_dashboard/data/interviews.json
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STORE_PATH = DATA_DIR / "interviews.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_store() -> dict[str, Any]:
    return {"invites": []}


def _ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        STORE_PATH.write_text(
            json.dumps(_empty_store(), indent=2) + "\n",
            encoding="utf-8",
        )


def _read() -> dict[str, Any]:
    _ensure_store()
    try:
        raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_store()
    if not isinstance(raw, dict) or not isinstance(raw.get("invites"), list):
        return _empty_store()
    return raw


def _write(data: dict[str, Any]) -> None:
    _ensure_store()
    STORE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def list_invites() -> list[dict[str, Any]]:
    with _LOCK:
        invites = list(_read()["invites"])
    invites.sort(key=lambda i: i.get("created_at") or "", reverse=True)
    return invites


def get_invite(token: str) -> dict[str, Any] | None:
    token = (token or "").strip()
    if not token:
        return None
    with _LOCK:
        for inv in _read()["invites"]:
            if inv.get("invite_token") == token:
                return dict(inv)
    return None


def create_invite(
    *,
    target_role: str,
    label: str | None = None,
    candidate_origin: str,
) -> dict[str, Any]:
    token = secrets.token_urlsafe(8)
    origin = candidate_origin.rstrip("/")
    invite = {
        "invite_token": token,
        "target_role": target_role,
        "label": (label or "").strip() or None,
        "status": "pending",
        "created_at": _utc_now(),
        "session_id": None,
        "completed_at": None,
        "candidate_url": f"{origin}/?invite={token}",
    }
    with _LOCK:
        data = _read()
        data["invites"].append(invite)
        _write(data)
    return dict(invite)


def bind_session(token: str, session_id: str) -> dict[str, Any] | None:
    token = (token or "").strip()
    session_id = (session_id or "").strip()
    if not token or not session_id:
        return None
    with _LOCK:
        data = _read()
        for inv in data["invites"]:
            if inv.get("invite_token") == token:
                inv["session_id"] = session_id
                if inv.get("status") == "pending":
                    inv["status"] = "bound"
                _write(data)
                return dict(inv)
    return None


def mark_completed_for_session(session_id: str) -> dict[str, Any] | None:
    """Soft-complete an invite when a matching report appears."""
    session_id = (session_id or "").strip()
    if not session_id:
        return None
    with _LOCK:
        data = _read()
        for inv in data["invites"]:
            if inv.get("session_id") == session_id:
                inv["status"] = "completed"
                if not inv.get("completed_at"):
                    inv["completed_at"] = _utc_now()
                _write(data)
                return dict(inv)
    return None


def find_by_session_id(session_id: str) -> dict[str, Any] | None:
    session_id = (session_id or "").strip()
    if not session_id:
        return None
    with _LOCK:
        for inv in _read()["invites"]:
            if inv.get("session_id") == session_id:
                return dict(inv)
    return None
