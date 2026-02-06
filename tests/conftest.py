"""Shared fixtures for Overlord tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


SAMPLE_CONFIG_YAML = """\
projects:
  nebulus-core:
    path: "{core_path}"
    remote: jlwestsr/nebulus-core
    role: shared-library
    branch_model: develop-main
    depends_on: []
  nebulus-prime:
    path: "{prime_path}"
    remote: jlwestsr/nebulus-prime
    role: platform-deployment
    branch_model: develop-main
    depends_on:
      - nebulus-core
  nebulus-atom:
    path: "{atom_path}"
    remote: jlwestsr/nebulus-atom
    role: tooling
    branch_model: develop-main
    depends_on:
      - nebulus-core
autonomy:
  global: cautious
  overrides:
    nebulus-core: proactive
"""


@pytest.fixture
def sample_config_yaml(tmp_path: Path) -> str:
    """Return sample YAML with tmp_path substituted in."""
    core = tmp_path / "nebulus-core"
    prime = tmp_path / "nebulus-prime"
    atom = tmp_path / "nebulus-atom"
    for d in (core, prime, atom):
        d.mkdir()
    return SAMPLE_CONFIG_YAML.format(
        core_path=str(core),
        prime_path=str(prime),
        atom_path=str(atom),
    )


@pytest.fixture
def sample_config_file(tmp_path: Path, sample_config_yaml: str) -> Path:
    """Write sample config to a YAML file and return its path."""
    config_file = tmp_path / "overlord.yml"
    config_file.write_text(sample_config_yaml)
    return config_file


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with an initial commit."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo),
        capture_output=True,
    )

    # Create initial commit
    readme = repo / "README.md"
    readme.write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=str(repo),
        capture_output=True,
    )

    return repo


@pytest.fixture
def temp_git_repo_dirty(temp_git_repo: Path) -> Path:
    """Create a temp git repo with uncommitted changes."""
    (temp_git_repo / "dirty.txt").write_text("uncommitted\n")
    return temp_git_repo
