"""启动脚本：启动 FastAPI 后端服务。

Windows 用法（无需设置 PYTHONPATH）:
    cd SourceCode
    python start_api.py

Linux/macOS 用法:
    cd SourceCode
    PYTHONPATH=src python -m api
"""

import sys
from pathlib import Path

# 确保 src/ 在 Python 路径中
src_dir = Path(__file__).parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from api.main import main

if __name__ == "__main__":
    sys.exit(main())
