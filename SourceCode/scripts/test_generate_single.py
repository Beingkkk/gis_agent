"""Quick test: generate a single template to verify pipeline fixes.

Usage:
    python scripts/test_generate_single.py <html_file> [--strict]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_SRC_DIR))

from config import load_config
from llm.client import LLMClient
from generate.extractor import HtmlExtractor
from generate.generator import LLMTemplateGenerator
from generate.renderer import render_j2
from generate.reviewer import LLMTemplateReviewer

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html_file", help="Path to single HTML file")
    parser.add_argument("--config", default="config/config.json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    load_config(args.config)
    llm_client = LLMClient()
    extractor = HtmlExtractor()
    generator = LLMTemplateGenerator(llm_client)
    reviewer = LLMTemplateReviewer(llm_client)

    html_path = Path(args.html_file)
    html_content = html_path.read_text(encoding="utf-8")
    logger.info("Testing: %s", html_path.name)

    # Step 1: Extract
    extracted = extractor.extract(html_content)
    logger.info("  Synopsis: %s", (extracted.synopsis or "(none)")[:80])
    logger.info("  Description: %s", (extracted.description or "(none)")[:80])

    if not extracted.synopsis and not extracted.description:
        logger.error("  Extraction failed: no content")
        return 1

    # Step 2: Generate
    template_def, error = generator.generate(extracted)
    if template_def is None:
        logger.error("  Generation failed: %s", error)
        return 1
    logger.info("  Generated: id=%s, params=%d", template_def.id, len(template_def.params))

    # Step 3: Review
    review_result = reviewer.review(template_def, strict=args.strict)
    logger.info("  Review passed=%s, issues=%d", review_result.passed, len(review_result.issues))
    for issue in review_result.issues:
        logger.info("    [%s] %s", issue.severity, issue.message)

    if not review_result.passed:
        logger.error("  Review rejected the template")
        return 1

    # Step 4: Render
    j2_content = render_j2(template_def)
    logger.info("  Rendered J2: %d chars", len(j2_content))
    print("\n--- Generated J2 (first 30 lines) ---")
    print("\n".join(j2_content.splitlines()[:30]))
    print("...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
