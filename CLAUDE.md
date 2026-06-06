# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GIS Agent (`gis-agent`) is a natural-language assistant for GIS data processing using GDAL tools. It accepts Chinese requests, maps them to predefined Jinja2 templates, generates batch scripts, and executes them only after explicit user confirmation.

The **Electron desktop app** (`frontend/` + `api/`) is the sole active user entry point. Packaged as v1.0.0 (NSIS installer + portable exe) via `scripts/build-electron.ps1`.

The project follows Specification-Driven Design: no functional code without a preceding `Document/plan-{module}.md` (see `constitution.md` RED-1).

**Local config**: `CLAUDE.local.md` (project root, not checked in) contains environment-specific paths and is loaded alongside this file.

## Development Workflow

Document hierarchy (highest to lowest authority):

```
Document/constitution.md → Document/spec.md → Document/plan-*.md → SourceCode/tasks/*.md → SourceCode/
```

| Document | Purpose |
|---|---|
| `constitution.md` | Development constitution, coding standards, quality gates |
| `spec.md` | Product requirements (MoSCoW), acceptance criteria |
| `plan-{module}.md` | Module-level design plan (required before coding) |
| `ADR-{NNNN}-{name}.md` | Architecture decision records |

**Directory boundary**: `Document/` holds only docs; `SourceCode/` holds only code. Never mix them.

## Architecture

Strict layered architecture. Upper layers may call lower layers; **reverse dependencies are prohibited**.

```
Frontend (frontend/)    → React + TypeScript + Vite + Electron desktop app
API layer (api/)        → FastAPI REST + WebSocket adapters (Python child process)
Core layer (core/)      → template registry, param validator, matching engine
App layer (llm/)        → LLM interaction, intent classification, Q&A, diagnosis
Infra layer             → anthropic SDK, jinja2, GDAL CLI
Templates (templates/)  → Jinja2 engine, .j2 scanner, script security checker
```

**Dependency rules**:
- `frontend/` calls `api/` via HTTP/WebSocket only; never imports Python code.
- `api/` may depend on `core/`, `llm/`, `templates/`.
- `core/` may depend on `llm/`, `templates/`.
- `llm/` may depend on `core/` (for `TemplateDef` metadata in Q&A).
- `templates/` may depend on `core/` (models).
- `scripts/generate/` is a development-time tool, not a runtime layer.
- External library types must not leak upward through layer boundaries.

**Packaged runtime layout**: After `electron-builder`, Python resources (`src/`, `data/`, `config/`, `start_api.py`) are copied into `dist/electron/win-unpacked/SourceCode/` to preserve `Path(__file__)` traversals. `main.ts` uses `app.getPath('exe')` / `SourceCode` in production, and `__dirname/../..` in dev.

**Key design patterns**:
- GDAL commands are rendered from Jinja2 templates in `data/templates/` — **never** string-concatenated (P1).
- LLM calls (`anthropic`) are encapsulated in `llm/` only (CODE-3).
- Session is immutable — every state transition returns a new `Session` via `with_*` methods.
- Streamed interactions (LLM output, subprocess logs) must use WebSocket (CODE-5).

**Frontend stack**: React 18 + TypeScript + Vite, TailwindCSS with custom tokens (`frontend/tailwind.config.js`), Zustand (`useSession`), Axios with IPC-resolved absolute baseURL, ReactMarkdown + remark-gfm, HashRouter for `file://` protocol.

## Cross-Cutting Concerns

Use `codegraph_search` to find specific functions. The patterns below require reading multiple files.

### Session State Machine

States: `IDLE → INTENT_CONFIRM → PARAM_COLLECT → SCRIPT_PREVIEW → EXECUTING → ERROR_RECOVERY`.

- State transitions are handled via REST in `api/routes/session.py`.
- `EXECUTING` is asynchronous: `websocket/execute.py` runs the script, then updates state — success resets to `IDLE` (clears history/error), failure moves to `ERROR_RECOVERY` with `ExecutionErrorContext` (DC-0048).
- The frontend then calls `POST /session/{id}/diagnose` to trigger lazy LLM diagnosis (DC-0049).

**History isolation (DC-0107)**: `Session` has two independent message lists:
- `history` — Discovery/Exec flow messages.
- `qa_history` — QATab multi-turn context. WebSocket Q&A handler reads from and writes to `qa_history`; Discovery messages never pollute Q&A.

### Two-Stage Intent Matching (DC-0098)

`api/routes/session.py::process_intent` runs a two-stage pipeline for **DiscoveryTab only**:
1. **Coarse filter**: `core/matching.score_template_match()` on ALL templates. Weights: keywords=+3, concepts=+2, id/name/description/notes=+1.
2. **Fine rank**: `llm.intent.classify_intent()` on top-10 candidates.
3. **Auto-decision**: confidence ≥0.85 → `PARAM_COLLECT`; ≥0.50 → `INTENT_CONFIRM` with top-1 + alternates; <0.50 → `INTENT_CONFIRM` with top-3 keyword candidates.

The same scoring is reused by Q&A context selection (`llm/qa.py`).

### Q&A API Separation

- **`POST /session/{id}/intent`** — DiscoveryTab only. All inputs go through template matching.
- **`POST /session/{id}/chat`** — HTTP fallback. The front-end uses WebSocket `/ws/chat/{id}` for streaming.
- `answer_question()` branches by `locked_template`: template-knowledge mode (locked) vs GIS-expert mode (unlocked).

Intent is determined by which Tab the user is in, not by keyword parsing.

### ERROR_RECOVERY

1. Backend WebSocket sets `ERROR_RECOVERY` + `ExecutionErrorContext`.
2. `POST /session/{id}/diagnose` lazily runs `llm.diagnosis.analyze_execution_error()`, populates `error_context.diagnosis`, and caches it.
3. Frontend auto-triggers diagnosis after execution failure. **No manual diagnosis button**.
4. If `diagnoseSession()` itself fails, `useSession.setDiagnosisFallback()` injects a conservative diagnosis so the UI exits the spinner instead of hanging on "LLM 诊断中，请稍候".

Diagnosis suggestion is rendered with `ReactMarkdown` + `remark-gfm`. When `can_auto_fix=true`, the prompt must include a 【修复命令参考】 markdown code block; the frontend renders it as a dark-themed code panel. Recovery actions are "修改参数" / "放弃任务".

### Template System

Templates are discovered by scanning `.j2` files at startup (`templates/scanner.py` parses Jinja2 comment headers). No JSON registry — add a file and restart.

The J2 template generator (`scripts/generate/`) is a **development-time only** batch tool that converts GDAL HTML docs to `.j2` files via generate → review workflow.

### Frontend State

- `useSession` (Zustand) holds minimal state. API calls return `SessionSnapshot`; the frontend replaces state wholesale (DC-UX-03).
- `qaMessages` is local-only and never synced from backend (DC-UX-15).
- Three-TAB architecture: Discovery (HTTP), Q&A (WebSocket), Exec (HTTP trigger + WebSocket logs).
- Routing uses `HashRouter`: `/` MainPage, `/generator` GeneratorPage, `/pipeline` PipelinePage.
- Window is frameless; `TopBar` provides custom title bar and window controls via IPC (DC-E07).

### GeneratorPage & Pipeline

- **GeneratorPage**: Five-step J2 template wizard at `/#/generator`. Uses `assemble_j2_body()` to produce the complete `.j2` file. `ScriptSecurityChecker` validates Jinja2-aware dangerous patterns. Save hot-reloads the registry.
- **Pipeline**: `/#/pipeline` chains template steps with auto-linked parameters, sharing the same WebSocket execution infrastructure.

## CodeGraph

This project has a CodeGraph MCP server configured (`.codegraph/`). Prefer `codegraph_*` tools for structural questions; use native grep/read only for literal text queries.

| Question | Tool |
|---|---|
| "Where is X defined?" | `codegraph_search` |
| "What calls function Y?" | `codegraph_callers` |
| "How does X reach Y?" | `codegraph_trace` |
| "What would break if I changed Z?" | `codegraph_impact` |
| "Context for a task/area" | `codegraph_context` |
| "Several related symbols at once" | `codegraph_explore` |

Trust codegraph results — they come from a full AST parse. Don't re-verify with grep. Index lag is ~500ms behind writes.

If `.codegraph/` does not exist, ask: *"Want me to run `codegraph init -i` to build the index?"*

## Environment

**Python interpreter**: `electron/main.ts` resolves Python automatically via `resolvePythonPath()` — priority: `GISAGENT_PYTHON_PATH` env var → `config.json` → `python_path` → system PATH (`python` / `python3`) → all conda/anaconda environments (scanned and dependency-checked). No hard-coded conda path.

For development, invoke the `gis-agent` conda Python directly (bash does not support `conda activate`):

```bash
"/c/Users/PC/.conda/envs/gis-agent/python" --version
```

**Production dependencies** (locked, ≤7): `anthropic`, `beautifulsoup4` (ADR-0003), `jinja2`, `json5` (ADR-0002), `pydantic>=2.0` (ADR-0004), `pydantic-settings>=2.0` (ADR-0004), `tenacity>=8.0` (ADR-0005). No others without ADR approval.

**Environment variables** (override `config.json`):

```bash
export GISAGENT_LLM_AUTH_KEY="sk-your-key"
export GISAGENT_LLM_BASE_URL="https://api.example.com"
export GISAGENT_API_PORT=19000        # if 18000 is occupied
export VITE_API_PORT=19000            # frontend dev proxy, keep in sync
```

Naming rule: `GISAGENT_` + config path (uppercase, `_` separated).

**Tailwind customizations** (`frontend/tailwind.config.js`): primary blue scale, `borderRadius: { sm: 8px, DEFAULT: 12px, lg: 16px }`, softer shadows, Inter/Noto Sans SC + JetBrains Mono.

## Commands

### Python (backend)

```bash
cd SourceCode

# Format / lint / type check
ruff format src/ tests/ scripts/
ruff check src/ tests/ scripts/
mypy --strict src/

# Tests (must run from SourceCode/)
pytest tests/unit/ -v
pytest tests/unit/test_something.py -v
pytest tests/unit/test_something.py::test_function_name -v
pytest tests/unit/ --cov=src --cov-report=term-missing --cov-fail-under=80

# Install dependencies
pip install -e .         # production only
pip install -e ".[dev]"  # + test/lint/FastAPI deps

# Quick LLM e2e test (requires valid API key)
python scripts/test_e2e_qa.py

# Batch generate J2 templates from GDAL HTML docs
python scripts/generate_templates.py \
  --source ../Document/Resource/gdal/build/doc/build/html/programs \
  --output data/templates/ \
  --config config/config.json
```

### Frontend (Electron)

```bash
cd SourceCode/frontend

npm install
npm run electron:dev     # Vite + Electron concurrently
npm run electron:build   # Vite build + electron-builder (NSIS + portable)

# Type check
./node_modules/.bin/tsc --noEmit -p tsconfig.json
./node_modules/.bin/tsc -p electron/tsconfig.json --noEmit
```

### Electron Packaging

One-click build (from repo root):

```bash
powershell -ExecutionPolicy Bypass -File scripts/build-electron.ps1
```

Requires:
- `SourceCode/src/icon.png` ≥ 256×256 (Windows icon requirement)
- `scripts/electron-v{version}-win32-x64.zip` cached locally (set `ELECTRON_CACHE=scripts/`)

Outputs to `dist/electron/`:
- `win-unpacked/` — portable directory (run `GIS Agent.exe` directly)
- `GIS Agent Setup 1.0.0.exe` — NSIS installer
- `GIS Agent Portable 1.0.0.exe` — single-file portable

## Tool Configuration

`pyproject.toml`:
- **ruff**: `line-length = 88`, `target-version = "py310"`. `per-file-ignores` exempts `scripts/generate/*.py` and `tests/unit/test_generate_*.py` from `I001`/`E501`/`E402`.
- **mypy**: `strict = true`, `python_version = "3.10"`.
- **pytest**: `pythonpath = ["src"]`.

## Coding Standards

- Python 3.10+ with mandatory type annotations.
- 88-character line limit.
- Public functions/classes must have docstrings referencing design decisions (`DC-XXXX`).
- All `except` blocks must log or re-raise — no silent swallowing.
- Template parameters in `.j2` files must use `{{ param | quote }}` / `{{ param | safe_path }}`.

## Security Principles (from `Document/spec.md`)

- **P1 (Template only)**: GDAL commands rendered from Jinja2 templates; no dynamic string construction.
- **P2 (Show before execute)**: UI displays the full script and requires explicit confirmation.
- **P3 (Minimal permissions)**: Output paths are user-specified absolute paths with timestamps to prevent silent overwrites.
- **P4 (Template knowledge only)**: Usage guidance from J2 metadata (`@concept`, `@note`, `@common_error`); no external knowledge APIs.
- **P5 (Minimal deps)**: Locked to the 7 production libraries listed above.

## Key Files

| File | Why It Matters |
|---|---|
| `Document/constitution.md` | Source of truth for workflow rules (RED-1), quality gates, change control |
| `Document/spec.md` | All requirements trace back here |
| `Document/plan-core.md` | ERROR_RECOVERY, matching engine, two-stage matching, `qa_history` isolation |
| `Document/plan-ux.md` | WebSocket streaming, state→UI mapping, diagnosis UX |
| `Document/plan-j2-generate.md` | Template generator: shared engine, multi-file import, streaming |
| `Document/plan-electron.md` | Electron shell, IPC, Python child process lifecycle |
| `Document/plan-exec-env.md` | Shell/Conda detection and execution |
| `src/api/routes/session.py` | Two-stage intent matching, Q&A, diagnose, export-script endpoints |
| `src/api/websocket/chat.py` | Q&A WebSocket; reads/writes `qa_history` |
| `src/api/websocket/execute.py` | Script execution WebSocket; streams stdout/stderr |
| `src/core/matching.py` | Unified template scoring (keywords=+3, concepts=+2, rest=+1) |
| `src/llm/client.py` | Anthropic SDK wrapper with `tenacity` retry: 4 attempts, 1→2→4→8s backoff (ADR-0005) |
| `src/llm/diagnosis.py` | One-shot error diagnosis; uses `json5` + `_extract_json_block()` for robust LLM JSON parsing |
| `src/llm/prompts.py` | PromptBuilder: 5 scenario-specific prompts (intent/qa/gis-expert/param/diagnosis) |
| `src/llm/qa.py` | `answer_question()` branches by `locked_template` |
| `src/llm/template_generator.py` | Shared generation engine; `parse_generated_response()`, `sanitize_params()`, `auto_complete_params()`, `assemble_j2_body()` |
| `src/templates/engine.py` | Jinja2 rendering, custom filters (`quote`, `safe_path`), `ScriptSecurityChecker` |
| `src/templates/scanner.py` | `.j2` file scanner; parses comment headers into `TemplateDef` |
| `frontend/electron/main.ts` | Frameless window, Python child process, IPC handlers |
| `frontend/src/hooks/useSession.ts` | Zustand store; `setDiagnosisFallback()` prevents permanent diagnosis spinner |
| `frontend/src/pages/MainPage.tsx` | Three-TAB orchestrator: WebSocket execution, state refresh, export flow |
| `frontend/src/api/client.ts` | Axios with dynamic absolute baseURL via IPC |
| `frontend/electron-builder.json5` | Electron-builder config: NSIS + portable, output to `../../dist/electron` |
| `scripts/build-electron.ps1` | One-click build: Vite → electron-builder → copy `SourceCode/` externals |
| `src/config/models.py` | Config pydantic models; `python_path` field for Electron mode |

## When Working on This Repo

- Verify a corresponding `Document/plan-{module}.md` exists before coding.
- The `llm/` module is the **only** code allowed to import `anthropic` (CODE-3).
- `PromptBuilder` has exactly **5 scenario-specific methods**; do not add catch-all prompts.
- `Document/Resource/` and `SourceCode/config/config.json` are gitignored; never commit them.
- Script execution writes to `./cache/`; users export explicitly via "Export Script".
- Packaged artifacts (`dist/electron/`, `scripts/*.zip`) are gitignored; never commit them.
- `vite.config.ts` must keep `base: './'` for `file://` protocol compatibility (Electron production).
- `main.ts` `resolveAppRoot()` must preserve `SourceCode/` directory level so Python `Path(__file__)` traversals remain valid after packaging.

## Electron Packaging

`electron-builder` packages the frontend (`dist/` + `dist-electron/`) into `app.asar`. Python code and data are **not** bundled into the asar; the build script copies them as external resources.

**Why `SourceCode/` is preserved in the package**: Python files (`config/loader.py`, `api/main.py`) use `Path(__file__)` with hard-coded `../..` traversals that expect a `SourceCode/` parent. The build script creates `win-unpacked/SourceCode/` and copies `src/`, `data/`, `config/`, `start_api.py` into it. `main.ts` uses `path.dirname(app.getPath('exe'))/SourceCode` in production.

**Python auto-discovery in production** (`main.ts`):
1. `GISAGENT_PYTHON_PATH` env var
2. `config.json` → `python_path`
3. System PATH (`python` / `python3`)
4. All conda/anaconda environments under `~/.conda/envs/`, `~/anaconda3/envs/`, etc.

Each candidate is dependency-checked (`import fastapi, uvicorn, jinja2, pydantic, anthropic`). The first passing candidate wins. If none pass, the first found candidate is returned and an error dialog guides the user to install deps.

**Build script flow** (`scripts/build-electron.ps1`):
1. Check icon (`src/icon.png` ≥ 256×256)
2. `npm run build` (Vite) → `dist/`
3. `tsc -p electron/tsconfig.json` → `dist-electron/`
4. `electron-builder --config electron-builder.json5` → `dist/electron/win-unpacked/`
5. `robocopy` Python externals → `win-unpacked/SourceCode/`

## Adding New Templates

Create a `.j2` file in `SourceCode/data/templates/` with a Jinja2 comment header:

```jinja2
{# @id my_template #}
{# @name 我的模板名称 #}
{# @description 一句话描述功能 #}
{# @keyword shp #}
{# @concept "术语" — 概念解释文本 #}
{# @note 使用前提或注意事项 #}
{# @seealso related_template_id — 关联模板 #}
{# @common_error "错误文本" — 原因与修复建议 #}
{# @param input file_path required 输入文件路径 #}
{# @param output file_path required 输出文件路径 #}
```

**Template body rules**:
- Use `{{ param_name | quote }}` for path/string parameters.
- Use `{{ param_name | safe_path }}` for raw path output.
- Never use `+` or f-string style concatenation inside templates.
- Post-render `ScriptSecurityChecker` validates dangerous patterns.

Restart the application to pick up new templates (templates are scanned at startup).

### ParamForm readOnly Mode

`ParamForm` supports `readOnly?: boolean`:
- Inputs are disabled, browse buttons hidden.
- Footer actions hidden.
- Title changes from "参数设置" to "参数值".
- Used by DetailPanel in `IDLE` (post-success) and inside `SCRIPT_PREVIEW` (adjust params).