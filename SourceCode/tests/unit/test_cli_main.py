"""Tests for CLI main entry point.

Design: plan-cli v1.0.0 (DC-0060, DC-0061), ADR-0001
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli.main import main


class TestMainSuccessPath:
    """Successful startup flow."""

    @patch("cli.main.REPL")
    @patch("cli.main.ScriptExecutor")
    @patch("cli.main.SessionProcessor")
    @patch("cli.main.PromptBuilder")
    @patch("cli.main.LLMClient")
    @patch("cli.main.TemplateEngine")
    @patch("cli.main.ParamValidator")
    @patch("cli.main.TemplateRegistry")
    @patch("cli.main.scan_templates")
    @patch("cli.main.load_config")
    @patch("cli.main.parse_args")
    def test_main_successful_startup(
        self,
        mock_parse_args: MagicMock,
        mock_load_config: MagicMock,
        mock_scan_templates: MagicMock,
        mock_template_registry: MagicMock,
        mock_param_validator: MagicMock,
        mock_template_engine: MagicMock,
        mock_llm_client: MagicMock,
        mock_prompt_builder: MagicMock,
        mock_session_processor: MagicMock,
        mock_script_executor: MagicMock,
        mock_repl: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Main initializes all components and starts REPL."""
        from cli.args import CLIArgs
        from core.models import TemplateDef

        mock_parse_args.return_value = CLIArgs()
        mock_config = MagicMock()
        mock_load_config.return_value = mock_config

        mock_scan_templates.return_value = [
            TemplateDef(id="t1", name="Test", description="", template_file="t.j2"),
        ]

        mock_repl_instance = MagicMock()
        mock_repl.return_value = mock_repl_instance

        result = main([])

        assert result == 0
        mock_scan_templates.assert_called_once()
        mock_repl_instance.run.assert_called_once()

    @patch("cli.main.REPL")
    @patch("cli.main.ScriptExecutor")
    @patch("cli.main.SessionProcessor")
    @patch("cli.main.PromptBuilder")
    @patch("cli.main.LLMClient")
    @patch("cli.main.TemplateEngine")
    @patch("cli.main.ParamValidator")
    @patch("cli.main.TemplateRegistry")
    @patch("cli.main.scan_templates")
    @patch("cli.main.load_config")
    @patch("cli.main.parse_args")
    def test_main_welcome_message(
        self,
        mock_parse_args: MagicMock,
        mock_load_config: MagicMock,
        mock_scan_templates: MagicMock,
        mock_template_registry: MagicMock,
        mock_param_validator: MagicMock,
        mock_template_engine: MagicMock,
        mock_llm_client: MagicMock,
        mock_prompt_builder: MagicMock,
        mock_session_processor: MagicMock,
        mock_script_executor: MagicMock,
        mock_repl: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Welcome message includes template count."""
        from cli.args import CLIArgs
        from core.models import TemplateDef

        mock_parse_args.return_value = CLIArgs()
        mock_config = MagicMock()
        mock_load_config.return_value = mock_config

        mock_scan_templates.return_value = [
            TemplateDef(id="t1", name="Test1", description="", template_file="a.j2"),
            TemplateDef(id="t2", name="Test2", description="", template_file="b.j2"),
        ]

        mock_repl_instance = MagicMock()
        mock_repl.return_value = mock_repl_instance

        main([])

        captured = capsys.readouterr()
        assert "2" in captured.out or "两" in captured.out or "模板" in captured.out

    @patch("cli.main.REPL")
    @patch("cli.main.ScriptExecutor")
    @patch("cli.main.SessionProcessor")
    @patch("cli.main.PromptBuilder")
    @patch("cli.main.LLMClient")
    @patch("cli.main.TemplateEngine")
    @patch("cli.main.ParamValidator")
    @patch("cli.main.TemplateRegistry")
    @patch("cli.main.scan_templates")
    @patch("cli.main.load_config")
    @patch("cli.main.parse_args")
    def test_main_dry_run_flag(
        self,
        mock_parse_args: MagicMock,
        mock_load_config: MagicMock,
        mock_scan_templates: MagicMock,
        mock_template_registry: MagicMock,
        mock_param_validator: MagicMock,
        mock_template_engine: MagicMock,
        mock_llm_client: MagicMock,
        mock_prompt_builder: MagicMock,
        mock_session_processor: MagicMock,
        mock_script_executor: MagicMock,
        mock_repl: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--dry-run flag is passed to REPL."""
        from cli.args import CLIArgs

        mock_parse_args.return_value = CLIArgs(dry_run=True)
        mock_config = MagicMock()
        mock_load_config.return_value = mock_config

        mock_scan_templates.return_value = []

        mock_repl_instance = MagicMock()
        mock_repl.return_value = mock_repl_instance

        main(["--dry-run"])

        # Verify REPL was constructed with dry_run=True
        repl_call = mock_repl.call_args
        assert repl_call.kwargs.get("dry_run") is True


class TestMainFailurePaths:
    """Failure paths and exit codes."""

    @patch("cli.main.parse_args")
    @patch("cli.main.load_config")
    def test_config_not_found(
        self,
        mock_load_config: MagicMock,
        mock_parse_args: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-existent config file returns exit code 2."""
        from cli.args import CLIArgs

        mock_parse_args.return_value = CLIArgs(config=Path("/nonexistent.json"))
        mock_load_config.side_effect = FileNotFoundError("config not found")

        result = main(["--config", "/nonexistent.json"])

        assert result == 2
        captured = capsys.readouterr()
        assert (
            "配置" in captured.out
            or "config" in captured.out.lower()
            or "不存在" in captured.out
        )
