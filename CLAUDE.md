# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GIS Agent (`gis-agent`) is a command-line assistant for GIS data processing using GDAL tools. It accepts natural language requests in Chinese, maps them to predefined Jinja2 templates, generates batch scripts, and executes them only after explicit user confirmation.

**Current phase**: config, rag, llm, core (models/registry/validator/processor/workspace), and templates (engine/scanner) modules are implemented. `cli/` is the only remaining module.

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
CLI layer (cli/)        → user interaction, state machine, command parsing              [pending]
Core layer (core/)      → workspace, template registry, param validator, session processor [done]
App layer (llm/ + rag/) → LLM interaction, intent classification, document retrieval     [done]
Infra layer             → anthropic SDK, chromadb, jinja2, GDAL CLI                     [done]
Templates (templates/)  → Jinja2 engine, .j2 scanner, script security checker           [done]
```

**Dependency rules**:
- `cli/` may depend on `core/`, `llm/`, `rag/`, `templates/`
- `core/` may depend on `llm/`, `rag/`, `templates/`
- `llm/` may depend on `rag/`
- `rag/` may depend on `config/`
- `templates/` may depend on `core/` (models + workspace)
- External library types must not leak upward through layer boundaries

**Key design patterns**:
- GDAL commands are rendered via Jinja2 templates in `SourceCode/data/templates/` — **never** string-concatenated
- Workspace is a memory anchor (v2.0), not a security boundary — paths are normalized, not sandboxed
- LLM calls (`anthropic`) are encapsulated in `llm/` only (CODE-3)
- ChromaDB operations are encapsulated in `rag/` only (CODE-4)

## Implemented Modules

### config (`SourceCode/src/config/`)

Configuration loading with validation and environment variable overrides.

- `load_config(path)` → `Config` dataclass
- `get_config()` → global singleton
- Supports `GISAGENT_*` env overrides
- **Note**: Module uses `from config import ...` imports (not `from src.config`), because `SourceCode/src/` is added to `PYTHONPATH` at runtime.
- **Security**: `config.json` is gitignored; use `config.json.template` as reference.

### rag (`SourceCode/src/rag/`)

GDAL document retrieval pipeline.

- `rag.preprocess` — HTML parsing, semantic chunking, JSON output (development-only)
- `rag.retriever` — ChromaDB vector retrieval with hash-based cache detection
  - `DocumentRetriever.search(query, top_k)` → `List[RetrievedDocument]`
  - `get_retriever()` → singleton, auto-loads/builds index on first call
- **RAG data**: `SourceCode/data/gdal-docs-chunks.json` (9706 chunks)
- **Embedding model**: `SourceCode/model/embedding/` (`paraphrase-multilingual-MiniLM-L12-v2`)
- **ChromaDB cache**: `~/.cache/gis-agent/chroma/` (persistent, hash-detected rebuilds)

### llm (`SourceCode/src/llm/`)

LLM interaction layer — the only module allowed to call the anthropic SDK (CODE-3).

- `LLMClient` — Anthropic SDK wrapper with exponential backoff retry (max 3), token budget truncation (FIFO, 8000 token limit)
- `PromptBuilder` — Dynamic system prompt assembly: safety constraints + Agents.md + RAG context + task context
- `classify_intent()` — Maps user input to predefined template ID with confidence
- `extract_params()` — Extracts template parameters, identifies missing required fields
- `answer_question()` — RAG-enhanced document Q&A

### core (`SourceCode/src/core/`)

Business logic core. All exposed through `core/__init__.py`.

- **`models.py`** — `SessionState` (5-state Enum), `Session` (immutable dataclass with `with_*` methods), `ParamDef`, `TemplateDef`
- **`workspace.py`** — `Workspace(root)`, `resolve_path()` (normalization, no scope restriction v2.0), `generate_output_path()` (timestamp), `load_agents_md()`, singleton via `initialize()` / `get_workspace()`
- **`registry.py`** — `TemplateRegistry(templates, template_dir)` — in-memory dict index from scanner results
- **`validator.py`** — `ParamValidator(workspace)` — type-specific validation chain (file_path, crs, string, boolean, integer). `must_exist` field on `ParamDef` controls existence checks. No "path sandbox" validation — workspace is not a security boundary.
- **`processor.py`** — `SessionProcessor(registry, validator, template_engine, llm_client, prompt_builder)` — state machine dispatcher: IDLE → INTENT_CONFIRM → PARAM_COLLECT → SCRIPT_PREVIEW. `_handle_script_preview()` generates script text only; Y/N confirmation lives in CLI layer.

### templates (`SourceCode/src/templates/`)

Template engine and scanner. Exposed through `templates/__init__.py`.

- **`engine.py`** — `TemplateEngine(template_dir, workspace)` — Jinja2 rendering with `quote` and `safe_path` filters. `ScriptSecurityChecker` post-render validation for dangerous patterns.
- **`scanner.py`** — `scan_templates(template_dir)` → `List[TemplateDef]` — parses Jinja2 comment headers (`{# @id ... #}`, `{# @param ... #}`) from `.j2` files. Stores `template_file` as a path relative to `template_dir` (e.g. `vector/shp2geojson.j2`).

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
"/c/Users/PC/.conda/envs/gis-agent/python" -c "import sentence_transformers"
```

**Production dependencies** (locked): `anthropic`, `chromadb`, `jinja2` — no others without explicit approval per constitution.md P5. `sentence-transformers` is accepted as an extended dependency for embedding model loading.

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

# Quick RAG end-to-end test
python -c "from rag.retriever import get_retriever; r = get_retriever(); print(r.search('ogr2ogr GeoJSON', top_k=3))"

# Quick LLM end-to-end test (requires valid API key)
python scripts/test_e2e_qa.py
```

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
- **P4 (Local docs only)**: RAG retrieves only from local GDAL documentation in `SourceCode/data/` — no web sources
- **P5 (Minimal deps)**: Production dependencies are locked to `anthropic`, `chromadb`, `jinja2`; `sentence-transformers` is accepted as an extended dependency for embedding model loading

## Important Files

| File | Why It Matters |
|------|---------------|
| `Document/spec.md` | Source of all requirements; every design decision must trace back to a requirement ID (e.g., `F1`, `F3`) |
| `Document/constitution.md` | Development constitution; defines specification-driven workflow, coding standards, quality gates, security red lines |
| `Document/plan-core.md` | Core module design (DC-0040~0049) — SessionProcessor, TemplateRegistry, ParamValidator, Session |
| `Document/plan-cli.md` | CLI module design (DC-0060~0069) — REPL, ScriptExecutor, SlashCommandHandler, main entry |
| `Document/plan-templates.md` | Template engine design (DC-0050~0054) — TemplateEngine, scanner, security checker |
| `SourceCode/config/config.json.template` | LLM and embedding configuration template; copy to `config.json` and set credentials |
| `SourceCode/src/core/processor.py` | Session state machine — the central orchestrator of the conversation lifecycle |
| `SourceCode/src/core/models.py` | SessionState, Session, ParamDef, TemplateDef dataclasses |
| `SourceCode/src/core/registry.py` | TemplateRegistry — in-memory index of scanned templates |
| `SourceCode/src/core/validator.py` | ParamValidator — type-specific parameter validation chain |
| `SourceCode/src/core/workspace.py` | Workspace management: path normalization, timestamps, Agents.md |
| `SourceCode/src/templates/engine.py` | Jinja2 template rendering with quote/safe_path filters and post-render security check |
| `SourceCode/src/templates/scanner.py` | .j2 file scanner — parses Jinja2 comment headers into TemplateDef |
| `SourceCode/src/llm/client.py` | Anthropic SDK wrapper with retry and token truncation |
| `SourceCode/src/llm/intent.py` | Intent classification (`classify_intent`) |
| `SourceCode/src/llm/params.py` | Parameter extraction (`extract_params`) |
| `SourceCode/src/rag/retriever.py` | ChromaDB retriever with hash cache + semantic search |
| `SourceCode/data/gdal-docs-chunks.json` | Preprocessed GDAL documentation for RAG (5.9MB, 9706 chunks) |
| `SourceCode/tasks/tasks-core.md` | Core implementation task breakdown (T-CORE-01~05) |
| `SourceCode/tasks/tasks-cli.md` | CLI implementation task breakdown (T-CLI-01~10) |

## When Working on This Repo

- Before implementing any feature, check if a corresponding `plan-{module}.md` exists in `Document/`. If not, the feature is not yet ready for coding.
- When modifying code, verify the change aligns with the locked plan. If the plan needs updating, follow the change control process in `Document/constitution.md`.
- The `llm/` module is the **only** code allowed to import `anthropic` (CODE-3). Never add anthropic imports outside `llm/`.
- `Document/Resource/` is gitignored; do not commit its contents.
- `SourceCode/model/embedding/` contains large model files and should not be committed.
- `SourceCode/config/config.json` is gitignored; never commit credentials.
