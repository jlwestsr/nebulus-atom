"""Docker container management for Minions."""

import logging
import uuid
from typing import Dict, List, Optional

import docker
from docker.errors import DockerException

from nebulus_swarm.config import MinionConfig, LLMConfig

logger = logging.getLogger(__name__)


class DockerManager:
    """Manages Minion container lifecycle."""

    def __init__(
        self,
        minion_config: MinionConfig,
        llm_config: LLMConfig,
        github_token: str,
        overlord_callback_url: str = "http://overlord:8080/minion/report",
    ):
        """Initialize Docker manager.

        Args:
            minion_config: Minion container configuration.
            llm_config: LLM backend configuration.
            github_token: GitHub token for Minion authentication.
            overlord_callback_url: URL for Minion to report back to.
        """
        self.minion_config = minion_config
        self.llm_config = llm_config
        self.github_token = github_token
        self.overlord_callback_url = overlord_callback_url

        self._client: Optional[docker.DockerClient] = None
        self._active_containers: Dict[str, str] = {}  # minion_id -> container_id

    def _get_client(self) -> docker.DockerClient:
        """Get or create Docker client."""
        if self._client is None:
            try:
                self._client = docker.from_env()
                # Test connection
                self._client.ping()
                logger.info("Docker client connected")
            except DockerException as e:
                logger.error(f"Failed to connect to Docker: {e}")
                raise
        return self._client

    def spawn_minion(
        self,
        repo: str,
        issue_number: int,
        minion_id: Optional[str] = None,
    ) -> str:
        """Spawn a new Minion container.

        Args:
            repo: GitHub repository (owner/name).
            issue_number: Issue number to work on.
            minion_id: Optional custom minion ID.

        Returns:
            The minion ID.

        Note:
            This is currently a STUB implementation.
            Real container spawning will be implemented in Phase 2.
        """
        if minion_id is None:
            minion_id = f"minion-{uuid.uuid4().hex[:8]}"

        logger.info(f"[STUB] Spawning minion {minion_id} for {repo}#{issue_number}")

        # Build environment variables for the Minion
        env = {
            "MINION_ID": minion_id,
            "GITHUB_REPO": repo,
            "GITHUB_ISSUE": str(issue_number),
            "GITHUB_TOKEN": self.github_token,
            "OVERLORD_CALLBACK_URL": self.overlord_callback_url,
            "NEBULUS_BASE_URL": self.llm_config.base_url,
            "NEBULUS_MODEL": self.llm_config.model,
            "NEBULUS_TIMEOUT": str(self.llm_config.timeout),
            "NEBULUS_STREAMING": str(self.llm_config.streaming).lower(),
        }

        logger.debug(f"[STUB] Would create container with env: {list(env.keys())}")

        # STUB: In Phase 2, this will actually create the container:
        # container = self._get_client().containers.run(
        #     image=self.minion_config.image,
        #     environment=env,
        #     network=self.minion_config.network,
        #     detach=True,
        #     name=minion_id,
        # )
        # self._active_containers[minion_id] = container.id

        # For now, just track the "fake" minion
        self._active_containers[minion_id] = f"stub-container-{minion_id}"

        logger.info(f"[STUB] Minion {minion_id} 'spawned' (stub mode)")
        return minion_id

    def kill_minion(self, minion_id: str) -> bool:
        """Kill a Minion container.

        Args:
            minion_id: The minion ID to kill.

        Returns:
            True if killed successfully, False otherwise.
        """
        logger.info(f"[STUB] Killing minion {minion_id}")

        if minion_id not in self._active_containers:
            logger.warning(f"Minion {minion_id} not found in active containers")
            return False

        # STUB: In Phase 2, this will actually kill the container:
        # try:
        #     container_id = self._active_containers[minion_id]
        #     container = self._get_client().containers.get(container_id)
        #     container.kill()
        #     container.remove()
        # except NotFound:
        #     pass

        del self._active_containers[minion_id]
        logger.info(f"[STUB] Minion {minion_id} 'killed' (stub mode)")
        return True

    def list_minions(self) -> List[Dict[str, str]]:
        """List all active Minion containers.

        Returns:
            List of minion info dictionaries.
        """
        logger.debug("[STUB] Listing active minions")

        # STUB: In Phase 2, this will query actual containers:
        # containers = self._get_client().containers.list(
        #     filters={"label": "nebulus.swarm.minion"}
        # )

        return [
            {"minion_id": mid, "container_id": cid}
            for mid, cid in self._active_containers.items()
        ]

    def get_minion_logs(self, minion_id: str, tail: int = 100) -> Optional[str]:
        """Get logs from a Minion container.

        Args:
            minion_id: The minion ID.
            tail: Number of lines to return.

        Returns:
            Log output or None if minion not found.
        """
        logger.debug(f"[STUB] Getting logs for minion {minion_id}")

        if minion_id not in self._active_containers:
            return None

        # STUB: In Phase 2, this will get actual logs:
        # container_id = self._active_containers[minion_id]
        # container = self._get_client().containers.get(container_id)
        # return container.logs(tail=tail).decode("utf-8")

        return f"[STUB] No real logs - minion {minion_id} is in stub mode"

    def cleanup_dead_containers(self) -> int:
        """Clean up any dead or exited Minion containers.

        Returns:
            Number of containers cleaned up.
        """
        logger.debug("[STUB] Cleaning up dead containers")

        # STUB: In Phase 2, this will clean up actual containers:
        # cleaned = 0
        # for container in self._get_client().containers.list(
        #     all=True, filters={"status": "exited", "label": "nebulus.swarm.minion"}
        # ):
        #     container.remove()
        #     cleaned += 1
        # return cleaned

        return 0

    def is_available(self) -> bool:
        """Check if Docker is available and connected.

        Returns:
            True if Docker is available.
        """
        try:
            self._get_client().ping()
            return True
        except Exception as e:
            logger.error(f"Docker not available: {e}")
            return False
