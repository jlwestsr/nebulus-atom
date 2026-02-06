"""Tests for the Overlord ecosystem scanner."""

from __future__ import annotations

import subprocess
from pathlib import Path


from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.scanner import (
    detect_test_command,
    scan_ecosystem,
    scan_project,
)


class TestScanProject:
    """Tests for scan_project()."""

    def test_clean_repo(self, temp_git_repo: Path) -> None:
        config = ProjectConfig(
            name="test",
            path=temp_git_repo,
            remote="test/test",
            role="tooling",
        )
        status = scan_project(config)
        assert status.name == "test"
        assert status.git.clean is True
        assert status.git.branch in ("main", "master")
        assert "initial commit" in status.git.last_commit

    def test_dirty_repo(self, temp_git_repo_dirty: Path) -> None:
        config = ProjectConfig(
            name="test",
            path=temp_git_repo_dirty,
            remote="test/test",
            role="tooling",
        )
        status = scan_project(config)
        assert status.git.clean is False
        assert any("Dirty" in i for i in status.issues)

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="gone",
            path=tmp_path / "nonexistent",
            remote="test/test",
            role="tooling",
        )
        status = scan_project(config)
        assert any("does not exist" in i for i in status.issues)

    def test_detects_branch(self, temp_git_repo: Path) -> None:
        # Create and switch to develop branch
        subprocess.run(
            ["git", "checkout", "-b", "develop"],
            cwd=str(temp_git_repo),
            capture_output=True,
        )
        config = ProjectConfig(
            name="test",
            path=temp_git_repo,
            remote="test/test",
            role="tooling",
            branch_model="develop-main",
        )
        status = scan_project(config)
        assert status.git.branch == "develop"
        # No branch alignment issue when on develop
        assert not any("expected develop or main" in i for i in status.issues)

    def test_branch_alignment_issue(self, temp_git_repo: Path) -> None:
        # Create and switch to a feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feat/something"],
            cwd=str(temp_git_repo),
            capture_output=True,
        )
        config = ProjectConfig(
            name="test",
            path=temp_git_repo,
            remote="test/test",
            role="tooling",
            branch_model="develop-main",
        )
        status = scan_project(config)
        assert any("expected develop or main" in i for i in status.issues)

    def test_tags_detected(self, temp_git_repo: Path) -> None:
        subprocess.run(
            ["git", "tag", "v1.0.0"],
            cwd=str(temp_git_repo),
            capture_output=True,
        )
        config = ProjectConfig(
            name="test",
            path=temp_git_repo,
            remote="test/test",
            role="tooling",
        )
        status = scan_project(config)
        assert "v1.0.0" in status.git.tags


class TestDetectTestCommand:
    """Tests for detect_test_command()."""

    def test_pytest_in_pyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
        assert detect_test_command(tmp_path) == "python -m pytest tests/"

    def test_bin_gantry_script(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "gantry").write_text("#!/bin/bash\n")
        assert detect_test_command(tmp_path) == "bin/gantry test"

    def test_makefile_test_target(self, tmp_path: Path) -> None:
        makefile = tmp_path / "Makefile"
        makefile.write_text("test:\n\tpytest\n")
        assert detect_test_command(tmp_path) == "make test"

    def test_tests_directory_fallback(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        assert detect_test_command(tmp_path) == "python -m pytest tests/"

    def test_no_tests_returns_none(self, tmp_path: Path) -> None:
        assert detect_test_command(tmp_path) is None


class TestScanEcosystem:
    """Tests for scan_ecosystem()."""

    def test_scans_all_projects(self, temp_git_repo: Path) -> None:
        config = OverlordConfig(
            projects={
                "a": ProjectConfig(
                    name="a",
                    path=temp_git_repo,
                    remote="t/a",
                    role="tooling",
                ),
            }
        )
        results = scan_ecosystem(config)
        assert len(results) == 1
        assert results[0].name == "a"

    def test_respects_dependency_order(
        self,
        temp_git_repo: Path,
        tmp_path: Path,
    ) -> None:
        # Create a second repo
        repo2 = tmp_path / "repo2"
        repo2.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo2), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=str(repo2),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=str(repo2),
            capture_output=True,
        )
        (repo2 / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "."], cwd=str(repo2), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(repo2),
            capture_output=True,
        )

        config = OverlordConfig(
            projects={
                "downstream": ProjectConfig(
                    name="downstream",
                    path=repo2,
                    remote="t/down",
                    role="tooling",
                    depends_on=["upstream"],
                ),
                "upstream": ProjectConfig(
                    name="upstream",
                    path=temp_git_repo,
                    remote="t/up",
                    role="shared-library",
                ),
            }
        )
        results = scan_ecosystem(config)
        names = [r.name for r in results]
        assert names.index("upstream") < names.index("downstream")
