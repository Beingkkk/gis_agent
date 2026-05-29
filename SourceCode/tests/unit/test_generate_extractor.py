"""Tests for generate.extractor module.

Design: plan-j2-generate T-GEN-02
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from generate.extractor import HtmlExtractor


SAMPLE_HTML = """<!DOCTYPE html>
<html><head><title>ogr2ogr — GDAL documentation</title></head>
<body><div role="main" class="document">
  <section id="ogr2ogr"><h1>ogr2ogr</h1>
    <p>Converts simple features data between file formats.</p>
    <section id="synopsis"><h2>Synopsis</h2>
      <pre>Usage: ogr2ogr [--help] [-f &lt;format&gt;] &lt;dst&gt; &lt;src&gt;</pre>
    </section>
    <section id="description"><h2>Description</h2>
      <p>It can also perform various operations.</p>
      <p>Second paragraph of description.</p>
    </section>
  </section>
</div></body></html>
"""


class TestHtmlExtractor:
    """HtmlExtractor tests."""

    @pytest.fixture
    def extractor(self) -> HtmlExtractor:
        return HtmlExtractor()

    def test_extract_title(self, extractor: HtmlExtractor) -> None:
        doc = extractor.extract(SAMPLE_HTML)
        assert doc.title == "ogr2ogr"

    def test_extract_synopsis(self, extractor: HtmlExtractor) -> None:
        doc = extractor.extract(SAMPLE_HTML)
        assert "Usage: ogr2ogr" in doc.synopsis
        assert "[-f" in doc.synopsis

    def test_extract_description(self, extractor: HtmlExtractor) -> None:
        doc = extractor.extract(SAMPLE_HTML)
        assert "perform various operations" in doc.description

    def test_description_truncation(self, extractor: HtmlExtractor) -> None:
        long_desc = "<p>word</p>" * 2000
        html = f"""<!DOCTYPE html>
<html><head><title>Test</title></head>
<body><div role="main" class="document">
  <section><h1>Test</h1>
    <section id="description"><h2>Description</h2>
      {long_desc}
    </section>
  </section>
</div></body></html>
"""
        doc = extractor.extract(html)
        assert len(doc.description) <= 3100  # 3000 + truncation marker
        assert "[truncated]" in doc.description

    def test_empty_html(self, extractor: HtmlExtractor) -> None:
        doc = extractor.extract("<html><body></body></html>")
        assert doc.title == ""
        assert doc.synopsis == ""
        assert doc.description == ""
