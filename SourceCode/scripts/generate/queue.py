"""Review queue for failed template generations.

Design: plan-j2-generate T-GEN-07, DC-0083
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QueueEntry:
    """A single failed generation record."""

    source_html: str
    stage: str
    reason: str
    raw_llm_output: str = ""
    template_def: dict[str, Any] | None = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class ReviewQueue:
    """Append-only JSONL queue for manual review.

    Design: DC-0083
    """

    def __init__(self, queue_file: Path) -> None:
        self._queue_file = queue_file

    def append(self, entry: QueueEntry) -> None:
        """Append a failed record to the queue.

        Args:
            entry: QueueEntry with failure details.
        """
        self._queue_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(entry), ensure_ascii=False)
        with self._queue_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_all(self) -> list[QueueEntry]:
        """Read all entries from the queue.

        Returns:
            List of QueueEntry objects.
        """
        if not self._queue_file.exists():
            return []

        entries: list[QueueEntry] = []
        with self._queue_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(QueueEntry(**data))
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("Skipping malformed queue entry: %s", exc)
        return entries

    def clear(self) -> None:
        """Clear the queue file."""
        if self._queue_file.exists():
            self._queue_file.unlink()
