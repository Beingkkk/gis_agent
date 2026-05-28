"""Integration test: error recovery scenarios.

Verifies the system recovers gracefully from invalid parameters
and other error conditions.

Design: plan-integration v1.0.0 (T-INT-04)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.models import Session, SessionState
from core.processor import SessionProcessor
from core.registry import TemplateRegistry
from core.validator import ParamValidator
from core.workspace import Workspace
from llm import PromptBuilder
from llm.models import IntentResult, ParamResult
from templates import TemplateEngine, scan_templates


@pytest.fixture
def processor_with_real_templates(
    real_template_dir: Path,
    tmp_path: Path,
    mock_llm_client: MagicMock,
    mock_retriever: MagicMock,
) -> SessionProcessor:
    """SessionProcessor with real templates and mock LLM."""
    workspace = Workspace(tmp_path)
    templates = scan_templates(real_template_dir)
    registry = TemplateRegistry(templates, real_template_dir)
    validator = ParamValidator(workspace)
    engine = TemplateEngine(real_template_dir, workspace)
    prompt_builder = PromptBuilder()

    return SessionProcessor(
        registry=registry,
        validator=validator,
        template_engine=engine,
        llm_client=mock_llm_client,
        prompt_builder=prompt_builder,
        retriever=mock_retriever,
    )


class TestErrorRecovery:
    """Error conditions and recovery paths."""

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_invalid_crs_format_stays_in_collect(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """Invalid CRS like '4326' (missing EPSG:) fails validation."""
        mock_classify.return_value = IntentResult(
            template_id="reproject",
            confidence=0.95,
            reasoning="User wants reprojection",
        )
        # First: invalid CRS
        mock_extract.return_value = ParamResult(
            params={"input": "a.shp", "output": "b.shp", "t_srs": "4326"},
            missing=[],
            questions=[],
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "重投影")
        assert session.state == SessionState.PARAM_COLLECT

        # User provides invalid CRS
        session, response = processor_with_real_templates.process(
            session, "输入 a.shp，输出 b.shp，目标 4326"
        )
        assert session.state == SessionState.PARAM_COLLECT
        assert "EPSG" in response or "格式" in response or "无效" in response

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_missing_required_param_stays_in_collect(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """Missing required 'output' param keeps state in PARAM_COLLECT."""
        mock_classify.return_value = IntentResult(
            template_id="shp2geojson",
            confidence=0.95,
            reasoning="Conversion",
        )
        # Only input provided, output missing
        mock_extract.return_value = ParamResult(
            params={"input": "roads.shp"},
            missing=["output"],
            questions=["请输入输出文件路径（output）："],
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "转成 GeoJSON")
        assert session.state == SessionState.PARAM_COLLECT

        session, response = processor_with_real_templates.process(
            session, "输入 roads.shp"
        )
        assert session.state == SessionState.PARAM_COLLECT
        assert "output" in response or "输出" in response or "缺失" in response

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_correction_after_validation_failure(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """Invalid param → error → corrected param → success."""
        mock_classify.return_value = IntentResult(
            template_id="reproject",
            confidence=0.95,
            reasoning="Reprojection",
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "重投影")
        assert session.state == SessionState.PARAM_COLLECT

        # First attempt: invalid CRS
        mock_extract.return_value = ParamResult(
            params={"input": "a.shp", "output": "b.shp", "t_srs": "bad"},
            missing=[],
            questions=[],
        )
        session, response = processor_with_real_templates.process(
            session, "输入 a.shp，输出 b.shp，目标 bad"
        )
        assert session.state == SessionState.PARAM_COLLECT

        # Second attempt: corrected CRS
        mock_extract.return_value = ParamResult(
            params={"input": "a.shp", "output": "b.shp", "t_srs": "EPSG:4326"},
            missing=[],
            questions=[],
        )
        session, response = processor_with_real_templates.process(
            session, "目标 EPSG:4326"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        assert "EPSG:4326" in response
