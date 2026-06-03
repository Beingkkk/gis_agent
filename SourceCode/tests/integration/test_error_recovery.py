"""Integration test: error recovery scenarios.

Verifies the system recovers gracefully from invalid parameters
and other error conditions.

【已废弃，代码保留】SessionProcessor 仅用于 CLI 层，不再维护。
参见 constitution.md §6.1、CLAUDE.md Key Files 表。
Design: plan-integration v1.0.0 (T-INT-04)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.models import Session, SessionState
from core.processor import SessionProcessor
from llm.models import IntentResult, ParamResult


class TestErrorRecovery:
    """Error conditions and recovery paths."""

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_missing_required_param_stays_in_collect(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """Missing required 'output' param keeps state in PARAM_COLLECT."""
        mock_classify.return_value = IntentResult(
            template_id="gdal_mdim_convert",
            confidence=0.95,
            reasoning="Conversion",
        )
        # Only input provided, output missing
        mock_extract.return_value = ParamResult(
            params={"input": "input.nc"},
            missing=["output"],
            questions=["请输入输出文件路径（output）："],
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "转换多维数据")
        assert session.state == SessionState.PARAM_COLLECT

        session, response = processor_with_real_templates.process(
            session, "输入 input.nc"
        )
        assert session.state == SessionState.PARAM_COLLECT
        assert "output" in response or "输出" in response or "缺失" in response

    @patch("core.processor.classify_intent")
    @patch("core.processor.extract_params")
    def test_correction_after_validation_failure(
        self,
        mock_extract: MagicMock,
        mock_classify: MagicMock,
        processor_with_real_templates: SessionProcessor,
    ) -> None:
        """Invalid param → error → corrected param → success."""
        mock_classify.return_value = IntentResult(
            template_id="gdal_mdim_convert",
            confidence=0.95,
            reasoning="Conversion",
        )

        session = Session()
        session, _ = processor_with_real_templates.process(session, "转换多维数据")
        assert session.state == SessionState.PARAM_COLLECT

        # First attempt: output path has invalid characters (pipe)
        mock_extract.return_value = ParamResult(
            params={"input": "input.nc", "output": "out|put.zarr"},
            missing=[],
            questions=[],
        )
        session, response = processor_with_real_templates.process(
            session, "输入 input.nc，输出 out|put.zarr"
        )
        assert session.state == SessionState.PARAM_COLLECT

        # Second attempt: corrected path
        mock_extract.return_value = ParamResult(
            params={"input": "input.nc", "output": "output.zarr"},
            missing=[],
            questions=[],
        )
        session, response = processor_with_real_templates.process(
            session, "输出 output.zarr"
        )
        assert session.state == SessionState.SCRIPT_PREVIEW
        assert "output.zarr" in response
