"""Document extractors for template generation.

Convert raw HTML/Markdown into clean, structured text suitable for LLM input.

Design:
    plan-j2-generate DC-0088, ADR-0003
"""

import re
from typing import ClassVar

from bs4 import BeautifulSoup


class HtmlExtractor:
    """Extract clean text from HTML documents.

    Removes navigation, scripts, styles, and other noisy elements.
    Preserves the core document structure (headings, paragraphs, lists,
    tables, code blocks).

    Design:
        DC-0088, ADR-0003
    """

    NOISY_TAGS: ClassVar[frozenset[str]] = frozenset(
        {
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
    )
    """Tags whose content is completely discarded."""

    def extract(self, html: str) -> str:
        """Extract clean text from HTML.

        Args:
            html: Raw HTML document text.

        Returns:
            Clean, newline-separated text with noisy elements removed.
        """
        if not html:
            return ""

        soup = BeautifulSoup(html, "html.parser")

        # Remove noisy tags and their entire subtree
        for tag in soup.find_all(self.NOISY_TAGS):
            tag.decompose()

        # Replace <br> with newline so get_text honours it
        for br in soup.find_all("br"):
            br.replace_with("\n")

        # Extract text with a newline between every element.  This gives
        # block-level tags (p, div, li, td, pre, h1-h6, tr) natural
        # separation while keeping inline tags contiguous.
        text = soup.get_text(separator="\n")

        # Normalise whitespace: collapse runs of spaces and newlines
        lines = [" ".join(line.split()) for line in text.split("\n")]
        return "\n".join(line for line in lines if line)


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
