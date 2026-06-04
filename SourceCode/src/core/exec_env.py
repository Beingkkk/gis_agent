"""Execution environment configuration and validation for GDAL scripts.

Provides shell detection, conda environment variable derivation,
environment building, and script execution with proper subprocess wiring.

Public API:
    ShellDetector      — detect available shells on the current platform
    CondaEnvDetector   — resolve conda env paths and build GDAL env vars
    EnvironmentBuilder — build a validated ExecEnvironment from user config
    ShellExecutor      — write and execute scripts with the configured env

Design: plan-exec-env v1.1.0 (DC-0101, DC-0102, DC-0103, DC-0104)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExecEnvType(Enum):
    """Execution environment type."""

    SYSTEM = "system"
    CONDA = "conda"


class ShellType(Enum):
    """Shell type for script execution."""

    BASH = "bash"
    CMD = "cmd"
    POWERSHELL = "powershell"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecEnvConfig:
    """User-configurable execution environment settings.

    Design:
        DC-0100
    """

    type: ExecEnvType = ExecEnvType.SYSTEM
    env_name: str = ""
    shell: str = "auto"
    shell_path: str = ""


@dataclass(frozen=True)
class ExecEnvironment:
    """Resolved execution environment ready for subprocess use.

    Design:
        DC-0102
    """

    env_vars: Dict[str, str]
    shell: ShellType
    shell_executable: Path
    gdal_available: bool
    gdal_version: str = ""
    env_name: str = ""  # 保留原始配置中的 conda 环境名（DC-0106）


# ---------------------------------------------------------------------------
# ExecEnvDefaultStore
# ---------------------------------------------------------------------------


class ExecEnvDefaultStore:
    """Persistent storage for default execution environment configuration.

    Saves validated environment settings to a local JSON file so that
    the next application startup can auto-apply them (DC-0106).

    Design:
        DC-0106
    """

    _DEFAULT_FILENAME = "exec_env_default.json"

    @classmethod
    def _get_default_path(cls) -> Path:
        """Return the path to the default config file.

        Located at {project_root}/SourceCode/data/exec_env_default.json.
        """
        # src/core/exec_env.py -> project root is 3 levels up
        project_root = Path(__file__).resolve().parents[2]
        data_dir = project_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / cls._DEFAULT_FILENAME

    @classmethod
    def load_default(cls) -> Optional[ExecEnvConfig]:
        """Load persisted default environment configuration.

        Returns:
            ExecEnvConfig if a saved config exists and is valid, else None.
        """
        path = cls._get_default_path()
        if not path.exists():
            return None

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load default exec env config: %s", exc)
            return None

        if not isinstance(raw, dict):
            logger.warning("Invalid default exec env config format")
            return None

        try:
            env_type = ExecEnvType(raw.get("type", "system"))
            # env_name only applies to conda; system always uses empty string
            env_name = (
                raw.get("env_name", "")
                if env_type == ExecEnvType.CONDA
                else ""
            )
            return ExecEnvConfig(
                type=env_type,
                env_name=env_name,
                shell=raw.get("shell", "auto"),
                shell_path=raw.get("shell_path", ""),
            )
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid default exec env config values: %s", exc)
            return None

    @classmethod
    def save_default(cls, config: ExecEnvConfig) -> None:
        """Persist environment configuration to local file.

        Only saves env_name for conda environments; system environments
        do not have a conda env_name.

        Args:
            config: Validated execution environment configuration.
        """
        path = cls._get_default_path()
        data: dict[str, str] = {
            "type": config.type.value,
            "shell": config.shell,
            "shell_path": config.shell_path,
        }
        # Only save env_name for conda environments (DC-0106)
        if config.type == ExecEnvType.CONDA:
            data["env_name"] = config.env_name
        try:
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Default exec env saved to %s", path)
        except OSError as exc:
            logger.error("Failed to save default exec env config: %s", exc)
            raise


# ---------------------------------------------------------------------------
# ShellDetector
# ---------------------------------------------------------------------------


class ShellDetector:
    """Detect available shells on the current platform.

    Design:
        DC-0101
    """

    # Known shell locations (Windows)
    _GIT_BASH_PATHS: tuple[str, ...] = (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    )
    _CONDA_BASH_REL = Path("Library") / "bin" / "bash.exe"

    # Known shell locations (Unix)
    _UNIX_BASH_PATHS: tuple[str, ...] = ("/bin/bash", "/usr/bin/bash")
    _UNIX_SH_PATHS: tuple[str, ...] = ("/bin/sh", "/usr/bin/sh")

    @classmethod
    def detect(cls) -> tuple[ShellType, Path]:
        """Auto-detect the best available shell for the current platform.

        Returns:
            Tuple of (shell_type, shell_executable_path).

        Raises:
            RuntimeError: If no usable shell is found.
        """
        system = platform.system()
        if system == "Windows":
            return cls._detect_windows()
        return cls._detect_unix()

    @classmethod
    def _detect_windows(cls) -> tuple[ShellType, Path]:
        """Windows shell detection priority:

        1. Git Bash
        2. Conda-embedded bash
        3. PowerShell (better Unicode support than cmd)
        4. cmd (always available)
        """
        # 1. Git Bash
        for path_str in cls._GIT_BASH_PATHS:
            path = Path(path_str)
            if path.exists():
                return (ShellType.BASH, path)

        # 2. Conda-embedded bash
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if conda_prefix:
            conda_bash = Path(conda_prefix) / cls._CONDA_BASH_REL
            if conda_bash.exists():
                return (ShellType.BASH, conda_bash)

        # 3. PowerShell (preferred over cmd for Unicode path support)
        ps_path = shutil.which("powershell") or shutil.which("pwsh")
        if ps_path:
            return (ShellType.POWERSHELL, Path(ps_path))

        # 4. cmd (builtin)
        cmd_path = shutil.which("cmd")
        if cmd_path:
            return (ShellType.CMD, Path(cmd_path))

        raise RuntimeError("No usable shell found on Windows")

    @classmethod
    def _detect_unix(cls) -> tuple[ShellType, Path]:
        """Unix shell detection priority:

        1. bash
        2. sh (fallback)
        """
        for path_str in cls._UNIX_BASH_PATHS:
            path = Path(path_str)
            if path.exists():
                return (ShellType.BASH, path)

        for path_str in cls._UNIX_SH_PATHS:
            path = Path(path_str)
            if path.exists():
                return (ShellType.BASH, path)

        raise RuntimeError("No usable shell found on Unix")

    @classmethod
    def verify(
        cls,
        shell: ShellType,
        custom_path: Optional[Path] = None,
    ) -> Path:
        """Verify a specific shell is executable.

        Args:
            shell: Target shell type.
            custom_path: Optional explicit path to the shell executable.

        Returns:
            Absolute path to the verified shell executable.

        Raises:
            FileNotFoundError: If the shell executable cannot be found.
        """
        if custom_path is not None:
            if custom_path.exists() and custom_path.is_file():
                return custom_path.resolve()
            raise FileNotFoundError(f"Custom shell path not found: {custom_path}")

        # Resolve via shutil.which for standard shells
        cmd_map = {
            ShellType.BASH: "bash",
            ShellType.CMD: "cmd",
            ShellType.POWERSHELL: "powershell",
        }
        cmd_name = cmd_map.get(shell)
        if cmd_name:
            found = shutil.which(cmd_name)
            if found:
                return Path(found).resolve()

        raise FileNotFoundError(f"Shell not found: {shell.value}")

    @classmethod
    def resolve_shell(
        cls,
        shell_str: str,
        custom_path: str = "",
    ) -> tuple[ShellType, Path]:
        """Resolve a shell string (possibly "auto") to a concrete shell.

        Args:
            shell_str: "auto", "bash", "cmd", or "powershell".
            custom_path: Optional explicit shell path.

        Returns:
            Tuple of (shell_type, shell_executable_path).
        """
        if shell_str == "auto":
            return cls.detect()

        shell_type = ShellType(shell_str)
        custom = Path(custom_path) if custom_path else None
        path = cls.verify(shell_type, custom)
        return (shell_type, path)


# ---------------------------------------------------------------------------
# CondaEnvDetector
# ---------------------------------------------------------------------------


class CondaEnvDetector:
    """Resolve conda environment paths without using conda CLI.

    Design:
        DC-0102
    """

    # Common conda installation paths (Windows)
    _WINDOWS_CONDA_PATHS: tuple[str, ...] = (
        r"C:\ProgramData\anaconda3",
        r"C:\ProgramData\miniconda3",
    )

    # Common conda installation paths (Unix)
    _UNIX_CONDA_PATHS: tuple[str, ...] = (
        "~/anaconda3",
        "~/miniconda3",
        "/opt/conda",
        "/usr/local/anaconda3",
    )

    @classmethod
    def find_conda_root(cls) -> Optional[Path]:
        """Detect conda installation root directory.

        Priority:
            1. CONDA_PREFIX environment variable
            2. CONDA_ROOT environment variable
            3. shutil.which("conda") → derive from executable location
            4. Common platform-specific paths

        Returns:
            Path to conda root if found, else None.
        """
        # 1. CONDA_PREFIX (current active conda env's parent)
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if conda_prefix:
            prefix_path = Path(conda_prefix)
            # If CONDA_PREFIX points to an env, go up to find base
            if (prefix_path.parent / "conda.exe").exists() or (
                prefix_path.parent / "conda"
            ).exists():
                return prefix_path.parent
            # Otherwise it may be the base itself
            if (prefix_path / "conda.exe").exists() or (prefix_path / "conda").exists():
                return prefix_path
            # Check for envs/ directory as indicator
            if (prefix_path.parent / "envs").is_dir():
                return prefix_path.parent

        # 2. CONDA_ROOT
        conda_root = os.environ.get("CONDA_ROOT")
        if conda_root:
            root_path = Path(conda_root)
            if root_path.exists():
                return root_path

        # 3. Derive from conda executable in PATH
        conda_exe = shutil.which("conda")
        if conda_exe:
            conda_path = Path(conda_exe).resolve()
            # conda.exe is typically at {root}/Scripts/conda.exe (Windows)
            # or {root}/bin/conda (Unix) or {root}/condabin/conda.bat
            for parent in conda_path.parents:
                if (parent / "conda.exe").exists() or (parent / "conda").exists():
                    return parent
                # Also check if this looks like a root (has envs/ or pkgs/)
                if (parent / "envs").is_dir() or (parent / "pkgs").is_dir():
                    return parent

        # 4. Common paths
        system = platform.system()
        if system == "Windows":
            for path_str in cls._WINDOWS_CONDA_PATHS:
                path = Path(path_str)
                if path.exists():
                    return path
            # User profile: check anaconda3 / miniconda3
            userprofile = os.environ.get("USERPROFILE")
            if userprofile:
                for candidate in ("anaconda3", "miniconda3"):
                    candidate_path = Path(userprofile) / candidate
                    if candidate_path.exists():
                        return candidate_path
        else:
            for path_str in cls._UNIX_CONDA_PATHS:
                path = Path(path_str).expanduser()
                if path.exists():
                    return path

        return None

    @classmethod
    def _find_user_conda_envs_dir(cls) -> Optional[Path]:
        """Find the user-level conda envs directory (~/.conda/envs).

        This is a fallback when the traditional conda root cannot be found.
        Some installations (especially user-level) store envs under ~/.conda.

        Returns:
            Path to ~/.conda/envs if it exists, else None.
        """
        system = platform.system()
        if system == "Windows":
            userprofile = os.environ.get("USERPROFILE")
            if userprofile:
                envs_dir = Path(userprofile) / ".conda" / "envs"
                if envs_dir.is_dir():
                    return envs_dir
        else:
            home = os.environ.get("HOME")
            if home:
                envs_dir = Path(home) / ".conda" / "envs"
                if envs_dir.is_dir():
                    return envs_dir
        return None

    @classmethod
    def resolve_env_path(cls, env_name: str) -> Optional[Path]:
        """Resolve conda environment absolute path from env name.

        Checks both the traditional {conda_root}/envs/ layout and the
        user-level ~/.conda/envs/ fallback.

        Args:
            env_name: Conda environment name (e.g. "gis-agent").

        Returns:
            Absolute path to the environment directory, or None if not found.
        """
        if not env_name:
            return None

        # 1. Traditional layout: {conda_root}/envs/{env_name}
        conda_root = cls.find_conda_root()
        if conda_root is not None:
            env_path = conda_root / "envs" / env_name
            if env_path.exists() and env_path.is_dir():
                return env_path.resolve()

        # 2. User-level fallback: ~/.conda/envs/{env_name}
        user_envs_dir = cls._find_user_conda_envs_dir()
        if user_envs_dir is not None:
            env_path = user_envs_dir / env_name
            if env_path.exists() and env_path.is_dir():
                return env_path.resolve()

        return None

    @classmethod
    def build_env_vars(cls, env_path: Path) -> Dict[str, str]:
        """Build GDAL-related environment variables from a conda env path.

        Derivation rules (DC-0102):
            PATH      ← prepend {env_path}/Library/bin
            GDAL_DATA ← {env_path}/Library/share/gdal
            PROJ_DATA ← {env_path}/Library/share/proj
            PROJ_LIB  ← {env_path}/Library/share/proj

        Args:
            env_path: Absolute path to a conda environment.

        Returns:
            Dictionary of environment variable overrides.
        """
        env_vars: Dict[str, str] = {}

        # PATH prepend
        bin_dir = env_path / "Library" / "bin"
        if bin_dir.exists():
            current_path = os.environ.get("PATH", "")
            env_vars["PATH"] = f"{bin_dir}{os.pathsep}{current_path}"

        # GDAL data
        gdal_data = env_path / "Library" / "share" / "gdal"
        if gdal_data.exists():
            env_vars["GDAL_DATA"] = str(gdal_data)

        # PROJ data (both PROJ_DATA and PROJ_LIB for compatibility)
        proj_data = env_path / "Library" / "share" / "proj"
        if proj_data.exists():
            env_vars["PROJ_DATA"] = str(proj_data)
            env_vars["PROJ_LIB"] = str(proj_data)

        return env_vars

    @classmethod
    def list_envs(cls) -> List[str]:
        """List all installed conda environment names.

        Reads subdirectory names from {conda_root}/envs/ and
        ~/.conda/envs/ as fallback.

        Returns:
            List of environment names (sorted, deduplicated).
        """
        envs: set[str] = set()

        # 1. Traditional layout: {conda_root}/envs/
        conda_root = cls.find_conda_root()
        if conda_root is not None:
            envs_dir = conda_root / "envs"
            if envs_dir.exists():
                envs.update(
                    p.name
                    for p in envs_dir.iterdir()
                    if p.is_dir() and not p.name.startswith(".")
                )

        # 2. User-level fallback: ~/.conda/envs/
        user_envs_dir = cls._find_user_conda_envs_dir()
        if user_envs_dir is not None:
            envs.update(
                p.name
                for p in user_envs_dir.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            )

        return sorted(envs)


# ---------------------------------------------------------------------------
# EnvironmentBuilder
# ---------------------------------------------------------------------------


class EnvironmentBuilder:
    """Build a validated ExecEnvironment from user configuration.

    Design:
        DC-0100, DC-0102
    """

    _VERIFY_TIMEOUT = 5

    def __init__(self, config: ExecEnvConfig) -> None:
        """Args:
        config: User-provided execution environment configuration.
        """
        self.config = config

    def build(self) -> ExecEnvironment:
        """Build and validate a complete execution environment.

        Steps:
            1. Resolve shell type (auto → detect)
            2. Verify shell executable
            3. Assemble environment variables (system / conda)
            4. Verify GDAL availability (ogr2ogr --version, 5s timeout)

        Returns:
            Complete execution environment object.

        Raises:
            RuntimeError: If shell is not available.
            FileNotFoundError: If conda environment does not exist.
        """
        # 1. Resolve shell
        shell_type, shell_path = ShellDetector.resolve_shell(
            self.config.shell,
            self.config.shell_path,
        )

        # 2. Build environment variables
        env_vars = dict(os.environ)

        if self.config.type == ExecEnvType.CONDA:
            if not self.config.env_name:
                raise FileNotFoundError(
                    "Conda environment name is required for type=conda"
                )
            env_path = CondaEnvDetector.resolve_env_path(self.config.env_name)
            if env_path is None:
                # Build a helpful error message showing what was searched
                searched: list[str] = []
                root = CondaEnvDetector.find_conda_root()
                if root is not None:
                    searched.append(str(root / "envs" / self.config.env_name))
                user_envs = CondaEnvDetector._find_user_conda_envs_dir()
                if user_envs is not None:
                    searched.append(str(user_envs / self.config.env_name))
                if not searched:
                    searched.append("(conda installation not detected)")
                raise FileNotFoundError(
                    f"Conda environment not found: {self.config.env_name}. "
                    f"Searched: {', '.join(searched)}"
                )
            conda_vars = CondaEnvDetector.build_env_vars(env_path)
            env_vars.update(conda_vars)

        # 3. Verify GDAL availability
        gdal_available, gdal_version = self._verify_gdal(env_vars)

        return ExecEnvironment(
            env_vars=env_vars,
            shell=shell_type,
            shell_executable=shell_path,
            gdal_available=gdal_available,
            gdal_version=gdal_version,
            env_name=self.config.env_name,
        )

    def _verify_gdal(self, env_vars: Dict[str, str]) -> tuple[bool, str]:
        """Verify GDAL is available by running ogr2ogr --version.

        Args:
            env_vars: Environment variables to use during verification.

        Returns:
            Tuple of (available, version_string).
        """
        try:
            result = subprocess.run(
                ["ogr2ogr", "--version"],
                capture_output=True,
                text=True,
                timeout=self._VERIFY_TIMEOUT,
                env=env_vars,
            )
            if result.returncode == 0:
                version_line = result.stdout.strip().split("\n")[0]
                return (True, version_line)
            return (False, result.stderr.strip()[:200])
        except subprocess.TimeoutExpired:
            logger.warning(
                "GDAL verification timed out after %ds", self._VERIFY_TIMEOUT
            )
            return (False, "验证超时")
        except FileNotFoundError:
            logger.warning("ogr2ogr not found in PATH")
            return (False, "未找到 ogr2ogr，请检查 GDAL 安装")
        except Exception as exc:
            logger.warning("GDAL verification failed: %s", exc)
            return (False, str(exc)[:200])


# ---------------------------------------------------------------------------
# ShellExecutor
# ---------------------------------------------------------------------------


class ShellExecutor:
    """Write and execute scripts with a configured environment.

    Design:
        DC-0101, DC-0103
    """

    def __init__(self, env: ExecEnvironment) -> None:
        """Args:
        env: Resolved execution environment.
        """
        self.env = env

    def _build_script_content(self, commands: List[str]) -> tuple[str, str]:
        """Build script header and body for the current shell type.

        Returns:
            (header, body) tuple.

        Design:
            DC-0103, DC-0105
        """
        shell = self.env.shell

        if shell == ShellType.BASH:
            header = "#!/bin/bash\nset -euo pipefail\n"
            body = "\n".join(commands) + "\n"
        elif shell == ShellType.CMD:
            header = "@echo off\nchcp 65001 >nul\n"
            body_parts = []
            for cmd in commands:
                body_parts.append(cmd)
                body_parts.append("if errorlevel 1 exit /b 1")
            body = "\n".join(body_parts) + "\n"
        elif shell == ShellType.POWERSHELL:
            header = "#Requires -Version 5.1\n$ErrorActionPreference = 'Stop'\n"
            body = "\n".join(commands) + "\n"
        else:
            raise ValueError(f"Unsupported shell: {shell}")

        return header, body

    def write_script(self, commands: List[str], output_path: Path) -> Path:
        """Write commands to a script file at the specified path.

        Args:
            commands: List of command lines to include in the script.
            output_path: Full path to the target script file
                (including filename and extension).

        Returns:
            Path to the written script file.

        Design:
            DC-0103, DC-0105
        """
        header, body = self._build_script_content(commands)
        output_path.write_text(header + body, encoding="utf-8")
        logger.debug("Script written to %s (%s)", output_path, self.env.shell.value)
        return output_path

    def write_script_to_temp(self, commands: List[str]) -> Path:
        """Write commands to a temporary script file for execution.

        Uses ./cache relative to the project root (created if missing).
        The caller is responsible for cleanup.

        Returns:
            Path to the temporary script file.

        Design:
            DC-0105
        """
        shell = self.env.shell
        timestamp = str(int(time.time()))
        uid = str(uuid.uuid4())[:8]

        if shell == ShellType.BASH:
            ext = ".sh"
        elif shell == ShellType.CMD:
            ext = ".bat"
        elif shell == ShellType.POWERSHELL:
            ext = ".ps1"
        else:
            raise ValueError(f"Unsupported shell: {shell}")

        filename = f"gis_script_{timestamp}_{uid}{ext}"
        # Resolve cache dir relative to project root (where this file lives:
        # src/core/exec_env.py → project root is 3 levels up)
        cache_dir = Path(__file__).resolve().parents[3] / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        script_path = cache_dir / filename

        header, body = self._build_script_content(commands)
        script_path.write_text(header + body, encoding="utf-8")
        logger.debug("Temp script written to %s (%s)", script_path, shell.value)
        return script_path

    async def execute(
        self,
        script_path: Path,
        cwd: Path,
    ) -> asyncio.subprocess.Process:
        """Start a subprocess to execute the script.

        Args:
            script_path: Path to the script file.
            cwd: Working directory for the subprocess.

        Returns:
            The asyncio subprocess process object.

        Raises:
            RuntimeError: If the subprocess cannot be started.
        """
        shell = self.env.shell
        executable = str(self.env.shell_executable)

        if shell == ShellType.BASH:
            # On Windows, MSYS/Git Bash interprets backslashes as escape
            # sequences. Convert to forward slashes so the path survives.
            script_arg = (
                script_path.as_posix()
                if sys.platform == "win32"
                else str(script_path)
            )
            cmd = [executable, script_arg]
        elif shell == ShellType.CMD:
            cmd = [executable, "/c", str(script_path)]
        elif shell == ShellType.POWERSHELL:
            cmd = [executable, "-File", str(script_path)]
        else:
            raise ValueError(f"Unsupported shell: {shell}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env.env_vars,
            )
            return process
        except Exception as exc:
            raise RuntimeError(
                f"Failed to start subprocess with {shell.value}: {exc}"
            ) from exc
