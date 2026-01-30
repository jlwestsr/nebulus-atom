import os
import docker
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class DockerService:
    def __init__(self):
        self.enabled = os.getenv("SANDBOX_MODE", "false").lower() == "true"
        self.client = None
        self.container_name = "nebulus-atom-sandbox"
        self.image_name = "python:3.12-slim"

        if self.enabled:
            try:
                self.client = docker.from_env()
                self._ensure_container_running()
            except Exception as e:
                logger.error(f"Failed to initialize Docker client: {e}")
                self.enabled = False

    def _ensure_container_running(self):
        if not self.client:
            return

        try:
            container = self.client.containers.get(self.container_name)
            if container.status != "running":
                container.start()
        except docker.errors.NotFound:
            # Create container
            # Mount current directory to /app
            workdir = os.getcwd()
            self.client.containers.run(
                self.image_name,
                command="tail -f /dev/null",  # Keep running
                name=self.container_name,
                volumes={workdir: {"bind": "/app", "mode": "rw"}},
                working_dir="/app",
                detach=True,
                auto_remove=True,
            )
            logger.info(f"Started sandbox container {self.container_name}")

    def execute_command(self, command: str) -> str:
        if not self.enabled or not self.client:
            return "Sandbox disabled or unavailable."

        try:
            container = self.client.containers.get(self.container_name)
            exec_result = container.exec_run(["/bin/sh", "-c", command])
            output = exec_result.output.decode("utf-8").strip()
            return output if output else "(no output)"
        except Exception as e:
            return f"Error executing in sandbox: {e}"


class DockerServiceManager:
    def __init__(self):
        self.service = None

    def get_service(self, session_id: str = "default") -> DockerService:
        if not self.service:
            self.service = DockerService()
        return self.service
