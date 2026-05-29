"""End-to-end test: Template-knowledge Q&A.

Usage:
    cd SourceCode
    python scripts/test_e2e_qa.py
"""

import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("e2e_qa")


def main() -> int:
    """Run end-to-end Q&A test."""
    query = "shp是什么"

    print("=" * 60)
    print("End-to-End Test: Template Knowledge + LLM Q&A")
    print("=" * 60)
    print(f"Query: {query}")
    print()

    # Step 1: Load config
    print("[1/3] Loading config...")
    try:
        from config import load_config

        config_path = Path(__file__).parent.parent / "config" / "config.json"
        load_config(config_path)
        print("      Config loaded.")
    except Exception as exc:
        logger.error("Failed to load config: %s", exc)
        return 1

    # Step 2: Scan templates and find matching ones
    print("[2/3] Scanning templates for knowledge context...")
    try:
        from templates import scan_templates

        template_dir = Path(__file__).parent.parent / "data" / "templates"
        templates = scan_templates(template_dir)
        print(f"      Found {len(templates)} templates.")

        # Simple keyword matching for demo
        matched = [t for t in templates if "shp" in t.id.lower()]
        print(f"      Matched {len(matched)} templates for context.")
    except Exception as exc:
        logger.error("Template scanning failed: %s", exc)
        return 1

    # Step 3: Call LLM to generate answer
    print("[3/3] Calling LLM to generate answer...")
    try:
        from llm.client import LLMClient
        from llm.prompts import PromptBuilder
        from llm.qa import answer_question

        client = LLMClient()
        builder = PromptBuilder()

        answer = answer_question(
            user_input=query,
            templates=matched,
            history=[],
            client=client,
            builder=builder,
        )

        print()
        print("=" * 60)
        print("ANSWER:")
        print("=" * 60)
        print(answer)
        print("=" * 60)

    except Exception as exc:
        logger.error("LLM Q&A failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
