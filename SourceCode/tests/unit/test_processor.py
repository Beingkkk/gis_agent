"""Tests for core.processor module.

Design: DC-0040, DC-0043, DC-0044
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.models import (
    ExecutionErrorContext,
    ParamDef,
    Session,
    SessionState,
    TemplateDef,
)
from core.processor import SessionProcessor
from core.registry import TemplateRegistry
from core.validator import ParamValidator
from core.workspace import Workspace
from llm.models import ErrorDiagnosis, IntentResult, ParamResult
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
# IDLE state: empty input
# ---------------------------------------------------------------------------


def test_idle_empty_input_returns_hint(processor: SessionProcessor) -> None:
    """Empty or whitespace-only input stays IDLE with a hint."""
    session = Session()
    new_session, response = processor.process(session, "")

    assert new_session.state == SessionState.IDLE
    assert new_session is session  # no mutation
    assert "请输入" in response or "help" in response.lower()


def test_idle_whitespace_input_returns_hint(processor: SessionProcessor) -> None:
    """Whitespace-only input stays IDLE with a hint."""
    session = Session()
    new_session, response = processor.process(session, "   \n\t  ")

    assert new_session.state == SessionState.IDLE
    assert new_session is session
    assert "请输入" in response or "help" in response.lower()


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
    assert "Shapefile" in response or "裁剪" in response or "重新描述" in response


# ---------------------------------------------------------------------------
# IDLE state: no match
# ---------------------------------------------------------------------------


@patch("core.processor.classify_intent")
def test_idle_no_match_goes_to_intent_confirm(
    mock_classify: MagicMock,
    processor: SessionProcessor,
) -> None:
    """Empty template_id -> INTENT_CONFIRM with candidate list and friendly message."""
    mock_classify.return_value = IntentResult(
        template_id="",
        confidence=0.0,
        reasoning="No match",
    )

    session = Session()
    new_session, response = processor.process(session, "天气预报怎么样")

    assert new_session.state == SessionState.INTENT_CONFIRM
    assert new_session.template is None
    assert len(new_session.candidates) > 0
    assert "暂没有完全匹配的模板" in response
    assert "天气预报怎么样" in response


# ---------------------------------------------------------------------------
# IDLE state: Q&A route
# ---------------------------------------------------------------------------


@patch("core.processor.classify_intent")
@patch("core.processor.extract_keywords")
@patch("core.processor.answer_question")
def test_idle_qa_route_returns_answer(
    mock_answer: MagicMock,
    mock_extract_keywords: MagicMock,
    mock_classify: MagicMock,
    registry: TemplateRegistry,
    validator: ParamValidator,
    mock_template_engine: MagicMock,
    mock_llm_client: MagicMock,
    mock_prompt_builder: MagicMock,
) -> None:
    """LLM routes to __qa__ -> keywords -> multi-search -> answer -> IDLE."""
    mock_classify.return_value = IntentResult(
        template_id="__qa__",
        confidence=0.9,
        reasoning="User is asking about SHP format",
    )
    mock_extract_keywords.return_value = ["Shapefile format", "SHP GDAL"]
    mock_answer.return_value = "SHP 是 Shapefile 格式，由 ESRI 开发..."

    mock_retriever = MagicMock()
    mock_retriever.search_multi.return_value = []

    processor = SessionProcessor(
        registry=registry,
        validator=validator,
        template_engine=mock_template_engine,
        llm_client=mock_llm_client,
        prompt_builder=mock_prompt_builder,
        retriever=mock_retriever,
    )

    session = Session()
    new_session, response = processor.process(session, "shp格式是什么")

    assert new_session.state == SessionState.IDLE
    assert "SHP" in response
    mock_extract_keywords.assert_called_once()
    mock_retriever.search_multi.assert_called_once_with(
        ["Shapefile format", "SHP GDAL"], top_k_per_query=2
    )
    mock_answer.assert_called_once()


@patch("core.processor.classify_intent")
def test_idle_qa_route_no_retriever_returns_error(
    mock_classify: MagicMock,
    processor: SessionProcessor,
) -> None:
    """LLM routes to __qa__ but retriever is None -> error message."""
    mock_classify.return_value = IntentResult(
        template_id="__qa__",
        confidence=0.9,
        reasoning="User is asking a question",
    )

    session = Session()
    new_session, response = processor.process(session, "geojson是什么")

    assert new_session.state == SessionState.IDLE
    assert "不可用" in response


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


def test_intent_confirm_template_name_selects(
    processor: SessionProcessor,
    registry: TemplateRegistry,
) -> None:
    """User types template name directly -> PARAM_COLLECT."""
    session = Session(
        state=SessionState.INTENT_CONFIRM,
        candidates=registry.list_templates(),
    )
    new_session, response = processor.process(session, "Shapefile 转 GeoJSON")

    assert new_session.state == SessionState.PARAM_COLLECT
    assert new_session.template is not None
    assert new_session.template.id == "shp2geojson"


def test_intent_confirm_template_id_selects(
    processor: SessionProcessor,
    registry: TemplateRegistry,
) -> None:
    """User types template ID directly -> PARAM_COLLECT."""
    session = Session(
        state=SessionState.INTENT_CONFIRM,
        candidates=registry.list_templates(),
    )
    new_session, response = processor.process(session, "shp2geojson")

    assert new_session.state == SessionState.PARAM_COLLECT
    assert new_session.template is not None
    assert new_session.template.id == "shp2geojson"


@patch("core.processor.classify_intent")
def test_intent_confirm_question_goes_to_idle(
    mock_classify: MagicMock,
    processor: SessionProcessor,
    registry: TemplateRegistry,
) -> None:
    """User asks a question in intent confirm -> routed to _handle_idle for re-classification."""
    mock_classify.return_value = IntentResult(
        template_id="__qa__",
        confidence=0.9,
        reasoning="User is asking a question",
    )

    session = Session(
        state=SessionState.INTENT_CONFIRM,
        candidates=registry.list_templates(),
    )
    new_session, response = processor.process(session, "shp如何转kml")

    assert new_session.state == SessionState.IDLE
    mock_classify.assert_called_once()


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


# ---------------------------------------------------------------------------
# Parameter prompt helper
# ---------------------------------------------------------------------------


def test_build_param_prompt_shows_required_and_optional(
    sample_templates: list[TemplateDef],
) -> None:
    """_build_param_prompt lists params with required/optional tags and defaults."""
    template = sample_templates[0]  # shp2geojson
    prompt = SessionProcessor._build_param_prompt(template)

    assert "Shapefile" in prompt
    assert "input" in prompt
    assert "output" in prompt
    assert "t_srs" in prompt
    assert "必填" in prompt
    assert "可选" in prompt
    assert "EPSG:4326" in prompt


def test_build_param_prompt_no_params() -> None:
    """Template with no params shows a no-params message."""
    template = TemplateDef(
        id="noop",
        name="空任务",
        description="Does nothing",
        template_file="noop.j2",
        params=[],
    )
    prompt = SessionProcessor._build_param_prompt(template)

    assert "无需额外参数" in prompt


# ---------------------------------------------------------------------------
# ERROR_RECOVERY state
# ---------------------------------------------------------------------------


@patch("core.processor.analyze_execution_error")
def test_error_recovery_first_entry_triggers_diagnosis(
    mock_diagnose: MagicMock,
    processor: SessionProcessor,
    registry: TemplateRegistry,
    mock_template_engine: MagicMock,
) -> None:
    """First entry into ERROR_RECOVERY triggers LLM diagnosis and shows options."""
    mock_diagnose.return_value = ErrorDiagnosis(
        cause="文件不存在",
        suggestion="使用绝对路径",
        fixed_params={"input": "C:\\data\\roads.shp"},
        confidence=0.85,
        can_auto_fix=True,
    )
    mock_template_engine.render.return_value = RenderedScript(
        content="ogr2ogr -f GeoJSON out.geojson roads.shp",
        command_lines=["ogr2ogr -f GeoJSON out.geojson roads.shp"],
        platform=Platform.WINDOWS,
        output_path="test.bat",
    )

    shp_template = registry.get_template("shp2geojson")
    assert shp_template is not None

    session = Session(
        state=SessionState.ERROR_RECOVERY,
        template=shp_template,
        params={"input": "roads.shp", "output": "out.geojson"},
        error_context=ExecutionErrorContext(
            returncode=1,
            stdout="",
            stderr="ERROR: Unable to open datasource",
            duration_ms=100,
        ),
    )
    new_session, response = processor.process(session, "Y")

    assert new_session.state == SessionState.ERROR_RECOVERY
    assert new_session.error_context is not None
    assert new_session.error_context.diagnosis is not None
    assert "文件不存在" in response
    assert "确认修正" in response
    assert "手动修改" in response
    assert "放弃任务" in response
    mock_diagnose.assert_called_once()


@patch("core.processor.analyze_execution_error")
def test_error_recovery_confirm_auto_fix_goes_to_preview(
    mock_diagnose: MagicMock,
    processor: SessionProcessor,
    registry: TemplateRegistry,
    mock_template_engine: MagicMock,
) -> None:
    """User selects '1' with can_auto_fix=True → SCRIPT_PREVIEW with fixed params."""
    mock_template_engine.render.return_value = RenderedScript(
        content='ogr2ogr -f "GeoJSON" out.geojson C:\\data\\roads.shp',
        command_lines=['ogr2ogr -f "GeoJSON" out.geojson C:\\data\\roads.shp'],
        platform=Platform.WINDOWS,
        output_path="test.bat",
    )

    shp_template = registry.get_template("shp2geojson")
    assert shp_template is not None

    diagnosis = ErrorDiagnosis(
        cause="文件不存在",
        suggestion="使用绝对路径",
        fixed_params={"input": "C:\\data\\roads.shp"},
        confidence=0.85,
        can_auto_fix=True,
    )
    session = Session(
        state=SessionState.ERROR_RECOVERY,
        template=shp_template,
        params={"input": "roads.shp", "output": "out.geojson"},
        error_context=ExecutionErrorContext(
            returncode=1,
            stdout="",
            stderr="ERROR",
            duration_ms=100,
            diagnosis=diagnosis,
        ),
    )
    new_session, response = processor.process(session, "1")

    assert new_session.state == SessionState.SCRIPT_PREVIEW
    assert new_session.error_context is None
    assert new_session.params["input"] == "C:\\data\\roads.shp"
    assert "已自动修正参数" in response
    mock_template_engine.render.assert_called_once()


def test_error_recovery_manual_edit_goes_to_param_collect(
    processor: SessionProcessor,
    registry: TemplateRegistry,
) -> None:
    """User selects '2' → PARAM_COLLECT with error_context cleared."""
    shp_template = registry.get_template("shp2geojson")
    assert shp_template is not None

    diagnosis = ErrorDiagnosis(
        cause="文件不存在",
        suggestion="检查路径",
        fixed_params={},
        confidence=0.5,
        can_auto_fix=False,
    )
    session = Session(
        state=SessionState.ERROR_RECOVERY,
        template=shp_template,
        params={"input": "roads.shp", "output": "out.geojson"},
        error_context=ExecutionErrorContext(
            returncode=1,
            stdout="",
            stderr="ERROR",
            duration_ms=100,
            diagnosis=diagnosis,
        ),
    )
    new_session, response = processor.process(session, "2")

    assert new_session.state == SessionState.PARAM_COLLECT
    assert new_session.error_context is None
    assert new_session.template == shp_template


def test_error_recovery_abandon_goes_to_idle(
    processor: SessionProcessor,
    registry: TemplateRegistry,
) -> None:
    """User selects '3' → IDLE with all context cleared."""
    shp_template = registry.get_template("shp2geojson")
    assert shp_template is not None

    diagnosis = ErrorDiagnosis(
        cause="文件不存在",
        suggestion="检查路径",
        fixed_params={},
        confidence=0.5,
        can_auto_fix=False,
    )
    session = Session(
        state=SessionState.ERROR_RECOVERY,
        template=shp_template,
        params={"input": "roads.shp"},
        candidates=[shp_template],
        error_context=ExecutionErrorContext(
            returncode=1,
            stdout="",
            stderr="ERROR",
            duration_ms=100,
            diagnosis=diagnosis,
        ),
    )
    new_session, response = processor.process(session, "3")

    assert new_session.state == SessionState.IDLE
    assert new_session.error_context is None
    assert new_session.template is None
    assert new_session.params == {}
    assert new_session.candidates == []
    assert "已放弃" in response


def test_error_recovery_no_error_context_goes_to_idle(
    processor: SessionProcessor,
) -> None:
    """ERROR_RECOVERY without error_context → IDLE with error message."""
    session = Session(state=SessionState.ERROR_RECOVERY)
    new_session, response = processor.process(session, "anything")

    assert new_session.state == SessionState.IDLE
    assert "状态异常" in response


def test_error_recovery_unknown_input_treated_as_param_edit(
    processor: SessionProcessor,
    registry: TemplateRegistry,
    mock_template_engine: MagicMock,
) -> None:
    """Unknown input in ERROR_RECOVERY → PARAM_COLLECT (parameter modification)."""
    shp_template = registry.get_template("shp2geojson")
    assert shp_template is not None

    diagnosis = ErrorDiagnosis(
        cause="文件不存在",
        suggestion="检查路径",
        fixed_params={},
        confidence=0.5,
        can_auto_fix=False,
    )
    session = Session(
        state=SessionState.ERROR_RECOVERY,
        template=shp_template,
        params={"input": "roads.shp"},
        error_context=ExecutionErrorContext(
            returncode=1,
            stdout="",
            stderr="ERROR",
            duration_ms=100,
            diagnosis=diagnosis,
        ),
    )

    with patch("core.processor.extract_params") as mock_extract:
        mock_extract.return_value = ParamResult(
            params={"input": "new_roads.shp"},
            missing=["output"],
            questions=["请输入输出文件路径"],
        )
        new_session, response = processor.process(session, "输入改成 new_roads.shp")

    assert new_session.state == SessionState.PARAM_COLLECT
    assert new_session.error_context is None
    mock_extract.assert_called_once()
