"""Integration test fixtures.

Provides real template directory access and mock LLM
for cross-module integration testing.

Design: plan-integration v1.0.0 (DC-0070, DC-0071)
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from core.workspace import Workspace
from llm.models import IntentResult, Message, ParamResult


@pytest.fixture(scope="session")
def real_template_dir() -> Path:
    """Return the actual template directory used in production.

    Assumes tests run from SourceCode/ directory.
    """
    return Path(__file__).parent.parent.parent / "data" / "templates"


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """Fresh workspace for each test."""
    return Workspace(tmp_path)


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """LLMClient whose chat() returns empty JSON by default.

    Tests should set side_effect or return_value to control behavior.
    """
    client = MagicMock()
    client.chat.return_value = "{}"
    return client


@pytest.fixture
def make_intent_result() -> Any:
    """Factory for IntentResult objects."""

    def _factory(
        template_id: str, confidence: float, reasoning: str = ""
    ) -> IntentResult:
        return IntentResult(
            template_id=template_id,
            confidence=confidence,
            reasoning=reasoning,
        )

    return _factory


@pytest.fixture
def make_param_result() -> Any:
    """Factory for ParamResult objects."""

    def _factory(
        params: dict[str, str],
        missing: list[str],
        questions: list[str],
    ) -> ParamResult:
        return ParamResult(
            params=params,
            missing=missing,
            questions=questions,
        )

    return _factory


@pytest.fixture
def mock_messages() -> list[Message]:
    """Empty message history for tests."""
    return []
