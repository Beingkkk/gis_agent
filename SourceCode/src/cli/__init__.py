"""GIS Agent CLI module.

Public API:
    main — CLI entry point
    REPL — interactive Read-Eval-Print Loop
    CLIArgs, parse_args — command-line argument parsing
    ScriptExecutor, ExecutionResult — script execution
    SlashCommandHandler — slash command dispatcher

Design: plan-cli v1.0.0 (DC-0060 ~ DC-0066)
"""

from cli.args import CLIArgs, parse_args
from cli.commands import SlashCommandHandler
from cli.executor import ExecutionResult, ScriptExecutor
from cli.main import main
from cli.repl import REPL

__all__ = [
    "CLIArgs",
    "ExecutionResult",
    "REPL",
    "ScriptExecutor",
    "SlashCommandHandler",
    "main",
    "parse_args",
]
