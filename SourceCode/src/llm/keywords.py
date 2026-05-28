"""Keyword extraction for multi-query retrieval.

Uses LLM to distill search keywords from user questions,
improving RAG recall for Q&A scenarios.

Design: plan-qa-optimization v1.0.0
"""

import json
import logging
from typing import List

from llm.client import LLMClient
from llm.models import Message
from llm.prompts import PromptBuilder

logger = logging.getLogger(__name__)

_MAX_KEYWORDS = 5

_KEYWORD_EXTRACTION_INSTRUCTION = """
【搜索关键词提炼】
请从用户的问题中提炼 2-3 个最适合用于向量语义搜索的关键词或短语。

要求：
1. 关键词应简洁、具体，最好包含 GDAL 工具名、格式名、参数名等技术术语
2. 可中英文混合，优先使用英文术语（因为文档是英文的）
3. 如果问题涉及多个概念，分别提炼每个概念的关键词
4. 返回格式：JSON 数组，例如 ["GeoJSON format", "GDAL ogr2ogr", "vector conversion"]
"""


def extract_keywords(
    user_input: str,
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
) -> List[str]:
    """Extract search keywords from user input using LLM.

    Falls back to ``[user_input]`` if LLM returns invalid JSON,
    empty list, or an error occurs.

    Args:
        user_input: The user's question.
        history: Conversation history messages.
        client: LLM client for keyword extraction.
        builder: Prompt builder for system prompt assembly.

    Returns:
        List of 1-5 unique, non-empty keywords/phrases.

    Design:
        plan-qa-optimization v1.0.0
    """
    base_prompt = builder.build_system_prompt()
    system_prompt = base_prompt + "\n" + _KEYWORD_EXTRACTION_INSTRUCTION

    try:
        response = client.chat(
            system_prompt=system_prompt,
            messages=list(history),
            temperature=0.1,
            current_input=user_input,
        )
    except Exception as exc:
        logger.warning("Keyword extraction LLM call failed: %s", exc)
        return [user_input]

    # Parse JSON array from response
    try:
        # Handle possible markdown code blocks
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        keywords = json.loads(cleaned)
        if not isinstance(keywords, list):
            raise ValueError("Response is not a JSON array")
    except Exception as exc:
        logger.debug("Failed to parse keywords JSON: %s (response=%r)", exc, response)
        return [user_input]

    # Filter: non-empty strings, deduplicate, strip whitespace
    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords:
        if isinstance(kw, str):
            stripped = kw.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                result.append(stripped)

    if not result:
        logger.debug("Keyword extraction returned empty list, falling back")
        return [user_input]

    # Limit to max keywords
    if len(result) > _MAX_KEYWORDS:
        result = result[:_MAX_KEYWORDS]
        logger.debug("Truncated keywords from %d to %d", len(keywords), _MAX_KEYWORDS)

    return result
