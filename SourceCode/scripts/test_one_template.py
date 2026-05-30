"""Test single HTML -> J2 template generation pipeline.

Usage (from SourceCode/):
    python scripts/test_one_template.py <html_file>

Example:
    python scripts/test_one_template.py \
        ../Document/Resource/gdal/build/doc/build/html/programs/gdal_vector.html
"""

import json
import sys
from pathlib import Path

# Add src/ to path
_SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_SRC_DIR))

from config import load_config
from llm.client import LLMClient

from generate.extractor import HtmlExtractor
from generate.generator import LLMTemplateGenerator
from generate.renderer import render_j2
from generate.reviewer import LLMTemplateReviewer


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <html_file>")
        return 1

    html_path = Path(sys.argv[1])
    if not html_path.exists():
        print(f"File not found: {html_path}")
        return 1

    # Load config
    load_config("config/config.json")
    llm_client = LLMClient()

    # Read HTML
    html_content = html_path.read_text(encoding="utf-8")
    print(f"=== HTML file: {html_path.name} ({len(html_content)} chars) ===\n")

    # Step 1: Extract
    print("--- Step 1: Extract ---")
    extractor = HtmlExtractor()
    extracted = extractor.extract(html_content)
    print(f"Title: {extracted.title}")
    print(f"Synopsis: {extracted.synopsis[:200]}...")
    print(f"Description: {extracted.description[:200]}...")
    print(f"Options count: {len(extracted.options)}\n")

    # Step 2: Generate
    print("--- Step 2: Generate (LLM) ---")
    generator = LLMTemplateGenerator(llm_client)
    tdef, error = generator.generate(extracted)

    if tdef is None:
        print(f"Generation failed: {error}")
        return 1
    print(f"ID: {tdef.id}")
    print(f"Name: {tdef.name}")
    print(f"Description: {tdef.description}")
    print(f"Category: {tdef.category}")
    print(f"Params: {[p.name for p in tdef.params]}")
    print(f"Concepts: {tdef.concepts}")
    print(f"Notes: {tdef.notes}\n")

    # Step 3: Review
    print("--- Step 3: Review (LLM) ---")
    reviewer = LLMTemplateReviewer(llm_client)
    try:
        review = reviewer.review(tdef)
        print(f"Review passed: {review.passed}")
        for issue in review.issues:
            sev = "[WARN]" if issue.severity == "warning" else "[ERR]"
            print(f"  {sev} [Item {issue.item}] {issue.message[:120]}")
        print()
        if not review.passed:
            print("Review failed, but still rendering for inspection.")
    except Exception as exc:
        print(f"Review parse failed: {exc}")
        print("Still rendering for inspection.")

    # Step 4: Render
    print("--- Step 4: Render J2 ---")
    j2_content = render_j2(tdef)
    print(f"J2 content length: {len(j2_content)} chars")
    print("\n=== Generated J2 template (first 80 lines) ===\n")
    lines = j2_content.splitlines()
    for line in lines[:80]:
        print(line)
    if len(lines) > 80:
        print(f"\n... ({len(lines) - 80} more lines)")

    # Save to file for inspection
    output_path = Path("data/templates/test_generated.j2")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(j2_content, encoding="utf-8")
    print(f"\n=== Saved to: {output_path} ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
