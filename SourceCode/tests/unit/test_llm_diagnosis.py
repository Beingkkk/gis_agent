"""Tests for llm.diagnosis module.

Design: DC-0036
"""

from unittest.mock import MagicMock, patch

import pytest

from llm.diagnosis import _fallback_diagnosis, _filter_fixed_params, _parse_diagnosis_response
from llm.models import ErrorDiagnosis


# ---------------------------------------------------------------------------
# _parse_diagnosis_response
# ---------------------------------------------------------------------------


def test_parse_diagnosis_response_valid_json() -> None:
    """Valid JSON response is parsed into ErrorDiagnosis."""
    response = (
        '{"cause": "文件不存在", '
        '"suggestion": "检查路径", '
        '"fixed_params": {"input": "/a/b.shp"}, '
        '"confidence": 0.85, '
        '"can_auto_fix": true}'
    )
    result = _parse_diagnosis_response(response)

    assert isinstance(result, ErrorDiagnosis)
    assert result.cause == "文件不存在"
    assert result.suggestion == "检查路径"
    assert result.fixed_params == {"input": "/a/b.shp"}
    assert result.confidence == 0.85
    assert result.can_auto_fix is True


def test_parse_diagnosis_response_with_markdown_code_block() -> None:
    """Markdown code block wrapper is stripped before parsing."""
    response = (
        '```json\n'
        '{"cause": "CRS错误", '
        '"suggestion": "修正坐标系", '
        '"fixed_params": {}, '
        '"confidence": 0.7, '
        '"can_auto_fix": false}\n'
        '```'
    )
    result = _parse_diagnosis_response(response)

    assert result.cause == "CRS错误"
    assert result.can_auto_fix is False


def test_parse_diagnosis_response_invalid_json_fallback() -> None:
    """Invalid JSON falls back to conservative diagnosis."""
    result = _parse_diagnosis_response("not json at all")

    assert result.can_auto_fix is False
    assert result.confidence == 0.0
    assert "诊断失败" in result.cause


def test_parse_diagnosis_response_missing_field_fallback() -> None:
    """Missing required field falls back to conservative diagnosis."""
    response = '{"cause": "ok", "suggestion": "ok"}'  # missing fixed_params, confidence, can_auto_fix
    result = _parse_diagnosis_response(response)

    assert result.can_auto_fix is False
    assert result.confidence == 0.0


def test_parse_diagnosis_response_low_confidence_forces_false() -> None:
    """confidence < 0.5 forces can_auto_fix to False."""
    response = (
        '{"cause": "x", "suggestion": "y", '
        '"fixed_params": {}, "confidence": 0.3, "can_auto_fix": true}'
    )
    result = _parse_diagnosis_response(response)

    assert result.confidence == 0.3
    assert result.can_auto_fix is False


# ---------------------------------------------------------------------------
# _filter_fixed_params
# ---------------------------------------------------------------------------


def test_filter_fixed_params_keeps_string_pairs() -> None:
    """String key-value pairs are preserved."""
    raw = {"input": "/a.shp", "output": "/b.geojson"}
    result = _filter_fixed_params(raw)
    assert result == raw


def test_filter_fixed_params_converts_non_string_values() -> None:
    """Non-string values are converted to string."""
    raw = {"epsg": 4326, "flag": True}
    result = _filter_fixed_params(raw)
    assert result == {"epsg": "4326", "flag": "True"}


def test_filter_fixed_params_filters_non_string_keys() -> None:
    """Non-string keys are dropped."""
    raw = {"valid": "ok", 123: "bad"}
    result = _filter_fixed_params(raw)
    assert result == {"valid": "ok"}


# ---------------------------------------------------------------------------
# _fallback_diagnosis
# ---------------------------------------------------------------------------


def test_fallback_diagnosis_is_conservative() -> None:
    """Fallback diagnosis is conservative (can_auto_fix=False)."""
    result = _fallback_diagnosis()

    assert result.can_auto_fix is False
    assert result.confidence == 0.0
    assert result.fixed_params == {}
    assert "诊断失败" in result.cause


# ---------------------------------------------------------------------------
# analyze_execution_error (integration with mocked LLM)
# ---------------------------------------------------------------------------


@patch("llm.diagnosis._parse_diagnosis_response")
def test_analyze_execution_error_calls_llm_and_parses(
    mock_parse: MagicMock,
) -> None:
    """analyze_execution_error calls LLM and parses the response."""
    mock_client = MagicMock()
    mock_client.chat.return_value = '{"cause": "test"}'

    mock_builder = MagicMock()
    mock_builder.build_system_prompt.return_value = "system prompt"

    mock_parse.return_value = ErrorDiagnosis(
        cause="test cause",
        suggestion="test suggestion",
        fixed_params={},
        confidence=0.5,
        can_auto_fix=False,
    )

    from llm.diagnosis import analyze_execution_error
    from llm.models import Message

    result = analyze_execution_error(
        returncode=1,
        stdout="",
        stderr="error",
        diagnosis_context="template info",
        history=[Message(role="user", content="hello")],
        client=mock_client,
        builder=mock_builder,
    )

    assert result.cause == "test cause"
    mock_client.chat.assert_called_once()
    mock_parse.assert_called_once()


@patch("llm.diagnosis._fallback_diagnosis")
def test_analyze_execution_error_fallback_on_llm_failure(
    mock_fallback: MagicMock,
) -> None:
    """LLM call failure triggers fallback diagnosis."""
    mock_client = MagicMock()
    mock_client.chat.side_effect = Exception("network error")

    mock_builder = MagicMock()
    mock_builder.build_system_prompt.return_value = "system prompt"

    mock_fallback.return_value = ErrorDiagnosis(
        cause="fallback",
        suggestion="fallback suggestion",
        fixed_params={},
        confidence=0.0,
        can_auto_fix=False,
    )

    from llm.diagnosis import analyze_execution_error
    from llm.models import Message

    result = analyze_execution_error(
        returncode=1,
        stdout="",
        stderr="error",
        diagnosis_context="template info",
        history=[],
        client=mock_client,
        builder=mock_builder,
    )

    assert result.cause == "fallback"
    mock_fallback.assert_called_once()
