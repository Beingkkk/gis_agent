# plan-batch-convert

| 项目 | 内容 |
|------|------|
| 版本 | v1.0.0 |
| 状态 | 设计基线（已实现） |
| 日期 | 2026-06-05 |

---

## 1. 设计概述

为 SCRIPT_PREVIEW 状态增加【批量指令】按钮。点击后将当前渲染后的单文件脚本 + 模板元数据发给 LLM，LLM 返回批量遍历脚本建议。下方展开 Markdown 面板直接展示 LLM 回答，用户自行复制使用。

**零侵入**：不改模板系统、参数表单、状态机、执行通路。

---

## 2. 设计决策

### DC-0113: 简化方案 — WebSocket 流式输出，不做脚本替换

**决策**: 前端点击【批量指令】后，通过 WebSocket `/ws/batch-convert/{session_id}` 连接后端，后端流式推送 LLM 生成的批量脚本建议，直接在下方 Markdown 面板展示。用户自行复制脚本内容。不做自动替换、不做成功/失败分支。

**理由**: 改动最小，失败无影响，用户完全掌控。

---

## 3. 接口定义

```python
# api/websocket/batch_convert.py

async def handle_batch_convert_websocket(websocket: WebSocket, session_id: str) -> None:
    """Batch convert WebSocket handler.

    Receives start message, streams LLM response chunks back as
    {type: "chunk", content: "..."} frames, followed by
    {type: "done", content: "..."} or {type: "error", message: "..."}.
    """

class BatchConvertRequest(BaseModel):
    script: str              # 当前渲染后的单文件脚本
    template_name: str       # 模板名称
    params_meta: list[dict]  # 参数定义元数据
    params_values: dict      # 用户实际参数值
```

**Prompt 输入**：模板元数据（参数定义 + 实际值）+ 渲染后脚本。

**WebSocket 协议**：
- Client→Server: `{"type": "start", "script": "...", "template_name": "...", ...}`
- Server→Client chunk: `{"type": "chunk", "content": "..."}`
- Server→Client done: `{"type": "done", "content": "..."}`
- Server→Client error: `{"type": "error", "message": "..."}`

---

## 4. 模块变更清单

| 文件 | 变更 |
|------|------|
| `api/routes/session.py` | 新增 `batch_convert` 接口 |
| `llm/batch_convert.py` | 新增 Prompt 组装 + LLM 调用 |
| `frontend/src/components/ScriptPreview.tsx` | 新增【批量指令】按钮 + Markdown 面板 |

---

## 5. 测试策略

- 单元测试：`build_batch_convert_prompt` 正确组装 Prompt
- 单元测试：接口返回 LLM 回答内容
- 集成测试：端到端按钮点击 → 面板展示

---

## 6. 需求追溯

| 需求 ID | 设计决策 | 代码 |
|---------|---------|------|
| F5 | DC-0113 | `ScriptPreview.tsx` 预览态按钮 |
| P1 | DC-0113 | LLM 只建议，核心命令仍由模板渲染 |
