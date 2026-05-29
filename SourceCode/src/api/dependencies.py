"""FastAPI dependency injection functions.

Provides singleton access to core business logic components
via FastAPI's Depends mechanism.

Public API:
    SessionManager — in-memory session lifecycle manager
    get_session_manager() -> SessionManager
    set_registry(), get_registry()
    set_validator(), get_validator()
    set_template_engine(), get_template_engine()

Design:
    T-UX-01, T-UX-02 (DC-UX-03)
"""

import uuid
from typing import Optional

from core.models import Session
from core.registry import TemplateRegistry
from core.validator import ParamValidator
from core.workspace import Workspace
from llm.client import LLMClient
from llm.prompts import PromptBuilder
from templates.engine import TemplateEngine


class SessionManager:
    """In-memory session lifecycle manager.

    Maps session_id to Session instances. Thread-safe via GIL
    (Python dict operations are atomic). For true concurrency
    safety under async load, add asyncio.Lock.

    Design:
        DC-UX-03
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(self) -> tuple[str, Session]:
        """Create a new session and store it.

        Returns:
            (session_id, session) tuple.
        """
        session_id = str(uuid.uuid4())
        session = Session()
        self._sessions[session_id] = session
        return session_id, session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve session by ID.

        Args:
            session_id: UUID string.

        Returns:
            Session if found, None otherwise.
        """
        return self._sessions.get(session_id)

    def update_session(self, session_id: str, session: Session) -> None:
        """Replace session for the given ID.

        Args:
            session_id: UUID string.
            session: New Session instance (immutable replacement).
        """
        self._sessions[session_id] = session

    def clear_session(self, session_id: str) -> None:
        """Reset session to IDLE state.

        Creates a fresh Session and stores it. If session_id
        does not exist, creates it with a fresh Session.

        Args:
            session_id: UUID string.
        """
        self._sessions[session_id] = Session()


# Module-level singleton instance
_session_manager_instance: Optional[SessionManager] = None

# Optional injected dependencies (for testing)
_registry_instance: Optional[TemplateRegistry] = None
_validator_instance: Optional[ParamValidator] = None
_template_engine_instance: Optional[TemplateEngine] = None
_llm_client_instance: Optional[LLMClient] = None
_prompt_builder_instance: Optional[PromptBuilder] = None
_workspace_instance: Optional[Workspace] = None


def get_session_manager() -> SessionManager:
    """Get or create the global SessionManager singleton.

    Returns:
        SessionManager instance.
    """
    global _session_manager_instance
    if _session_manager_instance is None:
        _session_manager_instance = SessionManager()
    return _session_manager_instance


def set_registry(registry: TemplateRegistry) -> None:
    """Inject a TemplateRegistry instance (for testing)."""
    global _registry_instance
    _registry_instance = registry


def get_registry() -> TemplateRegistry:
    """Get the global TemplateRegistry.

    Returns:
        TemplateRegistry instance.

    Raises:
        RuntimeError: If registry has not been set.
    """
    if _registry_instance is None:
        raise RuntimeError("Registry not initialized. Call set_registry() first.")
    return _registry_instance


def set_validator(validator: ParamValidator) -> None:
    """Inject a ParamValidator instance (for testing)."""
    global _validator_instance
    _validator_instance = validator


def get_validator() -> ParamValidator:
    """Get the global ParamValidator.

    Returns:
        ParamValidator instance.

    Raises:
        RuntimeError: If validator has not been set.
    """
    if _validator_instance is None:
        raise RuntimeError("Validator not initialized. Call set_validator() first.")
    return _validator_instance


def set_template_engine(engine: TemplateEngine) -> None:
    """Inject a TemplateEngine instance (for testing)."""
    global _template_engine_instance
    _template_engine_instance = engine


def get_template_engine() -> TemplateEngine:
    """Get the global TemplateEngine.

    Returns:
        TemplateEngine instance.

    Raises:
        RuntimeError: If engine has not been set.
    """
    if _template_engine_instance is None:
        raise RuntimeError("Engine not initialized. Call set_template_engine() first.")
    return _template_engine_instance


def set_llm_client(client: LLMClient) -> None:
    """Inject an LLMClient instance (for testing)."""
    global _llm_client_instance
    _llm_client_instance = client


def get_llm_client() -> LLMClient:
    """Get the global LLMClient.

    Returns:
        LLMClient instance.

    Raises:
        RuntimeError: If client has not been set.
    """
    if _llm_client_instance is None:
        raise RuntimeError("LLM client not initialized. Call set_llm_client() first.")
    return _llm_client_instance


def set_prompt_builder(builder: PromptBuilder) -> None:
    """Inject a PromptBuilder instance (for testing)."""
    global _prompt_builder_instance
    _prompt_builder_instance = builder


def get_prompt_builder() -> PromptBuilder:
    """Get the global PromptBuilder.

    Returns:
        PromptBuilder instance.

    Raises:
        RuntimeError: If builder has not been set.
    """
    if _prompt_builder_instance is None:
        raise RuntimeError(
            "Prompt builder not initialized. Call set_prompt_builder() first."
        )
    return _prompt_builder_instance


def set_workspace(workspace: Workspace) -> None:
    """Inject a Workspace instance (for testing)."""
    global _workspace_instance
    _workspace_instance = workspace


def get_workspace() -> Workspace:
    """Get the global Workspace.

    Returns:
        Workspace instance.

    Raises:
        RuntimeError: If workspace has not been set.
    """
    if _workspace_instance is not None:
        return _workspace_instance
    # Fallback to core workspace singleton
    from core import workspace as core_workspace

    return core_workspace.get_workspace()


def _reset_dependencies() -> None:
    """Reset all global singleton instances. For testing only."""
    global _session_manager_instance, _registry_instance
    global _validator_instance, _template_engine_instance
    global _llm_client_instance, _prompt_builder_instance
    global _workspace_instance
    _session_manager_instance = None
    _registry_instance = None
    _validator_instance = None
    _template_engine_instance = None
    _llm_client_instance = None
    _prompt_builder_instance = None
    _workspace_instance = None
