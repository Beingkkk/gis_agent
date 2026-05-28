"""Tests for CLI argument parsing.

Design: plan-cli v1.0.0 (DC-0060)
"""

from pathlib import Path

import pytest

from cli.args import CLIArgs, parse_args


class TestCLIArgs:
    """CLIArgs dataclass tests."""

    def test_default_values(self) -> None:
        """Default values are None/False."""
        args = CLIArgs()
        assert args.workspace is None
        assert args.config is None
        assert args.dry_run is False

    def test_frozen_immutable(self) -> None:
        """CLIArgs is frozen — cannot modify after creation."""
        args = CLIArgs()
        with pytest.raises(AttributeError):
            args.dry_run = True  # type: ignore[misc]

    def test_explicit_values(self) -> None:
        """All fields can be set explicitly."""
        args = CLIArgs(
            workspace=Path("/data/gis"),
            config=Path("cfg.json"),
            dry_run=True,
        )
        assert args.workspace == Path("/data/gis")
        assert args.config == Path("cfg.json")
        assert args.dry_run is True


class TestParseArgs:
    """parse_args() function tests."""

    def test_workspace_flag(self) -> None:
        """--workspace is parsed as Path."""
        args = parse_args(["--workspace", "/data/gis"])
        assert args.workspace == Path("/data/gis")
        assert args.config is None
        assert args.dry_run is False

    def test_config_flag(self) -> None:
        """--config is parsed as Path."""
        args = parse_args(["--config", "/path/to/config.json"])
        assert args.config == Path("/path/to/config.json")
        assert args.workspace is None
        assert args.dry_run is False

    def test_dry_run_flag(self) -> None:
        """--dry-run is parsed as True."""
        args = parse_args(["--dry-run"])
        assert args.dry_run is True
        assert args.workspace is None
        assert args.config is None

    def test_combined_flags(self) -> None:
        """All flags can be combined."""
        args = parse_args(
            [
                "--workspace",
                "/data",
                "--config",
                "cfg.json",
                "--dry-run",
            ]
        )
        assert args.workspace == Path("/data")
        assert args.config == Path("cfg.json")
        assert args.dry_run is True

    def test_no_args_defaults(self) -> None:
        """No arguments yields default values."""
        args = parse_args([])
        assert args.workspace is None
        assert args.config is None
        assert args.dry_run is False

    def test_unknown_flag_errors(self) -> None:
        """Unknown flags raise SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--foo"])
        assert exc_info.value.code == 2

    def test_help_exits_zero(self) -> None:
        """--help raises SystemExit(0)."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_help_contains_all_options(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Help text mentions all supported options."""
        with pytest.raises(SystemExit):
            parse_args(["--help"])
        captured = capsys.readouterr()
        assert "--workspace" in captured.out
        assert "--config" in captured.out
        assert "--dry-run" in captured.out
