"""Tests for core session data models.

Design: DC-0040, DC-0043
"""

import pytest

from core.models import ParamDef, Session, SessionState, TemplateDef

# ---------------------------------------------------------------------------
# SessionState Enum
# ---------------------------------------------------------------------------


def test_session_state_enum_values() -> None:
    """SessionState has exactly the 5 defined states."""
    assert SessionState.IDLE.name == "IDLE"
    assert SessionState.INTENT_CONFIRM.name == "INTENT_CONFIRM"
    assert SessionState.PARAM_COLLECT.name == "PARAM_COLLECT"
    assert SessionState.SCRIPT_PREVIEW.name == "SCRIPT_PREVIEW"
    assert SessionState.EXECUTING.name == "EXECUTING"

    # Verify all members are auto-generated unique values
    values = {s.value for s in SessionState}
    assert len(values) == 5


# ---------------------------------------------------------------------------
# Session defaults
# ---------------------------------------------------------------------------


def test_session_defaults() -> None:
    """Default Session starts in IDLE with empty collections."""
    session = Session()
    assert session.state == SessionState.IDLE
    assert session.history == []
    assert session.template is None
    assert session.params == {}
    assert session.candidates == []


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_session_immutable() -> None:
    """Session is frozen; direct attribute mutation raises."""
    session = Session()
    with pytest.raises(AttributeError):
        session.state = SessionState.PARAM_COLLECT  # type: ignore[misc]


# ---------------------------------------------------------------------------
# with_state
# ---------------------------------------------------------------------------


def test_with_state_returns_new_instance() -> None:
    """with_state returns a new Session; original is unchanged."""
    original = Session()
    new_session = original.with_state(SessionState.PARAM_COLLECT)

    assert original.state == SessionState.IDLE
    assert new_session.state == SessionState.PARAM_COLLECT
    assert new_session is not original


# ---------------------------------------------------------------------------
# with_template
# ---------------------------------------------------------------------------


def test_with_template() -> None:
    """with_template sets template on a new instance."""
    original = Session()
    template = TemplateDef(
        id="shp2geojson",
        name="Shapefile 转 GeoJSON",
        description="Convert",
        template_file="vector/shp2geojson.j2",
        params=[ParamDef("input", "file_path", True, "Input path")],
    )
    new_session = original.with_template(template)

    assert original.template is None
    assert new_session.template == template
    assert new_session is not original


# ---------------------------------------------------------------------------
# with_param
# ---------------------------------------------------------------------------


def test_with_param() -> None:
    """with_param adds a key-value to params dict."""
    session = Session()
    new_session = session.with_param("input", "roads.shp")

    assert session.params == {}
    assert new_session.params == {"input": "roads.shp"}
    assert new_session is not session


def test_with_param_accumulates() -> None:
    """Multiple with_param calls accumulate parameters."""
    s1 = Session().with_param("input", "a.shp")
    s2 = s1.with_param("output", "b.geojson")

    assert s2.params == {"input": "a.shp", "output": "b.geojson"}
    assert s1.params == {"input": "a.shp"}  # s1 unchanged


# ---------------------------------------------------------------------------
# with_history
# ---------------------------------------------------------------------------


def test_with_history() -> None:
    """with_history appends a message to the history list."""
    from llm.models import Message

    session = Session()
    msg = Message(role="user", content="hello")
    new_session = session.with_history(msg)

    assert session.history == []
    assert new_session.history == [msg]
    assert new_session is not session


def test_with_history_accumulates() -> None:
    """Multiple with_history calls accumulate messages."""
    from llm.models import Message

    m1 = Message(role="user", content="hi")
    m2 = Message(role="assistant", content="hello")
    s1 = Session().with_history(m1)
    s2 = s1.with_history(m2)

    assert s2.history == [m1, m2]
    assert s1.history == [m1]


# ---------------------------------------------------------------------------
# Chained updates preserve unrelated fields
# ---------------------------------------------------------------------------


def test_with_param_preserves_other_fields() -> None:
    """Updating params does not affect state, template, etc."""
    template = TemplateDef(
        id="t1",
        name="Test",
        description="D",
        template_file="t.j2",
    )
    original = Session(
        state=SessionState.PARAM_COLLECT,
        template=template,
    )
    new_session = original.with_param("key", "value")

    assert new_session.state == SessionState.PARAM_COLLECT
    assert new_session.template == template
    assert new_session.params == {"key": "value"}
    # Original unchanged
    assert original.params == {}
