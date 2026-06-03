"""Tests for templates.extractors module.

Design:
    plan-j2-generate DC-0088, T-GEN-WEB-08
"""

import pytest

from templates.extractors import HtmlExtractor, MarkdownExtractor


class TestHtmlExtractor:
    """HtmlExtractor tests."""

    def test_noise_removal(self) -> None:
        """script/style/nav/footer/header/aside content is stripped."""
        html = (
            "<html><body>"
            "<nav>Navigation</nav>"
            "<header>Header</header>"
            "<script>alert('xss')</script>"
            "<style>body{color:red}</style>"
            "<aside>Sidebar</aside>"
            "<footer>Footer</footer>"
            "<form><input/></form>"
            "<div>Main content</div>"
            "</div></body></html>"
        )
        extractor = HtmlExtractor()
        result = extractor.extract(html)
        assert "Navigation" not in result
        assert "Header" not in result
        assert "alert" not in result
        assert "color:red" not in result
        assert "Sidebar" not in result
        assert "Footer" not in result
        assert "Main content" in result

    def test_block_tags_introduce_newlines(self) -> None:
        """Block-level tags produce line breaks in output."""
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        extractor = HtmlExtractor()
        result = extractor.extract(html)
        assert "First paragraph." in result
        assert "Second paragraph." in result
        # Two paragraphs should be separated by at least one newline
        assert "\n" in result

    def test_preserve_table_content(self) -> None:
        """Table cells are preserved with spaces between them."""
        html = (
            "<table><tr>"
            "<th>Option</th><th>Description</th>"
            "</tr><tr>"
            "<td>-f</td><td>Format</td>"
            "</tr></table>"
        )
        extractor = HtmlExtractor()
        result = extractor.extract(html)
        assert "Option" in result
        assert "Description" in result
        assert "-f" in result
        assert "Format" in result

    def test_nested_skip_tags(self) -> None:
        """Nested noisy tags are fully skipped."""
        html = (
            "<div>Before</div>"
            "<nav><div>Nested nav</div></nav>"
            "<div>After</div>"
        )
        extractor = HtmlExtractor()
        result = extractor.extract(html)
        assert "Before" in result
        assert "After" in result
        assert "Nested nav" not in result

    def test_empty_html(self) -> None:
        """Empty input returns empty string."""
        extractor = HtmlExtractor()
        assert extractor.extract("") == ""

    def test_br_tag(self) -> None:
        """br tags become newlines."""
        html = "Line one<br/>Line two"
        extractor = HtmlExtractor()
        result = extractor.extract(html)
        assert "Line one" in result
        assert "Line two" in result
        assert "\n" in result


class TestMarkdownExtractor:
    """MarkdownExtractor tests."""

    def test_remove_frontmatter(self) -> None:
        """YAML frontmatter between --- fences is removed."""
        md = (
            "---\n"
            "title: ogr2ogr\n"
            "version: 3.9\n"
            "---\n"
            "# ogr2ogr\n\n"
            "Convert vector data.\n"
        )
        result = MarkdownExtractor.extract(md)
        assert "title: ogr2ogr" not in result
        assert "version: 3.9" not in result
        assert "ogr2ogr" in result
        assert "Convert vector data." in result

    def test_no_frontmatter(self) -> None:
        """Content without frontmatter is preserved."""
        md = "# ogr2ogr\n\nConvert vector data.\n"
        result = MarkdownExtractor.extract(md)
        assert "ogr2ogr" in result
        assert "Convert vector data." in result

    def test_links_to_plain_text(self) -> None:
        """[text](url) becomes text."""
        md = "See [ogr2ogr docs](https://gdal.org/programs/ogr2ogr.html) for details."
        result = MarkdownExtractor.extract(md)
        assert "ogr2ogr docs" in result
        assert "https://gdal.org" not in result
        assert "[" not in result

    def test_images_to_alt_text(self) -> None:
        """![alt](url) becomes alt."""
        md = "Check ![workflow diagram](img/flow.png) below."
        result = MarkdownExtractor.extract(md)
        assert "workflow diagram" in result
        assert "![" not in result

    def test_remove_bold_italic(self) -> None:
        """Bold and italic markers are stripped, content kept."""
        md = "This is **bold** and _italic_ text."
        result = MarkdownExtractor.extract(md)
        assert "bold" in result
        assert "italic" in result
        assert "**" not in result
        assert "_italic_" not in result

    def test_remove_inline_code_backticks(self) -> None:
        """Inline code backticks are stripped, content kept."""
        md = "Use `ogr2ogr -f GeoJSON` to convert."
        result = MarkdownExtractor.extract(md)
        assert "ogr2ogr -f GeoJSON" in result
        assert "`" not in result

    def test_remove_horizontal_rules(self) -> None:
        """Horizontal rules are removed."""
        md = "Section one\n---\nSection two"
        result = MarkdownExtractor.extract(md)
        assert "Section one" in result
        assert "Section two" in result
        assert "---" not in result

    def test_remove_html_tags(self) -> None:
        """Embedded HTML tags are removed."""
        md = "Text with <span class='x'>inline html</span>."
        result = MarkdownExtractor.extract(md)
        assert "inline html" in result
        assert "<span" not in result

    def test_headings_preserved(self) -> None:
        """Heading text is preserved, # markers removed."""
        md = "## Usage\n\n### Options"
        result = MarkdownExtractor.extract(md)
        assert "Usage" in result
        assert "Options" in result
        assert "#" not in result

    def test_empty_input(self) -> None:
        """Empty input returns empty string."""
        assert MarkdownExtractor.extract("") == ""
