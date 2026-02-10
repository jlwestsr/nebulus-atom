"""Git mirror manager — maintains bare clones of ecosystem repos.

Provides init, sync, and status operations for local bare-clone
mirrors used by the Overlord for safe read-only repository access.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nebulus_swarm.overlord.registry import OverlordConfig

logger = logging.getLogger(__name__)

DEFAULT_MIRROR_ROOT = Path.home() / ".nebulus" / "mirrors"


@dataclass
class MirrorState:
    """Status of a single project mirror."""

    exists: bool
    last_fetch: Optional[datetime] = None
    ref_count: int = 0


class MirrorManager:
    """Manages bare-clone mirrors of ecosystem project repositories.

    Args:
        config: Overlord configuration with project registry.
        mirror_root: Root directory for bare clones.
    """

    def __init__(
        self,
        config: OverlordConfig,
        mirror_root: Optional[Path] = None,
    ) -> None:
        self.config = config
        self.mirror_root = mirror_root or DEFAULT_MIRROR_ROOT

    def _mirror_path(self, name: str) -> Path:
        """Get the mirror directory path for a project.

        Args:
            name: Project name.

        Returns:
            Path to the bare clone directory.
        """
        return self.mirror_root / f"{name}.git"

    def _remote_url(self, remote: str) -> str:
        """Build a git remote URL from the project's remote field.

        Args:
            remote: Remote identifier (e.g. ``jlwestsr/nebulus-core``).

        Returns:
            Full git SSH URL.
        """
        return f"git@github.com:{remote}.git"

    def init_project(self, name: str) -> bool:
        """Initialize a bare-clone mirror for a single project.

        Skips if the mirror already exists.

        Args:
            name: Project name from the registry.

        Returns:
            True if clone was created or already exists, False on error.
        """
        project = self.config.projects.get(name)
        if not project:
            logger.error(f"Unknown project: {name}")
            return False

        mirror_path = self._mirror_path(name)
        if mirror_path.exists():
            logger.info(f"Mirror already exists: {mirror_path}")
            return True

        self.mirror_root.mkdir(parents=True, exist_ok=True)
        remote_url = self._remote_url(project.remote)

        try:
            subprocess.run(
                ["git", "clone", "--bare", remote_url, str(mirror_path)],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
            logger.info(f"Cloned mirror: {name} -> {mirror_path}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone {name}: {e.stderr.strip()}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Clone timed out for {name}")
            return False

    def init_all(self) -> dict[str, bool]:
        """Initialize bare-clone mirrors for all registered projects.

        Returns:
            Dict mapping project name to success boolean.
        """
        results: dict[str, bool] = {}
        for name in self.config.projects:
            results[name] = self.init_project(name)
        return results

    def sync_project(self, name: str) -> bool:
        """Fetch updates for a single project mirror.

        Args:
            name: Project name from the registry.

        Returns:
            True if fetch succeeded, False on error.
        """
        mirror_path = self._mirror_path(name)
        if not mirror_path.exists():
            logger.error(f"Mirror not found: {mirror_path}. Run init first.")
            return False

        try:
            subprocess.run(
                ["git", "fetch", "--all", "--prune"],
                cwd=str(mirror_path),
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
            logger.info(f"Synced mirror: {name}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to sync {name}: {e.stderr.strip()}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Sync timed out for {name}")
            return False

    def sync_all(self) -> dict[str, bool]:
        """Fetch updates for all project mirrors.

        Returns:
            Dict mapping project name to success boolean.
        """
        results: dict[str, bool] = {}
        for name in self.config.projects:
            results[name] = self.sync_project(name)
        return results

    def status(self) -> dict[str, MirrorState]:
        """Get the state of all project mirrors.

        Returns:
            Dict mapping project name to MirrorState.
        """
        states: dict[str, MirrorState] = {}
        for name in self.config.projects:
            mirror_path = self._mirror_path(name)
            if not mirror_path.exists():
                states[name] = MirrorState(exists=False)
                continue

            last_fetch = self._get_last_fetch(mirror_path)
            ref_count = self._count_refs(mirror_path)
            states[name] = MirrorState(
                exists=True,
                last_fetch=last_fetch,
                ref_count=ref_count,
            )
        return states

    @staticmethod
    def _get_last_fetch(mirror_path: Path) -> Optional[datetime]:
        """Get the timestamp of the last fetch for a mirror.

        Args:
            mirror_path: Path to the bare clone.

        Returns:
            Datetime of last fetch, or None if unknown.
        """
        fetch_head = mirror_path / "FETCH_HEAD"
        if fetch_head.exists():
            mtime = fetch_head.stat().st_mtime
            return datetime.fromtimestamp(mtime, tz=timezone.utc)
        return None

    @staticmethod
    def _count_refs(mirror_path: Path) -> int:
        """Count the number of refs in a bare clone.

        Args:
            mirror_path: Path to the bare clone.

        Returns:
            Number of refs.
        """
        try:
            result = subprocess.run(
                ["git", "show-ref", "--head"],
                cwd=str(mirror_path),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return len(result.stdout.strip().splitlines())
        except (subprocess.TimeoutExpired, OSError):
            pass
        return 0
