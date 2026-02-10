"""Tests for MirrorManager worktree operations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nebulus_swarm.overlord.mirrors import MirrorManager
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig


@pytest.fixture
def config(tmp_path: Path) -> OverlordConfig:
    """Create a minimal OverlordConfig for testing."""
    return OverlordConfig(
        workspace_root=tmp_path,
        projects={
            "nebulus-core": ProjectConfig(
                name="nebulus-core",
                path=tmp_path / "nebulus-core",
                remote="jlwestsr/nebulus-core",
                role="shared-library",
            ),
        },
    )


@pytest.fixture
def mirror_root(tmp_path: Path) -> Path:
    """Provide a temporary mirror root directory."""
    return tmp_path / "mirrors"


@pytest.fixture
def mgr(config: OverlordConfig, mirror_root: Path) -> MirrorManager:
    """Create a MirrorManager with temp paths."""
    return MirrorManager(config, mirror_root=mirror_root)


TASK_ID = "abcdef12-3456-7890-abcd-ef1234567890"


class TestProvisionWorktree:
    """Tests for provision_worktree."""

    @patch("nebulus_swarm.overlord.mirrors.WORKTREE_ROOT")
    @patch("subprocess.run")
    def test_creates_worktree_directory(
        self,
        mock_run: MagicMock,
        mock_wt_root: MagicMock,
        mgr: MirrorManager,
        mirror_root: Path,
        tmp_path: Path,
    ) -> None:
        """Provision creates the worktree parent directory."""
        wt_root = tmp_path / "worktrees"
        mock_wt_root.__truediv__ = lambda self, x: wt_root / x
        # Create the bare mirror directory so the check passes
        (mirror_root / "nebulus-core.git").mkdir(parents=True)
        mock_run.return_value = MagicMock(returncode=0)

        # Patch the module-level constant for path construction
        with patch("nebulus_swarm.overlord.mirrors.WORKTREE_ROOT", wt_root):
            result = mgr.provision_worktree("nebulus-core", TASK_ID)

        assert result == wt_root / "nebulus-core" / TASK_ID[:8]
        assert (wt_root / "nebulus-core").exists()

    @patch("subprocess.run")
    def test_runs_correct_git_command(
        self,
        mock_run: MagicMock,
        mgr: MirrorManager,
        mirror_root: Path,
        tmp_path: Path,
    ) -> None:
        """Provision runs git worktree add with correct arguments."""
        (mirror_root / "nebulus-core.git").mkdir(parents=True)
        mock_run.return_value = MagicMock(returncode=0)

        with patch("nebulus_swarm.overlord.mirrors.WORKTREE_ROOT", tmp_path / "wt"):
            mgr.provision_worktree("nebulus-core", TASK_ID, branch="main")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0:3] == ["git", "worktree", "add"]
        assert "-b" in cmd
        assert f"atom/{TASK_ID[:8]}" in cmd
        assert "main" in cmd
        assert call_args[1]["cwd"] == str(mirror_root / "nebulus-core.git")

    @patch("subprocess.run")
    def test_returns_worktree_path(
        self,
        mock_run: MagicMock,
        mgr: MirrorManager,
        mirror_root: Path,
        tmp_path: Path,
    ) -> None:
        """Provision returns the path to the new worktree."""
        (mirror_root / "nebulus-core.git").mkdir(parents=True)
        mock_run.return_value = MagicMock(returncode=0)
        wt_root = tmp_path / "wt"

        with patch("nebulus_swarm.overlord.mirrors.WORKTREE_ROOT", wt_root):
            result = mgr.provision_worktree("nebulus-core", TASK_ID)

        assert result == wt_root / "nebulus-core" / TASK_ID[:8]

    @patch("subprocess.run")
    def test_branch_naming(
        self,
        mock_run: MagicMock,
        mgr: MirrorManager,
        mirror_root: Path,
        tmp_path: Path,
    ) -> None:
        """Branch name uses atom/ prefix and short task ID."""
        (mirror_root / "nebulus-core.git").mkdir(parents=True)
        mock_run.return_value = MagicMock(returncode=0)

        with patch("nebulus_swarm.overlord.mirrors.WORKTREE_ROOT", tmp_path / "wt"):
            mgr.provision_worktree("nebulus-core", TASK_ID)

        cmd = mock_run.call_args[0][0]
        branch_idx = cmd.index("-b") + 1
        assert cmd[branch_idx] == f"atom/{TASK_ID[:8]}"

    def test_mirror_not_initialized_raises(self, mgr: MirrorManager) -> None:
        """RuntimeError raised when mirror doesn't exist."""
        with pytest.raises(RuntimeError, match="Mirror not initialized"):
            mgr.provision_worktree("nebulus-core", TASK_ID)


class TestCleanupWorktree:
    """Tests for cleanup_worktree."""

    @patch("subprocess.run")
    def test_removes_worktree(
        self,
        mock_run: MagicMock,
        mgr: MirrorManager,
        mirror_root: Path,
        tmp_path: Path,
    ) -> None:
        """Cleanup calls git worktree remove."""
        (mirror_root / "nebulus-core.git").mkdir(parents=True)
        wt_path = tmp_path / "wt" / "nebulus-core" / TASK_ID[:8]
        wt_path.mkdir(parents=True)
        mock_run.return_value = MagicMock(returncode=0)

        result = mgr.cleanup_worktree("nebulus-core", wt_path)

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0:3] == ["git", "worktree", "remove"]
        assert str(wt_path) in cmd
        assert "--force" in cmd

    def test_handles_missing_worktree_path(
        self, mgr: MirrorManager, mirror_root: Path, tmp_path: Path
    ) -> None:
        """Cleanup returns False when worktree path doesn't exist."""
        (mirror_root / "nebulus-core.git").mkdir(parents=True)
        missing_path = tmp_path / "nonexistent"

        result = mgr.cleanup_worktree("nebulus-core", missing_path)

        assert result is False

    @patch("subprocess.run")
    def test_removes_empty_parent_dir(
        self,
        mock_run: MagicMock,
        mgr: MirrorManager,
        mirror_root: Path,
        tmp_path: Path,
    ) -> None:
        """Cleanup removes the empty parent directory after worktree removal."""
        (mirror_root / "nebulus-core.git").mkdir(parents=True)
        wt_path = tmp_path / "wt" / "nebulus-core" / TASK_ID[:8]
        wt_path.mkdir(parents=True)

        def side_effect(*args, **kwargs):
            # Simulate git removing the worktree directory
            if wt_path.exists():
                wt_path.rmdir()
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        result = mgr.cleanup_worktree("nebulus-core", wt_path)

        assert result is True
        # Parent (nebulus-core dir) should have been cleaned up
        assert not wt_path.parent.exists()

    @patch("subprocess.run")
    def test_git_worktree_remove_called_with_mirror_cwd(
        self,
        mock_run: MagicMock,
        mgr: MirrorManager,
        mirror_root: Path,
        tmp_path: Path,
    ) -> None:
        """Git worktree remove runs in the mirror directory."""
        (mirror_root / "nebulus-core.git").mkdir(parents=True)
        wt_path = tmp_path / "wt" / "nebulus-core" / TASK_ID[:8]
        wt_path.mkdir(parents=True)
        mock_run.return_value = MagicMock(returncode=0)

        mgr.cleanup_worktree("nebulus-core", wt_path)

        assert mock_run.call_args[1]["cwd"] == str(mirror_root / "nebulus-core.git")


class TestListWorktrees:
    """Tests for list_worktrees."""

    def test_lists_by_project(self, tmp_path: Path, config: OverlordConfig) -> None:
        """Lists worktree directories grouped by project."""
        wt_root = tmp_path / "worktrees"
        (wt_root / "nebulus-core" / "abc12345").mkdir(parents=True)
        (wt_root / "nebulus-core" / "def67890").mkdir(parents=True)

        mgr = MirrorManager(config)
        with patch("nebulus_swarm.overlord.mirrors.WORKTREE_ROOT", wt_root):
            result = mgr.list_worktrees()

        assert "nebulus-core" in result
        assert len(result["nebulus-core"]) == 2

    def test_empty_state(self, tmp_path: Path, config: OverlordConfig) -> None:
        """Returns empty dict when no worktrees exist."""
        wt_root = tmp_path / "nonexistent_worktrees"
        mgr = MirrorManager(config)

        with patch("nebulus_swarm.overlord.mirrors.WORKTREE_ROOT", wt_root):
            result = mgr.list_worktrees()

        assert result == {}

    def test_filters_by_project_name(
        self, tmp_path: Path, config: OverlordConfig
    ) -> None:
        """Filters results when project name is specified."""
        wt_root = tmp_path / "worktrees"
        (wt_root / "nebulus-core" / "abc12345").mkdir(parents=True)
        (wt_root / "nebulus-prime" / "xyz99999").mkdir(parents=True)

        mgr = MirrorManager(config)
        with patch("nebulus_swarm.overlord.mirrors.WORKTREE_ROOT", wt_root):
            result = mgr.list_worktrees(project="nebulus-core")

        assert "nebulus-core" in result
        assert "nebulus-prime" not in result
