"""Tests for config module.

Design: DC-0001, DC-0002, DC-0003, DC-0004, DC-0005
"""

import json
import logging
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.config import (
    Config,
    EmbeddingConfig,
    LLMConfig,
    RAGConfig,
    WorkspaceConfig,
    get_config,
    load_config,
)
from src.config.loader import _clear_config_singleton

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_config_dict() -> dict:
    """Return a complete valid config dict."""
    return {
        "llm": {
            "base_url": "https://api.kimi.com/coding/",
            "auth_key": "sk-test",
            "model_name": "claude-sonnet-4-6",
        },
        "embedding": {
            "model_path": str(Path(__file__).parent.parent / "fixtures"),
            "device": "cpu",
        },
        "rag": {
            "chunk_size": 512,
            "chunk_overlap": 128,
            "top_k": 5,
        },
        "workspace": {
            "default_path": ".",
            "allow_parent_access": False,
        },
    }


@pytest.fixture
def config_file(tmp_path: Path, valid_config_dict: dict) -> Path:
    """Create a temporary valid config file."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps(valid_config_dict), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def clear_singleton():
    """Clear the module-level singleton before each test."""
    _clear_config_singleton()
    yield
    _clear_config_singleton()


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestDataModels:
    """Tests for frozen dataclass models (C-02)."""

    def test_llm_config_creation(self) -> None:
        cfg = LLMConfig(
            base_url="https://api.example.com", auth_key="sk-xxx", model_name="test"
        )
        assert cfg.base_url == "https://api.example.com"
        assert cfg.auth_key == "sk-xxx"
        assert cfg.model_name == "test"

    def test_embedding_config_defaults(self) -> None:
        cfg = EmbeddingConfig(model_path="/model")
        assert cfg.model_path == "/model"
        assert cfg.device == "cpu"

    def test_embedding_config_cuda(self) -> None:
        cfg = EmbeddingConfig(model_path="/model", device="cuda")
        assert cfg.device == "cuda"

    def test_rag_config_defaults(self) -> None:
        cfg = RAGConfig()
        assert cfg.chunk_size == 512
        assert cfg.chunk_overlap == 128
        assert cfg.top_k == 5

    def test_workspace_config_defaults(self) -> None:
        cfg = WorkspaceConfig()
        assert cfg.default_path == "."
        assert cfg.allow_parent_access is False

    def test_config_creation(self) -> None:
        cfg = Config(
            llm=LLMConfig(base_url="https://a.com", auth_key="k", model_name="m"),
            embedding=EmbeddingConfig(model_path="/m"),
            rag=RAGConfig(),
            workspace=WorkspaceConfig(),
        )
        assert cfg.llm.base_url == "https://a.com"
        assert cfg.embedding.device == "cpu"

    def test_immutability(self) -> None:
        cfg = LLMConfig(base_url="https://a.com", auth_key="k", model_name="m")
        with pytest.raises(FrozenInstanceError):
            cfg.base_url = "https://b.com"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# load_config tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for load_config function (C-03)."""

    def test_load_valid_config(self, config_file: Path) -> None:
        cfg = load_config(config_file)
        assert isinstance(cfg, Config)
        assert cfg.llm.base_url == "https://api.kimi.com/coding/"
        assert cfg.llm.auth_key == "sk-test"
        assert cfg.llm.model_name == "claude-sonnet-4-6"
        assert cfg.embedding.device == "cpu"
        assert cfg.rag.chunk_size == 512
        assert cfg.rag.top_k == 5
        assert cfg.workspace.default_path == "."
        assert cfg.workspace.allow_parent_access is False

    def test_missing_required_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(
            json.dumps({"llm": {}, "embedding": {}, "rag": {}, "workspace": {}})
        )
        with pytest.raises(ValueError, match="Missing required fields"):
            load_config(path)

    def test_missing_llm_section(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"embedding": {"model_path": "/m"}}))
        with pytest.raises(ValueError, match="llm"):
            load_config(path)

    def test_type_error_chunk_size_string(
        self, tmp_path: Path, valid_config_dict: dict
    ) -> None:
        path = tmp_path / "bad.json"
        data = valid_config_dict.copy()
        data["rag"]["chunk_size"] = "not_a_number"
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="chunk_size"):
            load_config(path)

    def test_business_rule_overlap(
        self, tmp_path: Path, valid_config_dict: dict
    ) -> None:
        path = tmp_path / "bad.json"
        data = valid_config_dict.copy()
        data["rag"]["chunk_overlap"] = 600  # > chunk_size 512
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="chunk_overlap.*chunk_size"):
            load_config(path)

    def test_empty_base_url(self, tmp_path: Path, valid_config_dict: dict) -> None:
        path = tmp_path / "bad.json"
        data = valid_config_dict.copy()
        data["llm"]["base_url"] = ""
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="base_url"):
            load_config(path)

    def test_invalid_device(self, tmp_path: Path, valid_config_dict: dict) -> None:
        path = tmp_path / "bad.json"
        data = valid_config_dict.copy()
        data["embedding"]["device"] = "gpu"
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="device"):
            load_config(path)

    def test_model_path_not_exist(
        self, tmp_path: Path, valid_config_dict: dict
    ) -> None:
        path = tmp_path / "bad.json"
        data = valid_config_dict.copy()
        data["embedding"]["model_path"] = "/nonexistent/path/to/model"
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="model_path"):
            load_config(path)

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.json")

    def test_json_decode_error(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not valid json{", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_config(path)

    def test_logs_error_before_raise(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "bad.json"
        path.write_text("invalid", encoding="utf-8")
        with caplog.at_level(logging.ERROR):
            with pytest.raises(json.JSONDecodeError):
                load_config(path)
        assert any(logging.ERROR == r.levelno for r in caplog.records)


# ---------------------------------------------------------------------------
# Environment variable override tests
# ---------------------------------------------------------------------------


class TestEnvOverride:
    """Tests for GISAGENT_* environment variable overrides (C-04)."""

    def test_override_auth_key(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GISAGENT_LLM_AUTH_KEY", "env-sk-override")
        cfg = load_config(config_file)
        assert cfg.llm.auth_key == "env-sk-override"

    def test_override_chunk_size(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GISAGENT_RAG_CHUNK_SIZE", "1024")
        cfg = load_config(config_file)
        assert cfg.rag.chunk_size == 1024

    def test_override_top_k(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GISAGENT_RAG_TOP_K", "10")
        cfg = load_config(config_file)
        assert cfg.rag.top_k == 10

    def test_override_device(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GISAGENT_EMBEDDING_DEVICE", "cuda")
        cfg = load_config(config_file)
        assert cfg.embedding.device == "cuda"

    def test_override_bool_allow_parent_access(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GISAGENT_WORKSPACE_ALLOW_PARENT_ACCESS", "true")
        cfg = load_config(config_file)
        assert cfg.workspace.allow_parent_access is True

    def test_env_takes_precedence_over_file(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GISAGENT_LLM_MODEL_NAME", "env-model")
        cfg = load_config(config_file)
        # File says "claude-sonnet-4-6", env overrides
        assert cfg.llm.model_name == "env-model"

    def test_unset_env_does_not_interfere(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Ensure env is not set
        monkeypatch.delenv("GISAGENT_LLM_BASE_URL", raising=False)
        cfg = load_config(config_file)
        assert cfg.llm.base_url == "https://api.kimi.com/coding/"


# ---------------------------------------------------------------------------
# Default values tests
# ---------------------------------------------------------------------------


class TestDefaults:
    """Tests for default value filling (C-05)."""

    def test_defaults_filled(self, tmp_path: Path) -> None:
        path = tmp_path / "minimal.json"
        path.write_text(
            json.dumps(
                {
                    "llm": {
                        "base_url": "https://api.example.com",
                        "auth_key": "sk-xxx",
                        "model_name": "test-model",
                    },
                    "embedding": {
                        "model_path": str(tmp_path),
                    },
                }
            )
        )
        cfg = load_config(path)
        assert cfg.embedding.device == "cpu"
        assert cfg.rag.chunk_size == 512
        assert cfg.rag.chunk_overlap == 128
        assert cfg.rag.top_k == 5
        assert cfg.workspace.default_path == "."
        assert cfg.workspace.allow_parent_access is False


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------


class TestSingleton:
    """Tests for get_config singleton access (C-06)."""

    def test_uninitialized_get_config(self) -> None:
        with pytest.raises(RuntimeError, match="load_config"):
            get_config()

    def test_get_config_returns_same_instance(self, config_file: Path) -> None:
        cfg1 = load_config(config_file)
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_multiple_get_config_calls_same(self, config_file: Path) -> None:
        load_config(config_file)
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_re_load_config_replaces_singleton(
        self, config_file: Path, tmp_path: Path
    ) -> None:
        cfg1 = load_config(config_file)
        new_path = tmp_path / "config2.json"
        data = {
            "llm": {
                "base_url": "https://new.com",
                "auth_key": "sk-new",
                "model_name": "new",
            },
            "embedding": {"model_path": str(tmp_path)},
            "rag": {},
            "workspace": {},
        }
        new_path.write_text(json.dumps(data))
        cfg2 = load_config(new_path)
        assert cfg2.llm.base_url == "https://new.com"
        assert get_config() is cfg2
        assert get_config() is not cfg1


# ---------------------------------------------------------------------------
# Integration / smoke
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration-level smoke tests."""

    def test_full_config_matches_expected_structure(self, config_file: Path) -> None:
        cfg = load_config(config_file)
        assert isinstance(cfg.llm, LLMConfig)
        assert isinstance(cfg.embedding, EmbeddingConfig)
        assert isinstance(cfg.rag, RAGConfig)
        assert isinstance(cfg.workspace, WorkspaceConfig)
        assert isinstance(cfg, Config)
