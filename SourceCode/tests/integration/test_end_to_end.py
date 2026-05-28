"""End-to-end integration test: full REPL session in dry-run mode.

Simulates a complete user session from startup to script preview
using mock input/output and real template files.

Design: plan-integration v1.0.0 (T-INT-05)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from cli.repl import REPL
from core.models import Session
from core.processor import SessionProcessor
from core.registry import TemplateRegistry
from core.validator import ParamValidator
from core.workspace import Workspace
from llm import PromptBuilder
from llm.models import IntentResult, ParamResult
from templates import RenderedScript, TemplateEngine, scan_templates


class TestEndToEndDryRun:
    """Full REPL session simulation with dry-run mode."""

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_full_repl_session_shp2geojson(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        real_template_dir: Path,
        tmp_path: Path,
        mock_llm_client: MagicMock,
        mock_retriever: MagicMock,
    ) -> None:
        """Simulate: describe task → provide params → see preview → dry-run skip."""
        mock_classify.return_value = IntentResult(
            template_id="shp2geojson",
            confidence=0.95,
            reasoning="Conversion to GeoJSON",
        )
        mock_extract.return_value = ParamResult(
            params={"input": "roads.shp", "output": "roads.geojson"},
            missing=[],
            questions=[],
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
            retriever=mock_retriever,
        )

        # Simulate user inputs and capture outputs
        inputs = [
            "把 roads.shp 转成 GeoJSON",  # Round 1: task description
            "输入 roads.shp，输出 roads.geojson",  # Round 2: params
            # REPL will auto-handle SCRIPT_PREVIEW → skip (dry_run)
            "/quit",  # Exit
        ]
        outputs: list[str] = []
        input_iter = iter(inputs)

        def mock_input_fn(prompt: str) -> str:
            return next(input_iter)

        def mock_output_fn(text: str) -> None:
            outputs.append(text)

        def render_fn(session: Session) -> "RenderedScript":
            if session.template is None:
                raise ValueError("No template")
            return engine.render(session.template, session.params)

        from cli.commands import SlashCommandHandler
        from cli.executor import ScriptExecutor

        repl = REPL(
            processor=processor,
            executor=ScriptExecutor(workspace),
            slash_handler=SlashCommandHandler(),
            registry=registry,
            workspace=workspace,
            dry_run=True,
            input_fn=mock_input_fn,
            output_fn=mock_output_fn,
            render_fn=render_fn,
        )

        repl.run(Session())

        # Verify outputs contain expected content
        all_output = "\n".join(outputs)
        assert "已识别任务" in all_output or "Shapefile" in all_output
        assert "脚本预览" in all_output
        assert "ogr2ogr" in all_output
        assert "roads.shp" in all_output
        assert "dry-run" in all_output or "跳过" in all_output
        assert "再见" in all_output

    @patch("core.processor.classify_intent")
    def test_full_repl_session_qa_then_quit(
        self,
        mock_classify: MagicMock,
        real_template_dir: Path,
        tmp_path: Path,
        mock_llm_client: MagicMock,
        mock_retriever: MagicMock,
        make_retrieved_docs: MagicMock,
    ) -> None:
        """Simulate: ask a question → get answer → quit."""
        mock_classify.return_value = IntentResult(
            template_id="__qa__",
            confidence=0.9,
            reasoning="User is asking a question",
        )
        mock_retriever.search.return_value = make_retrieved_docs(
            ["GeoJSON is an open standard format..."]
        )

        with patch("core.processor.answer_question") as mock_answer:
            mock_answer.return_value = "GeoJSON 是一种开放的地理数据交换格式..."

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
                retriever=mock_retriever,
            )

            inputs = [
                "GeoJSON 是什么",
                "/quit",
            ]
            outputs: list[str] = []
            input_iter = iter(inputs)

            def mock_input_fn(prompt: str) -> str:
                return next(input_iter)

            def mock_output_fn(text: str) -> None:
                outputs.append(text)

            from cli.commands import SlashCommandHandler
            from cli.executor import ScriptExecutor

            repl = REPL(
                processor=processor,
                executor=ScriptExecutor(workspace),
                slash_handler=SlashCommandHandler(),
                registry=registry,
                workspace=workspace,
                dry_run=True,
                input_fn=mock_input_fn,
                output_fn=mock_output_fn,
                render_fn=None,
            )

            repl.run(Session())

            all_output = "\n".join(outputs)
            assert "GeoJSON" in all_output
            assert "再见" in all_output
