"""Tests for the Overlord project registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from nebulus_swarm.overlord.registry import (
    OverlordConfig,
    ProjectConfig,
    get_dependency_order,
    load_config,
    validate_config,
)


class TestLoadConfig:
    """Tests for load_config()."""

    def test_load_from_yaml_file(self, sample_config_file: Path) -> None:
        config = load_config(sample_config_file)
        assert "nebulus-core" in config.projects
        assert "nebulus-prime" in config.projects
        assert "nebulus-atom" in config.projects

    def test_load_parses_project_fields(self, sample_config_file: Path) -> None:
        config = load_config(sample_config_file)
        core = config.projects["nebulus-core"]
        assert core.name == "nebulus-core"
        assert core.remote == "jlwestsr/nebulus-core"
        assert core.role == "shared-library"
        assert core.branch_model == "develop-main"
        assert core.depends_on == []

    def test_load_parses_dependencies(self, sample_config_file: Path) -> None:
        config = load_config(sample_config_file)
        prime = config.projects["nebulus-prime"]
        assert prime.depends_on == ["nebulus-core"]

    def test_load_parses_autonomy(self, sample_config_file: Path) -> None:
        config = load_config(sample_config_file)
        assert config.autonomy_global == "cautious"
        assert config.autonomy_overrides == {"nebulus-core": "proactive"}

    def test_load_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        config = load_config(tmp_path / "nonexistent.yml")
        assert config.projects == {}

    def test_load_expands_tilde_in_paths(self, tmp_path: Path) -> None:
        yaml_content = """\
projects:
  test:
    path: "~/some-project"
    remote: test/test
    role: tooling
"""
        config_file = tmp_path / "overlord.yml"
        config_file.write_text(yaml_content)
        config = load_config(config_file)
        # Tilde should be expanded
        assert "~" not in str(config.projects["test"].path)

    def test_load_invalid_projects_type_raises(self, tmp_path: Path) -> None:
        config_file = tmp_path / "overlord.yml"
        config_file.write_text("projects: not-a-dict\n")
        with pytest.raises(ValueError, match="must be a mapping"):
            load_config(config_file)


class TestValidateConfig:
    """Tests for validate_config()."""

    def test_valid_config_no_errors(self, sample_config_file: Path) -> None:
        config = load_config(sample_config_file)
        errors = validate_config(config)
        assert errors == []

    def test_invalid_role(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        config = OverlordConfig(
            projects={
                "proj": ProjectConfig(
                    name="proj",
                    path=proj_dir,
                    remote="test/proj",
                    role="invalid-role",
                ),
            }
        )
        errors = validate_config(config)
        assert any("invalid role" in e for e in errors)

    def test_invalid_branch_model(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        config = OverlordConfig(
            projects={
                "proj": ProjectConfig(
                    name="proj",
                    path=proj_dir,
                    remote="test/proj",
                    role="tooling",
                    branch_model="invalid",
                ),
            }
        )
        errors = validate_config(config)
        assert any("invalid branch_model" in e for e in errors)

    def test_missing_path(self, tmp_path: Path) -> None:
        config = OverlordConfig(
            projects={
                "proj": ProjectConfig(
                    name="proj",
                    path=tmp_path / "nonexistent",
                    remote="test/proj",
                    role="tooling",
                ),
            }
        )
        errors = validate_config(config)
        assert any("path does not exist" in e for e in errors)

    def test_missing_remote(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        config = OverlordConfig(
            projects={
                "proj": ProjectConfig(
                    name="proj",
                    path=proj_dir,
                    remote="",
                    role="tooling",
                ),
            }
        )
        errors = validate_config(config)
        assert any("remote is required" in e for e in errors)

    def test_depends_on_unknown_project(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        config = OverlordConfig(
            projects={
                "proj": ProjectConfig(
                    name="proj",
                    path=proj_dir,
                    remote="test/proj",
                    role="tooling",
                    depends_on=["nonexistent"],
                ),
            }
        )
        errors = validate_config(config)
        assert any("unknown project 'nonexistent'" in e for e in errors)

    def test_invalid_autonomy_global(self, tmp_path: Path) -> None:
        config = OverlordConfig(autonomy_global="reckless")
        errors = validate_config(config)
        assert any("Invalid global autonomy" in e for e in errors)

    def test_invalid_autonomy_override(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        config = OverlordConfig(
            projects={
                "proj": ProjectConfig(
                    name="proj",
                    path=proj_dir,
                    remote="test/proj",
                    role="tooling",
                ),
            },
            autonomy_overrides={"proj": "yolo"},
        )
        errors = validate_config(config)
        assert any("Invalid autonomy override" in e for e in errors)

    def test_circular_dependency(self, tmp_path: Path) -> None:
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        config = OverlordConfig(
            projects={
                "a": ProjectConfig(
                    name="a",
                    path=a_dir,
                    remote="t/a",
                    role="tooling",
                    depends_on=["b"],
                ),
                "b": ProjectConfig(
                    name="b",
                    path=b_dir,
                    remote="t/b",
                    role="tooling",
                    depends_on=["a"],
                ),
            }
        )
        errors = validate_config(config)
        assert any("Circular dependency" in e for e in errors)


class TestGetDependencyOrder:
    """Tests for get_dependency_order()."""

    def test_simple_chain(self, sample_config_file: Path) -> None:
        config = load_config(sample_config_file)
        order = get_dependency_order(config)
        # nebulus-core must come before nebulus-prime and nebulus-atom
        core_idx = order.index("nebulus-core")
        prime_idx = order.index("nebulus-prime")
        atom_idx = order.index("nebulus-atom")
        assert core_idx < prime_idx
        assert core_idx < atom_idx

    def test_no_dependencies(self, tmp_path: Path) -> None:
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        config = OverlordConfig(
            projects={
                "a": ProjectConfig(name="a", path=a_dir, remote="t/a", role="tooling"),
                "b": ProjectConfig(name="b", path=b_dir, remote="t/b", role="tooling"),
            }
        )
        order = get_dependency_order(config)
        assert set(order) == {"a", "b"}

    def test_circular_raises(self, tmp_path: Path) -> None:
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        config = OverlordConfig(
            projects={
                "a": ProjectConfig(
                    name="a",
                    path=a_dir,
                    remote="t/a",
                    role="tooling",
                    depends_on=["b"],
                ),
                "b": ProjectConfig(
                    name="b",
                    path=b_dir,
                    remote="t/b",
                    role="tooling",
                    depends_on=["a"],
                ),
            }
        )
        with pytest.raises(ValueError, match="Circular"):
            get_dependency_order(config)

    def test_empty_config(self) -> None:
        config = OverlordConfig()
        assert get_dependency_order(config) == []
