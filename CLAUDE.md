# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GIS Agent (`gis-agent`) is a command-line assistant for GIS data processing using GDAL tools. It accepts natural language requests in Chinese, maps them to predefined Jinja2 templates, generates batch scripts, and executes them only after explicit user confirmation within a sandboxed workspace.

**Current phase**: Document/design phase. Source code structure is planned but not yet implemented. The project strictly follows SDD (Software Design Document) driven development: no code without a preceding design document.

## Development Workflow (SDD-Driven)

This project enforces a **design-first, document-driven, code-last** workflow. Any code change must have a supporting design document.

The document hierarchy (highest to lowest authority):

```
Document/constitution.md  →  Document/spec.md  →  Document/SDD-*.md  →  SourceCode/
```

**Key constraint**: Functional code cannot enter git history without a corresponding `Document/SDD-{module}.md` already committed. See `RED-1` in `Document/constitution.md`.

### Design Documents

| Document | Location | Purpose |
|----------|----------|---------|
| `spec.md` | `Document/` | Product requirements (MoSCoW), acceptance criteria |
| `constitution.md` | `Document/` | Development constitution, coding standards, quality gates |
| `SDD-{module}.md` | `Document/` | Module-level design (required before coding) |
| `ADR-{NNNN}-{name}.md` | `Document/` | Architecture decision records |

**Directory boundary**: `Document/` holds only docs; `SourceCode/` holds only code. Never mix them.

## Architecture (Planned)

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

## Environment

GDAL is installed via Conda. Python dependencies are minimal and fixed.

```bash
# Activate environment
conda activate gis-agent

# Verify GDAL
ogr2ogr --version
```

**Production dependencies** (locked): `anthropic`, `chromadb`, `jinja2` — no others without explicit approval.

## Commands (Expected After Setup)

The project uses `ruff` for formatting/linting, `mypy --strict` for type checking, and `pytest` for testing. These commands are defined as quality gates in `Document/constitution.md`.

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

These are hard constraints, not suggestions:

- **P1 (Template only)**: GDAL commands must be rendered from Jinja2 templates in `src/templates/` — dynamic string construction is prohibited
- **P2 (Show before execute)**: The CLI must display the full script and require explicit `Y/N` confirmation before execution
- **P3 (Sandbox)**: All file operations are restricted to the configured workspace; output files get timestamps to prevent silent overwrites
- **P4 (Local docs only)**: RAG retrieves only from local GDAL documentation in `Document/references/` — no web sources
- **P5 (Minimal deps)**: Production dependencies are locked to `anthropic`, `chromadb`, `jinja2`

## Important Files

| File | Why It Matters |
|------|---------------|
| `Document/spec.md` | Source of all requirements; every design decision must trace back to a requirement ID (e.g., `F1`, `F3`) |
| `Document/constitution.md` | Development constitution; defines SDD workflow, coding standards, quality gates, security red lines |
| `SourceCode/env-install.txt` | Conda environment setup instructions for GDAL |
| `SourceCode/src/templates/` | Jinja2 templates for GDAL command generation (to be created) |
| `Document/references/` | Local GDAL documentation for RAG (to be populated) |

## When Working on This Repo

- Before implementing any feature, check if a corresponding `SDD-{module}.md` exists in `Document/`. If not, the feature is not yet ready for coding.
- When modifying code, verify the change aligns with the locked SDD. If the SDD needs updating, follow the change control process in `Document/constitution.md`.
- The `Document/Resource/` directory is gitignored; do not commit its contents.
