"""Tests for llm.template_generator module.

Design:
    DC-0094
"""

from unittest.mock import MagicMock

import pytest

from llm.models import Message
from llm.template_generator import (
    assemble_j2_body,
    auto_complete_params,
    build_generation_messages,
    generate_template_stream,
    generate_template_sync,
    parse_generated_response,
    sanitize_params,
)


class TestParseGeneratedResponse:
    """Tests for parse_generated_response robust JSON parsing."""

    def test_strip_markdown_json_fences(self) -> None:
        """Markdown ```json ... ``` fences are stripped before parsing."""
        text = (
            'Some explanation\n'
            '```json\n'
            '{"template_id": "test", "name": "Test"}\n'
            '```\n'
            'More text'
        )
        result = parse_generated_response(text)
        assert result["template_id"] == "test"
        assert result["name"] == "Test"

    def test_strip_plain_code_fences(self) -> None:
        """Markdown ``` ... ``` fences without language tag are stripped."""
        text = (
            '```\n'
            '{"template_id": "test", "name": "Test"}\n'
            '```'
        )
        result = parse_generated_response(text)
        assert result["template_id"] == "test"

    def test_fix_bare_json_keys(self) -> None:
        """Unquoted object keys like {name: "value"} are fixed."""
        text = '{template_id: "test", name: "Test", params: [{name: "input", type: "file_path"}]}'
        result = parse_generated_response(text)
        assert result["template_id"] == "test"
        assert result["params"][0]["name"] == "input"

    def test_extract_inner_braces(self) -> None:
        """When text contains multiple braces, extracts the innermost JSON object."""
        text = 'Here is the result: {"template_id": "test", "name": "Test"} and some more'
        result = parse_generated_response(text)
        assert result["template_id"] == "test"

    def test_pure_json(self) -> None:
        """Already-valid JSON parses directly."""
        text = '{"template_id": "test", "name": "Test", "body": "ogr2ogr {{ output }}"}'
        result = parse_generated_response(text)
        assert result["template_id"] == "test"
        assert result["body"] == "ogr2ogr {{ output }}"

    def test_invalid_json_raises(self) -> None:
        """Truly unparseable text raises ValueError."""
        with pytest.raises(ValueError):
            parse_generated_response("this is not json at all")


class TestSanitizeParams:
    """Tests for sanitize_params fixes."""

    def test_required_true_with_default_becomes_false(self) -> None:
        """Param with required=true and a default value → required=false."""
        params = [
            {"name": "format", "type": "string", "required": True, "default": "GeoJSON"},
        ]
        result = sanitize_params(params)
        assert result[0]["required"] is False
        assert result[0]["default"] == "GeoJSON"

    def test_enum_without_options_gets_placeholder(self) -> None:
        """Enum or format type with empty options list gets a placeholder."""
        params = [
            {"name": "of", "type": "format", "required": False, "options": []},
        ]
        result = sanitize_params(params)
        assert result[0]["options"] == ["(see documentation)"]

    def test_valid_param_unchanged(self) -> None:
        """Valid params pass through unchanged."""
        params = [
            {"name": "input", "type": "file_path", "required": True},
        ]
        result = sanitize_params(params)
        assert result[0]["name"] == "input"
        assert result[0]["required"] is True


class TestAutoCompleteParams:
    """Tests for auto_complete_params undeclared variable detection."""

    def test_undeclared_variable_added(self) -> None:
        """Body references a variable not in params → auto-add as optional boolean."""
        body = 'ogr2ogr{% if append %} -append{% endif %} {{ output | quote }} {{ input | quote }}'
        params = [
            {"name": "input", "type": "file_path", "required": True},
            {"name": "output", "type": "file_path", "required": True},
        ]
        result = auto_complete_params(body, params)
        names = {p["name"] for p in result}
        assert "append" in names
        append_param = [p for p in result if p["name"] == "append"][0]
        assert append_param["type"] == "boolean"
        assert append_param["required"] is False

    def test_all_declared_no_change(self) -> None:
        """All variables in body are already declared → no new params."""
        body = 'ogr2ogr {{ output | quote }} {{ input | quote }}'
        params = [
            {"name": "input", "type": "file_path", "required": True},
            {"name": "output", "type": "file_path", "required": True},
        ]
        result = auto_complete_params(body, params)
        assert len(result) == 2


class TestBuildGenerationMessages:
    """Tests for build_generation_messages."""

    def test_few_shot_structure(self) -> None:
        """Messages contain few-shot example, assistant ack, and document."""
        document_text = "GDAL Tool: gdalwarp\nSYNOPSIS: gdalwarp [options] src dst"
        messages = build_generation_messages(document_text)

        assert len(messages) == 3
        assert messages[0].role == "user"
        assert "ogr2ogr" in messages[0].content  # few-shot example contains ogr2ogr
        assert messages[1].role == "assistant"
        assert "Understood" in messages[1].content
        assert messages[2].role == "user"
        assert "gdalwarp" in messages[2].content


class TestGenerateTemplateSync:
    """Tests for generate_template_sync with mocked LLMClient."""

    def test_success_returns_parsed_dict(self) -> None:
        """LLM returns valid JSON → sync function returns parsed dict."""
        client = MagicMock()
        client.chat.return_value = (
            '{"template_id": "test_convert", "name": "Test", '
            '"description": "A test", "body": "echo {{ input }}", '
            '"params": [{"name": "input", "type": "file_path", "required": true}], '
            '"concepts": [], "notes": []}'
        )

        result = generate_template_sync(
            client=client,
            document_text="Convert data using ogr2ogr",
            config={"category": "vector", "tool_source": "GDAL"},
        )

        assert result["template_id"] == "test_convert"
        assert result["name"] == "Test"
        assert "body" in result
        assert "params" in result
        # Verify LLM was called with few-shot messages
        call_args = client.chat.call_args
        assert call_args is not None
        messages = call_args.kwargs["messages"]
        assert len(messages) == 3  # few-shot + ack + document

    def test_retry_on_parse_failure(self) -> None:
        """First response unparseable, second response valid → retry succeeds."""
        client = MagicMock()
        client.chat.side_effect = [
            "not valid json",  # attempt 1 fails
            '{"template_id": "test_retry", "name": "Retry", '
            '"description": "Works", "body": "echo ok", '
            '"params": [], "concepts": [], "notes": []}',  # attempt 2 succeeds
        ]

        result = generate_template_sync(
            client=client,
            document_text="Simple tool",
            config={},
        )

        assert result["template_id"] == "test_retry"
        assert client.chat.call_count == 2
        # Second call should have higher temperature
        second_call = client.chat.call_args_list[1]
        assert second_call.kwargs["temperature"] == 0.2

    def test_retry_exhausted_raises(self) -> None:
        """Both attempts fail to parse → raises ValueError."""
        client = MagicMock()
        client.chat.side_effect = [
            "not valid json",
            "still not valid json",
        ]

        with pytest.raises(ValueError, match="JSON parse failed"):
            generate_template_sync(
                client=client,
                document_text="Simple tool",
                config={},
            )


class TestGenerateTemplateStream:
    """Tests for generate_template_stream with mocked LLMClient."""

    def test_streaming_calls_on_chunk(self) -> None:
        """Each chunk from chat_stream is forwarded to on_chunk callback."""
        client = MagicMock()
        client.chat_stream.return_value = iter([
            '{"template_id": ',
            '"test_stream", ',
            '"name": "Stream"}',
        ])

        chunks: list[str] = []

        def on_chunk(chunk: str) -> None:
            chunks.append(chunk)

        result_text = generate_template_stream(
            client=client,
            document_text="Streaming test",
            config={},
            on_chunk=on_chunk,
        )

        assert chunks == ['{"template_id": ', '"test_stream", ', '"name": "Stream"}']
        assert result_text == '{"template_id": "test_stream", "name": "Stream"}'

    def test_streaming_empty_response(self) -> None:
        """Empty stream returns empty string."""
        client = MagicMock()
        client.chat_stream.return_value = iter([])

        chunks: list[str] = []

        result_text = generate_template_stream(
            client=client,
            document_text="Empty",
            config={},
            on_chunk=lambda c: chunks.append(c),
        )

        assert chunks == []
        assert result_text == ""


class TestAssembleJ2Body:
    """Tests for assemble_j2_body — building complete .j2 from LLM dict."""

    def test_assembles_comment_header(self) -> None:
        """Header contains @id, @name, @description, @category comments."""
        data = {
            "id": "test_tool",
            "name": "测试工具",
            "description": "一个测试工具",
            "category": "vector",
            "command_template": "ogr2ogr {{ output }} {{ input }}",
            "params": [],
        }
        body = assemble_j2_body(data)
        assert "{# @id test_tool #}" in body
        assert "{# @name 测试工具 #}" in body
        assert "{# @description 一个测试工具 #}" in body
        assert "{# @category vector #}" in body

    def test_assembles_keywords_concepts_notes(self) -> None:
        """Keywords, concepts, notes, seealso, common_errors become comments."""
        data = {
            "template_id": "test_tool",
            "name": "Test",
            "description": "Desc",
            "category": "general",
            "keywords": ["shp", "geojson"],
            "concepts": ["概念A"],
            "notes": ["注意1"],
            "seealso": ["other_tool"],
            "common_errors": [
                {"error_text": "Error A", "explanation": "因为X"}
            ],
            "command_template": "echo ok",
            "params": [],
        }
        body = assemble_j2_body(data)
        assert "{# @keyword shp #}" in body
        assert "{# @keyword geojson #}" in body
        assert '{# @concept "概念A" #}' in body
        assert "{# @note 注意1 #}" in body
        assert "{# @seealso other_tool #}" in body
        assert '{# @common_error "Error A" — 因为X #}' in body

    def test_assembles_params(self) -> None:
        """Params become @param comment lines with type, required, default, options."""
        data = {
            "id": "test_tool",
            "name": "Test",
            "description": "Desc",
            "category": "vector",
            "command_template": "ogr2ogr {{ output }} {{ input }}",
            "params": [
                {
                    "name": "input",
                    "type": "file_path",
                    "required": True,
                    "description": "输入文件",
                },
                {
                    "name": "of",
                    "type": "format",
                    "required": False,
                    "description": "输出格式",
                    "default": "GeoJSON",
                    "options": ["GeoJSON", "Shapefile"],
                },
            ],
        }
        body = assemble_j2_body(data)
        assert "{# @param input file_path required 输入文件 #}" in body
        assert (
            "{# @param of format optional 输出格式 default=GeoJSON options=GeoJSON,Shapefile #}"
            in body
        )

    def test_assembles_command_body(self) -> None:
        """Command body includes @echo off, REM, and the command_template."""
        data = {
            "id": "test_tool",
            "name": "Test",
            "description": "Desc",
            "category": "general",
            "command_template": "ogr2ogr -f GeoJSON {{ output }} {{ input }}",
            "params": [],
        }
        body = assemble_j2_body(data)
        assert "@echo off" in body
        assert "REM Generated by GIS Agent" in body
        assert "REM Template: test_tool" in body
        assert "ogr2ogr -f GeoJSON {{ output }} {{ input }}" in body
        assert "REM Done" in body

    def test_uses_body_fallback(self) -> None:
        """Falls back to 'body' key if 'command_template' is absent."""
        data = {
            "template_id": "test_tool",
            "name": "Test",
            "description": "Desc",
            "category": "general",
            "body": "gdalinfo {{ input }}",
            "params": [],
        }
        body = assemble_j2_body(data)
        assert "gdalinfo {{ input }}" in body

    def test_multiline_formatting(self) -> None:
        """Output has proper line breaks — not a single line."""
        data = {
            "id": "test_tool",
            "name": "Test",
            "description": "Desc",
            "category": "general",
            "command_template": "echo hello",
            "params": [],
        }
        body = assemble_j2_body(data)
        lines = body.split("\n")
        assert len(lines) > 5  # header + blank + @echo + REMs + blank + cmd + blank + REM
        assert lines[0] == "{# @id test_tool #}"
