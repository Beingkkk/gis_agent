# plan-j2-generate v3.0.0

---

## 9. R1: Unified Generation Engine

### 9.1 Problem
Two independent generation logics exist. API uses simplified prompt + simple JSON parsing. CLI uses rich system prompt + few-shot examples + robust JSON parsing + param sanitization + auto-complete.

### 9.2 DC-0094: Extract shared engine to src/llm/
Extract complete generation engine into src/llm/template_generator.py. Both API and CLI call this module.

### 9.3 New file: src/llm/template_generator.py
Contains: ParamDef, TemplateDefinition, ExtractedDoc data models; _SYSTEM_PROMPT, _FEW_SHOT_EXAMPLES constants; _strip_markdown_json, _fix_json_keys, _parse_json_forgiving utilities; _sanitize_param, _extract_template_vars, parse_template_def utilities; TemplateGenerationEngine class with generate() sync mode and generate_stream() streaming mode.

### 9.4 Modified files
src/llm/__init__.py: export TemplateGenerationEngine. src/api/routes/generator.py: delete _build_generate_prompt and _parse_generated_response, use TemplateGenerationEngine. scripts/generate/generator.py: backward-compatible wrapper importing from src/llm.

---

## 10. R2: Multi-file Document Import with Token Budget Check

### 10.1 Problem
POST /generator/parse-document accepts only single file. LLMClient.MAX_INPUT_TOKENS=2000 silently truncates oversized input.

### 10.2 DC-0095: Multi-file import with explicit token budget
1. parse-document accepts file array. 2. Backend merges cleaned texts. 3. If exceeds budget, return 413 with token count. 4. Frontend shows file list with per-file and total counts.

### 10.3 API Changes
Request: {files: [{content, file_type}]}. Response: adds files[], total_raw_chars, total_cleaned_chars, estimated_tokens. Error 413 when estimated_tokens > 2000.

### 10.4 Frontend Changes
Step 1: multiple file input, file list table with raw/cleaned chars, total tokens display, red warning when over budget, delete individual files, disabled Next button when over budget.

---

## 11. R3: WebSocket Streaming Generation

### 11.1 Problem
HTTP POST has 30s timeout. LLM generation takes 20-60s, causing frequent timeouts.

### 11.2 DC-0096: WebSocket streaming template generation
New endpoint /ws/generator/generate/{session_id}. Frontend connects WebSocket on Step 2 Generate click. Backend streams chunks via generate_stream(). After completion, pushes parsed JSON result.

### 11.3 Protocol
Client->Server: {type: start, document_text, config}. Server->Client chunk: {type: chunk, content}. Server->Client done: {type: done, result}. Server->Client error: {type: error, message, stage}.

### 11.4 Backend
New src/api/websocket/generator.py: handle_generator_websocket(). Runs engine.generate_stream() in thread pool. Sends chunks via asyncio.run_coroutine_threadsafe(). Collects full text, parses, renders J2, sends done/error.

### 11.5 Frontend
New frontend/src/hooks/useGeneratorWebSocket.ts: generate(), cancel(), returns isConnected, isGenerating, streamedText. GeneratorPage Step 2: streaming panel with spinner + live text + cancel button.

### 11.6 HTTP Fallback
POST /generator/generate kept, internally calls TemplateGenerationEngine.generate() sync mode.

---

## 12. Test Plan

R1: test_template_generator_sync, test_template_generator_stream, test_parse_json_forgiving_bare_keys, test_sanitize_param_required_default, test_auto_complete_undeclared_vars, test_api_uses_shared_engine, test_cli_backward_compat.

R2: test_parse_document_multi_file, test_parse_document_token_budget_pass, test_parse_document_token_budget_exceed, test_parse_document_mixed_types, test_parse_document_separator.

R3: test_generator_websocket_connect, test_generator_websocket_stream_chunks, test_generator_websocket_done_result, test_generator_websocket_error_parse, test_generator_websocket_cancel, test_http_fallback_still_works.

Integration: test_e2e_generate_via_websocket, test_e2e_multi_file_parse_then_generate, test_e2e_token_budget_blocks_generation.

---

## 13. Task Breakdown

R1: T-GEN-R1-01~08 (create engine, sync mode, stream mode, exports, CLI wrapper, API integration, tests, verify).

R2: T-GEN-R2-01~05 (models, endpoint, frontend API, frontend UI, tests).

R3: T-GEN-R3-01~07 (WS handler, register endpoint, hook, frontend integration, HTTP fallback, WS tests, integration tests).

---

## 14. Document Updates

New DC: DC-0094, DC-0095, DC-0096.

Modified DC: DC-0090 (add template_generator.py as unified entry), DC-0088 (multi-file array, token budget).

New endpoints: WS /ws/generator/generate/{session_id}.

Modified endpoints: POST /generator/parse-document (multi-file, 413), POST /generator/generate (internal engine change).

New files: src/llm/template_generator.py, src/api/websocket/generator.py, frontend/src/hooks/useGeneratorWebSocket.ts, tests/unit/test_llm_template_generator.py, tests/unit/test_generator_parse_multi.py, tests/unit/test_websocket_generator.py.

Modified files: src/llm/__init__.py, src/api/routes/generator.py, src/api/main.py, scripts/generate/generator.py, frontend/src/api/generator.ts, frontend/src/pages/GeneratorPage.tsx.
