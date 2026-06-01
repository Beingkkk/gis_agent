"""Tests for core.exec_env module.

Design: plan-exec-env v1.1.0 (DC-0101 ~ DC-0104)
"""

import platform
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.exec_env import (
    CondaEnvDetector,
    EnvironmentBuilder,
    ExecEnvConfig,
    ExecEnvType,
    ExecEnvironment,
    ShellDetector,
    ShellExecutor,
    ShellType,
)


# ---------------------------------------------------------------------------
# ShellDetector
# ---------------------------------------------------------------------------


class TestShellDetectorDetect:
    """ShellDetector.detect() platform-specific detection."""

    def test_windows_detect_git_bash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """On Windows, Git Bash is preferred over cmd."""
        monkeypatch.setattr(platform, "system", lambda: "Windows")

        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        with patch.object(Path, "exists", return_value=True):
            with patch.object(git_bash.__class__, "exists", return_value=True):
                shell_type, path = ShellDetector.detect()
                assert shell_type == ShellType.BASH
                assert "bash" in str(path).lower()

    def test_windows_fallback_cmd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """On Windows, fall back to cmd when no bash is found."""
        monkeypatch.setattr(platform, "system", lambda: "Windows")

        with patch.object(Path, "exists", return_value=False):
            with patch("core.exec_env.shutil.which", return_value=r"C:\Windows\System32\cmd.exe"):
                shell_type, path = ShellDetector.detect()
                assert shell_type == ShellType.CMD

    def test_linux_detect_bash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """On Linux, /bin/bash is detected."""
        monkeypatch.setattr(platform, "system", lambda: "Linux")

        with patch.object(
            ShellDetector, "_detect_unix", return_value=(ShellType.BASH, Path("/bin/bash"))
        ):
            shell_type, path = ShellDetector.detect()
            assert shell_type == ShellType.BASH
            assert "bash" in str(path).lower()

    def test_no_shell_raises_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When no shell is available, raise RuntimeError."""
        monkeypatch.setattr(platform, "system", lambda: "Windows")

        with patch.object(Path, "exists", return_value=False):
            with patch("core.exec_env.shutil.which", return_value=None):
                with pytest.raises(RuntimeError, match="No usable shell"):
                    ShellDetector.detect()


class TestShellDetectorVerify:
    """ShellDetector.verify() explicit path validation."""

    def test_verify_custom_path(self, tmp_path: Path) -> None:
        """Custom shell path is returned if it exists."""
        fake_shell = tmp_path / "fake_bash.exe"
        fake_shell.write_text("")
        result = ShellDetector.verify(ShellType.BASH, fake_shell)
        assert result == fake_shell.resolve()

    def test_verify_custom_path_not_found(self, tmp_path: Path) -> None:
        """Custom shell path raises FileNotFoundError if missing."""
        fake_shell = tmp_path / "nonexistent.exe"
        with pytest.raises(FileNotFoundError):
            ShellDetector.verify(ShellType.BASH, fake_shell)

    def test_verify_via_which(self) -> None:
        """Standard shells are resolved via shutil.which."""
        with patch("core.exec_env.shutil.which", return_value="/bin/bash"):
            result = ShellDetector.verify(ShellType.BASH)
            assert "bash" in str(result)


class TestShellDetectorResolve:
    """ShellDetector.resolve_shell() combines detection and verification."""

    def test_auto_resolves_to_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """"auto" triggers detect()."""
        monkeypatch.setattr(platform, "system", lambda: "Windows")

        with patch.object(Path, "exists", return_value=False):
            with patch("core.exec_env.shutil.which", return_value=r"C:\Windows\System32\cmd.exe"):
                shell_type, path = ShellDetector.resolve_shell("auto")
                assert shell_type == ShellType.CMD

    def test_explicit_bash(self) -> None:
        """Explicit "bash" resolves to bash."""
        with patch("core.exec_env.shutil.which", return_value="/bin/bash"):
            shell_type, path = ShellDetector.resolve_shell("bash")
            assert shell_type == ShellType.BASH


# ---------------------------------------------------------------------------
# CondaEnvDetector
# ---------------------------------------------------------------------------


class TestCondaEnvDetectorFindRoot:
    """CondaEnvDetector.find_conda_root() path discovery."""

    def test_from_conda_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CONDA_PREFIX environment variable is used to find root."""
        monkeypatch.setenv("CONDA_PREFIX", r"C:\Users\PC\.conda\envs\gis-agent")
        root = CondaEnvDetector.find_conda_root()
        # Should resolve to parent of envs/ directory
        assert root is not None
        assert "conda" in str(root).lower()

    def test_no_env_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When no conda is found, return None."""
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_ROOT", raising=False)

        with patch.object(Path, "exists", return_value=False):
            root = CondaEnvDetector.find_conda_root()
            assert root is None


class TestCondaEnvDetectorBuildEnvVars:
    """CondaEnvDetector.build_env_vars() variable derivation."""

    def test_build_env_vars(self, tmp_path: Path) -> None:
        """Build PATH, GDAL_DATA, PROJ_DATA, PROJ_LIB from env path."""
        env_path = tmp_path / "gis-agent"
        (env_path / "Library" / "bin").mkdir(parents=True)
        (env_path / "Library" / "share" / "gdal").mkdir(parents=True)
        (env_path / "Library" / "share" / "proj").mkdir(parents=True)

        vars_dict = CondaEnvDetector.build_env_vars(env_path)

        assert "PATH" in vars_dict
        assert str(env_path / "Library" / "bin") in vars_dict["PATH"]
        assert vars_dict.get("GDAL_DATA") == str(env_path / "Library" / "share" / "gdal")
        assert vars_dict.get("PROJ_DATA") == str(env_path / "Library" / "share" / "proj")
        assert vars_dict.get("PROJ_LIB") == str(env_path / "Library" / "share" / "proj")

    def test_build_env_vars_missing_dirs(self, tmp_path: Path) -> None:
        """Missing directories are silently skipped."""
        env_path = tmp_path / "empty-env"
        env_path.mkdir()

        vars_dict = CondaEnvDetector.build_env_vars(env_path)

        assert vars_dict == {}


class TestCondaEnvDetectorListEnvs:
    """CondaEnvDetector.list_envs() environment enumeration."""

    def test_list_envs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """List subdirectories under envs/ as environment names."""
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        monkeypatch.delenv("CONDA_ROOT", raising=False)

        fake_conda = tmp_path / "anaconda3"
        (fake_conda / "envs" / "gis-agent").mkdir(parents=True)
        (fake_conda / "envs" / "base").mkdir(parents=True)
        (fake_conda / "envs" / ".trash").mkdir(parents=True)

        with patch.object(
            CondaEnvDetector, "find_conda_root", return_value=fake_conda
        ):
            with patch.object(
                CondaEnvDetector, "_find_user_conda_envs_dir", return_value=None
            ):
                envs = CondaEnvDetector.list_envs()
                assert envs == ["base", "gis-agent"]  # sorted, hidden excluded

    def test_list_envs_no_conda(self) -> None:
        """Return empty list when conda is not found."""
        with patch.object(CondaEnvDetector, "find_conda_root", return_value=None):
            with patch.object(
                CondaEnvDetector, "_find_user_conda_envs_dir", return_value=None
            ):
                envs = CondaEnvDetector.list_envs()
                assert envs == []


# ---------------------------------------------------------------------------
# EnvironmentBuilder
# ---------------------------------------------------------------------------


class TestEnvironmentBuilderSystem:
    """EnvironmentBuilder with SYSTEM type."""

    def test_system_type_uses_os_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SYSTEM type inherits os.environ and verifies GDAL."""
        config = ExecEnvConfig(type=ExecEnvType.SYSTEM, shell="cmd")
        builder = EnvironmentBuilder(config)

        with patch("core.exec_env.ShellDetector.resolve_shell") as mock_resolve:
            mock_resolve.return_value = (ShellType.CMD, Path("cmd"))
            with patch.object(
                builder, "_verify_gdal", return_value=(True, "GDAL 3.9.0")
            ):
                env = builder.build()

        assert env.shell == ShellType.CMD
        assert env.gdal_available is True
        assert env.gdal_version == "GDAL 3.9.0"

    def test_system_type_gdal_not_found(self) -> None:
        """SYSTEM type handles GDAL not being available gracefully."""
        config = ExecEnvConfig(type=ExecEnvType.SYSTEM, shell="cmd")
        builder = EnvironmentBuilder(config)

        with patch("core.exec_env.ShellDetector.resolve_shell") as mock_resolve:
            mock_resolve.return_value = (ShellType.CMD, Path("cmd"))
            with patch.object(
                builder, "_verify_gdal", return_value=(False, "not found")
            ):
                env = builder.build()

        assert env.gdal_available is False
        assert env.gdal_version == "not found"


class TestEnvironmentBuilderConda:
    """EnvironmentBuilder with CONDA type."""

    def test_conda_type_builds_env_vars(self) -> None:
        """CONDA type derives env vars and verifies GDAL."""
        config = ExecEnvConfig(
            type=ExecEnvType.CONDA, env_name="gis-agent", shell="bash"
        )
        builder = EnvironmentBuilder(config)

        fake_env_path = Path("/fake/conda/envs/gis-agent")
        with patch(
            "core.exec_env.CondaEnvDetector.resolve_env_path",
            return_value=fake_env_path,
        ):
            with patch(
                "core.exec_env.CondaEnvDetector.build_env_vars",
                return_value={"PATH": "/fake/bin", "GDAL_DATA": "/fake/gdal"},
            ):
                with patch(
                    "core.exec_env.ShellDetector.resolve_shell"
                ) as mock_resolve:
                    mock_resolve.return_value = (
                        ShellType.BASH,
                        Path("/bin/bash"),
                    )
                    with patch.object(
                        builder,
                        "_verify_gdal",
                        return_value=(True, "GDAL 3.9.0"),
                    ):
                        env = builder.build()

        assert env.shell == ShellType.BASH
        assert env.env_vars.get("PATH") == "/fake/bin"
        assert env.env_vars.get("GDAL_DATA") == "/fake/gdal"
        assert env.gdal_available is True

    def test_conda_type_missing_env_raises(self) -> None:
        """CONDA type raises FileNotFoundError when env does not exist."""
        config = ExecEnvConfig(
            type=ExecEnvType.CONDA, env_name="nonexistent", shell="bash"
        )
        builder = EnvironmentBuilder(config)

        with patch(
            "core.exec_env.CondaEnvDetector.resolve_env_path", return_value=None
        ):
            with patch(
                "core.exec_env.CondaEnvDetector.find_conda_root", return_value=None
            ):
                with patch(
                    "core.exec_env.CondaEnvDetector._find_user_conda_envs_dir",
                    return_value=None,
                ):
                    with pytest.raises(FileNotFoundError, match="not found"):
                        builder.build()

    def test_conda_type_missing_env_name_raises(self) -> None:
        """CONDA type raises FileNotFoundError when env_name is empty."""
        config = ExecEnvConfig(type=ExecEnvType.CONDA, env_name="", shell="bash")
        builder = EnvironmentBuilder(config)

        with pytest.raises(FileNotFoundError, match="required"):
            builder.build()


class TestEnvironmentBuilderAutoShell:
    """EnvironmentBuilder with auto shell detection."""

    def test_auto_shell_resolved(self) -> None:
        """"auto" shell is resolved to a concrete shell during build."""
        config = ExecEnvConfig(type=ExecEnvType.SYSTEM, shell="auto")
        builder = EnvironmentBuilder(config)

        with patch("core.exec_env.ShellDetector.resolve_shell") as mock_resolve:
            mock_resolve.return_value = (ShellType.BASH, Path("/bin/bash"))
            with patch.object(
                builder, "_verify_gdal", return_value=(True, "GDAL 3.9.0")
            ):
                env = builder.build()

        assert env.shell == ShellType.BASH
        mock_resolve.assert_called_once_with("auto", "")


# ---------------------------------------------------------------------------
# ShellExecutor
# ---------------------------------------------------------------------------


class TestShellExecutorWriteScript:
    """ShellExecutor.write_script() format generation."""

    def test_write_bash_script(self, tmp_path: Path) -> None:
        """Bash script contains shebang and set -euo pipefail."""
        env = ExecEnvironment(
            env_vars={},
            shell=ShellType.BASH,
            shell_executable=Path("/bin/bash"),
            gdal_available=True,
        )
        executor = ShellExecutor(env)

        script_path = executor.write_script(
            ["ogr2ogr --version", "echo done"], tmp_path
        )

        content = script_path.read_text()
        assert script_path.suffix == ".sh"
        assert "#!/bin/bash" in content
        assert "set -euo pipefail" in content
        assert "ogr2ogr --version" in content

    def test_write_cmd_script(self, tmp_path: Path) -> None:
        """CMD script contains @echo off and errorlevel check."""
        env = ExecEnvironment(
            env_vars={},
            shell=ShellType.CMD,
            shell_executable=Path("cmd"),
            gdal_available=True,
        )
        executor = ShellExecutor(env)

        script_path = executor.write_script(
            ["ogr2ogr --version"], tmp_path
        )

        content = script_path.read_text()
        assert script_path.suffix == ".bat"
        assert "@echo off" in content
        assert "if errorlevel 1 exit /b 1" in content

    def test_write_powershell_script(self, tmp_path: Path) -> None:
        """PowerShell script contains #Requires and $ErrorActionPreference."""
        env = ExecEnvironment(
            env_vars={},
            shell=ShellType.POWERSHELL,
            shell_executable=Path("powershell"),
            gdal_available=True,
        )
        executor = ShellExecutor(env)

        script_path = executor.write_script(
            ["Write-Host 'test'"], tmp_path
        )

        content = script_path.read_text()
        assert script_path.suffix == ".ps1"
        assert "#Requires -Version 5.1" in content
        assert "$ErrorActionPreference = 'Stop'" in content


# ---------------------------------------------------------------------------
# Integration: verify + execute round-trip
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end integration tests."""

    def test_build_and_write_script(self, tmp_path: Path) -> None:
        """Build env then write script — full round trip."""
        config = ExecEnvConfig(type=ExecEnvType.SYSTEM, shell="cmd")
        builder = EnvironmentBuilder(config)

        with patch("core.exec_env.ShellDetector.resolve_shell") as mock_resolve:
            mock_resolve.return_value = (ShellType.CMD, Path("cmd"))
            with patch.object(
                builder, "_verify_gdal", return_value=(True, "GDAL 3.9.0")
            ):
                env = builder.build()

        executor = ShellExecutor(env)
        script_path = executor.write_script(["echo hello"], tmp_path)

        assert script_path.exists()
        assert script_path.suffix == ".bat"
