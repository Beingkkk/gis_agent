"""Execution environment REST API routes.

Provides endpoints for environment verification and session-level binding.

Design: plan-exec-env v1.1.0 (DC-0101 ~ DC-0104)
"""

import logging
from typing import Any, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.dependencies import get_session_manager
from api.routes.session import (
    SessionResponse,
    _build_session_response,
    _get_session_or_404,
)
from core.exec_env import (
    CondaEnvDetector,
    EnvironmentBuilder,
    ExecEnvConfig,
    ExecEnvDefaultStore,
    ExecEnvType,
    ShellDetector,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["exec-env"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ExecEnvVerifyRequest(BaseModel):
    """Request to verify an execution environment configuration."""

    type: str = "system"
    env_name: str = ""
    shell: str = "auto"
    shell_path: str = ""


class ShellInfo(BaseModel):
    """Shell information in verify response."""

    type: str
    path: str


class GDALInfo(BaseModel):
    """GDAL availability information."""

    available: bool
    version: str = ""


class ExecEnvVerifyResponse(BaseModel):
    """Response from environment verification."""

    valid: bool
    shell: ShellInfo
    gdal: GDALInfo
    env_vars: dict[str, str]
    error: Optional[str] = None


class ExecEnvSetRequest(BaseModel):
    """Request to save execution environment to session."""

    type: str = "system"
    env_name: str = ""
    shell: str = "auto"
    shell_path: str = ""


class CondaEnvsResponse(BaseModel):
    """Response listing available conda environments."""

    envs: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/exec-env/verify", response_model=ExecEnvVerifyResponse)
async def verify_exec_env(
    request: ExecEnvVerifyRequest,
) -> ExecEnvVerifyResponse:
    """Verify an execution environment configuration.

    Pure validation endpoint — does not modify any session state.
    Builds the environment and verifies shell + GDAL availability.

    Args:
        request: Environment configuration to verify.

    Returns:
        Verification result with shell info, GDAL status, and env vars.
    """
    try:
        env_type = ExecEnvType(request.type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid env type: {request.type}"
        ) from exc

    config = ExecEnvConfig(
        type=env_type,
        env_name=request.env_name,
        shell=request.shell,
        shell_path=request.shell_path,
    )

    builder = EnvironmentBuilder(config)
    try:
        env = builder.build()
    except FileNotFoundError as exc:
        return ExecEnvVerifyResponse(
            valid=False,
            shell=ShellInfo(type=config.shell, path=""),
            gdal=GDALInfo(available=False),
            env_vars={},
            error=str(exc),
        )
    except RuntimeError as exc:
        return ExecEnvVerifyResponse(
            valid=False,
            shell=ShellInfo(type=config.shell, path=""),
            gdal=GDALInfo(available=False),
            env_vars={},
            error=str(exc),
        )
    except Exception as exc:
        logger.exception("Environment verification failed: %s", exc)
        return ExecEnvVerifyResponse(
            valid=False,
            shell=ShellInfo(type=config.shell, path=""),
            gdal=GDALInfo(available=False),
            env_vars={},
            error=f"Verification failed: {exc}",
        )

    return ExecEnvVerifyResponse(
        valid=env.gdal_available,
        shell=ShellInfo(
            type=env.shell.value,
            path=str(env.shell_executable),
        ),
        gdal=GDALInfo(
            available=env.gdal_available,
            version=env.gdal_version,
        ),
        env_vars=env.env_vars,
        error=None if env.gdal_available else "GDAL not available",
    )


@router.post("/session/{session_id}/exec-env", response_model=SessionResponse)
async def set_session_exec_env(
    session_id: str,
    request: ExecEnvSetRequest,
    session_manager: Any = Depends(get_session_manager),
) -> SessionResponse:
    """Save execution environment configuration to a session.

    Validates the environment first, then binds it to the session.

    Args:
        session_id: Session UUID.
        request: Environment configuration to save.
        session_manager: SessionManager dependency.

    Returns:
        Updated SessionResponse with exec_env bound.

    Raises:
        HTTPException: 400 if environment validation fails.
    """
    session = _get_session_or_404(session_id, session_manager)

    try:
        env_type = ExecEnvType(request.type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid env type: {request.type}"
        ) from exc

    config = ExecEnvConfig(
        type=env_type,
        env_name=request.env_name,
        shell=request.shell,
        shell_path=request.shell_path,
    )

    builder = EnvironmentBuilder(config)
    try:
        env = builder.build()
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400, detail=f"Environment validation failed: {exc}"
        ) from exc
    except Exception as exc:
        logger.exception("Environment build failed: %s", exc)
        raise HTTPException(
            status_code=400, detail=f"Environment validation failed: {exc}"
        ) from exc

    new_session = session.with_exec_env(env)
    session_manager.update_session(session_id, new_session)
    logger.info(
        "Exec env saved to session=%s (type=%s, shell=%s, gdal=%s)",
        session_id,
        config.type.value,
        env.shell.value,
        env.gdal_available,
    )
    return _build_session_response(session_id, new_session)


@router.get("/exec-env/conda-envs", response_model=CondaEnvsResponse)
async def list_conda_envs() -> CondaEnvsResponse:
    """List available conda environments for dropdown population.

    Returns:
        List of conda environment names.
    """
    envs = CondaEnvDetector.list_envs()
    return CondaEnvsResponse(envs=envs)


@router.get("/exec-env/default", response_model=ExecEnvVerifyRequest)
async def get_default_exec_env() -> Union[ExecEnvVerifyRequest, JSONResponse]:
    """Read the persisted default execution environment configuration.

    Returns:
        Default environment config if exists.
        204 No Content if no default config has been saved.

    Design:
        DC-0106
    """
    config = ExecEnvDefaultStore.load_default()
    if config is None:
        return JSONResponse(status_code=204, content=None)

    return ExecEnvVerifyRequest(
        type=config.type.value,
        env_name=config.env_name,
        shell=config.shell,
        shell_path=config.shell_path,
    )


@router.post("/exec-env/default")
async def save_default_exec_env(
    request: ExecEnvVerifyRequest,
) -> dict[str, str]:
    """Persist the execution environment configuration to local file.

    Light validation only (shell + conda env existence).
    GDAL verification is skipped — user already verified via /exec-env/verify.

    Args:
        request: Environment configuration to persist.

    Returns:
        {"status": "saved"} on success.

    Raises:
        HTTPException: 400 if configuration is invalid.

    Design:
        DC-0106
    """
    try:
        env_type = ExecEnvType(request.type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid env type: {request.type}"
        ) from exc

    config = ExecEnvConfig(
        type=env_type,
        env_name=request.env_name,
        shell=request.shell,
        shell_path=request.shell_path,
    )

    # Light validation: shell existence + conda env existence (DC-0106)
    try:
        ShellDetector.resolve_shell(config.shell, config.shell_path)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=f"Shell validation failed: {exc}"
        ) from exc

    if config.type == ExecEnvType.CONDA:
        if not config.env_name:
            raise HTTPException(
                status_code=400, detail="Conda environment name is required"
            )
        env_path = CondaEnvDetector.resolve_env_path(config.env_name)
        if env_path is None:
            raise HTTPException(
                status_code=400,
                detail=f"Conda environment not found: {config.env_name}",
            )

    ExecEnvDefaultStore.save_default(config)
    logger.info(
        "Default exec env saved (type=%s, shell=%s, env_name=%s)",
        config.type.value,
        config.shell,
        config.env_name,
    )
    return {"status": "saved"}
