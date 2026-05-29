"""Tests for generate.queue module.

Design: plan-j2-generate T-GEN-07
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from generate.queue import QueueEntry, ReviewQueue


class TestReviewQueue:
    """ReviewQueue tests."""

    def test_append_and_read(self, tmp_path: Path) -> None:
        queue_file = tmp_path / "review_queue.jsonl"
        queue = ReviewQueue(queue_file)

        entry = QueueEntry(
            source_html="programs/ogr2ogr.html",
            stage="generation",
            reason="JSON parse failed",
            raw_llm_output="not json",
        )
        queue.append(entry)

        entries = queue.read_all()
        assert len(entries) == 1
        assert entries[0].source_html == "programs/ogr2ogr.html"
        assert entries[0].stage == "generation"
        assert entries[0].timestamp != ""

    def test_multiple_entries(self, tmp_path: Path) -> None:
        queue_file = tmp_path / "review_queue.jsonl"
        queue = ReviewQueue(queue_file)

        queue.append(QueueEntry("a.html", "generation", "fail1"))
        queue.append(QueueEntry("b.html", "review", "fail2"))

        entries = queue.read_all()
        assert len(entries) == 2
        assert entries[0].source_html == "a.html"
        assert entries[1].source_html == "b.html"

    def test_empty_queue(self, tmp_path: Path) -> None:
        queue_file = tmp_path / "review_queue.jsonl"
        queue = ReviewQueue(queue_file)

        entries = queue.read_all()
        assert entries == []

    def test_clear(self, tmp_path: Path) -> None:
        queue_file = tmp_path / "review_queue.jsonl"
        queue = ReviewQueue(queue_file)
        queue.append(QueueEntry("test.html", "generation", "fail"))

        queue.clear()

        assert not queue_file.exists()
        assert queue.read_all() == []
