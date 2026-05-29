"""Tests for api.dependencies module.

Design:
    T-UX-01 (DC-UX-03)
"""



from api.dependencies import SessionManager, get_session_manager
from core.models import Session, SessionState


class TestSessionManager:
    """Tests for SessionManager class."""

    def test_create_session_returns_id_and_session(self) -> None:
        sm = SessionManager()
        session_id, session = sm.create_session()
        assert isinstance(session_id, str)
        assert len(session_id) > 0
        assert isinstance(session, Session)
        assert session.state == SessionState.IDLE

    def test_create_session_unique_ids(self) -> None:
        sm = SessionManager()
        id1, _ = sm.create_session()
        id2, _ = sm.create_session()
        assert id1 != id2

    def test_create_session_stores_session(self) -> None:
        sm = SessionManager()
        session_id, session = sm.create_session()
        found = sm.get_session(session_id)
        assert found is not None
        assert found.state == session.state

    def test_get_session_found(self) -> None:
        sm = SessionManager()
        session_id, _ = sm.create_session()
        found = sm.get_session(session_id)
        assert found is not None

    def test_get_session_not_found(self) -> None:
        sm = SessionManager()
        found = sm.get_session("nonexistent-id")
        assert found is None

    def test_update_session(self) -> None:
        sm = SessionManager()
        session_id, session = sm.create_session()
        new_session = session.with_state(SessionState.PARAM_COLLECT)
        sm.update_session(session_id, new_session)
        found = sm.get_session(session_id)
        assert found is not None
        assert found.state == SessionState.PARAM_COLLECT

    def test_update_session_not_found(self) -> None:
        sm = SessionManager()
        # Should not raise for non-existent session
        sm.update_session("nonexistent", Session())
        assert sm.get_session("nonexistent") is not None

    def test_clear_session(self) -> None:
        sm = SessionManager()
        session_id, session = sm.create_session()
        sm.update_session(session_id, session.with_state(SessionState.SCRIPT_PREVIEW))
        sm.clear_session(session_id)
        found = sm.get_session(session_id)
        assert found is not None
        assert found.state == SessionState.IDLE
        assert found.template is None
        assert found.params == {}

    def test_clear_session_not_found(self) -> None:
        sm = SessionManager()
        # Should not raise for non-existent session
        sm.clear_session("nonexistent")


class TestGetSessionManager:
    """Tests for get_session_manager() dependency function."""

    def test_returns_singleton(self) -> None:
        sm1 = get_session_manager()
        sm2 = get_session_manager()
        assert sm1 is sm2
        assert isinstance(sm1, SessionManager)

    def test_singleton_isolated(self) -> None:
        # get_session_manager should return the same instance across calls
        sm1 = get_session_manager()
        session_id, _ = sm1.create_session()
        sm2 = get_session_manager()
        assert sm2.get_session(session_id) is not None
