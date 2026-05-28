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
    mock_retriever: MagicMock,
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
        retriever=mock_retriever,
    )


class TestIdleToPreview:
    """Full flow: user describes task → provides params → sees script."""

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_shp2geojson_full_flow(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """Round 1: task description → Round 2: params → script preview."""
        mock_classify.return_value = IntentResult(
            template_id="shp2geojson",
            confidence=0.95,
            reasoning="User wants shapefile conversion",
        )
        mock_extract.return_value = ParamResult(
            params={"input": "roads.shp", "output": "roads.geojson"},
            missing=[],
            questions=[],
        )

        session = Session()

        # Round 1: user describes the task
        session, response = processor_with_real_templates.process(
            session, "把 roads.shp 转成 GeoJSON"
        )
        assert session.state == SessionState.PARAM_COLLECT
        assert session.template is not None
        assert session.template.id == "shp2geojson"

        # Round 2: user provides parameters
        session, response = processor_with_real_templates.process(
            session, "输入 roads.shp，输出 roads.geojson"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        assert "ogr2ogr" in response
        assert "roads.shp" in response
        assert "roads.geojson" in response

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_reproject_full_flow(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """Reproject template: params include t_srs CRS."""
        mock_classify.return_value = IntentResult(
            template_id="reproject",
            confidence=0.92,
            reasoning="User wants reprojection",
        )
        mock_extract.return_value = ParamResult(
            params={
                "input": "data.shp",
                "output": "reprojected.shp",
                "t_srs": "EPSG:4326",
            },
            missing=[],
            questions=[],
        )

        session = Session()

        session, _ = processor_with_real_templates.process(
            session, "把 data.shp 重投影到 4326"
        )
        assert session.state == SessionState.PARAM_COLLECT
        assert session.template is not None
        assert session.template.id == "reproject"

        session, response = processor_with_real_templates.process(
            session, "输入 data.shp，输出 reprojected.shp，目标 4326"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        assert "ogr2ogr" in response
        assert "EPSG:4326" in response

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_warp_reproject_raster_flow(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """Raster reprojection using gdalwarp."""
        mock_classify.return_value = IntentResult(
            template_id="warp_reproject",
            confidence=0.9,
            reasoning="User wants raster reprojection",
        )
        mock_extract.return_value = ParamResult(
            params={
                "input": "dem.tif",
                "output": "dem_4326.tif",
                "t_srs": "EPSG:4326",
            },
            missing=[],
            questions=[],
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "把 dem.tif 重投影")
        assert session.state == SessionState.PARAM_COLLECT

        session, response = processor_with_real_templates.process(
            session, "输入 dem.tif，输出 dem_4326.tif，目标 4326"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        assert "gdalwarp" in response
        assert "dem.tif" in response

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_optional_params_omitted(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """shp2geojson without optional t_srs/s_srs still renders."""
        mock_classify.return_value = IntentResult(
            template_id="shp2geojson",
            confidence=0.95,
            reasoning="User wants conversion",
        )
        mock_extract.return_value = ParamResult(
            params={"input": "roads.shp", "output": "roads.geojson"},
            missing=[],
            questions=[],
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "转成 GeoJSON")
        assert session.state == SessionState.PARAM_COLLECT

        session, response = processor_with_real_templates.process(
            session, "roads.shp roads.geojson"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        # t_srs is optional, should not appear when not provided
        # (the Jinja2 template uses {% if t_srs %})
        rendered_text = response
        assert "roads.shp" in rendered_text
        assert "roads.geojson" in rendered_text
