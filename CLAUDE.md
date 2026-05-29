# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GIS Agent (`gis-agent`) is a command-line assistant for GIS data processing using GDAL tools. It accepts natural language requests in Chinese, maps them to predefined Jinja2 templates, generates batch scripts, and executes them only after explicit user confirmation.

The project strictly follows Specification-Driven Design: no code without a preceding design document.

## Development Workflow (Specification-Driven)

This project enforces a **design-first, document-driven, code-last** workflow. Any code change must have a supporting design document.

The document hierarchy (highest to lowest authority):

```
Document/constitution.md  →  Document/spec.md  →  Document/plan-*.md  →  SourceCode/tasks/*.md  →  SourceCode/
```

**Key constraint**: Functional code cannot enter git history without a corresponding `Document/plan-{module}.md` already committed. See `RED-1` in `Document/constitution.md`.

### Design Documents

| Document | Location | Purpose |
|----------|----------|---------|
| `constitution.md` | `Document/` | Development constitution, coding standards, quality gates |
| `spec.md` | `Document/` | Product requirements (MoSCoW), acceptance criteria |
| `plan-{module}.md` | `Document/` | Module-level design plan (required before coding) |
| `ADR-{NNNN}-{name}.md` | `Document/` | Architecture decision records |

**Directory boundary**: `Document/` holds only docs; `SourceCode/` holds only code. Never mix them.

## Architecture

Strict layered architecture. Upper layers may call lower layers; **reverse dependencies are prohibited**.

```
CLI layer (cli/)        → REPL, slash commands, script execution, main entry            [done]
Core layer (core/)      → workspace, template registry, param validator, session processor [done]
App layer (llm/)        → LLM interaction, intent classification, template-knowledge Q&A  [done]
Infra layer             → anthropic SDK, jinja2, GDAL CLI                              [done]
Templates (templates/)  → Jinja2 engine, .j2 scanner, script security checker           [done]
```

**Dependency rules**:
- `cli/` may depend on `core/`, `llm/`, `templates/`
- `core/` may depend on `llm/`, `templates/`
- `llm/` may depend on `core/` (for `TemplateDef` knowledge metadata in Q&A)
- `templates/` may depend on `core/` (models)
- `templates/` may depend on `core/` (models + workspace)
- External library types must not leak upward through layer boundaries

**Key design patterns**:
- GDAL commands are rendered via Jinja2 templates in `SourceCode/data/templates/` — **never** string-concatenated
- Workspace is a memory anchor (v2.0), not a security boundary — paths are normalized, not sandboxed
- LLM calls (`anthropic`) are encapsulated in `llm/` only (CODE-3)
- Session is immutable — every state transition returns a new `Session` instance via `with_*` methods

## Implemented Modules

### config (`SourceCode/src/config/`)

Configuration loading with validation and environment variable overrides.

- `load_config(path)` → `Config` dataclass
- `get_config()` → global singleton
- Supports `GISAGENT_*` env overrides
- **Note**: Module uses `from config import ...` imports (not `from src.config`), because `SourceCode/src/` is added to `PYTHONPATH` at runtime.
- **Security**: `config.json` is gitignored; use `config.json.template` as reference.

### rag (`SourceCode/src/rag/`)

**Removed per ADR-0001.** The runtime retriever (`rag.retriever`) has been deleted. Only `rag.preprocess` remains as a development tool for batch-generating J2 templates from GDAL HTML documentation.

- `rag.preprocess` — HTML parsing, semantic chunking, JSON output (development-only)

### llm (`SourceCode/src/llm/`)

LLM interaction layer — the only module allowed to call the anthropic SDK (CODE-3).

- `LLMClient` — Anthropic SDK wrapper with exponential backoff retry (max 3), token budget truncation (FIFO, 8000 token limit)
- `PromptBuilder` — Dynamic system prompt assembly: safety constraints + Agents.md + template knowledge context + task context
- `classify_intent()` — Maps user input to predefined template ID with confidence
- `extract_params()` — Extracts template parameters, identifies missing required fields
- `answer_question()` — Template-knowledge-based Q&A: basic concepts from LLM parametric knowledge; usage guidance from template metadata (`@concept`, `@note`, `@common_error`). Supports streaming via optional `on_chunk` callback (DC-0069)
- `chat_stream()` — Streaming LLM response via Anthropic SDK `stream=True` (DC-0068)
- `analyze_execution_error()` — LLM-driven execution error diagnosis: takes ExecutionResult + template context, returns structured `ErrorDiagnosis` (cause, suggestion, fixed_params, confidence, can_auto_fix). Includes markdown JSON stripping, fallback on parse failure, illegal key filtering, and low-confidence can_auto_fix enforcement (DC-0036)

### core (`SourceCode/src/core/`)

Business logic core. All exposed through `core/__init__.py`.

- **`models.py`** — `SessionState` (6-state Enum: IDLE, INTENT_CONFIRM, PARAM_COLLECT, SCRIPT_PREVIEW, EXECUTING, ERROR_RECOVERY), `Session` (immutable dataclass with `with_*` methods), `ParamDef`, `TemplateDef`, `ExecutionErrorContext`
- **`workspace.py`** — `Workspace(root)`, `resolve_path()` (normalization, no scope restriction v2.0), `generate_output_path()` (timestamp), `load_agents_md()`, `save_agents_md()` (append content, auto-create file with header), singleton via `initialize()` / `get_workspace()`
- **`registry.py`** — `TemplateRegistry(templates, template_dir)` — in-memory dict index from scanner results
- **`validator.py`** — `ParamValidator(workspace)` — type-specific validation chain (file_path, crs, string, boolean, integer). `must_exist` field on `ParamDef` controls existence checks. No "path sandbox" validation — workspace is not a security boundary.
- **`processor.py`** — `SessionProcessor(registry, validator, template_engine, llm_client, prompt_builder, output_fn=None)` — state machine dispatcher: IDLE → INTENT_CONFIRM → PARAM_COLLECT → SCRIPT_PREVIEW → EXECUTING → (失败) → ERROR_RECOVERY. `_handle_script_preview()` generates script text only; Y/N confirmation lives in CLI layer. Q&A route (`__qa__` template) uses `_find_matching_templates()` (keyword matching against template metadata) → `answer_question()` with optional `on_chunk` for streaming output (DC-0070). `_handle_error_recovery()` performs LLM diagnosis and presents repair options (auto-fix / manual edit / abandon). Execution acts as a natural breakpoint: success → full session reset; failure → history cleared, task context preserved (DC-0067).

### templates (`SourceCode/src/templates/`)

Template engine and scanner. Exposed through `templates/__init__.py`.

- **`engine.py`** — `TemplateEngine(template_dir, workspace)` — Jinja2 rendering with `quote` and `safe_path` filters. `ScriptSecurityChecker` post-render validation for dangerous patterns.
- **`scanner.py`** — `scan_templates(template_dir)` → `List[TemplateDef]` — parses Jinja2 comment headers (`{# @id ... #}`, `{# @param ... #}`, `{# @concept ... #}`, `{# @note ... #}`, `{# @seealso ... #}`, `{# @common_error ... #}`) from `.j2` files. Stores `template_file` as a path relative to `template_dir` (e.g. `vector/shp2geojson.j2`).

### cli (`SourceCode/src/cli/`)

User interaction layer. Exposed through `cli/__init__.py`.

- **`main.py`** — Entry point: parses args → loads config → initializes workspace → scans templates → builds processor → starts REPL
- **`repl.py`** — `REPL` class: input loop, slash command dispatch, state machine integration, SCRIPT_PREVIEW Y/N confirmation, script execution with formatted output. Exposes `output_fn` property for streaming Q&A injection into processor (DC-0071)
- **`commands.py`** — `SlashCommandHandler`: `/quit`, `/clear`, `/workspace`, `/templates`, `/status`, `/init` (persist session to Agents.md), `/help`
- **`executor.py`** — `ScriptExecutor` with `ExecutionResult`: subprocess execution with timeout (300s), cwd=workspace.root, stdout/stderr capture
- **`args.py`** — `argparse` wrapper for `--workspace`, `--config`, `--dry-run`

## CodeGraph

This project has a CodeGraph MCP server configured (`.codegraph/`). Prefer `codegraph_*` tools for structural questions — "what calls what", "where is X defined", "trace the flow from A to B". Use native grep/read only for literal text queries (string contents, comments, log messages) or to confirm a specific detail codegraph didn't cover.

| Question | Tool |
|---|---|
| "Where is X defined?" / "Find symbol named X" | `codegraph_search` |
| "What calls function Y?" | `codegraph_callers` |
| "How does X reach Y? / trace the flow" | `codegraph_trace` |
| "What would break if I changed Z?" | `codegraph_impact` |
| "Give me context for a task/area" | `codegraph_context` |
| "Show me several related symbols at once" | `codegraph_explore` |

- Trust codegraph results — they come from a full AST parse. Do not re-verify with grep.
- Don't grep first when looking up a symbol by name; `codegraph_search` is faster and returns kind + location + signature.
- Don't chain `codegraph_search` + `codegraph_node` when you want context — `codegraph_context` is one call.
- Don't loop `codegraph_node` over many symbols — one `codegraph_explore` call returns several symbols' source grouped in a single capped call.
- Index lag: the file watcher debounces ~500ms behind writes; don't re-query immediately after editing a file in the same turn.

If `.codegraph/` does not exist, ask the user: *"Want me to run `codegraph init -i` to build the index?"*

## Environment

GDAL is installed via Conda. Python dependencies are minimal and fixed.

```bash
# Verify GDAL
ogr2ogr --version
```

**Important**: In the bash shell used by Claude Code, `conda activate` does not work. Always invoke the environment's Python directly by full path:

```bash
"/c/Users/PC/.conda/envs/gis-agent/python" --version
```

**Production dependencies** (locked): `anthropic`, `jinja2` — no others without explicit approval per constitution.md P5.

## Commands

The project uses `ruff` for formatting/linting, `mypy --strict` for type checking, and `pytest` for testing. `pyproject.toml` configures `pythonpath = ["src"]` so `PYTHONPATH` does not need to be set manually when running from `SourceCode/`.

```bash
cd SourceCode

# Format code
ruff format src/ tests/ scripts/

# Check style and errors
ruff check src/ tests/ scripts/

# Type check (strict)
mypy --strict src/

# Run all unit tests
pytest tests/unit/ -v

# Run all unit tests with coverage
pytest tests/unit/ --cov=src --cov-report=term-missing --cov-fail-under=80

# Run a single test file
pytest tests/unit/test_something.py -v

# Run a single test function
pytest tests/unit/test_something.py::test_function_name -v

# Quick LLM end-to-end test (requires valid API key)
python scripts/test_e2e_qa.py
```

**pytest 工作目录约束**：测试路径 `tests/unit/` 是相对于 `SourceCode/` 解析的。在 `SourceCode/` 外运行 `pytest` 会因找不到测试文件而失败。始终在 `SourceCode/` 内执行测试命令。

## Coding Standards

- **Python 3.10+** with mandatory type annotations on all function parameters and return values
- **88-character line limit**
- All public functions/classes must have docstrings referencing their design decision (`DC-XXXX`)
- All `except` blocks must log or re-raise — no silent swallowing
- Template parameters in `.j2` files must be escaped to prevent command injection

## Security Principles

Hard constraints from `Document/spec.md`:

- **P1 (Template only)**: GDAL commands must be rendered from Jinja2 templates in `data/templates/` — dynamic string construction is prohibited
- **P2 (Show before execute)**: The CLI must display the full script and require explicit `Y/N` confirmation before execution
- **P3 (Minimal permissions)**: Default output to workspace with timestamps to prevent silent overwrites. Paths are normalized via `resolve()`. Workspace v2.0 is a memory anchor, not a security boundary — absolute paths are allowed.
- **P4 (Template knowledge only)**: Usage guidance knowledge comes exclusively from J2 template metadata (`@concept`, `@note`, `@common_error`); basic concepts may be answered from LLM parametric knowledge. No external API calls for knowledge.
- **P5 (Minimal deps)**: Production dependencies are locked to `anthropic`, `jinja2`

## Important Files

| File | Why It Matters |
|------|---------------|
| `Document/spec.md` | Source of all requirements; every design decision must trace back to a requirement ID (e.g., `F1`, `F3`) |
| `Document/constitution.md` | Development constitution; defines specification-driven workflow, coding standards, quality gates, security red lines |
| `Document/plan-core.md` | Core module design (DC-0040~0049, DC-0070) — SessionProcessor, TemplateRegistry, ParamValidator, Session, Workspace, streaming output callback |
| `Document/plan-cli.md` | CLI module design (DC-0060~0067, DC-0071) — REPL, ScriptExecutor, SlashCommandHandler, `/init` command, streaming output wiring |
| `Document/plan-llm.md` | LLM module design (DC-0030~0036, DC-0068~0069) — LLMClient, PromptBuilder, classify_intent, extract_params, answer_question, analyze_execution_error, chat_stream |
| `Document/ADR-0001-remove-rag.md` | Architecture decision: removed RAG runtime, migrated knowledge source to J2 template metadata |
| ~~`Document/plan-rag.md`~~ | ~~Deprecated~~ — RAG runtime removed per ADR-0001; `rag.preprocess` remains as development tool |
| `Document/plan-templates.md` | Template engine design (DC-0050~0054) — TemplateEngine, scanner, security checker |
| `SourceCode/config/config.json.template` | LLM and embedding configuration template; copy to `config.json` and set credentials |
| `SourceCode/src/core/processor.py` | Session state machine — the central orchestrator of the conversation lifecycle |
| `SourceCode/src/core/models.py` | SessionState, Session, ParamDef, TemplateDef dataclasses |
| `SourceCode/src/core/registry.py` | TemplateRegistry — in-memory index of scanned templates |
| `SourceCode/src/core/validator.py` | ParamValidator — type-specific parameter validation chain |
| `SourceCode/src/core/workspace.py` | Workspace management: path normalization, timestamps, Agents.md load/save |
| `SourceCode/src/templates/engine.py` | Jinja2 template rendering with quote/safe_path filters and post-render security check |
| `SourceCode/src/templates/scanner.py` | .j2 file scanner — parses Jinja2 comment headers into TemplateDef |
| `SourceCode/src/llm/client.py` | Anthropic SDK wrapper with retry and token truncation |
| `SourceCode/src/llm/intent.py` | Intent classification (`classify_intent`) |
| `SourceCode/src/llm/params.py` | Parameter extraction (`extract_params`) |
| `SourceCode/src/llm/qa.py` | Template-knowledge-based Q&A (`answer_question`, ADR-0001) |
| `SourceCode/src/llm/diagnosis.py` | Execution error diagnosis (`analyze_execution_error`, DC-0036) |
| `SourceCode/data/gdal-docs-chunks.json` | Development reference: GDAL documentation chunks for batch J2 template generation (not used at runtime) |
| `SourceCode/tasks/tasks-core.md` | Core implementation task breakdown (T-CORE-01~05) |
| `SourceCode/tasks/tasks-cli.md` | CLI implementation task breakdown (T-CLI-01~10) |

## Adding New Templates

New GDAL workflows are added by creating a `.j2` file in `SourceCode/data/templates/` with a Jinja2 comment header. The scanner (`templates.scanner`) parses the header at startup — no JSON registry edit needed.

**Comment header format**:
```jinja2
{# @id my_template #}
{# @name 我的模板名称 #}
{# @description 一句话描述功能 #}
{# @concept "术语" — 概念解释文本 #}
{# @note 使用前提或注意事项 #}
{# @seealso related_template_id — 关联模板 #}
{# @common_error "错误文本" — 原因与修复建议 #}
{# @param input file_path required 输入文件路径 #}
{# @param output file_path required 输出文件路径 #}
{# @param t_srs crs optional 目标坐标系 default=EPSG:4326 #}
```

**Template body rules**:
- Use `{{ param_name | quote }}` for path/string parameters (auto-escapes for shell safety)
- Use `{{ param_name | safe_path }}` for raw path output
- Never use `+` or f-string style concatenation inside templates
- Post-render security check (`ScriptSecurityChecker`) validates for dangerous patterns

After adding a template, restart the CLI to pick it up (templates are scanned at startup).

## When Working on This Repo

- Before implementing any feature, check if a corresponding `plan-{module}.md` exists in `Document/`. If not, the feature is not yet ready for coding.
- When modifying code, verify the change aligns with the locked plan. If the plan needs updating, follow the change control process in `Document/constitution.md`.
- The `llm/` module is the **only** code allowed to import `anthropic` (CODE-3). Never add anthropic imports outside `llm/`.
- `Document/Resource/` is gitignored; do not commit its contents.
- `SourceCode/model/embedding/` contains large model files and should not be committed.
- `SourceCode/config/config.json` is gitignored; never commit credentials.
