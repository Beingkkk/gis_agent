"""Tests for rag.preprocess HTML-to-chunks pipeline.

Design: DC-0020, DC-0021, DC-0025
"""

import json
from pathlib import Path

import pytest

from rag.preprocess import (
    _build_chunks_json,
    _list_html_files,
    extract_text_from_html,
    split_into_chunks,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_html() -> str:
    """Minimal GDAL-style HTML for unit testing."""
    return """<!DOCTYPE html>
<html>
<head><title>ogr2ogr — GDAL documentation</title></head>
<body>
<nav>Navigation menu</nav>
<div role="main" class="document">
  <section id="ogr2ogr">
    <h1>ogr2ogr</h1>
    <p>Converts simple features data between file formats.</p>
    <section id="synopsis">
      <h2>Synopsis</h2>
      <pre>Usage: ogr2ogr [--help] [--long-usage]</pre>
    </section>
    <section id="description">
      <h2>Description</h2>
      <p>It can also perform various operations.</p>
      <script>alert('xss')</script>
    </section>
  </section>
</div>
<footer>Footer content</footer>
</body>
</html>
"""


@pytest.fixture
def noisy_html() -> str:
    """HTML with heavy noise that must be stripped."""
    return """<html><head><title>Test Tool</title></head>
<body>
<div class="wy-nav-side">Sidebar</div>
<div role="main" class="document">
  <section><h1>Test Tool</h1>
  <style>.red{color:red}</style>
  <p>Real content here.</p>
  <div role="search"><form><input/></form></div>
  </section>
</div>
</body></html>
"""


@pytest.fixture
def long_content() -> str:
    """Generate content longer than chunk_size for split testing."""
    # Each paragraph ~100 chars, generate enough to exceed 512
    paragraph = (
        "This is a sample paragraph describing a GDAL option. "
        "It contains information about parameters and usage. "
    )
    return "\n\n".join([paragraph * 3] * 5)  # ~1500 chars


# ---------------------------------------------------------------------------
# HTML extraction tests
# ---------------------------------------------------------------------------


class TestHTMLExtract:
    """Tests for extract_text_from_html (DC-0020)."""

    def test_extract_title(self, sample_html: str) -> None:
        sections = extract_text_from_html(sample_html)
        assert sections[0]["title"] == "ogr2ogr"

    def test_extract_sections(self, sample_html: str) -> None:
        sections = extract_text_from_html(sample_html)
        # h1 + h2 sections should all be extracted
        assert len(sections) == 3
        assert sections[0]["section"] == "ogr2ogr"
        assert sections[1]["section"] == "Synopsis"
        assert sections[2]["section"] == "Description"

    def test_content_has_real_text(self, sample_html: str) -> None:
        sections = extract_text_from_html(sample_html)
        synopsis = [s for s in sections if s["section"] == "Synopsis"][0]
        assert "Usage: ogr2ogr" in synopsis["content"]

    def test_removes_script_and_style(self, sample_html: str) -> None:
        sections = extract_text_from_html(sample_html)
        all_content = " ".join(s["content"] for s in sections)
        assert "alert('xss')" not in all_content
        assert "xss" not in all_content

    def test_removes_nav_and_footer(self, sample_html: str) -> None:
        sections = extract_text_from_html(sample_html)
        all_content = " ".join(s["content"] for s in sections)
        assert "Navigation menu" not in all_content
        assert "Footer content" not in all_content

    def test_preserves_pre_content(self, sample_html: str) -> None:
        sections = extract_text_from_html(sample_html)
        synopsis = [s for s in sections if s["section"] == "Synopsis"][0]
        assert "Usage: ogr2ogr [--help] [--long-usage]" in synopsis["content"]

    def test_strips_noise_tags(self, noisy_html: str) -> None:
        sections = extract_text_from_html(noisy_html)
        all_content = " ".join(s["content"] for s in sections)
        assert "Sidebar" not in all_content
        assert 'role="search"' not in all_content.lower()
        assert "Real content here" in all_content

    def test_title_parsing_without_dash(self) -> None:
        html = (
            "<html><head><title>gdalwarp</title></head>"
            '<body><div role="main"><section><h1>gdalwarp</h1>'
            "<p>Raster warp.</p></section></div></body></html>"
        )
        sections = extract_text_from_html(html)
        assert sections[0]["title"] == "gdalwarp"


# ---------------------------------------------------------------------------
# Chunk splitting tests
# ---------------------------------------------------------------------------


class TestChunkSplit:
    """Tests for split_into_chunks (DC-0021)."""

    def test_no_split_within_size(self) -> None:
        sections = [
            {
                "title": "test",
                "section": "Small",
                "content": "Short content.",
            }
        ]
        chunks = split_into_chunks(sections, chunk_size=512, chunk_overlap=128)
        assert len(chunks) == 1
        assert chunks[0].content == "Short content."

    def test_split_long_content(self, long_content: str) -> None:
        sections = [
            {
                "title": "test",
                "section": "Big",
                "content": long_content,
            }
        ]
        chunks = split_into_chunks(sections, chunk_size=512, chunk_overlap=128)
        assert len(chunks) > 1
        # Each chunk should not exceed max allowed (1.5 * chunk_size)
        for chunk in chunks:
            assert len(chunk.content) <= 768

    def test_chunk_id_format(self) -> None:
        sections = [
            {
                "title": "ogr2ogr",
                "section": "Synopsis",
                "content": "Usage: ogr2ogr [--help]",
            }
        ]
        chunks = split_into_chunks(
            sections,
            chunk_size=512,
            chunk_overlap=128,
            source_file="programs/ogr2ogr.html",
        )
        assert chunks[0].id == "ogr2ogr-001"

    def test_token_estimate_positive(self) -> None:
        sections = [
            {
                "title": "t",
                "section": "s",
                "content": "Hello world.",
            }
        ]
        chunks = split_into_chunks(sections, chunk_size=512, chunk_overlap=128)
        assert chunks[0].token_estimate > 0

    def test_overlap_preserves_context(self, long_content: str) -> None:
        sections = [
            {
                "title": "t",
                "section": "s",
                "content": long_content,
            }
        ]
        chunks = split_into_chunks(
            sections, chunk_size=512, chunk_overlap=128, source_file="a.html"
        )
        if len(chunks) >= 2:
            # Adjacent chunks should share some text
            end_of_first = chunks[0].content[-100:]
            start_of_second = chunks[1].content[:100]
            # Some overlap should exist
            assert any(
                word in start_of_second
                for word in end_of_first.split()
                if len(word) > 3
            )

    def test_multi_section_chunks(self) -> None:
        sections = [
            {
                "title": "tool",
                "section": "Overview",
                "content": "Overview text here.",
            },
            {
                "title": "tool",
                "section": "Options",
                "content": "Options text here.",
            },
        ]
        chunks = split_into_chunks(sections, chunk_size=512, chunk_overlap=128)
        assert len(chunks) == 2
        assert chunks[0].section == "Overview"
        assert chunks[1].section == "Options"


# ---------------------------------------------------------------------------
# File listing tests
# ---------------------------------------------------------------------------


class TestFileFilter:
    """Tests for _list_html_files."""

    def test_include_patterns(self, tmp_path: Path) -> None:
        (tmp_path / "programs").mkdir()
        (tmp_path / "programs" / "a.html").write_text("a")
        (tmp_path / "programs" / "b.txt").write_text("b")
        files = _list_html_files(
            tmp_path, include_patterns=["programs/*.html"], exclude_patterns=[]
        )
        assert len(files) == 1
        assert files[0].name == "a.html"

    def test_exclude_patterns(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "programs").mkdir()
        (tmp_path / "api" / "x.html").write_text("x")
        (tmp_path / "programs" / "y.html").write_text("y")
        files = _list_html_files(
            tmp_path,
            include_patterns=["**/*.html"],
            exclude_patterns=["api/**"],
        )
        names = {f.name for f in files}
        assert "x.html" not in names
        assert "y.html" in names

    def test_recursive_include(self, tmp_path: Path) -> None:
        (tmp_path / "drivers" / "raster").mkdir(parents=True)
        (tmp_path / "drivers" / "vector").mkdir(parents=True)
        (tmp_path / "drivers" / "raster" / "geojson.html").write_text("r")
        (tmp_path / "drivers" / "vector" / "shp.html").write_text("v")
        files = _list_html_files(
            tmp_path,
            include_patterns=["drivers/**/*.html"],
            exclude_patterns=[],
        )
        names = {f.name for f in files}
        assert "geojson.html" in names
        assert "shp.html" in names


# ---------------------------------------------------------------------------
# JSON output tests
# ---------------------------------------------------------------------------


class TestJSONOutput:
    """Tests for _build_chunks_json."""

    def test_output_structure(self) -> None:
        sections = [
            {
                "title": "tool",
                "section": "Usage",
                "content": "tool --help",
            }
        ]
        chunks = split_into_chunks(sections, source_file="programs/tool.html")
        raw = _build_chunks_json(chunks, source="Test docs")
        assert raw["version"] == "1.0.0"
        assert raw["source"] == "Test docs"
        assert "generated_at" in raw
        assert len(raw["chunks"]) == 1
        chunk = raw["chunks"][0]
        assert chunk["id"] == "tool-001"
        assert chunk["source_file"] == "programs/tool.html"
        assert chunk["title"] == "tool"
        assert chunk["section"] == "Usage"
        assert chunk["content"] == "tool --help"
        assert isinstance(chunk["token_estimate"], int)

    def test_json_serializable(self) -> None:
        sections = [
            {
                "title": "t",
                "section": "s",
                "content": "content",
            }
        ]
        chunks = split_into_chunks(sections, source_file="a.html")
        raw = _build_chunks_json(chunks)
        # Should not raise
        json_text = json.dumps(raw, ensure_ascii=False, indent=2)
        assert "version" in json_text


# ---------------------------------------------------------------------------
# Integration / real HTML
# ---------------------------------------------------------------------------


class TestRealHTML:
    """Integration tests against real GDAL HTML files."""

    def test_ogr2ogr_html(self) -> None:
        """Verify extraction works on actual GDAL documentation."""
        html_path = (
            Path(__file__).parent.parent.parent.parent
            / "Document"
            / "Resource"
            / "gdal"
            / "build"
            / "doc"
            / "build"
            / "html"
            / "programs"
            / "ogr2ogr.html"
        )
        if not html_path.exists():
            pytest.skip("Real GDAL HTML not found at expected path")

        html = html_path.read_text(encoding="utf-8")
        sections = extract_text_from_html(html)
        assert len(sections) > 0

        # Should find Synopsis section
        synopsis = [s for s in sections if "Synopsis" in s["section"]]
        assert len(synopsis) > 0
        assert "Usage:" in synopsis[0]["content"]

        # Should find Description section
        desc = [s for s in sections if "Description" in s["section"]]
        assert len(desc) > 0
