"""Command-line argument parsing for GIS Agent.

Design: plan-cli v1.0.0 (DC-0060)
"""

from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CLIArgs:
    """Parsed command-line arguments."""

    workspace: Optional[Path] = None
    config: Optional[Path] = None
    dry_run: bool = False


def parse_args(argv: Optional[list[str]] = None) -> CLIArgs:
    """Parse command-line arguments.

    Args:
        argv: Argument list. Defaults to sys.argv[1:].

    Returns:
        Parsed CLIArgs instance.
    """
    parser = ArgumentParser(
        prog="gis-agent",
        description="Command-line assistant for GIS data processing.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Workspace directory path",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Configuration file path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run mode (show script without executing)",
    )
    namespace = parser.parse_args(argv)
    return CLIArgs(
        workspace=namespace.workspace,
        config=namespace.config,
        dry_run=namespace.dry_run,
    )
