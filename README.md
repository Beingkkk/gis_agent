# GIS Agent

基于自然语言的 GDAL 数据处理助手。接受中文需求描述，生成安全可审查的批处理脚本，经确认后执行。

## 核心能力

| 能力 | 说明 |
|------|------|
| 任务脚本化 | 自然语言需求 → Jinja2 模板渲染 → 可执行脚本 |
| 模板知识 | 模板内置概念/提示/常见错误，辅助使用 |
| 安全执行 | 路径规范化、执行前强制确认、脚本安全扫描 |

## 环境准备

### 1. 创建 Conda 环境

```bash
conda create -n gis-agent python=3.11 -y
conda activate gis-agent
```

### 2. 安装 GDAL

```bash
conda install -c conda-forge gdal -y
```

验证安装：

```bash
ogr2ogr --version
```

### 3. 安装 Python 依赖

```bash
# 进入源码目录
cd SourceCode

# 安装生产依赖
pip install -e .

# 如需开发（包含测试和代码检查工具）
pip install -e ".[dev]"
```

### 4. 配置

复制配置模板并填入实际凭证：

```bash
cd SourceCode
cp config/config.json.template config/config.json
```

编辑 `config/config.json`（在 `SourceCode/` 目录下）：

| 字段 | 说明 | 示例 |
|------|------|------|
| `llm.base_url` | LLM API 地址 | `https://api.anthropic.com` |
| `llm.auth_key` | API 密钥 | `sk-xxxxxxxx` |
| `llm.model_name` | 模型名称 | `claude-sonnet-4-6` |
| `workspace.default_path` | 默认工作空间 | `.` |

**环境变量覆盖**：敏感字段支持通过环境变量覆盖，避免密钥入仓。

```bash
export GISAGENT_LLM_AUTH_KEY="sk-your-key"
export GISAGENT_LLM_BASE_URL="https://api.example.com"
```

变量命名规则：`GISAGENT_` + 配置路径（大写，`_` 连接），优先级高于配置文件。

### 5. 工作空间配置（可选）

在工作空间根目录创建 `Agents.md`，为 Agent 提供项目级长期记忆：

```markdown
# 项目：城市道路数据处理

- 原始坐标系：EPSG:3857
- 输出坐标系：EPSG:4326
- 常用输入路径：./raw/
- 常用输出路径：./processed/
- 栅格裁剪默认无数据值：0
- 矢量输出格式优先 GeoJSON
```

启动时若检测到 `Agents.md`，内容自动注入 LLM 系统提示词，Agent 会据此调整默认行为。

## 启动

### 命令行入口

```bash
# 进入源码目录（必须在此目录下运行，因为模板和配置路径相对此目录）
cd SourceCode

# 基础启动（使用当前目录作为工作空间）
python -m cli

# 指定工作空间
python -m cli --workspace /path/to/project

# 指定配置文件
python -m cli --config /path/to/config.json

# 空跑模式（只展示脚本不执行，首次使用建议）
python -m cli --dry-run
```

> **Windows 用户注意**：`pip install -e .` 安装的 `gis-agent` 命令在部分终端环境下不可用，请使用 `python -m cli` 启动。

### 交互命令

进入 REPL 后可用以下斜杠命令：

| 命令 | 功能 |
|------|------|
| `/quit` / `/q` | 退出程序 |
| `/clear` | 清除会话历史 |
| `/workspace` | 显示当前工作空间 |
| `/templates` | 列出可用模板 |
| `/status` | 显示当前状态摘要 |
| `/help` | 显示帮助信息 |

### 典型会话流程

```
GIS> 把 data/roads.shp 转成 GeoJSON
已识别任务：Shapefile 转 GeoJSON。
请输入所需参数。

GIS> 输出叫 roads_out.json
───────────────────────────────
脚本预览：
───────────────────────────────
@echo off
ogr2ogr -f "GeoJSON" roads_out.json data/roads.shp
───────────────────────────────

确认执行？(Y/N)：Y
执行完成。
```

## 项目结构

```
gis-agent/
├── Document/               # 设计文档（spec/constitution/plan/ADR）
├── SourceCode/
│   ├── src/
│   │   ├── cli/           # CLI 层：REPL、命令解析、脚本执行
│   │   ├── core/          # 核心层：状态机、模板注册表、参数校验
│   │   ├── llm/           # LLM 层：意图分类、参数抽取、错误诊断
│   │   ├── templates/     # 模板引擎：Jinja2 渲染、扫描器、安全校验
│   │   └── config/        # 配置加载
│   ├── tests/unit/        # 单元测试
│   ├── data/
│   │   └── templates/     # .j2 模板文件（vector/raster/general）
│   ├── config/            # 运行时配置（config.json）
│   └── pyproject.toml
└── README.md
```

## 开发工具

### 批量生成 J2 模板

`scripts/generate_templates.py` 是一个开发时工具，用于从 GDAL HTML 文档批量生成 Jinja2 模板。当你需要扩充模板库（如 GDAL 版本升级、新增工具支持）时，使用此工具替代手工编写。

**工作原理**：HTML 解析 → LLM 生成模板定义 → LLM 审核 → 渲染为 `.j2` 文件。

**前置条件**：
- 已配置有效的 LLM API 密钥（`config/config.json`）
- 已构建 GDAL 文档（`Document/Resource/gdal/build/doc/build/html/programs`）

**执行命令**：

```bash
cd SourceCode

# 批量生成（从 programs 目录生成到 data/templates/）
python scripts/generate_templates.py \
  --source ../Document/Resource/gdal/build/doc/build/html/programs \
  --output data/templates/ \
  --config config/config.json
```

**参数说明**：

| 参数 | 说明 |
|------|------|
| `--source` | GDAL HTML 文档目录 |
| `--output` | J2 模板输出目录 |
| `--config` | 配置文件路径 |
| `--strict` | 严格审核模式（任何 warning 视为失败） |
| `--dry-run` | 空跑预览（不写入文件，但仍有 API 调用） |
| `--force` | 强制重跑（忽略断点续传缓存） |
| `--verbose` | 详细日志 |

**断点续传**：工具会自动跳过已处理的文件（通过 `.generate_state.json` 跟踪）。中断后重新执行同一命令即可恢复。

**审核队列**：生成或审核失败的文件会记录到 `.review_queue.jsonl`，可据此人工修正后补充模板。

**注意事项**：
- 该工具不是运行时组件，仅在开发时执行
- 批量处理涉及大量 LLM API 调用，请注意 token 消耗
- 生成的模板建议人工抽样检查后再提交

## 开发规范

本项目遵循规范驱动设计（Specification-Driven Design）流程。编码前必须先完成对应模块的 plan 设计文档，详见 [Document/constitution.md](Document/constitution.md)。

---

内部工具，单人维护，零外部服务依赖。
