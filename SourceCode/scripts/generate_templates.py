"""CLI entry for batch HTML to J2 template generation.

Usage (from SourceCode/ directory):
    python scripts/generate_templates.py --source <html_dir> --output <j2_dir>

Design: plan-j2-generate T-GEN-08, DC-0080
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src/ to path for existing module imports
_SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_SRC_DIR))

from config import load_config
from llm.client import LLMClient

from generate.extractor import HtmlExtractor
from generate.generator import LLMTemplateGenerator
from generate.queue import QueueEntry, ReviewQueue
from generate.renderer import render_j2
from generate.reviewer import LLMTemplateReviewer
from generate.state import GenerationState

logger = logging.getLogger(__name__)


def _list_html_files(source_dir: Path) -> list[Path]:
    """List all .html files recursively in source directory."""
    return sorted(source_dir.rglob("*.html"))


def _derive_category(source_path: Path) -> str:
    """Guess category from file path structure."""
    parts = [p.lower() for p in source_path.parts]
    if "raster" in parts:
        return "raster"
    if "vector" in parts:
        return "vector"
    return "general"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate J2 templates from GDAL HTML documentation"
    )
    parser.add_argument("--source", required=True, help="GDAL HTML source directory")
    parser.add_argument("--output", required=True, help="J2 template output directory")
    parser.add_argument(
        "--config",
        default="config/config.json",
        help="Config file path (default: config/config.json)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict review mode: any warning fails",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without writing files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocess all files (ignore state cache)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    source_dir = Path(args.source)
    output_dir = Path(args.output)
    config_path = Path(args.config)

    if not source_dir.exists():
        logger.error("Source directory not found: %s", source_dir)
        return 1

    # Load config and init LLM
    load_config(config_path)
    llm_client = LLMClient()

    # Init pipeline components
    extractor = HtmlExtractor()
    generator = LLMTemplateGenerator(llm_client)
    reviewer = LLMTemplateReviewer(llm_client)
    state = GenerationState(output_dir / ".generate_state.json")
    queue = ReviewQueue(output_dir / ".review_queue.jsonl")

    if args.force:
        state.clear()

    # List source files
    html_files = _list_html_files(source_dir)
    if not html_files:
        logger.warning("No HTML files found in %s", source_dir)
        return 0

    logger.info("Found %d HTML files", len(html_files))

    stats = {
        "total": 0,
        "success": 0,
        "failed_gen": 0,
        "failed_review": 0,
        "skipped": 0,
    }

    for html_file in html_files:
        rel_path = html_file.relative_to(source_dir).as_posix()
        stats["total"] += 1

        logger.info("[%d/%d] Processing: %s", stats["total"], len(html_files), rel_path)

        html_content = html_file.read_text(encoding="utf-8")

        # Skip if already processed
        if not args.force and state.is_processed(rel_path, html_content):
            logger.info("  Skipped (already processed)")
            stats["skipped"] += 1
            continue

        # Step 1: Extract
        extracted = extractor.extract(html_content)
        if not extracted.synopsis and not extracted.description:
            logger.warning("  No usable content extracted, skipping")
            queue.append(
                QueueEntry(
                    source_html=rel_path,
                    stage="extraction",
                    reason="No synopsis or description extracted",
                )
            )
            stats["failed_gen"] += 1
            continue

        # Step 2: Generate
        template_def, error = generator.generate(extracted)
        if template_def is None:
            logger.warning("  Generation failed: %s", error)
            queue.append(
                QueueEntry(
                    source_html=rel_path,
                    stage="generation",
                    reason=error,
                )
            )
            stats["failed_gen"] += 1
            continue

        logger.info(
            "  Generated: id=%s, params=%d", template_def.id, len(template_def.params)
        )

        # Step 3: Review
        review_result = reviewer.review(template_def, strict=args.strict)
        if not review_result.passed:
            logger.warning(
                "  Review failed with %d issue(s)", len(review_result.issues)
            )
            for issue in review_result.issues:
                logger.warning("    [%s] %s", issue.severity, issue.message)
            queue.append(
                QueueEntry(
                    source_html=rel_path,
                    stage="review",
                    reason="; ".join(
                        f"[{i.severity}] {i.message}" for i in review_result.issues
                    ),
                    template_def={
                        "id": template_def.id,
                        "name": template_def.name,
                        "command_template": template_def.command_template,
                    },
                )
            )
            stats["failed_review"] += 1
            continue

        # Step 4: Render and save
        j2_content = render_j2(template_def)

        # Derive output path from category + id
        category = template_def.category
        out_file = output_dir / category / f"{template_def.id}.j2"

        if not args.dry_run:
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(j2_content, encoding="utf-8")
            state.record(rel_path, html_content, str(out_file), "success")
            logger.info("  Saved: %s", out_file)
        else:
            logger.info("  [DRY RUN] Would save: %s", out_file)

        stats["success"] += 1

    # Summary
    logger.info("=" * 50)
    logger.info("Generation complete:")
    logger.info("  Total:      %d", stats["total"])
    logger.info("  Success:    %d", stats["success"])
    logger.info("  Skipped:    %d", stats["skipped"])
    logger.info("  Failed gen: %d", stats["failed_gen"])
    logger.info("  Failed rev: %d", stats["failed_review"])
    logger.info("  Queue:      %s", queue._queue_file)

    return 0


if __name__ == "__main__":
    sys.exit(main())
