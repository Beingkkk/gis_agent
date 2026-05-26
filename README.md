# GIS Agent

基于自然语言的 GDAL 数据处理助手。接受中文需求描述，生成安全可审查的批处理脚本，经确认后执行。

## 核心能力

| 能力 | 说明 |
|------|------|
| 文档问答 | 基于本地 GDAL 文档，解答工具使用问题 |
| 任务脚本化 | 自然语言需求 → Jinja2 模板渲染 → 可执行脚本 |
| 安全执行 | 工作空间隔离、路径白名单、执行前强制确认 |

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

### 3. 安装 Python 依赖（后续补充）

```bash
# 待添加 pyproject.toml 后执行
pip install -e .
```

## 项目结构

```
gis-agent/
├── Document/          # 设计文档
│   ├── spec.md        # 产品需求规格
│   └── constitution.md # 开发宪法
├── SourceCode/        # 源代码
│   └── src/           # 待创建
└── README.md
```

## 开发规范

本项目遵循 SDD（软件设计文档）驱动开发流程。编码前必须先完成对应模块的 SDD 设计文档，详见 [Document/constitution.md](Document/constitution.md)。

---

内部工具，单人维护，零外部服务依赖。
