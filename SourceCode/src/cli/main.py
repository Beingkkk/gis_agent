"""Main entry point for GIS Agent CLI.

Wires together all modules and starts the REPL.

Design: plan-cli v1.0.0 (DC-0060, DC-0061)
"""

import logging
from pathlib import Path
from typing import Optional

from cli.args import parse_args
from cli.commands import SlashCommandHandler
from cli.executor import ScriptExecutor
from cli.repl import REPL
from config import load_config
from core import (
    ParamValidator,
    Session,
    SessionProcessor,
    TemplateRegistry,
    get_workspace,
    initialize,
)
from core.workspace import WorkspaceNotFoundError
from llm import LLMClient, PromptBuilder
from rag.retriever import get_retriever
from templates import RenderedScript, TemplateEngine, scan_templates

logger = logging.getLogger(__name__)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point.

    Execution flow:
        1. Parse command-line arguments
        2. Load configuration
        3. Initialize workspace
        4. Initialize RAG retriever
        5. Scan templates and build registry
        6. Build SessionProcessor with all dependencies
        7. Build ScriptExecutor
        8. Start REPL loop

    Args:
        argv: Command-line arguments. Defaults to sys.argv[1:].

    Returns:
        Exit code: 0 = success, 1 = runtime error, 2 = argument/config error.
    """
    # 1. Parse arguments
    args = parse_args(argv)

    # 2. Load configuration
    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        print(f"配置文件不存在：{exc}")
        return 2
    except (ValueError, OSError) as exc:
        print(f"配置加载失败：{exc}")
        return 2

    # 3. Initialize workspace
    workspace_path = args.workspace
    if workspace_path is None:
        workspace_path = Path(config.workspace.default_path)

    try:
        initialize(workspace_path)
    except WorkspaceNotFoundError as exc:
        print(f"工作空间初始化失败：{exc}")
        return 2

    # 4. Initialize RAG retriever
    print("正在加载文档检索系统（首次启动可能需要 1-2 分钟）...")
    try:
        retriever = get_retriever()
    except RuntimeError as exc:
        print(f"RAG 初始化失败：{exc}")
        return 1
    print("文档检索系统加载完成。")

    # 5. Locate template directory and scan templates
    # __file__ = src/cli/main.py → parent.parent.parent = project_root/SourceCode
    template_dir = Path(__file__).parent.parent.parent / "data" / "templates"
    templates = scan_templates(template_dir)
    registry = TemplateRegistry(templates, template_dir)

    # 6. Build core components
    validator = ParamValidator(get_workspace())
    template_engine = TemplateEngine(template_dir, get_workspace())
    llm_client = LLMClient()

    agents_md = get_workspace().load_agents_md()
    agents_md_content = agents_md.content if agents_md is not None else None
    prompt_builder = PromptBuilder(agents_md_content)

    processor = SessionProcessor(
        registry=registry,
        validator=validator,
        template_engine=template_engine,
        llm_client=llm_client,
        prompt_builder=prompt_builder,
        retriever=retriever,
    )

    # 7. Build executor and REPL
    executor = ScriptExecutor(get_workspace())
    slash_handler = SlashCommandHandler()

    def render_fn(session: Session) -> "RenderedScript":
        """Render script from session for REPL execution."""
        if session.template is None:
            raise ValueError("No template selected in session")
        return template_engine.render(
            session.template,
            session.params,
        )

    repl = REPL(
        processor=processor,
        executor=executor,
        slash_handler=slash_handler,
        registry=registry,
        workspace=get_workspace(),
        dry_run=args.dry_run,
        render_fn=render_fn,
    )

    # 8. Print welcome and start loop
    print(
        f"GIS Agent 已启动。\n"
        f"工作空间：{get_workspace().root}\n"
        f"可用模板数：{len(templates)}\n"
        f"输入 /help 查看可用命令。"
    )
    repl.run(Session())
    return 0
