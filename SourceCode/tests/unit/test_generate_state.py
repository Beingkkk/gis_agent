"""Tests for generate.state module.

Design: plan-j2-generate T-GEN-06
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


from generate.state import GenerationState


class TestGenerationState:
    """GenerationState tests."""

    def test_new_state_empty(self, tmp_path: Path) -> None:
        state_file = tmp_path / ".state.json"
        state = GenerationState(state_file)
        assert not state.is_processed("test.html", "content")

    def test_record_and_check(self, tmp_path: Path) -> None:
        state_file = tmp_path / ".state.json"
        state = GenerationState(state_file)

        state.record("a/b.html", "hello", "output.j2", "success")

        assert state.is_processed("a/b.html", "hello")
        assert not state.is_processed("a/b.html", "different")
        assert not state.is_processed("other.html", "hello")

    def test_failed_not_processed(self, tmp_path: Path) -> None:
        state_file = tmp_path / ".state.json"
        state = GenerationState(state_file)

        state.record("test.html", "hello", "", "failed")

        assert not state.is_processed("test.html", "hello")

    def test_persistence(self, tmp_path: Path) -> None:
        state_file = tmp_path / ".state.json"

        state1 = GenerationState(state_file)
        state1.record("x.html", "data", "out.j2", "success")

        state2 = GenerationState(state_file)
        assert state2.is_processed("x.html", "data")

    def test_clear(self, tmp_path: Path) -> None:
        state_file = tmp_path / ".state.json"
        state = GenerationState(state_file)
        state.record("test.html", "hello", "out.j2", "success")

        state.clear()

        assert not state.is_processed("test.html", "hello")
        assert not state_file.exists()
