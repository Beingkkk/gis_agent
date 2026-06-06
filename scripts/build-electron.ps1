#Requires -Version 5.1
<#
.SYNOPSIS
    GIS Agent v1.0.0 Electron 一键打包脚本
.DESCRIPTION
    1. 构建前端（Vite + Electron main 进程）
    2. 运行 electron-builder 生成安装包与便携版
    3. 将 Python 外置资源（src/ data/ config/ start_api.py）拷贝到输出目录，
       保持 SourceCode/ 目录层级，确保 Python 的 Path(__file__) 硬编码路径在打包后仍然有效
    4. 生成 README.txt 说明文件

    打包产物输出到项目根目录 dist/ 下，不提交 git。
.NOTES
    运行前请确保：
      - Node.js + npm 已安装
      - 图标文件 SourceCode/src/icon.png 存在
      - config.json 已正确配置
#>

# 设置控制台输出编码，避免中文乱码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"

# ─── 路径常量 ──────────────────────────────────────────
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendDir = Join-Path (Join-Path $ProjectRoot "SourceCode") "frontend"
$SourceCodeDir = Join-Path $ProjectRoot "SourceCode"
$DistDir = Join-Path (Join-Path $ProjectRoot "dist") "electron"

# 外置资源清单（不进入 asar，打包后脚本拷贝）
$ExternalAssets = @(
    @{ Src = "src";           IsDir = $true }
    @{ Src = "data";          IsDir = $true }
    @{ Src = "config";        IsDir = $true }
    @{ Src = "start_api.py";  IsDir = $false }
)

# ─── 工具函数 ──────────────────────────────────────────
function Write-Step($msg) {
    Write-Host "`n>>> $msg" -ForegroundColor Cyan
}

function Write-Info($msg) {
    Write-Host "    $msg" -ForegroundColor DarkGray
}

function Write-Ok($msg) {
    Write-Host "    $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "    $msg" -ForegroundColor Yellow
}

# ─── 0. 前置检查 ───────────────────────────────────────
Write-Step "Step 0/5: 前置检查"

# 检查图标
$IconPath = Join-Path (Join-Path $SourceCodeDir "src") "icon.png"
if (-not (Test-Path $IconPath)) {
    throw "图标文件不存在: $IconPath`n请确认 icon.png 已放置在 SourceCode/src/ 下。"
}
Write-Ok "图标检查通过: $IconPath"

# 检查 config.json
$ConfigPath = Join-Path (Join-Path $SourceCodeDir "config") "config.json"
if (-not (Test-Path $ConfigPath)) {
    Write-Warn "config.json 不存在，将使用模板: config.json.template"
    $ConfigTemplate = Join-Path (Join-Path $SourceCodeDir "config") "config.json.template"
    if (Test-Path $ConfigTemplate) {
        Copy-Item -Path $ConfigTemplate -Destination $ConfigPath -Force
        Write-Info "已自动复制 config.json.template -> config.json"
    } else {
        throw "config.json 和 config.json.template 均不存在"
    }
}

# 检查 npm
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    throw "npm 未找到，请确保 Node.js 已安装并加入 PATH"
}
Write-Ok "npm 检查通过: $($npm.Source)"

# ─── 1. 前端构建 ───────────────────────────────────────
Write-Step "Step 1/5: 构建前端 (Vite + Electron)"
Set-Location $FrontendDir

# 安装依赖（如未安装）
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Warn "node_modules 不存在，正在安装 npm 依赖..."
    npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install 失败" }
}

# 构建渲染进程（dist/）
Write-Info "构建 Vite 渲染进程..."
npm run build
if ($LASTEXITCODE -ne 0) { throw "Vite build 失败" }
Write-Ok "Vite build 完成"

# 构建主进程（dist-electron/）
Write-Info "构建 Electron 主进程..."
npx tsc -p electron/tsconfig.json
if ($LASTEXITCODE -ne 0) { throw "Electron main 编译失败" }

# 写入 dist-electron/package.json 确保 commonjs 模块类型
$pkg = @{ type = "commonjs" } | ConvertTo-Json -Depth 1
$pkg | Set-Content -Path (Join-Path (Join-Path $FrontendDir "dist-electron") "package.json") -Encoding UTF8 -NoNewline
Write-Ok "Electron main 编译完成"

# 设置 Electron 缓存目录（本地 zip 包位置）
$env:ELECTRON_CACHE = Join-Path $ProjectRoot "scripts"
Write-Info "Electron 缓存目录: $($env:ELECTRON_CACHE)"

# ─── 2. Electron Builder 打包 ──────────────────────────
Write-Step "Step 2/5: Electron Builder 打包 (nsis + portable)"
Write-Info "开始打包，版本号: 1.0.0"

npx electron-builder --config electron-builder.json5
if ($LASTEXITCODE -ne 0) { throw "electron-builder 打包失败" }

# 探测输出目录（electron-builder 生成 win-unpacked 或 GIS Agent-win32-x64 等）
# 排除以 . 开头的临时目录（如 .icon-ico）
$BuildOutput = Get-ChildItem -Path $DistDir -Directory |
    Where-Object { $_.Name -notmatch '^\.' } |
    Select-Object -First 1
if (-not $BuildOutput) {
    throw "未找到 electron-builder 输出目录，请检查 $DistDir"
}
$BuildOutputPath = $BuildOutput.FullName
Write-Ok "打包输出目录: $($BuildOutput.Name)"

# ─── 3. 拷贝外置资源 ───────────────────────────────────
Write-Step "Step 3/5: 拷贝 Python 外置资源"
$TargetSourceCode = Join-Path $BuildOutputPath "SourceCode"

# 清理旧的 SourceCode/ 目录（如果存在）
if (Test-Path $TargetSourceCode) {
    Remove-Item -Recurse -Force $TargetSourceCode
    Write-Info "清理旧 SourceCode/ 目录"
}

# 创建目标 SourceCode/ 目录
New-Item -ItemType Directory -Force -Path $TargetSourceCode | Out-Null

foreach ($asset in $ExternalAssets) {
    $srcPath = Join-Path $SourceCodeDir $asset.Src
    $dstPath = Join-Path $TargetSourceCode $asset.Src

    if (-not (Test-Path $srcPath)) {
        Write-Warn "源文件不存在，跳过: $($asset.Src)"
        continue
    }

    if ($asset.IsDir) {
        # 使用 robocopy 拷贝目录，排除开发时产生的缓存/垃圾文件
        Write-Info "拷贝目录: $($asset.Src) -> SourceCode/$($asset.Src)"
        $roboLog = Join-Path $env:TEMP "robocopy-$($asset.Src).log"
        & robocopy `
            $srcPath $dstPath `
            /E `
            /XD "__pycache__" "node_modules" ".git" ".pytest_cache" ".ruff_cache" ".mypy_cache" ".codegraph" ".pixi" ".venv" "venv" "env" `
            /XF "*.pyc" "*.pyo" "*.pyd" ".coverage" "*.egg-info" "*.log" "*.tmp" "*.bak" `
            /NP /NFL /NDL /NJH /NJS `
            /LOG:$roboLog
        if ($LASTEXITCODE -ge 8) {
            Write-Warn "robocopy 退出码 $LASTEXITCODE，但通常不影响结果"
        }
    } else {
        Write-Info "拷贝文件: $($asset.Src) -> SourceCode/$($asset.Src)"
        Copy-Item -Path $srcPath -Destination $dstPath -Force
    }
}

Write-Ok "外置资源拷贝完成"

# ─── 4. 生成说明文件 ───────────────────────────────────
Write-Step "Step 4/5: 生成说明文件"
$ReadmePath = Join-Path $BuildOutputPath "README.txt"
$ReadmeContent = @"
================================================================================
  GIS Agent v1.0.0
================================================================================

启动方式
--------
双击 GIS Agent.exe 即可启动应用程序。

目录说明
--------
- resources/app.asar      前端资源（Electron 渲染进程）
- SourceCode/             Python 后端源码及数据（外置资源）
  |-- src/                Python 后端代码
  |-- data/templates/     Jinja2 GDAL 模板文件
  |-- config/             配置文件（config.json）
  |-- start_api.py        后端启动脚本

环境依赖
--------
- Windows 10/11 x64
- Python 3.11+ 及以下依赖包：
    fastapi, uvicorn, jinja2, pydantic, anthropic,
    beautifulsoup4, json5, tenacity
- GDAL 命令行工具（gdalinfo, ogr2ogr, gdal_translate 等）

Python 路径配置（三选一）
-------------------------
软件启动时会按以下顺序查找 Python：

1. 环境变量 GISAGENT_PYTHON_PATH（优先级最高）
   命令行设置示例：
   set GISAGENT_PYTHON_PATH=C:\path\to\python.exe

2. config.json 中的 python_path 字段
   编辑 SourceCode/config/config.json：
   {
     "python_path": "C:\\\\path\\\\to\\\\python.exe",
     "llm": { ... }
   }

3. 自动检测（无需配置）
   - 系统 PATH 中的 python / python3
   - 常见 conda/anaconda 环境目录下的所有环境

注意：conda 环境名不限定为 gis-agent，任何包含所需依赖的
      Python 环境均可使用。

注意事项
--------
- config.json 包含 API 密钥等敏感信息，请勿泄露
- 模板文件位于 SourceCode/data/templates/，可热更新
- 首次启动前请确保 Python 依赖已安装完毕
================================================================================
"@
$ReadmeContent | Set-Content -Path $ReadmePath -Encoding UTF8 -NoNewline
Write-Ok "README.txt 已生成"

# ─── 5. 完成汇总 ───────────────────────────────────────
Write-Step "Step 5/5: 打包完成汇总"

$NsisExe = Get-ChildItem -Path $DistDir -Filter "*.exe" -File | Where-Object { $_.Name -like "*Setup*" } | Select-Object -First 1
$PortableExe = Get-ChildItem -Path $DistDir -Filter "*.exe" -File | Where-Object { $_.Name -like "*Portable*" } | Select-Object -First 1

Write-Host "`n    ╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "    ║  ✅ GIS Agent v1.0.0 打包完成                      ║" -ForegroundColor Green
Write-Host "    ╠══════════════════════════════════════════════════════╣" -ForegroundColor Green
Write-Host "    ║  输出目录: $($BuildOutput.Name)" -ForegroundColor Green
if ($NsisExe) {
    Write-Host "    ║  安装包  : $($NsisExe.Name)" -ForegroundColor Green
}
if ($PortableExe) {
    Write-Host "    ║  便携版  : $($PortableExe.Name)" -ForegroundColor Green
}
Write-Host "    ║  完整路径: $BuildOutputPath" -ForegroundColor Green
Write-Host "    ╚══════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host "`n📦 如需分发给用户，可将以下文件打包:" -ForegroundColor Cyan
Write-Host "   - $BuildOutputPath/ (便携版可直接使用整个文件夹)" -ForegroundColor White
if ($NsisExe) {
    Write-Host "   - $($NsisExe.FullName) (NSIS 安装包)" -ForegroundColor White
}

# 切回原目录
Set-Location $ProjectRoot
