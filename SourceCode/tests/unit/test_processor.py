"""Tests for core.processor module.

Design: DC-0040, DC-0043, DC-0044
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.models import ParamDef, Session, SessionState, TemplateDef
from core.processor import SessionProcessor
from core.registry import TemplateRegistry
from core.validator import ParamValidator
from core.workspace import Workspace
from llm.models import IntentResult, ParamResult
from templates.engine import Platform, RenderedScript

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_templates() -> list[TemplateDef]:
    """Template definitions for testing."""
    return [
        TemplateDef(
            id="shp2geojson",
            name="Shapefile 转 GeoJSON",
            description="Convert SHP to GeoJSON",
            template_file="vector/shp2geojson.j2",
            params=[
                ParamDef("input", "file_path", True, "Input SHP path"),
                ParamDef("output", "file_path", True, "Output GeoJSON path"),
                ParamDef("t_srs", "crs", False, "Target CRS", default="EPSG:4326"),
            ],
        ),
        TemplateDef(
            id="clip_raster",
            name="栅格裁剪",
            description="Clip raster",
            template_file="raster/clip_raster.j2",
            params=[
                ParamDef("input", "file_path", True, "Input raster"),
                ParamDef("output", "file_path", True, "Output raster"),
            ],
        ),
    ]


@pytest.fixture
def registry(sample_templates: list[TemplateDef], tmp_path: Path) -> TemplateRegistry:
    """TemplateRegistry backed by temp directory."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "vector").mkdir()
    (template_dir / "raster").mkdir()
    (template_dir / "vector" / "shp2geojson.j2").write_text("echo hello\n")
    (template_dir / "raster" / "clip_raster.j2").write_text("echo world\n")
    return TemplateRegistry(sample_templates, template_dir)


@pytest.fixture
def validator(tmp_path: Path) -> ParamValidator:
    """ParamValidator backed by temp workspace."""
    workspace = Workspace(tmp_path)
    return ParamValidator(workspace)


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock LLMClient."""
    return MagicMock()


@pytest.fixture
def mock_prompt_builder() -> MagicMock:
    """Mock PromptBuilder."""
    return MagicMock()


@pytest.fixture
def mock_template_engine() -> MagicMock:
    """Mock TemplateEngine."""
    return MagicMock()


@pytest.fixture
def processor(
    registry: TemplateRegistry,
    validator: ParamValidator,
    mock_template_engine: MagicMock,
    mock_llm_client: MagicMock,
    mock_prompt_builder: MagicMock,
) -> SessionProcessor:
    """SessionProcessor with mocked LLM and template engine."""
    return SessionProcessor(
        registry=registry,
        validator=validator,
        template_engine=mock_template_engine,
        llm_client=mock_llm_client,
        prompt_builder=mock_prompt_builder,
    )


# ---------------------------------------------------------------------------
# IDLE state: high confidence
# ---------------------------------------------------------------------------


@patch("core.processor.classify_intent")
def test_idle_high_confidence_goes_to_param_collect(
    mock_classify: MagicMock,
    processor: SessionProcessor,
) -> None:
    """High confidence intent classification -> PARAM_COLLECT with template set."""
    mock_classify.return_value = IntentResult(
        template_id="shp2geojson",
        confidence=0.95,
        reasoning="User wants shapefile conversion",
    )

    session = Session()
    new_session, response = processor.process(session, "把 roads.shp 转成 GeoJSON")

    assert new_session.state == SessionState.PARAM_COLLECT
    assert new_session.template is not None
    assert new_session.template.id == "shp2geojson"
    assert "shp2geojson" in response.lower() or "Shapefile" in response
    # Original unchanged
    assert session.state == SessionState.IDLE


# ---------------------------------------------------------------------------
# IDLE state: low confidence
# ---------------------------------------------------------------------------


@patch("core.processor.classify_intent")
def test_idle_low_confidence_goes_to_intent_confirm(
    mock_classify: MagicMock,
    processor: SessionProcessor,
) -> None:
    """Low confidence -> INTENT_CONFIRM with candidate list."""
    mock_classify.return_value = IntentResult(
        template_id="shp2geojson",
        confidence=0.45,
        reasoning="Ambiguous request",
    )

    session = Session()
    new_session, response = processor.process(session, "处理一下文件")

    assert new_session.state == SessionState.INTENT_CONFIRM
    assert len(new_session.candidates) > 0
    assert "shp2geojson" in response or "clip_raster" in response or "选择" in response


# ---------------------------------------------------------------------------
# IDLE state: no match
# ---------------------------------------------------------------------------


@patch("core.processor.classify_intent")
def test_idle_no_match_stays_idle(
    mock_classify: MagicMock,
    processor: SessionProcessor,
) -> None:
    """No matching template -> stays IDLE with helpful message."""
    mock_classify.return_value = IntentResult(
        template_id="",
        confidence=0.0,
        reasoning="No match",
    )

    session = Session()
    new_session, response = processor.process(session, "天气预报怎么样")

    assert new_session.state == SessionState.IDLE
    assert new_session.template is None
    assert "无法" in response or "不知道" in response or "不明白" in response


# ---------------------------------------------------------------------------
# INTENT_CONFIRM state: user selects
# ---------------------------------------------------------------------------


def test_intent_confirm_selection_goes_to_param_collect(
    processor: SessionProcessor,
    registry: TemplateRegistry,
) -> None:
    """User selects a candidate -> PARAM_COLLECT."""
    shp_template = registry.get_template("shp2geojson")
    assert shp_template is not None

    session = Session(
        state=SessionState.INTENT_CONFIRM,
        candidates=registry.list_templates(),
    )
    new_session, response = processor.process(session, "1")

    # candidates are sorted alphabetically: clip_raster (1), shp2geojson (2)
    assert new_session.state == SessionState.PARAM_COLLECT
    assert new_session.template is not None
    assert new_session.template.id == "clip_raster"


# ---------------------------------------------------------------------------
# INTENT_CONFIRM state: user denies
# ---------------------------------------------------------------------------


def test_intent_confirm_deny_goes_to_idle(
    processor: SessionProcessor,
    registry: TemplateRegistry,
) -> None:
    """User denies candidates -> IDLE."""
    session = Session(
        state=SessionState.INTENT_CONFIRM,
        candidates=registry.list_templates(),
    )
    new_session, response = processor.process(session, "都不是")

    assert new_session.state == SessionState.IDLE
    assert new_session.template is None


# ---------------------------------------------------------------------------
# PARAM_COLLECT state: incomplete params
# ---------------------------------------------------------------------------


@patch("core.processor.extract_params")
def test_param_collect_incomplete_stays_collect(
    mock_extract: MagicMock,
    processor: SessionProcessor,
    registry: TemplateRegistry,
) -> None:
    """Missing required params -> stays PARAM_COLLECT, asks questions."""
    mock_extract.return_value = ParamResult(
        params={},
        missing=["input", "output"],
        questions=["请输入输入文件路径", "请输入输出文件路径"],
    )

    shp_template = registry.get_template("shp2geojson")
    assert shp_template is not None

    session = Session(
        state=SessionState.PARAM_COLLECT,
        template=shp_template,
    )
    new_session, response = processor.process(session, " roads.shp")

    assert new_session.state == SessionState.PARAM_COLLECT
    assert "input" in response or "输出" in response or "路径" in response


# ---------------------------------------------------------------------------
# PARAM_COLLECT state: complete params -> SCRIPT_PREVIEW
# ---------------------------------------------------------------------------


@patch("core.processor.extract_params")
def test_param_collect_complete_goes_to_preview(
    mock_extract: MagicMock,
    processor: SessionProcessor,
    registry: TemplateRegistry,
    mock_template_engine: MagicMock,
) -> None:
    """All params collected and valid -> SCRIPT_PREVIEW with script text."""
    mock_extract.return_value = ParamResult(
        params={"input": "roads.shp", "output": "roads.geojson"},
        missing=[],
        questions=[],
    )
    mock_template_engine.render.return_value = RenderedScript(
        content='ogr2ogr -f "GeoJSON" roads.geojson roads.shp',
        command_lines=['ogr2ogr -f "GeoJSON" roads.geojson roads.shp'],
        platform=Platform.WINDOWS,
        output_path="shp2geojson.bat",
    )

    shp_template = registry.get_template("shp2geojson")
    assert shp_template is not None

    session = Session(
        state=SessionState.PARAM_COLLECT,
        template=shp_template,
    )
    new_session, response = processor.process(
        session, "输入 roads.shp，输出 roads.geojson"
    )

    assert new_session.state == SessionState.SCRIPT_PREVIEW
    assert "ogr2ogr" in response
    mock_template_engine.render.assert_called_once()


# ---------------------------------------------------------------------------
# PARAM_COLLECT state: validation failed
# ---------------------------------------------------------------------------


@patch("core.processor.extract_params")
def test_param_collect_validation_failed_stays_collect(
    mock_extract: MagicMock,
    processor: SessionProcessor,
    registry: TemplateRegistry,
) -> None:
    """Invalid param value -> stays PARAM_COLLECT with error message."""
    mock_extract.return_value = ParamResult(
        params={"input": "", "output": "out.geojson"},
        missing=[],
        questions=[],
    )

    shp_template = registry.get_template("shp2geojson")
    assert shp_template is not None

    session = Session(
        state=SessionState.PARAM_COLLECT,
        template=shp_template,
    )
    new_session, response = processor.process(session, "输入空路径")

    assert new_session.state == SessionState.PARAM_COLLECT
    assert "不能为空" in response or "失败" in response


# ---------------------------------------------------------------------------
# SCRIPT_PREVIEW state
# ---------------------------------------------------------------------------


def test_script_preview_returns_script_text(
    processor: SessionProcessor,
    registry: TemplateRegistry,
    mock_template_engine: MagicMock,
) -> None:
    """SCRIPT_PREVIEW returns rendered script text."""
    mock_template_engine.render.return_value = RenderedScript(
        content="echo hello",
        command_lines=["echo hello"],
        platform=Platform.WINDOWS,
        output_path="test.bat",
    )

    shp_template = registry.get_template("shp2geojson")
    assert shp_template is not None

    session = Session(
        state=SessionState.SCRIPT_PREVIEW,
        template=shp_template,
        params={"input": "a.shp", "output": "b.geojson"},
    )
    new_session, response = processor.process(session, "")

    assert new_session.state == SessionState.SCRIPT_PREVIEW
    assert "echo hello" in response


# ---------------------------------------------------------------------------
# Session immutability
# ---------------------------------------------------------------------------


@patch("core.processor.classify_intent")
def test_process_returns_new_session(
    mock_classify: MagicMock,
    processor: SessionProcessor,
) -> None:
    """Each process() call returns a new Session instance."""
    mock_classify.return_value = IntentResult(
        template_id="shp2geojson",
        confidence=0.95,
        reasoning="test",
    )

    original = Session()
    new_session, _ = processor.process(original, "test input")
    assert new_session is not original


# ---------------------------------------------------------------------------
# Invalid state
# ---------------------------------------------------------------------------


def test_invalid_state_raises_value_error(processor: SessionProcessor) -> None:
    """Unknown state raises ValueError."""
    # Create a session with invalid state via object replacement
    bad_session = Session(state=SessionState.EXECUTING)
    with pytest.raises(ValueError):
        processor.process(bad_session, "anything")
