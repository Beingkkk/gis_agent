"""Document extractors for template generation.

Convert raw HTML/Markdown into clean, structured text suitable for LLM input.

Design:
    plan-j2-generate DC-0088
"""

import re
from html.parser import HTMLParser
from typing import ClassVar


class HtmlExtractor(HTMLParser):
    """Extract clean text from HTML documents.

    Removes navigation, scripts, styles, and other noisy elements.
    Preserves the core document structure (headings, paragraphs, lists,
    tables, code blocks).

    Design:
        DC-0088
    """

    NOISY_TAGS: ClassVar[set[str]] = {
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside",
        "noscript",
        "iframe",
        "embed",
        "object",
        "form",
        "button",
        "input",
    }
    """Tags whose content is completely discarded."""

    BLOCK_TAGS: ClassVar[set[str]] = {
        "p",
        "div",
        "section",
        "article",
        "li",
        "td",
        "th",
        "dd",
        "dt",
        "pre",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "br",
        "hr",
        "tr",
    }
    """Tags that introduce line breaks in text output."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._text_parts: list[str] = []
        self._skip_depth = 0
        self._last_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._last_tag = tag
        if tag in self.NOISY_TAGS:
            self._skip_depth += 1
            return
        if tag in self.BLOCK_TAGS and self._text_parts and not self._text_parts[-1].endswith("\n"):
            self._text_parts.append("\n")
        if tag == "br":
            self._text_parts.append("\n")
        if tag in ("td", "th") and self._text_parts:
            self._text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.NOISY_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag in self.BLOCK_TAGS and self._text_parts and not self._text_parts[-1].endswith("\n"):
            self._text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        # Collapse multiple whitespace, but preserve single spaces
        cleaned = " ".join(data.split())
        if cleaned:
            self._text_parts.append(cleaned)
            if self._last_tag not in self.BLOCK_TAGS:
                self._text_parts.append(" ")

    def extract(self, html: str) -> str:
        """Extract clean text from HTML.

        Args:
            html: Raw HTML document text.

        Returns:
            Clean, newline-separated text with noisy elements removed.
        """
        self._text_parts = []
        self._skip_depth = 0
        self._last_tag = None
        self.feed(html)
        self.close()
        raw = "".join(self._text_parts)
        # Collapse multiple consecutive newlines
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


class MarkdownExtractor:
    """Extract clean text from Markdown documents.

    Removes YAML frontmatter, formatting noise, and converts links to
    plain text while preserving structure.

    Design:
        DC-0088
    """

    @staticmethod
    def extract(text: str) -> str:
        """Extract clean text from Markdown.

        Args:
            text: Raw Markdown document text.

        Returns:
            Clean text with frontmatter and excessive formatting removed.
        """
        # Remove YAML frontmatter
        text = MarkdownExtractor._remove_frontmatter(text)
        # Convert links [text](url) → text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Convert image alt ![alt](url) → alt
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Normalize heading markers (keep the text, remove #)
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Remove bold/italic markers but keep content
        text = re.sub(r"(\*{1,2}|_{1,2})(.+?)\1", r"\2", text)
        # Remove inline code backticks but keep content
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Remove horizontal rules
        text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _remove_frontmatter(text: str) -> str:
        """Remove YAML frontmatter if present."""
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    return "\n".join(lines[i + 1 :])
        return text
