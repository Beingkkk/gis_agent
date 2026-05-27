"""Unit tests for llm.params module.

Design: F3
"""

import json
from unittest.mock import MagicMock

import pytest

from llm.exceptions import LLMResponseError
from llm.models import Message, ParamResult
from llm.params import extract_params
from llm.prompts import PromptBuilder


class TestExtractParams:
    """Test extract_params function."""

    @pytest.fixture
    def builder(self) -> PromptBuilder:
        return PromptBuilder()

    @pytest.fixture
    def client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def param_schema(self) -> dict:
        return {
            "input": {
                "type": "file_path",
                "required": True,
                "description": "输入文件路径",
            },
            "output": {
                "type": "file_path",
                "required": True,
                "description": "输出文件路径",
            },
            "crs": {"type": "string", "required": False, "description": "目标坐标系"},
        }

    def test_returns_param_result(
        self, client: MagicMock, builder: PromptBuilder, param_schema: dict
    ) -> None:
        """F3: Normal extraction returns ParamResult."""
        client.chat.return_value = json.dumps(
            {
                "params": {"input": "roads.shp", "output": "roads.json"},
                "missing": ["crs"],
                "questions": ["请输入目标坐标系（如 EPSG:4326）"],
            }
        )

        result = extract_params(
            user_input="输入 roads.shp，输出 roads.json",
            template_id="shp2geojson",
            param_schema=param_schema,
            current_params={},
            history=[],
            client=client,
            builder=builder,
        )

        assert isinstance(result, ParamResult)
        assert result.params["input"] == "roads.shp"
        assert result.params["output"] == "roads.json"
        assert "crs" in result.missing
        assert len(result.questions) == 1

    def test_merges_with_current_params(
        self, client: MagicMock, builder: PromptBuilder, param_schema: dict
    ) -> None:
        """F3: Merges newly extracted params with current params."""
        client.chat.return_value = json.dumps(
            {
                "params": {"output": "roads.json"},
                "missing": ["crs"],
                "questions": ["请输入目标坐标系"],
            }
        )

        result = extract_params(
            user_input="输出 roads.json",
            template_id="shp2geojson",
            param_schema=param_schema,
            current_params={"input": "roads.shp"},
            history=[],
            client=client,
            builder=builder,
        )

        assert result.params["input"] == "roads.shp"
        assert result.params["output"] == "roads.json"

    def test_all_params_collected_no_questions(
        self, client: MagicMock, builder: PromptBuilder, param_schema: dict
    ) -> None:
        """F3: All required params collected, no questions."""
        client.chat.return_value = json.dumps(
            {
                "params": {
                    "input": "roads.shp",
                    "output": "roads.json",
                    "crs": "EPSG:4326",
                },
                "missing": [],
                "questions": [],
            }
        )

        result = extract_params(
            user_input="roads.shp roads.json EPSG:4326",
            template_id="shp2geojson",
            param_schema=param_schema,
            current_params={},
            history=[],
            client=client,
            builder=builder,
        )

        assert result.missing == []
        assert result.questions == []

    def test_includes_param_schema_in_prompt(
        self, client: MagicMock, builder: PromptBuilder, param_schema: dict
    ) -> None:
        """F3: Parameter schema included in prompt."""
        client.chat.return_value = json.dumps(
            {"params": {}, "missing": [], "questions": []}
        )

        extract_params(
            user_input="test",
            template_id="shp2geojson",
            param_schema=param_schema,
            current_params={},
            history=[],
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        system_prompt = call_args.kwargs["system_prompt"]
        assert "file_path" in system_prompt
        assert "输入文件路径" in system_prompt

    def test_includes_current_params_in_prompt(
        self, client: MagicMock, builder: PromptBuilder, param_schema: dict
    ) -> None:
        """F3: Current params state included in prompt."""
        client.chat.return_value = json.dumps(
            {"params": {}, "missing": [], "questions": []}
        )

        extract_params(
            user_input="test",
            template_id="shp2geojson",
            param_schema=param_schema,
            current_params={"input": "roads.shp"},
            history=[],
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        system_prompt = call_args.kwargs["system_prompt"]
        assert "roads.shp" in system_prompt

    def test_uses_low_temperature(
        self, client: MagicMock, builder: PromptBuilder, param_schema: dict
    ) -> None:
        """F3: Param extraction uses temperature=0.1."""
        client.chat.return_value = json.dumps(
            {"params": {}, "missing": [], "questions": []}
        )

        extract_params(
            user_input="test",
            template_id="shp2geojson",
            param_schema=param_schema,
            current_params={},
            history=[],
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        assert call_args.kwargs["temperature"] == 0.1

    def test_non_json_response_raises(
        self, client: MagicMock, builder: PromptBuilder, param_schema: dict
    ) -> None:
        """F3: Non-JSON response raises LLMResponseError."""
        client.chat.return_value = "invalid json"

        with pytest.raises(LLMResponseError):
            extract_params(
                user_input="test",
                template_id="shp2geojson",
                param_schema=param_schema,
                current_params={},
                history=[],
                client=client,
                builder=builder,
            )

    def test_missing_required_fields_in_json(
        self, client: MagicMock, builder: PromptBuilder, param_schema: dict
    ) -> None:
        """F3: JSON missing required fields raises LLMResponseError."""
        client.chat.return_value = json.dumps({"params": {}})

        with pytest.raises(LLMResponseError):
            extract_params(
                user_input="test",
                template_id="shp2geojson",
                param_schema=param_schema,
                current_params={},
                history=[],
                client=client,
                builder=builder,
            )

    def test_user_input_in_messages(
        self, client: MagicMock, builder: PromptBuilder, param_schema: dict
    ) -> None:
        """F3: Current user input is the last message."""
        client.chat.return_value = json.dumps(
            {"params": {}, "missing": [], "questions": []}
        )

        extract_params(
            user_input="输出叫 roads.json",
            template_id="shp2geojson",
            param_schema=param_schema,
            current_params={},
            history=[Message(role="user", content="之前的问题")],
            client=client,
            builder=builder,
        )

        call_args = client.chat.call_args
        messages = call_args.kwargs["messages"]
        assert messages[-1].role == "user"
        assert "roads.json" in messages[-1].content
