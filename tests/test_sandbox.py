import pytest
from unittest.mock import MagicMock, patch
import os
from mini_nebulus.services.docker_service import DockerService


@pytest.fixture
def mock_docker():
    with patch("mini_nebulus.services.docker_service.docker") as mock:
        mock_client = MagicMock()
        mock.from_env.return_value = mock_client
        yield mock


def test_sandbox_disabled_by_default(mock_docker):
    # Ensure env var is false
    with patch.dict(os.environ, {"SANDBOX_MODE": "false"}):
        service = DockerService()
        assert not service.enabled
        assert service.execute_command("ls") == "Sandbox disabled or unavailable."


def test_sandbox_enabled(mock_docker):
    with patch.dict(os.environ, {"SANDBOX_MODE": "true"}):
        service = DockerService()
        assert service.enabled
        assert service.client is not None
        mock_docker.from_env.assert_called_once()


def test_execute_command(mock_docker):
    with patch.dict(os.environ, {"SANDBOX_MODE": "true"}):
        service = DockerService()

        # Mock container
        mock_container = MagicMock()
        service.client.containers.get.return_value = mock_container

        # Mock exec_run
        mock_exec = MagicMock()
        mock_exec.output = b"hello from docker"
        mock_container.exec_run.return_value = mock_exec

        output = service.execute_command("echo hello")

        assert output == "hello from docker"
        mock_container.exec_run.assert_called_with(["/bin/sh", "-c", "echo hello"])
