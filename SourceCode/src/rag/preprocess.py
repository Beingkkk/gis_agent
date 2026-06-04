"""GDAL HTML documentation preprocessor.

Converts GDAL Sphinx-generated HTML into structured JSON chunks for
vector retrieval. Used only at development time; not imported at runtime.

Design: DC-0020, DC-0021, DC-0025, ADR-0003
"""

import fnmatch
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

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


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------


def extract_text_from_html(html_content: str) -> list[dict[str, str]]:
    """Extract structured text sections from GDAL Sphinx HTML.

    Uses BeautifulSoup to parse the document, locate the main content
    area, and split it into sections by ``<section>`` tags.

    Args:
        html_content: Raw HTML string.

    Returns:
        List of section dicts with keys: title, section, content.

    Design: DC-0020, ADR-0003
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Document title
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text().split("—")[0].strip()

    # Locate main content (GDAL Sphinx uses role="main" or articleBody)
    main = soup.find("div", role="main") or soup.find("div", itemprop="articleBody")
    if not main:
        return []

    # Strip noise tags inside main content
    for tag in main.find_all({"script", "style", "nav", "footer", "form", "noscript"}):
        tag.decompose()

    result: list[dict[str, str]] = []
    for sec in main.find_all("section"):
        heading = sec.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        section_name = (
            heading.get_text(strip=True) if heading else str(sec.get("id", ""))
        )
        # Strip Unicode private-use characters (e.g. Font Awesome icons
        # in Sphinx headerlink anchors) that the old HTMLParser cleaned.
        section_name = "".join(
            ch for ch in section_name if not (0xE000 <= ord(ch) <= 0xF8FF)
        )

        # Clone the section so we can decompose nested elements without
        # mutating the original tree (find_all returns a snapshot but
        # Tag.extract mutates the live DOM).
        sec_copy = BeautifulSoup(str(sec), "html.parser").find("section")
        if sec_copy is None:
            continue

        # Remove heading so its text doesn't duplicate section_name
        h = sec_copy.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if h:
            h.decompose()

        # Remove nested sections so their text doesn't leak into the
        # parent content (matching the old HTMLParser behaviour where
        # each section was independently extracted).
        for nested in sec_copy.find_all("section"):
            nested.decompose()

        content = " ".join(sec_copy.get_text(separator=" ", strip=True).split())

        if content or section_name:
            result.append(
                {
                    "title": title,
                    "section": section_name,
                    "content": content,
                }
            )

    return result


# ---------------------------------------------------------------------------
# Chunk splitting
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# File listing helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# JSON output builder
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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
