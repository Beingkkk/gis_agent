# plan-ux

| 项目 | 内容 |
|------|------|
| 版本 | v1.13.0 |
| 状态 | 设计基线 |
| 作者 | - |
| 日期 | 2026-06-02 |

---

## 1. 设计概述

### 1.1 模块职责

实现 GIS Agent 的图形用户界面：基于 Electron 桌面的前端交互层，通过 HTTP API 和 WebSocket 与后端通信。本模块**替换原有的 CLI 层（`cli/`）**，复用 core、llm、templates 三层业务逻辑，将 REPL 文本交互升级为可视化卡片、表单、对话流的交互范式。

本模块同时覆盖 Pipeline 多任务串行和 J2 模板生成器两个新增功能的 UX。

### 1.2 所属架构层次

前端层（`frontend/`）+ API 层（`api/`）。

- `frontend/` 为纯前端代码（React + TypeScript），通过 HTTP/WebSocket 调用后端
- `api/` 为后端适配层（FastAPI），将现有 core/llm/templates 能力暴露为 REST + WS 接口
- `core/`、`llm/`、`templates/` 完全复用，**不做任何修改**

### 1.3 对应需求项

| 需求 ID | 需求描述 |
|:-------:|---------|
| F5 | 向用户完整展示脚本内容，要求明确确认后执行（UI 按钮替代 Y/N） |
| F8 | 会话内记忆（多轮追问和补充） |
| P2 | 先展后行：脚本预览 + 确认执行 |
| UX-1 | 模板以卡片形式浏览，参数以表单形式填写 |
| UX-2 | Pipeline 多任务串行的可视化编辑和合并脚本生成 |
| UX-3 | J2 模板生成器：文档输入 → LLM 生成 → 审查 → 保存 |

---

## 2. 设计决策

### DC-UX-01: 采用 Electron 桌面外壳 + FastAPI 后端（方案B）

**决策**: 前端使用 React + TypeScript + Vite 构建，通过 Electron 桌面外壳提供原生文件系统访问能力。后端使用 FastAPI 提供 HTTP API 和 WebSocket，作为 Electron 主进程启动的独立 Python 子进程运行。

**历史**: v1.0.0 原决策为纯浏览器方案（React + FastAPI，用户手动启动后端并打开浏览器），因标准浏览器无法通过 `<input type="file">` 获取本地文件系统绝对路径（F6/F7 需求无法满足），于 v1.3.0 废弃。

**理由**:
- 标准浏览器的安全沙箱禁止返回绝对文件路径，导致工作空间设置和参数路径浏览功能无法正常工作
- Electron 通过 `dialog.showOpenDialog` 可获取完整绝对路径，解决核心痛点
- Python FastAPI 作为独立子进程运行，后端代码零改动（参见 plan-electron DC-E01）
- 前端业务逻辑（React 组件、状态管理、API 调用）基本不变，仅需替换文件浏览实现（参见 plan-electron DC-E04）
- 路由采用 `HashRouter`（`react-router-dom`），兼容 Electron `file://` 协议

**替代方案（已否决）**:
- 继续使用浏览器：`<input type="file">` 无法返回绝对路径，工作空间和参数路径功能不可用
- Electron 全内置方案（Python 打包进 Electron）：conda + GDAL 打包复杂，包体积过大，违反 DEP-4

### DC-UX-02: CLI 状态机直接映射为 UI 状态，不改核心逻辑

**决策**: `core/models.py` 中的 `SessionState` 6 状态 Enum 保持不变。UI 层通过 `Session.state` 值判断当前应渲染的界面元素。

**理由**:
- 状态机是核心资产，其正确性已在 CLI 中验证
- UI 只是状态机的另一种呈现方式，状态流转规则完全一致
- 避免为 UI 引入第二套状态管理，防止状态不一致

**映射关系**:

| SessionState | UI 表现 | 用户操作 |
|-------------|---------|---------|
| `IDLE` | 模板识别 TAB | 浏览模板卡片网格或搜索，自由问答 |
| `INTENT_CONFIRM` | 模板识别 TAB | 显示 LLM 匹配的候选模板列表，用户点击"确认" |
| `PARAM_COLLECT` | 模板识别 TAB + 右侧面板 | 右侧面板展开参数表单，用户填写；可随时点击"预览命令"查看生成的 bash |
| `SCRIPT_PREVIEW` | 脚本执行 TAB | 命令预览态：显示生成的 bash 命令（点击刷新更新），提供"执行"/"返回修改"按钮 |
| `EXECUTING` | 脚本执行 TAB | 执行中态：实时输出日志，显示进度，可取消 |
| `ERROR_RECOVERY` | 脚本执行 TAB | 失败态：自动诊断 + 诊断结果面板 + 错误输出 + 修改参数 / 放弃任务 |

**状态 → TAB 路由**：

| 状态 | 自动激活的 TAB |
|------|---------------|
| `IDLE` / `INTENT_CONFIRM` / `PARAM_COLLECT` | 模板识别 |
| `SCRIPT_PREVIEW` / `EXECUTING` | 脚本执行 |
| `ERROR_RECOVERY` | 脚本执行 |

### DC-UX-03: Session 对象由后端维护，前端仅持有 session_id

**决策**: 前端不维护完整的 `Session` 对象，每次交互携带 `session_id`，后端返回更新后的 `Session` 快照。前端根据快照更新 UI。

**理由**:
- `Session` 是核心层复杂数据结构，前端不需要了解其内部结构
- 前端只需消费 `Session` 中用于展示的字段（state、task_context、params、history）
- 防止前后端状态漂移

**接口示例**:
```typescript
// 前端持有的最小状态
interface UIState {
  sessionId: string;
  state: 'IDLE' | 'INTENT_CONFIRM' | 'PARAM_COLLECT' | 'SCRIPT_PREVIEW' | 'EXECUTING' | 'ERROR_RECOVERY';
  taskContext: TaskContext | null;
  messages: ChatMessage[];
  lockedTemplateId: string | null;
}
```

### DC-UX-04: LLM 流式输出通过 WebSocket 推送

**决策**: Q&A 对话和脚本生成等需要流式输出的场景，使用 WebSocket 连接，后端将 LLM 的 `on_chunk` 回调内容逐片推送到前端。

**理由**:
- `llm/chat_stream()` 和 `llm/answer_question()` 已通过 `on_chunk` 回调支持流式（DC-0068/DC-0069）
- 后端只需将 callback 接入 WebSocket send，无需改动 LLM 层
- SSE 在重新连接时容易丢失中间状态，WebSocket 更适合持续会话

### DC-UX-05: 脚本执行日志通过 WebSocket 实时推送

**决策**: 脚本执行不再使用 `subprocess.run()` 的阻塞模式，改用 `subprocess.Popen()` 逐行读取 stdout/stderr，通过独立 WebSocket 连接推送到前端。

**理由**:
- UI 需要实时展示执行进度（如 `0...10...20...`），阻塞模式无法提供增量输出
- 与 CLI 的 `--dry-run` 模式兼容：dry-run 时只返回脚本预览，不启动 subprocess
- 脚本执行不设固定超时，由子进程自然完成；前端通过 WebSocket 实时输出执行日志。GDAL 数据处理（如大栅格重投影、批量矢量转换）可能耗时数小时，强制超时会导致用户任务被异常中断

### DC-UX-06: Pipeline 多任务在 core 层外独立管理

**决策**: Pipeline（多任务串行）不改动 `Session` 状态机，而是在前端维护一个 `Pipeline` 对象，提交执行时由后端合并为单脚本。

**理由**:
- `Session` 状态机设计为单任务生命周期，引入 Pipeline 会显著增加复杂度
- Pipeline 本质是多张模板的参数组合 + 步骤间自动关联，前端天然适合管理这种列表结构
- 执行时后端将 Pipeline 展开为多步骤脚本，复用现有 `ScriptExecutor`

**Pipeline 结构**:
```typescript
interface Pipeline {
  id: string;
  steps: PipelineStep[];        // 有序步骤列表
  autoLinks: DataLink[];        // 步骤间自动关联规则
}

interface PipelineStep {
  order: number;
  templateId: string;
  params: Record<string, string>;
}

interface DataLink {
  fromStep: number;
  fromParam: string;            // 通常是 "output"
  toStep: number;
  toParam: string;
}
```

### DC-UX-07: 模板生成器作为独立子页面

**决策**: J2 模板生成器（LLM 驱动的文档→模板）不集成在主应用状态机中，而是作为独立路由 `/generator`，完成后返回主应用。

**理由**:
- 模板生成是开发工具，使用频率远低于主任务流程
- 独立页面避免干扰主应用的状态管理
- 生成器有自己的 5 步向导（文档输入 → 配置 → 预览 → 审查 → 保存），不适合塞进主状态机

### DC-0095: 前端 ParamForm 支持新参数类型的差异化渲染

**决策**: `ParamForm` 根据参数类型渲染不同的表单控件：

| 类型 | 控件 | 属性 |
|------|------|------|
| `boolean` | select | 是/否 |
| `enum` | select | options 列表 |
| `format` | select | options 列表（可差异化显示 GDAL 图标） |
| `text` | textarea | rows=4 |
| `integer` | input | type="number", step="1" |
| `float` | input | type="number", step="any" |
| `file_path` | input + button | 浏览按钮（占位） |
| `folder_path` | input + button | 浏览按钮（占位） |
| `string` / 其他 | input | type="text" |

**理由**:
- 用户看到 `of` 参数时直接看到下拉框而非空白文本框
- textarea 适合多行输入（如 WKT 坐标系定义）
- number input 的 step 属性影响浏览器的增减按钮行为

### DC-0096: 模板卡片列表搜索包含 keywords

**决策**: `TemplateCardList` 的客户端搜索过滤在现有 `name`、`id`、`description` 基础上，增加 `keywords` 字段的匹配。

**理由**:
- 用户搜索 "shp" 时应显示所有含该关键词的模板
- 与后端匹配逻辑一致（DC-0090 / DC-0094）

### DC-0097: API 响应模型透传 keywords 和 options

**决策**: `TemplateDefResponse`、`TemplateDetailResponse`、`ParamDefResponse` 分别新增 `keywords` 和 `options` 字段，后端从 `TemplateDef` / `ParamDef` 原样透传。

**理由**:
- 前端需要 keywords 做搜索（DC-0096）
- 前端需要 options 做下拉框渲染（DC-0095）
- 默认值确保旧客户端忽略未知字段

### DC-UX-08: 参数面板采用分组折叠 + 水平行布局 + 扩宽面板

**决策**: `ParamForm` 渲染方式全面重构：

1. **面板扩宽**：`DetailPanel` 容器从 `w-[360px]` 扩至 **`w-[580px]`**，`Layout` 中主交互区相应缩小（左栏 300px 已移除并入 TAB），确保参数面板有足够水平空间。
2. **水平行布局**：每个参数渲染为一行，Label 列固定宽度左对齐（`w-[140px]`），Input 列弹性填充。Label 区域包含参数名、必填标记 `*`、信息图标 `?`、类型标签。
3. **参数分组折叠**：参数按逻辑分组渲染为可折叠的 Accordion 面板。分组通过前端**启发式规则**推断，不修改模板系统和 `@param` 注释格式。
4. **默认展开策略**：含必填参数的分组默认展开；全为可选参数的分组默认折叠。

**分组推断规则**（前端 `inferParamGroup()` 实现）：

| 分组名 | 匹配规则（参数名关键词） |
|--------|------------------------|
| 输入输出 | `input`, `output`, `of`, `format`, `input_layer`, `output_layer`, `output_dir` |
| 坐标系设置 | `s_srs`, `t_srs`, `srs`, `crs`, `rpc`, `geoloc` |
| 变换选项 | `resampling`, `xres`, `yres`, `order`, `et`, `te`, `ts`, `tr`, `tap` |
| 裁剪与范围 | `cutline`, `crop_to_cutline`, `projwin`, `srcwin`, `extent` |
| 高级选项 | `overwrite`, `quiet`, `multi`, `dstalpha`, `update`, `append`, `upsert`, `skip_errors`, `processes`, `nodata` |
| 其他选项 | 未匹配到的参数统一归入此组 |

**理由**:
- 垂直单列布局在参数超过 8 个时产生大量滚动，体验差
- 水平行布局将每个参数的垂直占用从 ~80px 压缩到 ~40px，参数密度翻倍
- 分组折叠将次要参数隐藏，减少视觉噪音，突出核心参数
- 方案 B（前端启发式）避免修改模板注释格式、扫描器、API 模型等后端代码，实现成本低

**局限与后续**:
- 规则为启发式，特殊模板的参数可能分错组；若后续模板系统原生支持分组（plan-templates DC-00xx），可无缝替换为后端提供的分组信息
- 规则表维护在前端代码中，新增非常规参数名时需要补充规则

### DC-UX-09: 描述文字 Tooltip 化 + 进度条替代 Dot 指示器

**决策**: `ParamForm` 视觉细节优化：

1. **描述文字 Tooltip 化**：参数描述文字不再常驻显示在输入框下方，而是隐藏在信息图标 `?` 的 hover tooltip 中。tooltip 采用深色背景（`bg-slate-800`），左侧小三角箭头，最大宽度 260px。
2. **进度条替代 Dot 指示器**：原来的逐参数 dot 指示器（`●●●○○`）替换为细进度条 + 文字「N / M 已填写」。进度条高度 5px，蓝色渐变填充，带宽度动画过渡。
3. **类型标签彩色化**：每个参数旁显示彩色小标签标明数据类型（`file_path`=黄色、`enum`=紫色、`crs`=粉色、`boolean`=绿色、`number`=蓝色、`text`=灰色）。
4. **输入框填充状态视觉反馈**：已填写参数边框变为 emerald（`border-emerald-200 bg-emerald-50`），与空状态区分。

**理由**:
- 描述文字常驻占用大量垂直空间；对重复使用该模板的用户，描述是冗余信息
- Dot 指示器在参数超过 12 个时换行混乱，进度条更紧凑且信息量相同
- 类型标签让用户不用看输入控件就能预判参数类型，减少认知负担
- 填充状态反馈让用户一眼看出哪些参数已填、哪些还需填写

### DC-UX-10: 三 TAB 分离：模板识别 / GIS 问答 / 脚本执行

**决策**: 将模板搜索匹配、知识问答、脚本执行从混合的聊天区分离为三个独立的顶部 TAB。每个 TAB 对应独立的后端 API，代码层面决定场景，不依赖 LLM 猜测用户意图。

| TAB | 职责 | 后端 API | 历史存储 | 典型内容 |
|-----|------|---------|---------|---------|
| **模板识别** | 搜索模板、LLM 意图匹配、选中模板 | `POST /session/{id}/intent` | `session.history`（流程消息） | 模板卡片网格、分类过滤芯片、候选模板列表（带置信度） |
| **GIS 问答** | 学习 GIS 概念、问参数含义、获取使用建议 | `WS /ws/chat/{id}`（流式） | `session.qa_history`（多轮对话，DC-0107） | 聊天消息流、快捷问题建议 |
| **脚本执行** | 命令预览、执行、结果查看 | `WS /ws/execute/{id}` | 无 | 命令编辑器、实时日志、成功/失败结果 |

**DiscoveryTab（模板识别）约束**：
- 所有输入走 `process_intent()`，**仅做意图匹配，不做问答**
- 不再通过关键词（如"什么""怎么"）判断是否为问答请求
- 用户有纯问答需求时，需切换到 GIS 问答 TAB
- 意图匹配过程中显示加载提示（"正在分析您的需求..."）
- 匹配完成后根据结果给出状态反馈：
  - **高置信度匹配**（`PARAM_COLLECT`）：轻量绿色提示"✓ 已确认模板，请填写参数"
  - **候选模式**（`INTENT_CONFIRM`）：展示候选模板列表供用户选择
  - **未匹配**（`INTENT_CONFIRM` 无候选）：黄色提示"未找到匹配的模板，请尝试其他描述或手动选择"

**QATab（GIS 问答）约束**：
- 所有输入走 WebSocket `/ws/chat/{id}`（前端），**始终视为问答请求，不做意图匹配**
- 后端根据 `session.template` 是否存在，代码层面选择模板知识问答或 GIS 专家问答
- `answer_question()` 的 history 从 `session.qa_history` 读取，对话完成后写回 `qa_history`（DC-UX-14）
- 提问"这个模板的参数怎么填"时，若已锁定模板则基于模板上下文回答；若未锁定则作为 GIS 专家问题回答

**GIS 问答 TAB 的特殊机制**：
- 提供"清空会话"按钮，一键清除前端 `qaMessages` 本地状态
- 当用户已选中模板时，问答上下文自动绑定该模板的元数据（`@concept`、`@note`、`@common_error`），AI 回答会引用模板知识
- 诊断结果直接在脚本执行 TAB 的诊断结果面板中展示，不跳转 Q&A TAB
- 前端 `qaMessages` 与后端 `qa_history` 读写分离（DC-UX-15）：前端维护本地消息列表用于渲染，后端维护 `qa_history` 用于 LLM 多轮上下文

**理由**：
- 模板搜索和知识问答虽然都使用 LLM，但目的不同、交互模式不同、历史策略不同，混在一起会让用户困惑
- 旧设计中通过关键词（"什么""怎么"等）判断用户意图，存在误判风险；改为 UI 层面 + 代码层面分离后，意图判断零歧义
- 模板识别需要"干净 slate"（每次输入独立匹配），而问答需要"累积上下文"（多轮追问）
- 分离后两个 TAB 的界面可以针对各自场景优化（卡片网格 vs 消息流）

### DC-UX-11: 脚本执行 TAB：命令预览 + 执行 + 结果

**决策**: 确认参数后自动切换到脚本执行 TAB。该 TAB 包含四种状态：

| 状态 | 触发条件 | 界面内容 | 用户操作 |
|------|---------|---------|---------|
| **命令预览** | 确认参数后自动进入；或填参数过程中手动点击"预览命令" | 命令编辑器（显示生成的 bash）、参数摘要表 | 点击"刷新"更新命令、点击"执行"启动、点击"导出脚本"选择目录保存、点击"返回修改"回到参数面板 |
| **执行中** | 点击"执行"后 | 转圈状态条 + 执行命令 + 实时日志输出（黑色终端风格） | 点击"取消"终止执行 |
| **成功** | 执行返回码 0 | 绿色成功卡片 + 结果详情表（输出文件、大小、坐标系、耗时） | "新任务" |
| **失败** | 执行返回码非 0 | 红色失败卡片 + 诊断结果 + 错误输出（bash 面板） | "修改参数"、"放弃任务" |

**命令预览刷新机制**：
- 用户调整参数后，点击"刷新"按钮才重新生成并显示命令（非实时刷新）
- 参数未填完时允许进入预览态，但"执行"按钮禁用，提示"还有 N 个必填参数"

**导出脚本机制**（DC-UX-11a）：
- 触发：命令预览态点击"导出脚本"按钮
- 流程：前端调用 IPC `saveFile` → 用户选择保存路径和文件名 → 前端将路径发给后端 `POST /session/{id}/export-script` → 后端按当前 shell 类型生成对应格式的脚本文件 → 保存到用户指定路径
- 默认文件名：`script_{template_id}_{timestamp}.{ext}`（ext 根据 shell 类型：`.bat` / `.sh` / `.ps1`）
- 导出操作不影响当前会话状态，不触发状态机流转

**执行历史策略**：单次任务内多次执行覆盖上一次的日志，始终只展示当前任务的最新状态。

**理由**:
- 脚本展示、执行、结果查看是同一任务的连续阶段，放在同一视图内比分散在聊天流中更直觉
- 命令编辑器让用户在执行前最后确认命令内容，符合 P2"先展后行"
- 成功/失败结果在同一位置呈现，用户不需要在多个区域间跳转

### DC-UX-12: 自动诊断：执行失败 LLM 诊断

**决策**: 脚本执行失败时，系统**自动触发** LLM 诊断，诊断结果直接展示在脚本执行 TAB 的【诊断结果】面板中，**不跳转**到其他 TAB。

1. **自动触发**：WebSocket 执行完成后，若返回码非 0，后端自动调用 `diagnoseSession` 进行 LLM 诊断
2. **收集上下文**：模板名称、模板 ID、模板元数据（`@note`、`@common_error`）、参数值列表、生成的执行命令、stdout、stderr、返回码、工作空间路径、执行耗时
3. **LLM 诊断**：后端使用专门的诊断 Prompt，结合模板 `@common_error` 和错误输出进行推理，返回根因分析和修复建议
4. **结果展示**：诊断结果（根因、建议、可自动修复状态）直接渲染在脚本执行 TAB 的【诊断结果】面板中，与错误输出同屏展示

**诊断 Prompt 设计要点**：
- 系统 Prompt 明确 instruct："你是一个 GDAL 命令行工具的错误诊断专家，分析以下执行错误，结合模板和参数上下文，判断错误根因并给出修复建议"
- 用户消息包含：模板描述、参数值、执行命令、错误输出、相关 `@common_error`
- 要求 LLM 输出：
  - `cause`：错误根因，用中文简洁描述
  - `suggestion`：修复建议。当 `can_auto_fix=true` 时，必须在建议末尾换行并写入【修复命令参考】，随后换行用三个反引号包裹修正后的完整 GDAL 命令
  - `fixed_params`：修正后的参数键值对
  - `confidence`：置信度 0.0–1.0
  - `can_auto_fix`：是否可自动修复
- `can_auto_fix` 判定规则（严格执行）：
  - `true`：错误根因明确为参数值问题（路径不存在、坐标系错误、格式不支持、必填参数缺失），修改参数值后重新执行同一模板即可修复
  - `false`：以下情况必须设为 false——系统级问题（权限不足、GDAL 版本不支持、驱动缺失、数据损坏）、模板渲染逻辑错误（参数值为 false 时模板仍输出标志位、多个互斥参数同时输出）、需要修改模板文件本身才能修复的问题、需要用户手动判断修复策略的情况
  - `confidence < 0.5` 时，`can_auto_fix` 必须设为 false
- 诊断结果面板使用 `ReactMarkdown` 渲染 suggestion，LLM 输出的 markdown 代码块自动高亮显示

**理由**:
- 诊断结果与错误输出同屏展示，用户无需在 TAB 间跳转即可获取完整信息
- 自动触发避免用户手动点击，减少操作步骤
- 诊断结果面板与 Q&A TAB 分离，保持问答历史独立
- 诊断结果支持用户点击"修改参数"后直接修复参数并重新执行

### DC-UX-13: 布局从三栏变为两栏 + 三 TAB

**决策**: 移除独立的模板列表侧边栏（原 300px），将其功能并入模板识别 TAB。主交互区改为 flex-1 自适应。参数面板从 520px 扩宽至 **580px**。

**新布局**：

```
┌─────────────────────────────────────────┬──────────────────────┐
│ TopBar                                   │                      │
├──────────────────────────────────────────┼──────────────────────┤
│ [🔍模板识别] [💬GIS问答] [⚡脚本执行]      │   参数/详情面板      │
│                                          │   580px              │
├──────────────────────────────────────────┤                      │
│                                          │                      │
│  TAB 内容区                               │                      │
│  （根据选中 TAB 和状态切换）               │                      │
│                                          │                      │
│  flex-1                                  │   flex-shrink-0      │
│                                          │                      │
└──────────────────────────────────────────┴──────────────────────┘
```

**理由**:
- 模板列表和聊天区本质上都是"找模板"，合并到同一 TAB 减少了用户的认知负担
- 释放的 300px 空间分配给参数面板，让参数表单更从容（label 列从 140px → 160px）
- 三 TAB 的切换比在三栏间跳转更符合用户的任务流（发现 → 配置 → 执行）

### DC-UX-14: WebSocket Q&A 写回 qa_history

**决策**: `handle_chat_websocket` 在每次 Q&A 对话完成后，将 user 消息和 assistant 回复追加到 `session.qa_history`（而非 `session.history`）。

**理由**:
- 当前 WebSocket chat handler 读取 `session.history` 作为 `answer_question()` 的上下文，但对话完成后不写入任何消息 → QATab 多轮对话形同单轮（DC-0107）
- 写入 `qa_history` 而非 `history`，确保 QATab 历史与 Discovery/Exec 历史隔离
- WebSocket Q&A 是前端 QATab 的**唯一**入口（HTTP fallback `/session/{id}/chat` 保留但前端不使用）

**实现要点**:
1. WebSocket 收到用户消息后，先追加到 `session.qa_history`
2. `answer_question()` 的 `history` 参数从 `session.qa_history` 读取（含当前轮次）
3. LLM 流式输出完成后，将完整 assistant 回复追加到 `session.qa_history`
4. 返回 `{"type": "done"}` 给前端

### DC-UX-15: QATab 消息完全隔离，前端独立维护 qaMessages

**决策**: 前端 `QATab` 的消息列表完全由前端本地状态 `qaMessages`（Zustand）维护，不依赖后端 `SessionSnapshot.history`。后端 `qa_history` 仅用于 LLM 多轮上下文，不向前端透传。

**理由**:
- QATab 的消息是"对话流"，需要前端本地维护才能支持流式输出（chunk-by-chunk 更新）
- 如果前端依赖后端 history，每次 Q&A 后需要额外 HTTP 请求刷新，增加延迟且破坏流式体验
- 后端 `qa_history` 的职责：**仅**为 `answer_question()` 提供多轮上下文；前端的职责：管理消息渲染和流式更新
- `SessionSnapshot` 不再包含 `qa_history`，减少每次 API 调用的 payload

**与 DC-0107 的关系**：后端 `Session.qa_history` ↔ 前端 `useSession.qaMessages` 是读写分离的镜像：后端写（WebSocket handler）、前端读（本地状态）。两者不直接同步，但都按 (user, assistant) 顺序累积。

---

## 3. 接口定义

### 3.1 REST API

```python
# api/routes/session.py

@router.post("/session", response_model=SessionResponse)
async def create_session() -> Session:
    """创建新会话，返回 session_id 和初始状态。"""

@router.post("/session/{session_id}/intent", response_model=SessionResponse)
async def process_intent(session_id: str, request: IntentRequest) -> Session:
    """DiscoveryTab 用户输入自然语言需求，返回匹配模板和候选列表。

    **此接口不处理 Q&A**，仅做意图匹配。Q&A 请使用 `/session/{id}/chat`。

    两阶段匹配（DC-0098）：
    1. 对所有模板执行关键词打分（score_template_match）
    2. 高分快速路径（≥ 8）→ 直接 PARAM_COLLECT
    3. 否则取 top-10 候选池，调用 LLM 精排（classify_intent，不传 history，DC-0106）
    4. 按 LLM confidence 自动决策：
       ≥ 0.85 → PARAM_COLLECT（绝对优势，自动选中）
       ≥ 0.50 → INTENT_CONFIRM（返回 top-1 推荐 + 备选）
       < 0.50 → INTENT_CONFIRM（返回 top-3 关键词候选）
    """

@router.post("/session/{session_id}/chat", response_model=SessionResponse)
async def chat_question(session_id: str, request: IntentRequest) -> Session:
    """QATab 用户提问（HTTP fallback，前端使用 WebSocket `/ws/chat/{id}`）。

    不走意图匹配，直接调用 `answer_question()`：
    - history 从 `session.qa_history` 读取（DC-0107）
    - 若 session 已锁定模板 → 基于模板上下文回答（模板知识问答）
    - 若 session 无锁定模板 → GIS 专家问答（无模板上下文）

    对话完成后将 user + assistant 消息写入 `session.qa_history`（DC-UX-14）。
    返回 IDLE 状态 + agent 回复消息。
    """

@router.post("/session/{session_id}/lock", response_model=SessionResponse)
async def lock_template(session_id: str, request: LockRequest) -> Session:
    """用户确认模板，进入 PARAM_COLLECT 状态。"""

@router.post("/session/{session_id}/params", response_model=SessionResponse)
async def submit_params(session_id: str, request: ParamsRequest) -> Session:
    """提交参数，返回渲染后的脚本预览（SCRIPT_PREVIEW）。"""

@router.post("/session/{session_id}/execute", response_model=ExecutionResponse)
async def execute_script(session_id: str, dry_run: bool = False) -> ExecutionResponse:
    """确认执行脚本。实际执行走 WebSocket，此接口仅触发。"""

@router.post("/session/{session_id}/export-script")
async def export_script(session_id: str, request: ExportScriptRequest) -> ExportScriptResponse:
    """导出脚本到用户指定路径。

    根据 session 的模板 + 参数 + 当前 shell 类型渲染脚本内容，
    写入用户选择的本地文件路径。不影响会话状态。

    Request:
        {"output_path": "C:\\Users\\PC\\Desktop\\script_shp2geojson_1234567890.bat"}

    Response:
        {"success": true, "path": "...", "size": 256}
    """

@router.post("/session/{session_id}/clear")
async def clear_session(session_id: str):
    """清空会话，重置为 IDLE。"""

# api/routes/templates.py

@router.get("/templates", response_model=List[TemplateDef])
async def list_templates() -> List[TemplateDef]:
    """返回所有扫描到的模板列表（复用 TemplateRegistry）。"""

@router.get("/templates/{template_id}", response_model=TemplateDetail)
async def get_template(template_id: str) -> TemplateDetail:
    """返回模板详情（参数定义、概念、注意事项、错误说明）。"""

# api/routes/pipeline.py

@router.post("/pipeline", response_model=ScriptPreview)
async def preview_pipeline(request: PipelineRequest) -> ScriptPreview:
    """提交 Pipeline，返回合并后的多步骤脚本预览。"""

@router.post("/pipeline/execute")
async def execute_pipeline(request: PipelineRequest) -> ExecutionResponse:
    """执行 Pipeline 合并脚本。"""

# api/routes/generator.py (模板生成器)

@router.post("/generator/generate", response_model=GeneratedTemplate)
async def generate_template(request: GenerateRequest) -> GeneratedTemplate:
    """提交文档和配置，LLM 生成 J2 模板。"""

@router.post("/generator/validate")
async def validate_template(request: ValidateRequest) -> ValidationResult:
    """对生成的模板进行安全扫描和语法校验。"""

@router.post("/generator/save")
async def save_template(request: SaveRequest):
    """保存审查通过的模板到 data/templates/ 目录。"""
```

### 3.2 WebSocket 接口

```python
# api/websocket.py

class ChatWebSocket:
    """Q&A 流式对话。前端发送消息，后端通过 LLM 流式推送回复。

    每轮对话完成后将 user + assistant 消息写入 session.qa_history（DC-UX-14）。
    answer_question() 的 history 参数从 session.qa_history 读取（DC-0107）。
    """
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        # 复用 llm/answer_question() 的 on_chunk 回调
        # 每收到一个 chunk，websocket.send_text(chunk)
        # 对话完成后：session.with_qa_history(user_msg) + session.with_qa_history(assistant_msg)

class ExecuteWebSocket:
    """脚本执行实时日志。前端连接后，后端启动 subprocess 并逐行推送输出。"""
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        # 使用 subprocess.Popen 而非 run
        # 逐行读取 stdout/stderr，websocket.send_text(line)
        # 完成后发送 {"type": "done", "success": true/false, "returncode": N,
        #            "stdout": "...", "stderr": "...", "duration_ms": N}
```

### 3.3 核心数据结构（前后端共享）

```typescript
// 前端从后端 Session 快照中提取的展示结构

interface SessionSnapshot {
  session_id: string;
  state: SessionState;
  task_context: {
    template_id: string | null;
    template_name: string | null;
    params: Record<string, string>;
    missing_params: string[];
    candidates: CandidateTemplate[];
  };
  script_preview: string | null;
  error_context: ErrorContext | null;
  history: ChatMessage[];      // Discovery/Exec 流程消息（DC-0107）
  // qa_history 在后端维护，不向前端透传（DC-UX-15）
  workspace: string;
}

interface ChatMessage {
  role: 'user' | 'agent';
  content: string;
  type?: 'text' | 'cards' | 'script' | 'timeline' | 'error';
  meta?: Record<string, any>;   // 卡片列表、脚本内容、时间线数据等
}

interface TemplateDef {
  id: string;
  name: string;
  description: string;
  category: 'vector' | 'raster' | 'general' | 'database';
  tool_source: string;           // GDAL, GRASS, SAGA, PostGIS, etc.
  tags: string[];
}

interface TemplateDetail extends TemplateDef {
  params: ParamDef[];
  concepts: ConceptItem[];
  notes: string[];
  common_errors: CommonErrorItem[];
  seealso: string[];
}
```

---

## 4. 状态机与数据流

### 4.1 单任务流程

```
用户打开应用 ──→ GET /templates（加载模板识别 TAB 的卡片网格）
                      │
                      ▼
用户在模板识别 TAB 输入需求
                      │
              ┌──────┼──────┐
              │             │
              ▼             ▼
       快速路径（关键词高分）  需精排
   （关键词高分 ≥ 8）         │
              │             │
              ▼             ▼
        PARAM_COLLECT    LLM 精排（classify_intent）
   （直达参数填写）      │
   ↳ 前端提示：已确认模板  │
            ├──→ confidence ≥ 0.85
            │       │
            │       ▼
            │   PARAM_COLLECT（自动选中）
            │       ↳ 前端提示：✓ 已确认模板，请填写参数
            │
            ├──→ 0.50 ≤ confidence < 0.85
            │       │
            │       ▼
            │   INTENT_CONFIRM（top-1 推荐 + 备选）
            │       ↳ 前端展示候选卡片列表
            │
            └──→ confidence < 0.50
                    │
                    ▼
                INTENT_CONFIRM（top-3 候选）
                    │   ↳ 前端展示候选卡片列表
                    │
                    │
                    └─→ 用户点击确认
                                        POST /session/{id}/lock
                                             │
                                             ▼
                                 进入 PARAM_COLLECT（右侧面板展开参数表单）
                                             │
                                 用户填写参数（可随时点击"预览命令"）
                                             │
                                 点击"确认参数" ──→ 自动切换到脚本执行 TAB
                                             │
                                             ▼
                                 脚本执行 TAB：命令预览态
                                             │
                                 点击"刷新"更新命令（参数有改动时）
                                             │
                                 点击"执行" ──→ WS /ws/execute 连接
                                             │
                                             ▼
                                 脚本执行 TAB：执行中态（实时日志推送）
                                             │
                               ┌────────────┴────────────┐
                               │                         │
                               ▼                         ▼
                          成功（rc=0）              失败（rc≠0）
                               │                         │
                               ▼                         ▼
                    脚本执行 TAB：成功态           脚本执行 TAB：失败态
                    （结果详情+打开输出目录）       （诊断结果+错误输出+修改参数/放弃任务）
                               │                         │
                               │                         ├──→ 自动触发 LLM 诊断
                               │                         │
                               │                         ▼
                               │              诊断结果面板（根因+建议+可自动修复）
                               │                         │
                               │                         ├──→ 点击"修改参数" → 回到参数面板
                               │                         │
                               │                         └──→ 点击"放弃任务" → 回到模板识别 TAB
                               │                         │
                               └───────────────────────────┘
                                               │
                                               ▼
                                    用户选择"新任务" → 回到模板识别 TAB（IDLE）
```

### 4.2 Pipeline 流程

```
用户描述多步骤需求
       │
       ▼
后端解析为 Pipeline 结构（多个模板 + 关联规则）
       │
       ▼
前端进入 Pipeline 模式：
   - 聊天区显示横向时间线概览
   - 右栏纵向堆叠任务卡片
   - 步骤间显示数据流指示条
       │
用户检查/修改每步参数
       │
       ▼
点击"生成脚本" ──→ POST /pipeline（返回合并脚本预览）
       │
       ▼
用户确认执行 ──→ POST /pipeline/execute（走 WS 实时日志）
```

---

## 5. 前端组件结构

```
frontend/
├── electron/                       # Electron 桌面外壳（plan-electron）
│   ├── main.ts                     # 主进程：窗口管理、Python 进程生命周期
│   ├── preload.ts                  # 预加载脚本：暴露 IPC API 给前端
│   └── tsconfig.json               # Electron 专用 TS 配置
├── src/
│   ├── main.tsx                    # 入口，启动时请求 /session 创建会话
│   ├── App.tsx                     # 路由：/ /generator /pipeline
│   ├── electron-api.ts             # IPC 封装：getApiBaseUrl / selectFile / selectDirectory
│   ├── api/
│   │   ├── client.ts               # axios 实例，baseURL = "/api"
│   │   ├── session.ts              # 会话相关 API 调用
│   │   ├── templates.ts            # 模板相关 API 调用
│   │   ├── pipeline.ts             # Pipeline API
│   │   └── generator.ts            # 模板生成器 API
│   ├── components/
│   │   ├── Layout.tsx              # 两栏布局框架（主交互区 + 参数面板）
│   │   ├── TopBar.tsx              # 顶部栏（Logo + 状态）
│   │   ├── TabBar.tsx              # TAB 切换栏（模板识别 / GIS 问答 / 脚本执行）
│   │   ├── DiscoveryTab.tsx        # 模板识别 TAB：搜索框 + 卡片网格 + 候选结果
│   │   ├── QATab.tsx               # GIS 问答 TAB：聊天消息流 + 输入框 + 清空按钮
│   │   ├── ExecTab.tsx             # 脚本执行 TAB：命令预览 / 执行中 / 成功 / 失败 四态 + 工作空间选择
│   │   ├── CmdEditor.tsx           # 命令编辑器（显示生成的 bash，语法高亮）
│   │   ├── ExecStatusPanel.tsx     # 执行状态面板（成功/失败结果展示）
│   │   ├── DetailPanel.tsx         # 右栏：模板详情 / 参数表单
│   │   ├── ParamForm.tsx           # 参数表单组件（分组折叠 + 水平行布局）
│   │   ├── TemplateCardList.tsx    # 模板卡片列表（用于 DiscoveryTab 内）
│   │   ├── ChatMessage.tsx         # 单条消息气泡（支持多种 type）
│   │   ├── PipelineOverview.tsx    # Pipeline 横向时间线
│   │   ├── PipelineStepCard.tsx    # Pipeline 纵向任务卡片
│   │   └── DataFlowIndicator.tsx   # 步骤间数据流指示
│   ├── hooks/
│   │   ├── useSession.ts           # 会话状态管理（Zustand）
│   │   ├── useWebSocket.ts         # WebSocket 连接管理
│   │   └── useTemplates.ts         # 模板列表和详情
│   ├── pages/
│   │   ├── MainPage.tsx            # 主应用页面
│   │   ├── GeneratorPage.tsx       # 模板生成器页面
│   │   └── PipelinePage.tsx        # Pipeline 编排页面
│   └── types/
│       └── index.ts                # TypeScript 类型定义
├── index.html
├── vite.config.ts
└── .env.template                   # 前端环境变量模板（API 端口）
```

---

## 6. 后端文件结构（新增）

```
SourceCode/src/
├── api/                            # 新增：HTTP + WebSocket 适配层
│   ├── __init__.py
│   ├── main.py                     # FastAPI app 实例，CORS，路由注册
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── session.py              # 会话状态流转 API
│   │   ├── templates.py            # 模板查询 API
│   │   ├── pipeline.py             # Pipeline 合并脚本 API
│   │   └── generator.py            # J2 模板生成器 API
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── chat.py                 # Q&A 流式 WS
│   │   └── execute.py              # 执行日志流式 WS
│   └── dependencies.py             # FastAPI Depends：Session 获取、Workspace 初始化
├── core/                           # 完全复用，不修改
├── llm/                            # 完全复用，不修改
├── templates/                      # 完全复用，不修改
└── ...
```

---

## 7. 启动方式

### 7.1 Electron 开发模式（推荐）

```bash
cd SourceCode

# 终端 1：启动 Python 后端
python start_api.py

# 终端 2：启动前端开发服务器 + Electron
cd frontend
npm run dev          # Vite dev server
npm run electron:dev # Electron 加载 localhost:5173
```

### 7.2 Electron 生产模式

```bash
cd frontend
npm run build          # Vite 构建前端
npm run electron:build # electron-builder 打包
# 输出：frontend/dist-electron/GIS-Agent-Setup.exe
```

### 端口配置

后端端口硬编码为 18000，由 Electron 主进程与 Python 子进程约定，无需用户配置：

前端开发服务器通过 `frontend/.env` 同步代理目标：
```
VITE_API_PORT=18000
```

---

## 8. 与 CLI 的兼容性

UX 方案**不删除**现有 CLI 代码。`cli/` 目录保持完整，与 `api/` 并行存在：

- `python start_cli.py` → 启动命令行版本
- `python start_api.py` → 启动 API 服务（由 Electron 内部调用）

两套入口共享 core/llm/templates，互不干扰。CLI 的维护成本不增加。

---

## 9. 依赖增量（相对现有）

**后端新增**（放入 `pyproject.toml` 的 `dev` 组，不影响 CLI 依赖）：
- `fastapi` — Web 框架
- `uvicorn[standard]` — ASGI 服务器
- `websockets` — WebSocket 支持
- `python-multipart` — 文件上传支持

**前端新增**：
- `react`, `react-dom`, `react-router-dom`
- `typescript`, `vite`
- `zustand` — 状态管理
- `tailwindcss`, `shadcn/ui` — UI 组件
- `axios` — HTTP 客户端

**现有依赖不变**：`anthropic`, `jinja2`（P5 仍然满足）

---

## 附录：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.14.0 | 2026-06-03 | **移除脚本执行超时**：DC-UX-05 理由更新——脚本执行不设固定超时，GDAL 数据处理（如大栅格重投影、批量矢量转换）可能耗时数小时，强制超时会导致用户任务被异常中断；前端通过 WebSocket 实时输出日志，用户可自主决定是否取消 |
| v1.13.0 | 2026-06-02 | **诊断体验优化**：DC-UX-12 更新诊断 Prompt 设计要点——增加【修复命令参考】输出要求、收紧 `can_auto_fix` 判定规则（明确排除模板渲染逻辑错误类问题）、诊断结果面板改用 `ReactMarkdown` 渲染 suggestion 中的 markdown 代码块；§3.2 `ExecuteWebSocket` done 消息补全 `stdout`/`stderr`/`duration_ms` 字段 |
| v1.12.0 | 2026-06-02 | **Q&A 历史隔离**：新增 DC-UX-14（WebSocket Q&A 写回 `qa_history`）、DC-UX-15（QATab 消息完全隔离，前端独立维护 `qaMessages`）；§3.1 更新 `process_intent`（classify_intent 不传 history，DC-0106）和 `chat_question`（使用 `qa_history`，DC-0107）；§3.2 更新 `ChatWebSocket` 说明；§3.3 `SessionSnapshot` 标注 `qa_history` 不向前端透传 |
| v1.11.0 | 2026-06-02 | **诊断流程简化**：DC-UX-12 从"一键诊断+跳转 Q&A TAB"改为"自动诊断+结果直接展示在脚本执行 TAB"；移除一键诊断按钮；失败态操作简化为"修改参数"/"放弃任务"；执行中态新增"执行命令"展示 |
| v1.10.0 | 2026-06-02 | **导出脚本**：DC-UX-11 命令预览态新增"导出脚本"按钮（DC-UX-11a）；成功态移除"打开输出目录"按钮（脚本不再自动写入 workspace） |
| v1.9.0 | 2026-05-31 | **DiscoveryTab 意图匹配状态反馈**：§2 新增三种匹配结果的前端状态提示（识别中/已确认/未匹配）；§4.1 流程图补充前端反馈标注；移除冗余的 MatchedBanner 横幅，改为轻量状态条 |
| v1.8.0 | 2026-05-31 | **切换工作空间保留会话状态**：`POST /session/{id}/workspace` 不再清空会话，仅变更默认 cwd 和输出基准目录；template、params、history、error_context 等全部保留；§3.1 `update_session_workspace` docstring 更新 |
| v1.7.0 | 2026-05-31 | **API 分离 + Prompt 场景拆分**：§3.1 新增 `POST /session/{id}/chat` endpoint（Q&A 专用）；更新 DC-UX-10 为三 TAB 分离（模板识别 / GIS 问答 / 脚本执行），明确各 TAB 的后端 API 和行为约束；移除 `process_intent` 中的 `is_question` 判断逻辑；§4.1 流程图移除"探索性问题 → Q&A 文本回复"分支 |
| v1.6.0 | 2026-05-31 | **架构升级：三 TAB 设计**。新增 DC-UX-10（双 TAB 分离：模板识别 / GIS 问答）、DC-UX-11（脚本执行 TAB：四态命令预览/执行/成功/失败）、DC-UX-12（一键诊断：执行错误自动问答）、DC-UX-13（两栏+三TAB布局，面板扩宽至 580px）；更新 DC-UX-02 状态映射表；重绘 §4.1 单任务流程图；更新 §5 组件结构 |
| v1.5.0 | 2026-05-31 | 新增 DC-UX-08：参数面板分组折叠 + 水平行布局 + 面板扩宽至 520px（方案 B：前端启发式分组）；新增 DC-UX-09：描述 Tooltip 化 + 进度条替代 Dot 指示器 + 类型标签彩色化 |
| v1.4.0 | 2026-05-31 | 废弃纯浏览器模式：移除 §7.3 浏览器模式、移除 `isElectron` 特性检测、路由改为 HashRouter；端口默认改为 18000 |
| v1.3.0 | 2026-05-31 | **架构变更**：DC-UX-01 从纯浏览器方案升级为 Electron 桌面外壳（plan-electron DC-E01）；更新 §5 组件结构增加 `electron/` 目录；更新 §7 启动方式增加 Electron 开发/生产模式；保留纯浏览器模式作为向后兼容 |
| v1.2.0 | 2026-05-30 | 更新 §3.1 `process_intent` API 为两阶段匹配（DC-0098）；更新 §4.1 单任务流程图，增加快速路径（关键词高分直达）和 LLM 精排三级决策分支 |
| v1.1.0 | 2026-05-29 | 新增 `/pipeline` 路由；启动方式改为 `start_api.py`/`start_cli.py`；端口支持前后端配置同步 |
| v1.0.0 | 2026-05-29 | 初版，定义 React + FastAPI 浏览器 UI 方案 |
