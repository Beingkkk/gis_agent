"""Tests for api.routes.exec_env module.

Design: plan-exec-env v1.1.0 (DC-0103, DC-0104)
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client() -> TestClient:
    """TestClient with initialized dependencies."""
    app = create_app()
    return TestClient(app)


class TestVerifyEndpoint:
    """POST /api/exec-env/verify"""

    def test_verify_valid_system_config(self, client: TestClient) -> None:
        """Valid system config returns valid=true."""
        with patch("api.routes.exec_env.EnvironmentBuilder") as mock_builder_cls:
            mock_env = MagicMock()
            mock_env.shell.value = "cmd"
            mock_env.shell_executable = "C:\\Windows\\System32\\cmd.exe"
            mock_env.gdal_available = True
            mock_env.gdal_version = "GDAL 3.9.0"
            mock_env.env_vars = {}

            mock_builder = MagicMock()
            mock_builder.build.return_value = mock_env
            mock_builder_cls.return_value = mock_builder

            response = client.post("/api/exec-env/verify", json={
                "type": "system",
                "env_name": "",
                "shell": "cmd",
                "shell_path": "",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["shell"]["type"] == "cmd"
        assert data["gdal"]["available"] is True

    def test_verify_invalid_shell(self, client: TestClient) -> None:
        """Invalid shell returns valid=false with error."""
        with patch("api.routes.exec_env.EnvironmentBuilder") as mock_builder_cls:
            mock_builder = MagicMock()
            mock_builder.build.side_effect = RuntimeError("shell not found")
            mock_builder_cls.return_value = mock_builder

            response = client.post("/api/exec-env/verify", json={
                "type": "system",
                "env_name": "",
                "shell": "bash",
                "shell_path": "",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "shell not found" in data["error"]

    def test_verify_invalid_conda_env(self, client: TestClient) -> None:
        """Invalid conda env returns valid=false."""
        with patch("api.routes.exec_env.EnvironmentBuilder") as mock_builder_cls:
            mock_builder = MagicMock()
            mock_builder.build.side_effect = FileNotFoundError("env not found")
            mock_builder_cls.return_value = mock_builder

            response = client.post("/api/exec-env/verify", json={
                "type": "conda",
                "env_name": "nonexistent",
                "shell": "bash",
                "shell_path": "",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "env not found" in data["error"]

    def test_verify_invalid_env_type(self, client: TestClient) -> None:
        """Invalid env type returns 400."""
        response = client.post("/api/exec-env/verify", json={
            "type": "invalid",
            "env_name": "",
            "shell": "auto",
            "shell_path": "",
        })

        assert response.status_code == 400


class TestSetSessionExecEnv:
    """POST /api/session/{id}/exec-env"""

    def test_save_success(self, client: TestClient) -> None:
        """Valid config is saved to session."""
        # Create a session first
        create_resp = client.post("/api/session")
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        with patch("api.routes.exec_env.EnvironmentBuilder") as mock_builder_cls:
            mock_env = MagicMock()
            mock_env.shell.value = "bash"
            mock_env.shell_executable = "/bin/bash"
            mock_env.gdal_available = True
            mock_env.gdal_version = "GDAL 3.9.0"
            mock_env.env_vars = {"PATH": "/fake/bin"}

            mock_builder = MagicMock()
            mock_builder.build.return_value = mock_env
            mock_builder_cls.return_value = mock_builder

            response = client.post(f"/api/session/{session_id}/exec-env", json={
                "type": "system",
                "env_name": "",
                "shell": "bash",
                "shell_path": "",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["exec_env"] is not None
        assert data["exec_env"]["shell"] == "bash"
        assert data["exec_env"]["gdal_available"] is True

    def test_save_validation_fails(self, client: TestClient) -> None:
        """Invalid config returns 400, session unchanged."""
        # Create a session first
        create_resp = client.post("/api/session")
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        with patch("api.routes.exec_env.EnvironmentBuilder") as mock_builder_cls:
            mock_builder = MagicMock()
            mock_builder.build.side_effect = FileNotFoundError("env not found")
            mock_builder_cls.return_value = mock_builder

            response = client.post(f"/api/session/{session_id}/exec-env", json={
                "type": "conda",
                "env_name": "nonexistent",
                "shell": "bash",
                "shell_path": "",
            })

        assert response.status_code == 400
        assert "env not found" in response.json()["detail"]


class TestListCondaEnvs:
    """GET /api/exec-env/conda-envs"""

    def test_list_conda_envs(self, client: TestClient) -> None:
        """Returns list of conda environments."""
        with patch("api.routes.exec_env.CondaEnvDetector.list_envs", return_value=["base", "gis-agent"]):
            response = client.get("/api/exec-env/conda-envs")

        assert response.status_code == 200
        data = response.json()
        assert data["envs"] == ["base", "gis-agent"]

    def test_list_conda_envs_empty(self, client: TestClient) -> None:
        """Returns empty list when no conda found."""
        with patch("api.routes.exec_env.CondaEnvDetector.list_envs", return_value=[]):
            response = client.get("/api/exec-env/conda-envs")

        assert response.status_code == 200
        data = response.json()
        assert data["envs"] == []
