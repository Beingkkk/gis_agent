"""Generation state tracking for resume support.

Design: plan-j2-generate T-GEN-06, DC-0084
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class _StateEntry:
    """Single processed file record."""

    source_path: str
    content_hash: str
    output_path: str
    status: str  # "success" | "failed"


class GenerationState:
    """Track processed files to support resume and skip.

    Design: DC-0084
    """

    def __init__(self, state_file: Path) -> None:
        self._state_file = state_file
        self._entries: dict[str, _StateEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load state from disk if exists."""
        if not self._state_file.exists():
            return
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            for item in raw.get("entries", []):
                entry = _StateEntry(**item)
                self._entries[entry.source_path] = entry
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("Failed to load state file: %s", exc)
            self._entries = {}

    def _save(self) -> None:
        """Persist state to disk."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "entries": [asdict(e) for e in self._entries.values()],
        }
        self._state_file.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute MD5 hash of content string."""
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def is_processed(self, source_path: str, content: str) -> bool:
        """Check if source file was already processed with same content.

        Args:
            source_path: Relative path of source file.
            content: Current file content.

        Returns:
            True if previously processed successfully with same hash.
        """
        entry = self._entries.get(source_path)
        if entry is None:
            return False
        if entry.status != "success":
            return False
        current_hash = self._compute_hash(content)
        return entry.content_hash == current_hash

    def record(
        self,
        source_path: str,
        content: str,
        output_path: str,
        status: str,
    ) -> None:
        """Record processing result for a source file.

        Args:
            source_path: Relative path of source file.
            content: File content (for hash).
            output_path: Generated output path.
            status: "success" or "failed".
        """
        self._entries[source_path] = _StateEntry(
            source_path=source_path,
            content_hash=self._compute_hash(content),
            output_path=output_path,
            status=status,
        )
        self._save()

    def clear(self) -> None:
        """Clear all state entries and delete state file."""
        self._entries = {}
        if self._state_file.exists():
            self._state_file.unlink()
