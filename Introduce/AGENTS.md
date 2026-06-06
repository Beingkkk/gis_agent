# GIS Agent Introduce — HyperFrames 项目规则

## 项目信息

- **时长**: 50s
- **分辨率**: 1920×1080（landscape）
- **风格**: 科技感深色主题
- **品牌色**: 主蓝 `#3b82f6`，辅青 `#06b6d4`，背景 `#0a0e1a`

## 文件结构

```
index.html          # 单文件合成（6 个场景 + GSAP 时间线）
introduce.md        # 文案脚本与截图素材清单
package.json        # hyperframes@0.6.32
meta.json           # 项目元数据
AGENTS.md           # 本文件
renders/            # 输出 MP4
snapshots/          # PNG 关键帧
assets/             # 截图素材（1-13.png）
```

## 截图素材

| 编号 | 文件名 | 用途 |
|------|--------|------|
| 1 | 1.软件启动初始.png | 启动界面 |
| 2 | 4.意图识别筛选（shp转geojson）.png | 意图匹配 |
| 3 | 5.基于模板问答.png | 参数问答 |
| 4 | 6.模板内填入数据生成指令.png | 指令生成 |
| 5 | 7.指令执行错误一键诊断修复.png | 错误诊断 |
| 6 | 8.指令执行成功.png | 执行成功 |
| 7 | 9.工具文档导入（html或md).png | 文档导入 |
| 8 | 10.模板生成结果.png | 生成结果 |
| 9 | 11.模板编辑.png | 模板编辑 |
| 10 | 12.模板审核成功保存.png | 审核保存 |
| 11 | 13.模板库查找验证.png | 模板验证 |

## 场景时间线

| # | 场景 | Start | Duration | DOM id |
|---|------|-------|----------|--------|
| 0 | 品牌底栏 | 0s | 50s | persistent |
| 1 | 开场 | 0s | 5s | #scene-intro |
| 2 | 痛点→方案 | 5s | 5s | #scene-pain |
| 3 | 核心工作流 | 10s | 18s | #scene-workflow |
| 4 | 模板生成器 | 28s | 12s | #scene-generator |
| 5 | 扩展能力 | 40s | 5s | #scene-extend |
| 6 | 结尾 | 45s | 5s | #scene-outro |

## 约束

- 不使用 `Date.now()` / `Math.random()`
- 不使用模板字符串选择器（如 `` `#${id}` ``）
- 每个场景元素使用 `class="clip"`
- GSAP 时间线注册为 `window.__timelines["main"]`
