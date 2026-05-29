"""HTML document extractor for template generation.

Wraps _GDALDocParser to produce structured ExtractedDoc output.

Design: plan-j2-generate T-GEN-02, DC-0088
"""

from rag.preprocess import extract_text_from_html

from generate.models import ExtractedDoc


class HtmlExtractor:
    """Extract structured document content from GDAL Sphinx HTML.

    Design: DC-0088
    """

    def extract(self, html_content: str) -> ExtractedDoc:
        """Extract title, synopsis, and description from GDAL HTML.

        Args:
            html_content: Raw HTML string.

        Returns:
            ExtractedDoc with title, synopsis, and description.
        """
        sections = extract_text_from_html(html_content)

        # Extract title from first section or document title
        title = ""
        if sections:
            raw_title = sections[0].get("title", "").split("—")[0].strip()
            title = raw_title

        # Find Synopsis section
        synopsis = ""
        for sec in sections:
            if "Synopsis" in sec.get("section", ""):
                synopsis = sec.get("content", "")
                break

        # Find Description section
        description = ""
        for sec in sections:
            if "Description" in sec.get("section", ""):
                description = sec.get("content", "")
                break

        # Truncate description to avoid overly long prompts
        if len(description) > 3000:
            description = description[:3000] + "\n...[truncated]"

        return ExtractedDoc(
            title=title,
            synopsis=synopsis,
            description=description,
            options=[],
        )
