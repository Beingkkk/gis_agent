"""Integration test: initialization chain.

Verifies that all core components can be wired together using real
template files and mock LLM dependencies.

Design: plan-integration v1.0.0 (T-INT-01)
"""

from pathlib import Path
from unittest.mock import MagicMock

from core import (
    ParamValidator,
    SessionProcessor,
    TemplateRegistry,
)
from core.workspace import Workspace
from llm import PromptBuilder
from templates import TemplateEngine, scan_templates


class TestInitChain:
    """Component assembly with real template directory."""

    def test_scan_templates_finds_all_templates(
        self,
        real_template_dir: Path,
    ) -> None:
        """Scanner discovers all 10 templates."""
        templates = scan_templates(real_template_dir)

        assert len(templates) >= 10
        ids = {t.id for t in templates}
        # Templates are batch-generated from GDAL docs; verify some known ones exist
        assert "gdal_info" in ids

    def test_template_registry_builds_from_real_scan(
        self,
        real_template_dir: Path,
    ) -> None:
        """Registry indexes scanned templates correctly."""
        templates = scan_templates(real_template_dir)
        registry = TemplateRegistry(templates, real_template_dir)

        assert len(registry.list_templates()) >= 10
        assert registry.get_template("gdal_info") is not None

    def test_template_engine_loads_all_templates(
        self,
        real_template_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Engine can load every template file."""
        workspace = Workspace(tmp_path)
        engine = TemplateEngine(real_template_dir, workspace)
        templates = scan_templates(real_template_dir)

        for template_def in templates:
            # Just verify get_template doesn't raise
            loaded = engine._env.get_template(template_def.template_file)
            assert loaded is not None

    def test_session_processor_assembles_with_real_components(
        self,
        real_template_dir: Path,
        tmp_path: Path,
        mock_llm_client: MagicMock,
    ) -> None:
        """SessionProcessor can be built with real registry/engine + mock LLM."""
        workspace = Workspace(tmp_path)
        templates = scan_templates(real_template_dir)
        registry = TemplateRegistry(templates, real_template_dir)
        validator = ParamValidator(workspace)
        engine = TemplateEngine(real_template_dir, workspace)
        prompt_builder = PromptBuilder()

        processor = SessionProcessor(
            registry=registry,
            validator=validator,
            template_engine=engine,
            llm_client=mock_llm_client,
            prompt_builder=prompt_builder,
        )

        assert processor is not None

    def test_all_templates_have_valid_params(self, real_template_dir: Path) -> None:
        """Every template has at least required params defined."""
        templates = scan_templates(real_template_dir)

        for t in templates:
            assert t.id, f"Template missing id: {t.template_file}"
            assert t.name, f"Template missing name: {t.template_file}"
            # Some templates like gdal_info have only 1 param (input)
            assert len(t.params) >= 1, f"Template {t.id} has no params"
