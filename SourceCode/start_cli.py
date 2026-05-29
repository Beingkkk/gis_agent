"""启动脚本：启动 GIS Agent CLI。

Windows 用法（无需设置 PYTHONPATH）:
    cd SourceCode
    python start_cli.py

Linux/macOS 用法:
    cd SourceCode
    PYTHONPATH=src python -m cli.main
"""

import sys
from pathlib import Path

src_dir = Path(__file__).parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from cli.main import main

if __name__ == "__main__":
    sys.exit(main())
