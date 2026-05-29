"""Integration test: IDLE to SCRIPT_PREVIEW flow.

Simulates a complete user conversation: task description → parameter
collection → script preview, using real template files and real
parameter validation.

Design: plan-integration v1.0.0 (T-INT-02)
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
    """SessionProcessor wired with real templates and mock LLM."""
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


class TestIdleToPreview:
    """Full flow: user describes task → provides params → sees script."""

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_gdal_mdim_convert_full_flow(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """Round 1: task description → Round 2: params → script preview."""
        mock_classify.return_value = IntentResult(
            template_id="gdal_mdim_convert",
            confidence=0.95,
            reasoning="User wants multidimensional conversion",
        )
        mock_extract.return_value = ParamResult(
            params={"input": "input.nc", "output": "output.zarr"},
            missing=[],
            questions=[],
        )

        session = Session()

        # Round 1: user describes the task
        session, response = processor_with_real_templates.process(
            session, "把 NetCDF 转成 ZARR"
        )
        assert session.state == SessionState.PARAM_COLLECT
        assert session.template is not None
        assert session.template.id == "gdal_mdim_convert"

        # Round 2: user provides parameters
        session, response = processor_with_real_templates.process(
            session, "输入 input.nc，输出 output.zarr"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        assert "gdal" in response
        assert "input.nc" in response
        assert "output.zarr" in response

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_gdal_raster_as_features_full_flow(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """gdal raster as features: params include optional of format."""
        mock_classify.return_value = IntentResult(
            template_id="gdal_raster_as_features",
            confidence=0.92,
            reasoning="User wants raster to vector conversion",
        )
        mock_extract.return_value = ParamResult(
            params={
                "input": "dem.tif",
                "output": "dem.geojson",
                "of": "GeoJSON",
            },
            missing=[],
            questions=[],
        )

        session = Session()

        session, _ = processor_with_real_templates.process(
            session, "把 dem.tif 转成矢量"
        )
        assert session.state == SessionState.PARAM_COLLECT
        assert session.template is not None
        assert session.template.id == "gdal_raster_as_features"

        session, response = processor_with_real_templates.process(
            session, "输入 dem.tif，输出 dem.geojson，格式 GeoJSON"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        assert "gdal" in response
        assert "dem.tif" in response

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_gdal2xyz_raster_flow(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """Raster to XYZ conversion using gdal2xyz."""
        mock_classify.return_value = IntentResult(
            template_id="gdal2xyz",
            confidence=0.9,
            reasoning="User wants raster to XYZ conversion",
        )
        mock_extract.return_value = ParamResult(
            params={
                "src_dataset": "dem.tif",
                "dst_dataset": "dem.xyz",
                "band": "1",
            },
            missing=[],
            questions=[],
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "把 dem.tif 转成 XYZ")
        assert session.state == SessionState.PARAM_COLLECT

        session, response = processor_with_real_templates.process(
            session, "输入 dem.tif，输出 dem.xyz，波段 1"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        assert "gdal" in response
        assert "dem.tif" in response

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_optional_params_omitted(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """gdal_mdim_convert without optional of still renders."""
        mock_classify.return_value = IntentResult(
            template_id="gdal_mdim_convert",
            confidence=0.95,
            reasoning="User wants conversion",
        )
        mock_extract.return_value = ParamResult(
            params={"input": "input.nc", "output": "output.zarr"},
            missing=[],
            questions=[],
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "转成 ZARR")
        assert session.state == SessionState.PARAM_COLLECT

        session, response = processor_with_real_templates.process(
            session, "input.nc output.zarr"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        # of is optional, should not appear when not provided
        rendered_text = response
        assert "input.nc" in rendered_text
        assert "output.zarr" in rendered_text
