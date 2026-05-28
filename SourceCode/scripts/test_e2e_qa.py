"""End-to-end test: RAG retrieval + LLM Q&A.

Usage:
    cd SourceCode
    set PYTHONPATH=src
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
    top_k = 5

    print("=" * 60)
    print("End-to-End Test: RAG + LLM Q&A")
    print("=" * 60)
    print(f"Query: {query}")
    print()

    # Step 1: Load config
    print("[1/4] Loading config...")
    try:
        from config import load_config

        config_path = Path(__file__).parent.parent / "config" / "config.json"
        load_config(config_path)
        print("      Config loaded.")
    except Exception as exc:
        logger.error("Failed to load config: %s", exc)
        return 1

    # Step 2: Initialize RAG retriever
    print("[2/4] Initializing RAG retriever (may take a moment)...")
    try:
        from rag.retriever import get_retriever

        retriever = get_retriever()
        print("      RAG retriever ready.")
    except Exception as exc:
        logger.error("Failed to initialize RAG: %s", exc)
        return 1

    # Step 3: Retrieve relevant documents
    print(f"[3/4] Retrieving top-{top_k} documents for query...")
    try:
        from rag.retriever import RetrievedDocument

        retrieved_docs: list[RetrievedDocument] = retriever.search(query, top_k=top_k)
        print(f"      Retrieved {len(retrieved_docs)} documents.")
        print()

        for i, doc in enumerate(retrieved_docs, 1):
            chunk = doc.chunk
            print(f"  [{i}] {chunk.source_file} / {chunk.section}")
            print(f"      distance={doc.distance:.4f}")
            content_preview = chunk.content[:200].replace("\n", " ")
            print(f"      {content_preview}...")
            print()
    except Exception as exc:
        logger.error("RAG retrieval failed: %s", exc)
        return 1

    # Step 4: Call LLM to generate answer
    print("[4/4] Calling LLM to generate answer...")
    try:
        from llm.client import LLMClient
        from llm.prompts import PromptBuilder
        from llm.qa import answer_question

        client = LLMClient()
        builder = PromptBuilder()

        answer = answer_question(
            user_input=query,
            retrieved_docs=retrieved_docs,
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
