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
    )


class TestErrorRecovery:
    """Error conditions and recovery paths."""

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
            template_id="gdal_mdim_convert",
            confidence=0.95,
            reasoning="Conversion",
        )
        # Only input provided, output missing
        mock_extract.return_value = ParamResult(
            params={"input": "input.nc"},
            missing=["output"],
            questions=["请输入输出文件路径（output）："],
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "转换多维数据")
        assert session.state == SessionState.PARAM_COLLECT

        session, response = processor_with_real_templates.process(
            session, "输入 input.nc"
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
            template_id="gdal_mdim_convert",
            confidence=0.95,
            reasoning="Conversion",
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "转换多维数据")
        assert session.state == SessionState.PARAM_COLLECT

        # First attempt: output path has invalid characters (pipe)
        mock_extract.return_value = ParamResult(
            params={"input": "input.nc", "output": "out|put.zarr"},
            missing=[],
            questions=[],
        )
        session, response = processor_with_real_templates.process(
            session, "输入 input.nc，输出 out|put.zarr"
        )
        assert session.state == SessionState.PARAM_COLLECT

        # Second attempt: corrected path
        mock_extract.return_value = ParamResult(
            params={"input": "input.nc", "output": "output.zarr"},
            missing=[],
            questions=[],
        )
        session, response = processor_with_real_templates.process(
            session, "输出 output.zarr"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        assert "output.zarr" in response
