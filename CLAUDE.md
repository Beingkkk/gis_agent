# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GIS Agent (`gis-agent`) is a natural-language assistant for GIS data processing using GDAL tools. It accepts Chinese requests, maps them to predefined Jinja2 templates, generates batch scripts, and executes them only after explicit user confirmation.

The project provides **two UIs**: an Electron desktop application (`frontend/` + `api/`) and a command-line REPL (`cli/`). Both share the same `core/llm/templates` business logic. The browser-based UI has been removed; Electron is the sole graphical entry point.

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
Frontend (frontend/)    → React + TypeScript + Vite + Electron desktop app
API layer (api/)        → FastAPI REST + WebSocket adapters (Python child process)
CLI layer (cli/)        → REPL, slash commands, script execution
Core layer (core/)      → workspace, template registry, param validator, session processor, matching engine
App layer (llm/)        → LLM interaction, intent classification, template-knowledge Q&A, error diagnosis
Infra layer             → anthropic SDK, jinja2, GDAL CLI
Templates (templates/)  → Jinja2 engine, .j2 scanner, script security checker
```

**Dependency rules**:
- `frontend/` calls `api/` via HTTP/WebSocket only; never imports Python code
- `api/` may depend on `core/`, `llm/`, `templates/`
- `cli/` may depend on `core/`, `llm/`, `templates/`
- `core/` may depend on `llm/`, `templates/`
- `llm/` may depend on `core/` (for `TemplateDef` knowledge metadata in Q&A)
- `templates/` may depend on `core/` (models + workspace)
- `scripts/generate/` is a development-time tool, not a runtime layer
- External library types must not leak upward through layer boundaries

**Key design patterns**:
- GDAL commands are rendered via Jinja2 templates in `data/templates/` — **never** string-concatenated
- Workspace is a memory anchor (v2.0), not a security boundary — paths are normalized, not sandboxed
- LLM calls (`anthropic`) are encapsulated in `llm/` only (CODE-3)
- Session is immutable — every state transition returns a new `Session` instance via `with_*` methods

## Module Design (Cross-Cutting Concerns)

Use `codegraph_search` to find specific functions. The following are design patterns that require reading multiple files to understand.

### Session State Machine

`SessionState` has 6 states: `IDLE → INTENT_CONFIRM → PARAM_COLLECT → SCRIPT_PREVIEW → EXECUTING → ERROR_RECOVERY`.

- **CLI**: `SessionProcessor` (in `core/processor.py`) drives the full state machine single-threaded. `_handle_error_recovery()` performs LLM diagnosis and parses user text choices ("1"/"2"/"3").
- **Desktop UI**: The API routes (`api/routes/session.py`) handle state transitions via REST. `EXECUTING` is special — the `websocket/execute.py` handler runs the script asynchronously, then updates the session state: success → `IDLE` (clears history and error context); failure → `ERROR_RECOVERY` with `ExecutionErrorContext` (DC-0048). The frontend then calls `POST /session/{id}/diagnose` to trigger lazy LLM diagnosis (plan-core DC-0049).

### Two-Stage Intent Matching (DC-0098)

`api/routes/session.py::process_intent` implements a two-stage pipeline for **DiscoveryTab only** (Q&A has its own endpoint, see below):
1. **Coarse filter**: `core/matching.score_template_match()` on ALL templates (fast, code-level). Weights: keywords=+3, concepts=+2, id/name/description/notes=+1.
2. **Fine rank**: `llm.intent.classify_intent()` on top-10 candidates (LLM semantic match).
3. **Auto-decision** by confidence: ≥0.85 → `PARAM_COLLECT`; ≥0.50 → `INTENT_CONFIRM` (top-1 + alternates); <0.50 → `INTENT_CONFIRM` (top-3 keyword candidates).

The same `score_template_match()` scoring is reused by Q&A context selection (`llm/qa.py`).

### Q&A API Separation (DC-0071)

Q&A and intent matching are separated at the API level:
- **`POST /session/{id}/intent`** — DiscoveryTab only. Pure intent matching, no `is_question` keyword heuristic. All inputs go through template matching.
- **`POST /session/{id}/chat`** — QATab only. Always treated as a question. Calls `answer_question()` with `locked_template` to determine whether to include template context (template-knowledge mode) or not (GIS-expert mode).

This removes the old keyword-based (`什么`, `怎么`) question detection from `process_intent`. Intent is determined by which Tab the user is in, not by parsing their text.

### ERROR_RECOVERY in the Desktop UI

Unlike the CLI where `SessionProcessor._handle_error_recovery()` drives the entire recovery loop, the desktop UI splits it across three pieces:
1. **Backend websocket**: `websocket/execute.py` sets `ERROR_RECOVERY` + basic `ExecutionErrorContext` (stdout/stderr/returncode/duration_ms, diagnosis=None).
2. **Backend diagnose endpoint**: `POST /session/{id}/diagnose` lazily triggers `llm.diagnosis.analyze_execution_error()`, populates `error_context.diagnosis` (cause, suggestion, fixed_params, confidence, can_auto_fix), and caches the result.
3. **Frontend DetailPanel**: `ERROR_RECOVERY` state renders a diagnosis panel (loading spinner → diagnosis result → repair options: re-execute / edit params / abandon).

### Template System

Templates are discovered by scanning `.j2` files at startup (`templates/scanner.py` parses Jinja2 comment headers: `{# @id ... #}`, `{# @param ... #}`, `{# @concept ... #}`, `{# @note ... #}`, `{# @seealso ... #}`, `{# @common_error ... #}`, `{# @keyword ... #}`). No JSON registry — add a file and restart.

The J2 template generator (`scripts/generate/`) is a **development-time only** batch tool (DC-0080) that converts GDAL HTML docs to `.j2` files via two-phase LLM workflow (generate → review, DC-0081).

### Frontend State Architecture

- `useSession` (Zustand) holds minimal UI state: `sessionId`, `state`, `taskContext`, `messages`, `scriptPreview`, `errorContext`, `workspace`.
- Every API call returns a `SessionSnapshot`; the frontend replaces its state wholesale (DC-UX-03).
- HTTP for state transitions (intent/**chat**/lock/params/clear/workspace). WebSocket for LLM streaming Q&A (`/ws/chat/{id}`) and real-time execution logs (`/ws/execute/{id}`).
- **Three-TAB architecture** (DC-UX-10): Discovery (template search), Q&A (GIS expert chat), Exec (script execution). Each TAB calls a dedicated API — `processIntent` for Discovery, `chatQuestion` for Q&A.
- After WebSocket execution completes, frontend calls `GET /session/{id}` to refresh the updated state.
- Routing uses `HashRouter` (not `BrowserRouter`) because Electron loads from `file://` protocol.
- API base URL is resolved via IPC (`getApiBaseUrl()`) returning an absolute URL like `http://localhost:18000`; the frontend never relies on relative `/api` paths in production.
- Window is frameless (`frame: false`, `titleBarStyle: 'hidden'`) with a custom `TopBar` component providing title, navigation, and window control buttons (minimize/maximize/close) via IPC (`windowControl` API, DC-E07).

### GeneratorPage (J2 Template Wizard)

Five-step wizard at `/#/generator`: Document input → Config → Preview → Review → Save. Step 3 features a Monaco-style code editor (dark theme, line numbers, Tab indentation), inline Jinja2 syntax highlighting, and live re-validation. Step 5 shows a hot-reload confirmation (backend calls `refresh_registry()` on save, new template is immediately available without restart).

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

**Conda environment**: `gis-agent` at `C:\Users\PC\.conda\envs\gis-agent` (Python 3.11.15).

```bash
# Verify GDAL (bash shell)
ogr2ogr --version

# Verify GDAL (Python backend — may differ from bash PATH)
"/c/Users/PC/.conda/envs/gis-agent/python" -c "import shutil; print(shutil.which('ogr2ogr'))"
```

**Important**: In the bash shell used by Claude Code, `conda activate` does not work. Always invoke the environment's Python directly by full path:

```bash
"/c/Users/PC/.conda/envs/gis-agent/python" --version
```

**Production dependencies** (locked): `anthropic`, `jinja2` — no others without explicit approval per constitution.md P5.

**GDAL execution environment**: Script execution environment is configured at runtime via the ExecTab environment panel (not in `config.json`). Users select shell type (`bash`/`cmd`/`powershell`) and optionally a conda environment. The backend validates GDAL availability on demand. `shutil.which('ogr2ogr')` can be used to verify the backend can locate GDAL binaries.

## Commands

### Python (backend)

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

**pytest working directory constraint**: Test paths `tests/unit/` are resolved relative to `SourceCode/`. Running `pytest` outside `SourceCode/` fails because it cannot find the test files. Always execute test commands from within `SourceCode/`.

### Frontend (Electron)

```bash
cd SourceCode/frontend

# Install dependencies (first time)
npm install

# Development: Vite dev server + Electron (concurrently)
npm run electron:dev

# Production build (Vite + electron-builder)
npm run electron:build
```

**Type checking**:

```bash
cd SourceCode/frontend

# Electron main process
./node_modules/.bin/tsc -p electron/tsconfig.json --noEmit

# Frontend renderer
./node_modules/.bin/tsc --noEmit -p tsconfig.json
```

### Running the Application

**Electron desktop app (development)**:

```bash
cd SourceCode/frontend
npm run electron:dev
```

`concurrently` starts both the Vite dev server and Electron. The Electron main process polls `http://localhost:5173` and loads the window once the dev server is ready.

**CLI**:

```bash
cd SourceCode
python start_cli.py
python start_cli.py --workspace /path/to/project
python start_cli.py --dry-run
```

### Development Tools

```bash
# Batch generate J2 templates from GDAL HTML docs
cd SourceCode
python scripts/generate_templates.py \
  --source ../Document/Resource/gdal/build/doc/build/html/programs \
  --output data/templates/ \
  --config config/config.json

# Dry-run preview
python scripts/generate_templates.py --source ... --output ... --dry-run

# Force re-run (ignore breakpoint state)
python scripts/generate_templates.py --source ... --output ... --force
```

## Tool Configuration

`pyproject.toml` configures the development toolchain. Key settings:

- **ruff**: `line-length = 88`, `target-version = "py310"`. `per-file-ignores` exempts `scripts/generate/*.py` and `tests/unit/test_generate_*.py` from import-sorting (`I001`) and line-length (`E501`) rules — these files contain LLM-generated JSON strings and long template bodies where strict formatting is impractical.
- **mypy**: `strict = true`, `python_version = "3.10"`
- **pytest**: `pythonpath = ["src"]` — eliminates manual `PYTHONPATH` setup when running from `SourceCode/`

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

## Key Files

These files are referenced frequently enough to be worth remembering, or they embody cross-cutting design decisions not obvious from the filename alone.

| File | Why It Matters |
|------|---------------|
| `Document/constitution.md` | Source of truth for workflow rules (RED-1: no code without plan), quality gates, change control |
| `Document/spec.md` | All requirements trace back here (F1-F11, P1-P5, UX-1~3) |
| `Document/plan-core.md` | ERROR_RECOVERY design (DC-0048/DC-0049), matching engine (DC-0094), two-stage matching (DC-0098) |
| `Document/plan-ux.md` | WebSocket streaming (DC-UX-04/05), state→UI mapping, Pipeline/Generator UX |
| `Document/plan-electron.md` | Electron shell architecture, IPC design, Python process lifecycle |
| `src/api/routes/session.py` | Two-stage intent matching API (DC-0098) + `POST /chat` for Q&A + `POST /diagnose` for lazy error diagnosis |
| `src/api/websocket/execute.py` | Execution breakpoint: success→IDLE / failure→ERROR_RECOVERY (DC-0048) |
| `src/core/processor.py` | CLI state machine dispatcher; `_handle_error_recovery()` is the CLI-side diagnosis driver |
| `src/core/matching.py` | Unified template matching scoring (keywords=+3, concepts=+2, id/name/desc/notes=+1) |
| `src/llm/prompts.py` | PromptBuilder with 5 scenario-specific system prompts (DC-0071): intent / template-qa / gis-expert / param / diagnosis |
| `src/llm/qa.py` | `answer_question()` — code-level branching: `locked_template` determines template-knowledge vs GIS-expert mode |
| `src/llm/diagnosis.py` | `analyze_execution_error()` — LLM error diagnosis returning structured `ErrorDiagnosis` |
| `frontend/electron/main.ts` | Electron main process: frameless window, Python child process, IPC handlers (file dialogs + window controls) |
| `frontend/electron/preload.ts` | `contextBridge` preload script exposing `selectFile`, `selectDirectory`, `getApiBaseUrl`, `windowControl` |
| `frontend/src/electron-api.ts` | Renderer-side IPC wrappers including `WindowControlAPI` (minimize/maximize/close) |
| `frontend/src/components/TopBar.tsx` | Custom title bar with draggable region and window control buttons (DC-E07) |
| `frontend/src/api/client.ts` | Axios instance with dynamic absolute baseURL via IPC |
| `frontend/src/main.tsx` | Entry point using `HashRouter` (required for `file://` protocol) |
| `frontend/src/pages/MainPage.tsx` | Main UI orchestrator: three-TAB lifecycle, WebSocket execution, state refresh |
| `frontend/src/components/DiscoveryTab.tsx` | Template discovery TAB: unified input box (local filter + intent send), card grid, candidate mode |
| `frontend/src/components/QATab.tsx` | GIS Q&A TAB: chat stream, locked-template badge. Workspace selector removed (moved to ExecTab) |
| `frontend/src/components/ExecTab.tsx` | Script execution TAB: command preview / executing / success / failure states + workspace selector + runtime exec-env panel |
| `frontend/src/components/paramGroups.ts` | Shared parameter grouping rules (input/output, CRS, transform, clip, advanced) used by ParamForm and DetailPanel |
| `frontend/src/api/health.ts` | Health API client — basic status check |
| `frontend/src/components/TabBar.tsx` | TAB switcher bar (Discovery / Q&A / Exec) with message count badge |
| `frontend/src/components/CmdEditor.tsx` | Monaco-style script editor with Jinja2 syntax highlighting, live validation |
| `frontend/src/components/ExecStatusPanel.tsx` | Execution result panel (success/failure) with one-click diagnose button |
| `frontend/src/components/DetailPanel.tsx` | Right-panel state renderer: `PARAM_COLLECT` → ParamForm (grouped); `SCRIPT_PREVIEW` → collapsible ParamForm only (script preview lives in ExecTab CmdEditor); `IDLE` (post-success) → read-only ParamForm showing grouped param values; `ERROR_RECOVERY` → diagnosis panel |
| `frontend/src/pages/GeneratorPage.tsx` | Five-step J2 wizard: Monaco-style editor, inline Jinja2 highlight, live re-validation |
| `src/templates/scanner.py` | `.j2` file scanner — parses comment headers into `TemplateDef` at startup |

### ParamForm readOnly Mode

`ParamForm` supports `readOnly?: boolean`:
- Inputs are disabled, browse buttons hidden
- Footer actions (confirm/cancel) hidden
- Title changes from "参数设置" to "参数值"
- Used by DetailPanel in `IDLE` (post-execution summary) and inside `SCRIPT_PREVIEW` (adjust params)

## Adding New Templates

New GDAL workflows are added by creating a `.j2` file in `SourceCode/data/templates/` with a Jinja2 comment header. The scanner parses the header at startup — no JSON registry edit needed.

**Comment header format**:
```jinja2
{# @id my_template #}
{# @name 我的模板名称 #}
{# @description 一句话描述功能 #}
{# @keyword shp #}
{# @keyword shapefile #}
{# @keyword geojson #}
{# @concept "术语" — 概念解释文本 #}
{# @note 使用前提或注意事项 #}
{# @seealso related_template_id — 关联模板 #}
{# @common_error "错误文本" — 原因与修复建议 #}
{# @param input file_path required 输入文件路径 #}
{# @param output file_path required 输出文件路径 #}
{# @param of format optional 输出格式名称 default=GeoJSON options=GeoJSON,ESRI Shapefile,GPKG,KML #}
{# @param t_srs crs optional 目标坐标系 default=EPSG:4326 #}
```

**Template body rules**:
- Use `{{ param_name | quote }}` for path/string parameters (auto-escapes for shell safety)
- Use `{{ param_name | safe_path }}` for raw path output
- Never use `+` or f-string style concatenation inside templates
- Post-render security check (`ScriptSecurityChecker`) validates for dangerous patterns

After adding a template, restart the application to pick it up (templates are scanned at startup).

## When Working on This Repo

- Before implementing any feature, check if a corresponding `plan-{module}.md` exists in `Document/`. If not, the feature is not yet ready for coding.
- When modifying code, verify the change aligns with the locked plan. If the plan needs updating, follow the change control process in `Document/constitution.md`.
- The `llm/` module is the **only** code allowed to import `anthropic` (CODE-3). Never add anthropic imports outside `llm/`.
- `PromptBuilder` provides **5 scenario-specific methods** (`build_intent_prompt`, `build_template_qa_prompt`, `build_gis_expert_prompt`, `build_param_prompt`, `build_diagnosis_prompt`). Do not add new catch-all methods — each LLM call scene gets its own dedicated prompt.
- `Document/Resource/` is gitignored; do not commit its contents.
- `SourceCode/model/embedding/` contains large model files (deprecated per ADR-0001, no longer used at runtime); should not be committed.
- `SourceCode/config/config.json` is gitignored; never commit credentials.
- `SourceCode/docs/README-UI.md` is outdated (browser UI mode was removed); Electron is the sole graphical entry point.
- The Electron desktop app (`frontend/`) and CLI (`cli/`) are parallel entry points sharing `core/llm/templates`. Changes to business logic affect both UIs.
- Workspace switching (`POST /session/{id}/workspace`) recreates `ParamValidator` and `TemplateEngine` singletons because they hold `Workspace` references. The core `Workspace` singleton is updated via `change_workspace()`. Switching workspace **does not clear** session state (template, params, history, error_context are preserved).
