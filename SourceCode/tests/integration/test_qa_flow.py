"""Integration test: Q&A flow.

Verifies that user questions are routed through template knowledge
+ answer_question, returning to IDLE state.

【已废弃，代码保留】SessionProcessor 仅用于 CLI 层，不再维护。
参见 constitution.md §6.1、CLAUDE.md Key Files 表。
Design: plan-integration v1.0.0 (T-INT-03), ADR-0001
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.models import Session, SessionState
from core.processor import SessionProcessor
from llm.models import IntentResult


@patch("core.processor.classify_intent")
@patch("llm.qa.answer_question")
def test_qa_route_returns_answer(
    mock_answer: MagicMock,
    mock_classify: MagicMock,
    processor_with_real_templates: SessionProcessor,
) -> None:
    """User asks about SHP format → template matching → answer returned."""
    mock_classify.return_value = IntentResult(
        template_id="__qa__",
        confidence=0.88,
        reasoning="User is asking about a format",
    )
    mock_answer.return_value = (
        "SHP（Shapefile）是 ESRI 开发的矢量数据格式，由 .shp、.shx、.dbf 三个文件组成。"
    )

    session = Session()
    new_session, response = processor_with_real_templates.process(session, "shp格式是什么")

    assert new_session.state == SessionState.IDLE
    assert "SHP" in response or "Shapefile" in response
    mock_answer.assert_called_once()
