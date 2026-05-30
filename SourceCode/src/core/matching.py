"""Template matching and scoring utilities.

Provides code-level keyword matching for template discovery.
Keywords are match-only metadata and are **not** included in LLM context
(see ``llm.qa._format_template_context``).

Design:
    DC-0094
"""

import logging
from typing import List, Tuple

from core.models import TemplateDef

logger = logging.getLogger(__name__)


def score_template_match(
    template: TemplateDef,
    user_input: str,
) -> int:
    """Score how well a template matches user input.

    Scoring rules (higher = better match):
    - Keyword match: +3 per keyword found in user input
    - Concept match: +2 per concept term/explanation found
    - ID/Name/Description word match: +1 per matching word
    - Note match: +1 per matching word

    Keywords are weighted highest because they are explicitly
    curated for matching purposes (DC-0090).

    Args:
        template: Template definition to score.
        user_input: Raw user input string.

    Returns:
        Integer score (0 = no match).
    """
    user_lower = user_input.lower()
    user_words = user_lower.split()
    score = 0

    # Keywords: highest weight (DC-0090)
    for keyword in template.keywords:
        if keyword.lower() in user_lower:
            score += 3

    # Concepts: high weight
    for term, expl in template.concepts:
        if term.lower() in user_lower or expl.lower() in user_lower:
            score += 2

    # ID, name, description: base weight
    for field in (
        template.id.lower(),
        template.name.lower(),
        template.description.lower(),
    ):
        if any(word in field for word in user_words):
            score += 1

    # Notes: base weight
    for note in template.notes:
        if any(word in note.lower() for word in user_words):
            score += 1

    return score


def find_matching_templates(
    templates: List[TemplateDef],
    user_input: str,
    top_n: int = 3,
) -> List[TemplateDef]:
    """Find top-N templates matching user input.

    Args:
        templates: All available templates.
        user_input: User's natural language input.
        top_n: Maximum number of candidates to return.

    Returns:
        List of matching templates, sorted by score descending.
    """
    scored: List[Tuple[int, TemplateDef]] = []

    for t in templates:
        s = score_template_match(t, user_input)
        if s > 0:
            scored.append((s, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:top_n]]
