"""Docker container management for Minions."""

import logging
import uuid
from typing import Any, Dict, List, Optional

import docker
from docker.errors import DockerException, ImageNotFound, NotFound

from nebulus_swarm.config import LLMConfig, MinionConfig

logger = logging.getLogger(__name__)

# Label used to identify Minion containers
MINION_LABEL = "nebulus.swarm.minion"


class DockerManager:
    """Manages Minion container lifecycle."""

    def __init__(
        self,
        minion_config: MinionConfig,
        llm_config: LLMConfig,
        github_token: str,
        overlord_callback_url: str = "http://overlord:8080/minion/report",
        stub_mode: bool = False,
    ):
        """Initialize Docker manager.

        Args:
            minion_config: Minion container configuration.
            llm_config: LLM backend configuration.
            github_token: GitHub token for Minion authentication.
            overlord_callback_url: URL for Minion to report back to.
            stub_mode: If True, don't actually spawn containers (for testing).
        """
        self.minion_config = minion_config
        self.llm_config = llm_config
        self.github_token = github_token
        self.overlord_callback_url = overlord_callback_url
        self.stub_mode = stub_mode

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

    def _build_environment(
        self, minion_id: str, repo: str, issue_number: int
    ) -> Dict[str, str]:
        """Build environment variables for a Minion container.

        Args:
            minion_id: Unique minion identifier.
            repo: GitHub repository (owner/name).
            issue_number: Issue number to work on.

        Returns:
            Dictionary of environment variables.
        """
        return {
            "MINION_ID": minion_id,
            "GITHUB_REPO": repo,
            "GITHUB_ISSUE": str(issue_number),
            "GITHUB_TOKEN": self.github_token,
            "OVERLORD_CALLBACK_URL": self.overlord_callback_url,
            "NEBULUS_BASE_URL": self.llm_config.base_url,
            "NEBULUS_MODEL": self.llm_config.model,
            "NEBULUS_TIMEOUT": str(self.llm_config.timeout),
            "NEBULUS_STREAMING": str(self.llm_config.streaming).lower(),
            "MINION_TIMEOUT": str(self.minion_config.timeout_minutes * 60),
        }

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

        Raises:
            DockerException: If container creation fails.
            ImageNotFound: If the Minion image doesn't exist.
        """
        if minion_id is None:
            minion_id = f"minion-{uuid.uuid4().hex[:8]}"

        logger.info(f"Spawning minion {minion_id} for {repo}#{issue_number}")

        # Build environment variables
        env = self._build_environment(minion_id, repo, issue_number)

        if self.stub_mode:
            # Stub mode for testing
            logger.debug(f"[STUB] Would create container with env: {list(env.keys())}")
            self._active_containers[minion_id] = f"stub-container-{minion_id}"
            logger.info(f"[STUB] Minion {minion_id} 'spawned' (stub mode)")
            return minion_id

        # Real container spawning
        try:
            client = self._get_client()

            # Check if image exists
            try:
                client.images.get(self.minion_config.image)
            except ImageNotFound:
                logger.error(f"Minion image not found: {self.minion_config.image}")
                logger.info(
                    "Build the image with: docker build -t nebulus-minion:latest -f nebulus_swarm/minion/Dockerfile ."
                )
                raise

            # Container labels for identification
            labels = {
                MINION_LABEL: "true",
                "nebulus.swarm.minion.id": minion_id,
                "nebulus.swarm.minion.repo": repo,
                "nebulus.swarm.minion.issue": str(issue_number),
            }

            # Create and start the container
            container = client.containers.run(
                image=self.minion_config.image,
                name=minion_id,
                environment=env,
                labels=labels,
                network=self.minion_config.network,
                detach=True,
                auto_remove=False,  # Keep for log retrieval after exit
                mem_limit="2g",  # Memory limit
                cpu_period=100000,
                cpu_quota=100000,  # 1 CPU
            )

            self._active_containers[minion_id] = container.id
            logger.info(f"Minion {minion_id} spawned (container: {container.short_id})")

            return minion_id

        except DockerException as e:
            logger.error(f"Failed to spawn minion {minion_id}: {e}")
            raise

    def kill_minion(self, minion_id: str, remove: bool = True) -> bool:
        """Kill a Minion container.

        Args:
            minion_id: The minion ID to kill.
            remove: Whether to remove the container after killing.

        Returns:
            True if killed successfully, False otherwise.
        """
        logger.info(f"Killing minion {minion_id}")

        if minion_id not in self._active_containers:
            logger.warning(f"Minion {minion_id} not found in active containers")
            return False

        if self.stub_mode:
            del self._active_containers[minion_id]
            logger.info(f"[STUB] Minion {minion_id} 'killed' (stub mode)")
            return True

        try:
            container_id = self._active_containers[minion_id]
            client = self._get_client()
            container = client.containers.get(container_id)

            # Kill if running
            if container.status == "running":
                container.kill()
                logger.debug(f"Container {container.short_id} killed")

            # Remove container
            if remove:
                container.remove(force=True)
                logger.debug(f"Container {container.short_id} removed")

            del self._active_containers[minion_id]
            logger.info(f"Minion {minion_id} killed and removed")
            return True

        except NotFound:
            # Container already gone
            logger.warning(
                f"Container for minion {minion_id} not found (already removed?)"
            )
            if minion_id in self._active_containers:
                del self._active_containers[minion_id]
            return True

        except DockerException as e:
            logger.error(f"Failed to kill minion {minion_id}: {e}")
            return False

    def list_minions(self) -> List[Dict[str, Any]]:
        """List all active Minion containers.

        Returns:
            List of minion info dictionaries.
        """
        if self.stub_mode:
            return [
                {"minion_id": mid, "container_id": cid, "status": "running"}
                for mid, cid in self._active_containers.items()
            ]

        try:
            client = self._get_client()
            containers = client.containers.list(
                all=True,
                filters={"label": MINION_LABEL},
            )

            minions = []
            for container in containers:
                minion_id = container.labels.get(
                    "nebulus.swarm.minion.id", container.name
                )
                minions.append(
                    {
                        "minion_id": minion_id,
                        "container_id": container.id,
                        "short_id": container.short_id,
                        "status": container.status,
                        "repo": container.labels.get("nebulus.swarm.minion.repo", ""),
                        "issue": container.labels.get("nebulus.swarm.minion.issue", ""),
                    }
                )

            return minions

        except DockerException as e:
            logger.error(f"Failed to list minions: {e}")
            return []

    def get_minion_status(self, minion_id: str) -> Optional[str]:
        """Get the status of a Minion container.

        Args:
            minion_id: The minion ID.

        Returns:
            Container status or None if not found.
        """
        if self.stub_mode:
            if minion_id in self._active_containers:
                return "running"
            return None

        if minion_id not in self._active_containers:
            return None

        try:
            container_id = self._active_containers[minion_id]
            container = self._get_client().containers.get(container_id)
            return container.status
        except NotFound:
            return None
        except DockerException:
            return None

    def get_minion_logs(self, minion_id: str, tail: int = 100) -> Optional[str]:
        """Get logs from a Minion container.

        Args:
            minion_id: The minion ID.
            tail: Number of lines to return.

        Returns:
            Log output or None if minion not found.
        """
        if minion_id not in self._active_containers:
            return None

        if self.stub_mode:
            return f"[STUB] No real logs - minion {minion_id} is in stub mode"

        try:
            container_id = self._active_containers[minion_id]
            container = self._get_client().containers.get(container_id)
            logs = container.logs(tail=tail, timestamps=True)
            return logs.decode("utf-8")
        except NotFound:
            return None
        except DockerException as e:
            logger.error(f"Failed to get logs for minion {minion_id}: {e}")
            return None

    def cleanup_dead_containers(self) -> int:
        """Clean up any dead or exited Minion containers.

        Returns:
            Number of containers cleaned up.
        """
        if self.stub_mode:
            return 0

        try:
            client = self._get_client()
            containers = client.containers.list(
                all=True,
                filters={
                    "status": "exited",
                    "label": MINION_LABEL,
                },
            )

            cleaned = 0
            for container in containers:
                minion_id = container.labels.get(
                    "nebulus.swarm.minion.id", container.name
                )
                logger.info(f"Cleaning up dead minion container: {minion_id}")

                try:
                    container.remove(force=True)
                    cleaned += 1

                    # Remove from tracking
                    if minion_id in self._active_containers:
                        del self._active_containers[minion_id]

                except DockerException as e:
                    logger.warning(
                        f"Failed to remove container {container.short_id}: {e}"
                    )

            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} dead minion containers")

            return cleaned

        except DockerException as e:
            logger.error(f"Failed to cleanup dead containers: {e}")
            return 0

    def sync_active_containers(self) -> None:
        """Sync internal tracking with actual Docker containers.

        This is useful after Overlord restart to recover state.
        """
        if self.stub_mode:
            return

        try:
            client = self._get_client()
            containers = client.containers.list(
                filters={"label": MINION_LABEL},
            )

            # Reset tracking
            self._active_containers.clear()

            for container in containers:
                minion_id = container.labels.get(
                    "nebulus.swarm.minion.id", container.name
                )
                self._active_containers[minion_id] = container.id
                logger.debug(f"Synced minion {minion_id} -> {container.short_id}")

            logger.info(
                f"Synced {len(self._active_containers)} active minion containers"
            )

        except DockerException as e:
            logger.error(f"Failed to sync containers: {e}")

    def is_available(self) -> bool:
        """Check if Docker is available and connected.

        Returns:
            True if Docker is available.
        """
        if self.stub_mode:
            return True

        try:
            self._get_client().ping()
            return True
        except Exception as e:
            logger.error(f"Docker not available: {e}")
            return False

    def ensure_network(self) -> bool:
        """Ensure the Minion network exists.

        Returns:
            True if network exists or was created.
        """
        if self.stub_mode:
            return True

        network_name = self.minion_config.network

        try:
            client = self._get_client()

            # Check if network exists
            networks = client.networks.list(names=[network_name])
            if networks:
                logger.debug(f"Network {network_name} already exists")
                return True

            # Create network
            client.networks.create(
                name=network_name,
                driver="bridge",
                labels={MINION_LABEL: "network"},
            )
            logger.info(f"Created network: {network_name}")
            return True

        except DockerException as e:
            logger.error(f"Failed to ensure network {network_name}: {e}")
            return False
