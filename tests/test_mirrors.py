"""Tests for the MirrorManager module."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch


from nebulus_swarm.overlord.mirrors import MirrorManager
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig


def _make_config(tmp_path: Path) -> OverlordConfig:
    """Create a minimal OverlordConfig with two projects."""
    d1 = tmp_path / "core"
    d1.mkdir()
    d2 = tmp_path / "prime"
    d2.mkdir()
    return OverlordConfig(
        projects={
            "nebulus-core": ProjectConfig(
                name="nebulus-core",
                path=d1,
                remote="jlwestsr/nebulus-core",
                role="shared-library",
            ),
            "nebulus-prime": ProjectConfig(
                name="nebulus-prime",
                path=d2,
                remote="jlwestsr/nebulus-prime",
                role="platform-deployment",
            ),
        }
    )


# --- Remote URL ---


class TestRemoteUrl:
    """Tests for remote URL generation."""

    def test_builds_ssh_url(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mgr = MirrorManager(config, mirror_root=tmp_path / "mirrors")
        url = mgr._remote_url("jlwestsr/nebulus-core")
        assert url == "git@github.com:jlwestsr/nebulus-core.git"


# --- Mirror path ---


class TestMirrorPath:
    """Tests for mirror path calculation."""

    def test_mirror_path(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mgr = MirrorManager(config, mirror_root=tmp_path / "mirrors")
        path = mgr._mirror_path("nebulus-core")
        assert path == tmp_path / "mirrors" / "nebulus-core.git"


# --- init_project ---


class TestInitProject:
    """Tests for init_project."""

    @patch("subprocess.run")
    def test_clones_new_mirror(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        config = _make_config(tmp_path)
        mgr = MirrorManager(config, mirror_root=tmp_path / "mirrors")

        result = mgr.init_project("nebulus-core")
        assert result is True
        mock_run.assert_called_once()

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "git"
        assert "clone" in cmd
        assert "--bare" in cmd
        assert "git@github.com:jlwestsr/nebulus-core.git" in cmd

    def test_skips_existing_mirror(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mirror_root = tmp_path / "mirrors"
        mirror_path = mirror_root / "nebulus-core.git"
        mirror_path.mkdir(parents=True)

        mgr = MirrorManager(config, mirror_root=mirror_root)
        result = mgr.init_project("nebulus-core")
        assert result is True

    def test_unknown_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mgr = MirrorManager(config, mirror_root=tmp_path / "mirrors")
        result = mgr.init_project("nonexistent")
        assert result is False

    @patch("subprocess.run")
    def test_clone_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(
            128, "git", stderr="fatal: remote not found"
        )
        config = _make_config(tmp_path)
        mgr = MirrorManager(config, mirror_root=tmp_path / "mirrors")
        result = mgr.init_project("nebulus-core")
        assert result is False

    @patch("subprocess.run")
    def test_clone_timeout(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=120)
        config = _make_config(tmp_path)
        mgr = MirrorManager(config, mirror_root=tmp_path / "mirrors")
        result = mgr.init_project("nebulus-core")
        assert result is False


# --- init_all ---


class TestInitAll:
    """Tests for init_all."""

    @patch("subprocess.run")
    def test_inits_all_projects(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        config = _make_config(tmp_path)
        mgr = MirrorManager(config, mirror_root=tmp_path / "mirrors")

        results = mgr.init_all()
        assert len(results) == 2
        assert results["nebulus-core"] is True
        assert results["nebulus-prime"] is True


# --- sync_project ---


class TestSyncProject:
    """Tests for sync_project."""

    @patch("subprocess.run")
    def test_fetches_existing_mirror(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        config = _make_config(tmp_path)
        mirror_root = tmp_path / "mirrors"
        (mirror_root / "nebulus-core.git").mkdir(parents=True)

        mgr = MirrorManager(config, mirror_root=mirror_root)
        result = mgr.sync_project("nebulus-core")
        assert result is True

        cmd = mock_run.call_args[0][0]
        assert "fetch" in cmd
        assert "--all" in cmd
        assert "--prune" in cmd

    def test_sync_missing_mirror(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mgr = MirrorManager(config, mirror_root=tmp_path / "mirrors")
        result = mgr.sync_project("nebulus-core")
        assert result is False

    @patch("subprocess.run")
    def test_sync_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "git", stderr="error: fetch failed"
        )
        config = _make_config(tmp_path)
        mirror_root = tmp_path / "mirrors"
        (mirror_root / "nebulus-core.git").mkdir(parents=True)

        mgr = MirrorManager(config, mirror_root=mirror_root)
        result = mgr.sync_project("nebulus-core")
        assert result is False


# --- sync_all ---


class TestSyncAll:
    """Tests for sync_all."""

    @patch("subprocess.run")
    def test_syncs_all_existing(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        config = _make_config(tmp_path)
        mirror_root = tmp_path / "mirrors"
        (mirror_root / "nebulus-core.git").mkdir(parents=True)
        (mirror_root / "nebulus-prime.git").mkdir(parents=True)

        mgr = MirrorManager(config, mirror_root=mirror_root)
        results = mgr.sync_all()
        assert results["nebulus-core"] is True
        assert results["nebulus-prime"] is True


# --- status ---


class TestMirrorStatus:
    """Tests for status."""

    def test_no_mirrors_exist(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mgr = MirrorManager(config, mirror_root=tmp_path / "mirrors")
        states = mgr.status()

        assert len(states) == 2
        assert states["nebulus-core"].exists is False
        assert states["nebulus-prime"].exists is False

    @patch("subprocess.run")
    def test_existing_mirror_with_refs(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc123 HEAD\ndef456 refs/heads/main\nghi789 refs/heads/develop\n",
        )
        config = _make_config(tmp_path)
        mirror_root = tmp_path / "mirrors"
        mirror_path = mirror_root / "nebulus-core.git"
        mirror_path.mkdir(parents=True)

        mgr = MirrorManager(config, mirror_root=mirror_root)
        states = mgr.status()

        assert states["nebulus-core"].exists is True
        assert states["nebulus-core"].ref_count == 3

    @patch("subprocess.run")
    def test_status_with_fetch_head(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="abc HEAD\n")
        config = _make_config(tmp_path)
        mirror_root = tmp_path / "mirrors"
        mirror_path = mirror_root / "nebulus-core.git"
        mirror_path.mkdir(parents=True)
        fetch_head = mirror_path / "FETCH_HEAD"
        fetch_head.write_text("dummy")

        mgr = MirrorManager(config, mirror_root=mirror_root)
        states = mgr.status()

        assert states["nebulus-core"].exists is True
        assert states["nebulus-core"].last_fetch is not None
        assert isinstance(states["nebulus-core"].last_fetch, datetime)
