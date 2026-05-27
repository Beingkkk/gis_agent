#!/usr/bin/env python3
"""CLI script to preprocess GDAL HTML docs into JSON chunks.

Development tool — not imported at runtime.

Usage:
    python scripts/preprocess_docs.py

Design: DC-0025
"""

import sys
import time
from pathlib import Path

# Allow importing rag.preprocess before the package is installed
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _PROJECT_ROOT / "SourceCode" / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from rag.preprocess import preprocess_directory  # noqa: E402


def main() -> int:
    """Run preprocessing and print statistics."""
    source_dir = (
        _PROJECT_ROOT
        / "Document"
        / "Resource"
        / "gdal"
        / "build"
        / "doc"
        / "build"
        / "html"
    )
    output_path = _PROJECT_ROOT / "SourceCode" / "data" / "gdal-docs-chunks.json"

    if not source_dir.exists():
        print(f"ERROR: Source directory not found: {source_dir}", file=sys.stderr)
        return 1

    print(f"Source:  {source_dir}")
    print(f"Output:  {output_path}")
    print("Preprocessing...")

    start = time.perf_counter()
    total = preprocess_directory(
        source_dir=source_dir,
        output_path=output_path,
        include_patterns=["programs/*.html", "drivers/**/*.html"],
        exclude_patterns=["api/**", "_*/**"],
        chunk_size=512,
        chunk_overlap=128,
    )
    elapsed = time.perf_counter() - start

    print(f"Done. {total} chunks written in {elapsed:.2f}s")
    print(f"Output:  {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
