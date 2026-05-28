"""Allow running CLI via ``python -m cli``.

Design: plan-cli v1.0.0 (DC-0060)
"""

import sys

from cli.main import main

if __name__ == "__main__":
    sys.exit(main())
