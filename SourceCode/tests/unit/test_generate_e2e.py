"""Integration test for generate pipeline.

Uses real GDAL HTML but mocks LLM to avoid API costs.

Design: plan-j2-generate T-GEN-10
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from generate.extractor import HtmlExtractor
from generate.generator import LLMTemplateGenerator
from generate.renderer import render_j2
from generate.reviewer import LLMTemplateReviewer
from templates.scanner import scan_templates


SAMPLE_HTML = """<!DOCTYPE html>
<html><head><title>ogr2ogr &mdash; GDAL documentation</title></head>
<body><div role="main" class="document">
  <section id="ogr2ogr"><h1>ogr2ogr</h1>
    <p>Converts simple features data between file formats.</p>
    <section id="synopsis"><h2>Synopsis</h2>
      <pre>Usage: ogr2ogr [-f &lt;format&gt;] &lt;dst&gt; &lt;src&gt;</pre>
    </section>
    <section id="description"><h2>Description</h2>
      <p>It can also perform various operations.</p>
    </section>
  </section>
</div></body></html>
"""

LLM_RESPONSE = """{
  "id": "ogr2ogr_test",
  "name": "测试转换",
  "description": "使用 ogr2ogr 进行格式转换",
  "category": "vector",
  "command_template": "ogr2ogr -f {{ of | quote }} {{ output | safe_path | quote }} {{ input | safe_path | quote }}",
  "params": [
    {"name": "input", "type": "file_path", "required": true, "description": "输入文件"},
    {"name": "output", "type": "file_path", "required": true, "description": "输出文件"},
    {"name": "of", "type": "string", "required": false, "description": "输出格式"}
  ],
  "concepts": ["ogr2ogr 是转换工具"],
  "notes": ["注意格式"],
  "common_errors": [{"error_text": "Unable to open", "explanation": "路径错误"}],
  "seealso": []
}"""

REVIEW_PASS = '{"passed": true, "issues": [], "suggested_fix": null}'


def test_e2e_pipeline(tmp_path: Path) -> None:
    """End-to-end test: HTML -> Extract -> Generate -> Review -> Render -> Scan."""
    # Step 1: Extract
    extractor = HtmlExtractor()
    extracted = extractor.extract(SAMPLE_HTML)
    assert extracted.title == "ogr2ogr"
    assert "Usage: ogr2ogr" in extracted.synopsis

    # Step 2: Generate (mocked LLM)
    mock_client = MagicMock()
    mock_client.chat.return_value = LLM_RESPONSE
    generator = LLMTemplateGenerator(mock_client)
    template_def, error = generator.generate(extracted)
    assert error == ""
    assert template_def is not None
    assert template_def.id == "ogr2ogr_test"

    # Step 3: Review (mocked LLM)
    mock_client.chat.return_value = REVIEW_PASS
    reviewer = LLMTemplateReviewer(mock_client)
    review_result = reviewer.review(template_def, strict=True)
    assert review_result.passed is True

    # Step 4: Render
    j2_content = render_j2(template_def)
    assert "{# @id ogr2ogr_test #}" in j2_content
    assert "{{ input | safe_path | quote }}" in j2_content

    # Step 5: Scan verification
    out_file = tmp_path / "vector" / "ogr2ogr_test.j2"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(j2_content, encoding="utf-8")

    scanned = scan_templates(tmp_path)
    assert len(scanned) == 1
    assert scanned[0].id == "ogr2ogr_test"
    assert scanned[0].name == "测试转换"
    assert len(scanned[0].params) == 3
