"""LLM module data models.

Design: DC-0031, DC-0032
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class IntentResult:
    """Intent classification result.

    Design: F2, P1
    """

    template_id: str
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class ParamResult:
    """Parameter extraction result.

    Design: F3
    """

    params: Dict[str, str]
    missing: List[str]
    questions: List[str]


@dataclass(frozen=True)
class Message:
    """Conversation message.

    Design: F8
    """

    role: str
    content: str
