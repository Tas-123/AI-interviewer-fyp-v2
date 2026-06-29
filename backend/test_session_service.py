"""
test_session_service.py — Unit tests for unified SessionService.
"""

import sys
import os
from unittest.mock import MagicMock, patch

backend_dir = os.path.abspath(os.path.dirname(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault("GROQ_API_KEY", "mock-key")

from core.session_service import SessionService, SessionNotFoundError, reset_session_service


def test_create_and_get_session():
    svc = SessionService()
    with patch("core.session_service.DialogueManager") as dm_cls, patch(
        "core.session_service.db.save_session"
    ):
        mock_dm = MagicMock()
        dm_cls.return_value = mock_dm
        stored = svc.create({"skills": ["Python"]}, session_id="abc-123")
        assert stored.session_id == "abc-123"
        assert svc.has("abc-123")
        assert svc.get_dialogue_manager("abc-123") is mock_dm
    print("[PASS] test_create_and_get_session")


def test_reuse_existing_session():
    svc = SessionService()
    with patch("core.session_service.DialogueManager") as dm_cls, patch(
        "core.session_service.db.save_session"
    ):
        mock_dm = MagicMock()
        dm_cls.return_value = mock_dm
        first = svc.create({"skills": ["Python"]}, session_id="reuse-me")
        second = svc.create({"skills": ["Python"]}, session_id="reuse-me")
        assert first is second
        assert dm_cls.call_count == 1
    print("[PASS] test_reuse_existing_session")


def test_end_session_removes_from_store():
    svc = SessionService()
    with patch("core.session_service.DialogueManager") as dm_cls, patch(
        "core.session_service.db.save_session"
    ):
        mock_dm = MagicMock()
        mock_dm.get_final_report.return_value = {"ok": True}
        dm_cls.return_value = mock_dm
        svc.create({"skills": ["Python"]}, session_id="end-me")
        result = svc.end_session("end-me", remove=True)
        assert result["status"] == "ended"
        assert not svc.has("end-me")
    print("[PASS] test_end_session_removes_from_store")


def test_session_not_found():
    svc = SessionService()
    try:
        svc.get_dialogue_manager("missing")
        assert False, "Expected SessionNotFoundError"
    except SessionNotFoundError:
        pass
    print("[PASS] test_session_not_found")


def test_shared_store_across_adapters():
    """REST and adapter paths see the same session when using singleton."""
    reset_session_service()
    from core.session_service import get_session_service
    from integration.dialogue_adapter import InterviewDialogueAdapter

    with patch("core.session_service.DialogueManager") as dm_cls, patch(
        "core.session_service.db.save_session"
    ):
        mock_dm = MagicMock()
        mock_dm.handle_turn.return_value = {"question": "Hi"}
        mock_dm.get_status.return_value = {"state": "intro", "turn_count": 0}
        dm_cls.return_value = mock_dm

        svc = get_session_service()
        sid, _ = svc.start_interview({"skills": ["ML"]}, session_id="shared-1")
        adapter = InterviewDialogueAdapter()
        assert adapter._sessions.has("shared-1")
        assert svc.has("shared-1")

    reset_session_service()
    print("[PASS] test_shared_store_across_adapters")


if __name__ == "__main__":
    tests = [
        test_create_and_get_session,
        test_reuse_existing_session,
        test_end_session_removes_from_store,
        test_session_not_found,
        test_shared_store_across_adapters,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            print(f"[FAIL] {t.__name__}: {exc}")
            failed += 1
    sys.exit(1 if failed else 0)
