"""RAG-enhanced document Q&A.

Design: F1, P4
"""

import logging
from typing import List

from llm.client import LLMClient
from llm.models import Message
from llm.prompts import PromptBuilder
from rag.retriever import RetrievedDocument

logger = logging.getLogger(__name__)


def _format_retrieved_docs(docs: List[RetrievedDocument]) -> str:
    """Format retrieved documents into context string.

    Args:
        docs: Retrieved documents from ChromaDB.

    Returns:
        Formatted context string.
    """
    if not docs:
        return "（未检索到相关文档片段）"

    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        chunk = doc.chunk
        parts.append(
            f"[{i}] 来源: {chunk.source_file} / {chunk.section}\n"
            f"标题: {chunk.title}\n"
            f"内容: {chunk.content}"
        )
    return "\n\n".join(parts)


def answer_question(
    user_input: str,
    retrieved_docs: List[RetrievedDocument],
    history: List[Message],
    client: LLMClient,
    builder: PromptBuilder,
) -> str:
    """Generate answer based on retrieved documents.

    Args:
        user_input: User question.
        retrieved_docs: RAG retrieval results.
        history: Conversation history.
        client: LLM client.
        builder: Prompt builder.

    Returns:
        Natural language answer.

    Design:
        F1, P4
    """
    rag_context = _format_retrieved_docs(retrieved_docs)
    system_prompt = builder.build_system_prompt(rag_context=rag_context)

    messages = list(history)
    messages.append(Message(role="user", content=user_input))

    response = client.chat(
        system_prompt=system_prompt,
        messages=messages,
        temperature=0.3,
    )

    return response
