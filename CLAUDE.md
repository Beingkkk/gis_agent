# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GIS Agent (`gis-agent`) is a command-line assistant for GIS data processing using GDAL tools. It accepts natural language requests in Chinese, maps them to predefined Jinja2 templates, generates batch scripts, and executes them only after explicit user confirmation within a sandboxed workspace.

**Current phase**: Design documents are complete (7 plans committed). Source code implementation has not yet started. The project strictly follows Specification-Driven Design: no code without a preceding design document.

## Development Workflow (Specification-Driven)

This project enforces a **design-first, document-driven, code-last** workflow. Any code change must have a supporting design document.

The document hierarchy (highest to lowest authority):

```
Document/constitution.md  →  Document/spec.md  →  Document/plan-*.md  →  SourceCode/tasks.md  →  SourceCode/
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
CLI layer (cli/)        → user interaction, state machine, command parsing
Core layer (core/)      → workspace management, template engine, security validation
App layer (llm/ + rag/) → LLM interaction, intent classification, document retrieval
Infra layer             → anthropic SDK, chromadb, jinja2, GDAL CLI
```

**Dependency rules**:
- `cli/` may depend on `core/`, `llm/`, `rag/`
- `core/` may depend on `llm/`, `rag/`
- `llm/` may depend on `rag/`
- `rag/` has no upward dependencies
- External library types must not leak upward through layer boundaries

**Key design patterns**:
- GDAL commands are rendered via Jinja2 templates in `SourceCode/src/templates/` — **never** string-concatenated
- Workspace paths are validated through a security layer (`core/workspace.py`) — **never** `os.path.join` with raw user input
- LLM calls (`anthropic`) are encapsulated in `llm/` only
- ChromaDB operations are encapsulated in `rag/` only

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
# Activate environment
conda activate gis-agent

# Verify GDAL
ogr2ogr --version
```

**Production dependencies** (locked): `anthropic`, `chromadb`, `jinja2` — no others without explicit approval per constitution.md P5.

## Commands

The project uses `ruff` for formatting/linting, `mypy --strict` for type checking, and `pytest` for testing. These are defined as quality gates in `Document/constitution.md` §8.

```bash
# Format code
ruff format src/ tests/

# Check style and errors
ruff check src/ tests/

# Type check (strict)
mypy --strict src/

# Run all unit tests with coverage
pytest tests/unit/ --cov=src --cov-report=term-missing --cov-fail-under=80

# Run a single test file
pytest tests/unit/test_something.py -v

# Run a single test function
pytest tests/unit/test_something.py::test_function_name -v
```

## Coding Standards

- **Python 3.10+** with mandatory type annotations on all function parameters and return values
- **88-character line limit**
- All public functions/classes must have docstrings referencing their design decision (`DC-XXXX`)
- All `except` blocks must log or re-raise — no silent swallowing
- Template parameters in `.j2` files must be escaped to prevent command injection

## Security Principles

Hard constraints from `Document/spec.md`:

- **P1 (Template only)**: GDAL commands must be rendered from Jinja2 templates in `src/templates/` — dynamic string construction is prohibited
- **P2 (Show before execute)**: The CLI must display the full script and require explicit `Y/N` confirmation before execution
- **P3 (Sandbox)**: All file operations are restricted to the configured workspace; output files get timestamps to prevent silent overwrites
- **P4 (Local docs only)**: RAG retrieves only from local GDAL documentation in `SourceCode/data/` — no web sources
- **P5 (Minimal deps)**: Production dependencies are locked to `anthropic`, `chromadb`, `jinja2`

## Important Files

| File | Why It Matters |
|------|---------------|
| `Document/spec.md` | Source of all requirements; every design decision must trace back to a requirement ID (e.g., `F1`, `F3`) |
| `Document/constitution.md` | Development constitution; defines specification-driven workflow, coding standards, quality gates, security red lines |
| `SourceCode/env-install.txt` | Conda environment setup instructions for GDAL |
| `SourceCode/config/config.json` | LLM configuration (base_url, auth_key, model_name) |
| `SourceCode/model/download_embedding.cmd` | Windows script to download the `paraphrase-multilingual-MiniLM-L12-v2` embedding model into `SourceCode/model/` |
| `SourceCode/src/templates/` | Jinja2 templates for GDAL command generation (to be created during implementation) |
| `SourceCode/data/` | Preprocessed GDAL documentation chunks (JSON) for RAG |

## When Working on This Repo

- Before implementing any feature, check if a corresponding `plan-{module}.md` exists in `Document/`. If not, the feature is not yet ready for coding.
- When modifying code, verify the change aligns with the locked plan. If the plan needs updating, follow the change control process in `Document/constitution.md`.
- The `Document/Resource/` directory is gitignored; do not commit its contents.
