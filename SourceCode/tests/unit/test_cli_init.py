"""Tests for CLI module imports and package structure.

【已废弃，代码保留】CLI 层不再维护，参见 constitution.md §6.1。
Design: Document/archive/plan-cli.md (DC-0060)
"""


class TestCLIImports:
    """Verify public API is importable."""

    def test_main_import(self) -> None:
        """main is importable from cli package."""
        from cli import main

        assert callable(main)

    def test_repl_import(self) -> None:
        """REPL is importable from cli package."""
        from cli import REPL

        assert isinstance(REPL, type)

    def test_cli_args_import(self) -> None:
        """CLIArgs and parse_args are importable."""
        from cli import CLIArgs, parse_args

        assert isinstance(CLIArgs, type)
        assert callable(parse_args)

    def test_script_executor_import(self) -> None:
        """ScriptExecutor is importable."""
        from cli import ScriptExecutor

        assert isinstance(ScriptExecutor, type)

    def test_slash_handler_import(self) -> None:
        """SlashCommandHandler is importable."""
        from cli import SlashCommandHandler

        assert isinstance(SlashCommandHandler, type)

    def test_execution_result_import(self) -> None:
        """ExecutionResult is importable."""
        from cli import ExecutionResult

        assert isinstance(ExecutionResult, type)

    def test_all_exports_present(self) -> None:
        """All items in __all__ are importable."""
        import cli

        for name in cli.__all__:
            assert hasattr(cli, name), f"{name} not found in cli module"
