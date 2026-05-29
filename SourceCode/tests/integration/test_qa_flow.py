"""Integration test: Q&A flow.

Verifies that user questions are routed through template knowledge
+ answer_question, returning to IDLE state.

Design: plan-integration v1.0.0 (T-INT-03), ADR-0001
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.models import Session, SessionState
from core.processor import SessionProcessor
from core.registry import TemplateRegistry
from core.validator import ParamValidator
from core.workspace import Workspace
from llm import PromptBuilder
from llm.models import IntentResult
from templates import TemplateEngine, scan_templates


@patch("core.processor.classify_intent")
@patch("llm.qa.answer_question")
def test_qa_route_returns_answer(
    mock_answer: MagicMock,
    mock_classify: MagicMock,
    real_template_dir: Path,
    tmp_path: Path,
    mock_llm_client: MagicMock,
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

    workspace = Workspace(tmp_path)
    templates = scan_templates(real_template_dir)
    registry = TemplateRegistry(templates, real_template_dir)
    validator = ParamValidator(workspace)
    engine = TemplateEngine(real_template_dir, workspace)
    prompt_builder = PromptBuilder()

    processor = SessionProcessor(
        registry=registry,
        validator=validator,
        template_engine=engine,
        llm_client=mock_llm_client,
        prompt_builder=prompt_builder,
    )

    session = Session()
    new_session, response = processor.process(session, "shp格式是什么")

    assert new_session.state == SessionState.IDLE
    assert "SHP" in response or "Shapefile" in response
    mock_answer.assert_called_once()
