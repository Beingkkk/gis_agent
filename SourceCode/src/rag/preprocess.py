"""GDAL HTML documentation preprocessor.

Converts GDAL Sphinx-generated HTML into structured JSON chunks for
vector retrieval. Used only at development time; not imported at runtime.

Design: DC-0020, DC-0021, DC-0025
"""

import fnmatch
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentChunk:
    """A single document chunk for vector retrieval."""

    id: str
    source_file: str
    title: str
    section: str
    content: str
    token_estimate: int


# Internal mutable structure used during parsing.
@dataclass
class _Section:
    title: str = ""
    section: str = ""
    section_id: str = ""
    content_parts: list[str] = field(default_factory=list)
    order: int = 0


# ---------------------------------------------------------------------------
# HTML parser
# ---------------------------------------------------------------------------


class _GDALDocParser(HTMLParser):
    """Parse GDAL Sphinx HTML and extract structured text sections.

    Extracts content from <div role="main"> or <div itemprop="articleBody">,
    skipping navigation, scripts, styles, and footers.
    """

    _NOISE_TAGS: frozenset[str] = frozenset(
        {"script", "style", "nav", "footer", "form", "noscript"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.doc_title: str = ""
        self.in_title: bool = False
        self.tag_stack: list[str] = []
        self.main_depth: int = 0
        self.noise_depth: int = 0
        self.section_stack: list[_Section] = []
        self.sections: list[_Section] = []
        self._section_counter: int = 0
        self.in_heading: bool = False
        self._heading_buf: list[str] = []
        self._in_pre: bool = False

    # --- helpers ---

    def _is_main_div(self, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        if tag != "div":
            return False
        attr_dict = dict(attrs)
        return (
            attr_dict.get("role") == "main"
            or attr_dict.get("itemprop") == "articleBody"
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        """Collapse excessive whitespace but preserve single newlines."""
        # Replace any whitespace run with a single space
        cleaned = " ".join(text.split())
        # Strip Unicode private-use characters (e.g. Font Awesome icons)
        cleaned = "".join(ch for ch in cleaned if not (0xE000 <= ord(ch) <= 0xF8FF))
        return cleaned.strip()

    @staticmethod
    def _clean_heading(text: str) -> str:
        """Clean heading text: drop headerlink icons and collapse space."""
        text = "".join(ch for ch in text if not (0xE000 <= ord(ch) <= 0xF8FF))
        return " ".join(text.split()).strip()

    # --- handlers ---

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag_stack.append(tag)

        if tag == "title":
            self.in_title = True
        elif self._is_main_div(tag, attrs):
            self.main_depth = len(self.tag_stack)
        elif tag in self._NOISE_TAGS and self.main_depth > 0:
            if self.noise_depth == 0:
                self.noise_depth = len(self.tag_stack)
        elif tag == "section" and self.main_depth > 0:
            attr_dict = dict(attrs)
            sid = attr_dict.get("id") or ""
            sec = _Section(
                title=self.doc_title,
                section=sid,
                section_id=sid,
                order=self._section_counter,
            )
            self._section_counter += 1
            self.section_stack.append(sec)
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.section_stack:
            self.in_heading = True
            self._heading_buf = []
        elif tag == "pre" and self.section_stack:
            self._in_pre = True

    def handle_endtag(self, tag: str) -> None:
        # Pop stack until matching tag
        while self.tag_stack and self.tag_stack.pop() != tag:
            pass

        if tag == "title":
            self.in_title = False
        elif self.main_depth > 0 and len(self.tag_stack) < self.main_depth:
            # Exited the main content div — clear any pending sections
            self.main_depth = 0
            self.section_stack.clear()
        elif self.noise_depth > 0 and len(self.tag_stack) < self.noise_depth:
            self.noise_depth = 0

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.in_heading:
            heading_text = self._clean_heading("".join(self._heading_buf))
            if heading_text and self.section_stack:
                current = self.section_stack[-1]
                # Only use first heading as section name
                if current.section == current.section_id:
                    current.section = heading_text
            self.in_heading = False

        if tag == "pre" and self.section_stack:
            self._in_pre = False
            # Add explicit newline after pre block for readability
            self.section_stack[-1].content_parts.append("\n")

        if tag in {"p", "dd", "dt", "li", "div", "td"} and self.section_stack:
            if not self._in_pre:
                # Add space after block-level elements
                self.section_stack[-1].content_parts.append(" ")

        if tag == "section" and self.section_stack:
            sec = self.section_stack.pop()
            if self._in_pre:
                content = "".join(sec.content_parts)
            else:
                content = self._clean_text("".join(sec.content_parts))
            sec.content_parts = []
            if content or sec.section:
                sec.content_parts = [content]
                self.sections.append(sec)

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.doc_title += data
        elif self.main_depth > 0 and self.noise_depth == 0 and self.section_stack:
            current = self.section_stack[-1]
            if self.in_heading:
                self._heading_buf.append(data)
            else:
                if self._in_pre:
                    current.content_parts.append(data)
                else:
                    current.content_parts.append(data)

    def get_result(self) -> list[dict[str, str]]:
        """Return parsed sections as list of dicts.

        Sections are ordered by their appearance in the document
        (outer sections before nested inner ones).
        """
        result: list[dict[str, str]] = []
        for sec in sorted(self.sections, key=lambda s: s.order):
            content = sec.content_parts[0] if sec.content_parts else ""
            # Clean up title (drop "— GDAL documentation" suffix)
            title = sec.title.split("—")[0].strip()
            result.append(
                {
                    "title": title,
                    "section": sec.section,
                    "content": content,
                }
            )
        return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_text_from_html(html_content: str) -> list[dict[str, str]]:
    """Extract structured text sections from GDAL Sphinx HTML.

    Args:
        html_content: Raw HTML string.

    Returns:
        List of section dicts with keys: title, section, content.

    Design: DC-0020
    """
    parser = _GDALDocParser()
    parser.feed(html_content)
    return parser.get_result()


def split_into_chunks(
    sections: list[dict[str, str]],
    *,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    source_file: str = "",
) -> list[DocumentChunk]:
    """Split extracted sections into DocumentChunks.

    First-level split is by section (already semantic).
    Second-level split applies to sections whose content exceeds
    chunk_size * 1.5 characters.

    Args:
        sections: Output from extract_text_from_html().
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between split chunks in characters.
        source_file: Relative path used for chunk IDs.

    Returns:
        List of DocumentChunk objects.

    Design: DC-0021
    """
    chunks: list[DocumentChunk] = []
    max_size = int(chunk_size * 1.5)

    # Derive base id from source file (e.g. "programs/ogr2ogr.html" → "ogr2ogr")
    base_id = Path(source_file).stem if source_file else "doc"

    for sec in sections:
        title = sec["title"]
        section_name = sec["section"]
        content = sec["content"]

        if not content.strip():
            continue

        if len(content) <= max_size:
            # No need to split
            chunks.append(
                DocumentChunk(
                    id=f"{base_id}-{len(chunks) + 1:03d}",
                    source_file=source_file,
                    title=title,
                    section=section_name,
                    content=content.strip(),
                    token_estimate=max(1, len(content) // 4),
                )
            )
        else:
            # Split into overlapping pieces
            start = 0
            piece_idx = 0
            while start < len(content):
                end = start + chunk_size
                if end >= len(content):
                    piece = content[start:]
                else:
                    # Try to find a good break point (paragraph or sentence)
                    piece = content[start:end]
                    # Look for paragraph break first
                    para_break = piece.rfind("\n\n")
                    if para_break > chunk_size // 2:
                        end = start + para_break
                    else:
                        # Try sentence break
                        sent_break = piece.rfind(". ")
                        if sent_break > chunk_size // 2:
                            end = start + sent_break + 1
                        else:
                            # Try space break
                            space_break = piece.rfind(" ")
                            if space_break > chunk_size // 2:
                                end = start + space_break
                    piece = content[start:end]

                piece_idx += 1
                chunks.append(
                    DocumentChunk(
                        id=f"{base_id}-{len(chunks) + 1:03d}",
                        source_file=source_file,
                        title=title,
                        section=section_name,
                        content=piece.strip(),
                        token_estimate=max(1, len(piece) // 4),
                    )
                )

                if end >= len(content):
                    break
                start = max(start + 1, end - chunk_overlap)

    return chunks


def _list_html_files(
    source_dir: Path,
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> list[Path]:
    """List HTML files matching include patterns but not exclude patterns.

    Args:
        source_dir: Root directory to scan.
        include_patterns: Glob patterns to include (e.g. "programs/*.html").
        exclude_patterns: Glob patterns to exclude (e.g. "api/**").

    Returns:
        Sorted list of matching file paths.
    """
    candidates: set[Path] = set()

    for pattern in include_patterns:
        # pathlib glob does not support ** in all Python versions equally;
        # use rglob for recursive patterns.
        if "**" in pattern:
            parts = pattern.split("/**/")
            if len(parts) == 2 and parts[0] == "":
                # Pattern like "**/*.html"
                candidates.update(source_dir.rglob(parts[1]))
            elif len(parts) == 2:
                # Pattern like "drivers/**/*.html"
                sub_dir = source_dir / parts[0]
                if sub_dir.exists():
                    candidates.update(sub_dir.rglob(parts[1]))
            else:
                candidates.update(source_dir.glob(pattern))
        else:
            candidates.update(source_dir.glob(pattern))

    # Apply excludes
    def _is_excluded(path: Path) -> bool:
        rel = path.relative_to(source_dir).as_posix()
        for pat in exclude_patterns:
            if "**" in pat:
                # Convert **/something to regex
                regex_pat = pat.replace("**", "###DOUBLESTAR###")
                regex_pat = regex_pat.replace("*", "[^/]*")
                regex_pat = regex_pat.replace("###DOUBLESTAR###", ".*")
                regex_pat = regex_pat.replace("?", ".")
                if re.match(regex_pat + "$", rel):
                    return True
            else:
                # Simple fnmatch on the relative path or filename
                if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat):
                    return True
        return False

    result = [p for p in candidates if p.is_file() and not _is_excluded(p)]
    return sorted(result)


def _build_chunks_json(
    chunks: list[DocumentChunk],
    *,
    source: str = "GDAL documentation",
) -> dict[str, Any]:
    """Build the JSON structure for chunks output.

    Args:
        chunks: List of DocumentChunk objects.
        source: Source description string.

    Returns:
        Dict ready for json.dumps().

    Design: DC-0025
    """
    return {
        "version": "1.0.0",
        "source": source,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "chunks": [
            {
                "id": c.id,
                "source_file": c.source_file,
                "title": c.title,
                "section": c.section,
                "content": c.content,
                "token_estimate": c.token_estimate,
            }
            for c in chunks
        ],
    }


def preprocess_directory(
    source_dir: Path,
    output_path: Path,
    *,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
) -> int:
    """Preprocess GDAL HTML docs into JSON chunks file.

    Args:
        source_dir: Root HTML directory.
        output_path: Where to write the JSON file.
        include_patterns: File patterns to include.
        exclude_patterns: File patterns to exclude.
        chunk_size: Target chunk size.
        chunk_overlap: Overlap between chunks.

    Returns:
        Total number of chunks generated.

    Design: DC-0020, DC-0021, DC-0025
    """
    if include_patterns is None:
        include_patterns = ["programs/*.html", "drivers/**/*.html"]
    if exclude_patterns is None:
        exclude_patterns = ["api/**", "_*/**"]

    files = _list_html_files(source_dir, include_patterns, exclude_patterns)

    all_chunks: list[DocumentChunk] = []
    for html_file in files:
        html = html_file.read_text(encoding="utf-8")
        sections = extract_text_from_html(html)
        rel_path = html_file.relative_to(source_dir).as_posix()
        chunks = split_into_chunks(
            sections,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            source_file=rel_path,
        )
        all_chunks.extend(chunks)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw = _build_chunks_json(all_chunks)
    output_path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return len(all_chunks)
