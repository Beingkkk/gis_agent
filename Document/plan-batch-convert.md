# plan-batch-convert

| 项目 | 内容 |
|------|------|
| 版本 | v1.0.0 |
| 状态 | 草案 |
| 日期 | 2026-06-04 |

---

## 1. 设计概述

为 SCRIPT_PREVIEW 状态增加【批量指令】按钮。点击后将当前渲染后的单文件脚本 + 模板元数据发给 LLM，LLM 返回批量遍历脚本建议。下方展开 Markdown 面板直接展示 LLM 回答，用户自行复制使用。

**零侵入**：不改模板系统、参数表单、状态机、执行通路。

---

## 2. 设计决策

### DC-0113: 简化方案 — LLM 回答直接展示，不做脚本替换

**决策**: 前端点击【批量指令】后，调用后端接口获取 LLM 回答，直接在下方 Markdown 面板展示。用户自行复制脚本内容，粘贴到执行窗口。不做自动替换、不做成功/失败分支。

**理由**: 改动最小，失败无影响，用户完全掌控。

---

## 3. 接口定义

```python
# api/routes/session.py

@router.post("/session/{session_id}/batch-convert")
async def batch_convert(session_id: str, request: BatchConvertRequest) -> BatchConvertResponse:
    """将单文件脚本提交给 LLM，获取批量遍历脚本建议。"""

class BatchConvertRequest(BaseModel):
    script: str           # 当前渲染后的单文件脚本
    template_id: str      # 模板 ID
    params: dict[str, str]  # 用户实际参数值

class BatchConvertResponse(BaseModel):
    content: str  # LLM 原始回答（Markdown 格式）
```

**Prompt 输入**：模板元数据（参数定义 + 实际值）+ 渲染后脚本。

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
