@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: GIS Agent — Embedding Model Download Script
:: Model: paraphrase-multilingual-MiniLM-L12-v2
:: Target: SourceCode/model/
::
:: Usage: double-click or run in terminal:
::        .\SourceCode\model\download_embedding.cmd
::
:: The script will auto-detect and activate the conda 'gis-agent'
:: environment if available. Otherwise falls back to system Python.
:: ============================================================

title GIS Agent — Download Embedding Model

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "MODEL_NAME=paraphrase-multilingual-MiniLM-L12-v2"
set "MODEL_DIR=%SCRIPT_DIR%"
set "CONDA_ENV_NAME=gis-agent"

echo.
echo ============================================
echo   GIS Agent — Embedding Model Downloader
echo ============================================
echo.
echo Model : %MODEL_NAME%
echo Target: %MODEL_DIR%
echo.

:: --- Conda environment auto-activation ---
set "CONDA_ACTIVATED=0"

:: Check if already in the correct conda environment
if "%CONDA_DEFAULT_ENV%"=="%CONDA_ENV_NAME%" (
    echo [INFO] Already in conda environment '%CONDA_ENV_NAME%'.
    set "CONDA_ACTIVATED=1"
    goto :python_check
)

:: Try to find conda activate.bat in common locations
set "ACTIVATE_BAT="
if exist "%CONDA_EXE%" (
    for %%p in ("%CONDA_EXE%") do set "CONDA_ROOT=%%~dpp"
    if exist "!CONDA_ROOT!\Scripts\activate.bat" set "ACTIVATE_BAT=!CONDA_ROOT!\Scripts\activate.bat"
)
if not defined ACTIVATE_BAT if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
    set "ACTIVATE_BAT=%USERPROFILE%\anaconda3\Scripts\activate.bat"
)
if not defined ACTIVATE_BAT if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
    set "ACTIVATE_BAT=%USERPROFILE%\miniconda3\Scripts\activate.bat"
)
if not defined ACTIVATE_BAT if exist "%ProgramData%\anaconda3\Scripts\activate.bat" (
    set "ACTIVATE_BAT=%ProgramData%\anaconda3\Scripts\activate.bat"
)
if not defined ACTIVATE_BAT if exist "%ProgramData%\miniconda3\Scripts\activate.bat" (
    set "ACTIVATE_BAT=%ProgramData%\miniconda3\Scripts\activate.bat"
)

if defined ACTIVATE_BAT (
    echo [INFO] Found conda at: %ACTIVATE_BAT%
    echo [INFO] Activating environment '%CONDA_ENV_NAME%' ...
    call "%ACTIVATE_BAT%" %CONDA_ENV_NAME%
    if not errorlevel 1 (
        set "CONDA_ACTIVATED=1"
        echo [INFO] Conda environment activated.
    ) else (
        echo [WARN] Failed to activate conda environment '%CONDA_ENV_NAME%'.
    )
) else (
    echo [INFO] Conda not found. Will try system Python.
)

:: --- Check Python ---
:python_check
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not found in PATH.
    echo.
    if "%CONDA_ACTIVATED%"=="0" (
        echo Please ensure one of the following:
        echo   1. Create and activate conda environment:
        echo      conda create -n %CONDA_ENV_NAME% python=3.10
        echo      conda activate %CONDA_ENV_NAME%
        echo   2. Install Python 3.10+ and add it to PATH
    ) else (
        echo The conda environment '%CONDA_ENV_NAME%' appears active,
        echo but Python is not accessible. Please check the environment.
    )
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%a in ('python --version 2^>^&1') do set "PY_VERSION=%%a"
echo [INFO] Found %PY_VERSION%

:: --- Check sentence-transformers ---
python -c "import sentence_transformers" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [WARN] sentence-transformers is not installed.
    echo.
    set /p INSTALL="Install now? (Y/N): "
    if /I "!INSTALL!"=="Y" (
        echo [INFO] Installing sentence-transformers ...
        pip install sentence-transformers
        if errorlevel 1 (
            echo [ERROR] Installation failed.
            pause
            exit /b 1
        )
    ) else (
        echo [INFO] Skipped. Please install manually:
        echo   pip install sentence-transformers
        pause
        exit /b 1
    )
) else (
    for /f "tokens=*" %%a in ('python -c "import sentence_transformers; print(sentence_transformers.__version__)" 2^>^&1') do set "ST_VERSION=%%a"
    echo [INFO] sentence-transformers version: %ST_VERSION%
)

:: --- Check if model already exists ---
echo.
echo [INFO] Checking existing model in:
echo        %MODEL_DIR%
echo.

python -c "
import os
import sys

cache_dir = r'%MODEL_DIR%'
model_name = '%MODEL_NAME%'

# Check common locations where sentence-transformers stores models
model_found = False
possible_paths = []

# New huggingface_hub cache format (models--org--model)
org, name = model_name.split('/', 1) if '/' in model_name else ('sentence-transformers', model_name)
hf_cache = os.path.join(cache_dir, 'models--%s--%s' % (org.replace('/', '-'), name.replace('/', '-')))
possible_paths.append(hf_cache)

# Legacy format (direct model folder)
legacy_path = os.path.join(cache_dir, model_name)
possible_paths.append(legacy_path)

# sentence_transformers subfolder
st_path = os.path.join(cache_dir, 'sentence_transformers', model_name)
possible_paths.append(st_path)

for p in possible_paths:
    if os.path.isdir(p):
        # Check for essential files
        has_config = os.path.exists(os.path.join(p, 'config.json'))
        has_model = any(os.path.exists(os.path.join(p, f)) for f in ['pytorch_model.bin', 'model.safetensors', 'tf_model.h5'])
        if has_config or has_model:
            model_found = True
            print('Found existing model at: %s' % p)
            break

if model_found:
    print('Model already downloaded. Skipping.')
    sys.exit(0)
else:
    sys.exit(1)
" >nul 2>&1

if not errorlevel 1 (
    echo [INFO] Model already exists. Nothing to do.
    echo.
    echo ============================================
    echo   Download Complete ^(already cached^)
    echo ============================================
    pause
    exit /b 0
)

:: --- Download model ---
echo [INFO] Starting download from Hugging Face Hub ...
echo        This may take a few minutes depending on your network.
echo        Model size: ~120 MB

python -c "
import os
import sys

cache_dir = r'%MODEL_DIR%'
os.makedirs(cache_dir, exist_ok=True)

try:
    from sentence_transformers import SentenceTransformer
    print('Downloading %s ...' % '%MODEL_NAME%')
    print('Cache directory: %s' % cache_dir)
    print('')
    # Download and cache the model
    model = SentenceTransformer('%MODEL_NAME%', cache_folder=cache_dir)
    print('')
    print('Download completed successfully.')
except Exception as e:
    print('')
    print('ERROR: %s' % str(e))
    sys.exit(1)
"

if errorlevel 1 (
    echo.
    echo [ERROR] Model download failed.
    echo.
    echo Troubleshooting:
    echo   1. Check your internet connection.
    echo   2. If behind a proxy, set HTTPS_PROXY environment variable.
    echo   3. Try manual download from:
    echo      https://huggingface.co/sentence-transformers/%MODEL_NAME%
    echo   4. Place the downloaded folder into:
    echo      %MODEL_DIR%
    echo.
    pause
    exit /b 1
)

:: --- Verify download ---
echo.
echo [INFO] Verifying downloaded model ...

python -c "
import os
import sys

cache_dir = r'%MODEL_DIR%'
model_name = '%MODEL_NAME%'

# Attempt to load the model to verify integrity
try:
    from sentence_transformers import SentenceTransformer
    # Try loading from cache directory
    model = SentenceTransformer(model_name, cache_folder=cache_dir)
    dim = model.get_sentence_embedding_dimension()
    print('Model loaded successfully.')
    print('Embedding dimension: %d' % dim)
    # Quick test encode
    test_vec = model.encode('test')
    print('Test encoding passed. Vector shape: %s' % str(test_vec.shape))
except Exception as e:
    print('Verification failed: %s' % str(e))
    sys.exit(1)
"

if errorlevel 1 (
    echo.
    echo [ERROR] Model verification failed. The downloaded files may be incomplete.
    echo Please delete the model folder and run this script again.
    pause
    exit /b 1
)

:: --- Done ---
echo.
echo ============================================
echo   Download and Verification Complete
echo ============================================
echo.
echo Model: %MODEL_NAME%
echo Location: %MODEL_DIR%
echo.
echo You can now use the RAG retrieval module.
echo The model will be loaded from local path at runtime.
echo.
pause
exit /b 0
