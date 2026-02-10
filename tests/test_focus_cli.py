"""Tests for the Focus CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from nebulus_atom.commands.focus_commands import focus_app
from nebulus_swarm.overlord.focus import FocusContext

runner = CliRunner()


def _mock_config():
    config = MagicMock()
    config.workspace_root = Path("/tmp/test-workspace")
    config.workers = {}
    return config


def _mock_context():
    return FocusContext(
        business_priorities=[
            {"name": "Security", "priority": "high", "description": "Harden APIs"}
        ],
        governance_rules=["No push to main"],
        workspace_root=Path("/tmp/test-workspace"),
    )


@patch("nebulus_swarm.overlord.registry.load_config")
@patch("nebulus_swarm.overlord.focus.build_focus_context")
def test_focus_show(mock_build, mock_config):
    """focus show should display parsed context."""
    mock_config.return_value = _mock_config()
    mock_build.return_value = _mock_context()

    result = runner.invoke(focus_app, ["show"])

    assert result.exit_code == 0
    assert "Security" in result.output or "Business" in result.output


@patch("nebulus_swarm.overlord.registry.load_config")
@patch("nebulus_swarm.overlord.focus.build_focus_context")
@patch("nebulus_swarm.overlord.workers.load_all_workers")
def test_focus_query_no_workers(mock_workers, mock_build, mock_config):
    """focus query with no workers should exit with error."""
    mock_config.return_value = _mock_config()
    mock_build.return_value = _mock_context()
    mock_workers.return_value = {}

    result = runner.invoke(focus_app, ["query", "What is next?"])

    assert result.exit_code == 1
    assert "No workers" in result.output


@patch("nebulus_swarm.overlord.registry.load_config")
@patch("nebulus_swarm.overlord.focus.build_focus_context")
@patch("nebulus_swarm.overlord.workers.load_all_workers")
def test_focus_query_success(mock_workers, mock_build, mock_config):
    """focus query should execute and display results."""
    mock_config.return_value = _mock_config()
    mock_build.return_value = _mock_context()

    worker = MagicMock()
    worker.available = True
    worker.execute.return_value = MagicMock(
        success=True, output="The next priority is security hardening."
    )
    mock_workers.return_value = {"claude": worker}

    result = runner.invoke(focus_app, ["query", "What is next?"])

    assert result.exit_code == 0
    worker.execute.assert_called_once()
    call_args = worker.execute.call_args
    # Check prompt contains the query (could be in args or kwargs)
    prompt = call_args.kwargs.get("prompt", "")
    assert "What is next?" in prompt


@patch("nebulus_swarm.overlord.registry.load_config")
@patch("nebulus_swarm.overlord.focus.build_focus_context")
@patch("nebulus_swarm.overlord.workers.load_all_workers")
def test_focus_query_pm_role(mock_workers, mock_build, mock_config):
    """focus query with pm role should include PM system prompt."""
    mock_config.return_value = _mock_config()
    mock_build.return_value = _mock_context()

    worker = MagicMock()
    worker.available = True
    worker.execute.return_value = MagicMock(success=True, output="PM response")
    mock_workers.return_value = {"claude": worker}

    result = runner.invoke(focus_app, ["query", "--role", "pm", "Plan next sprint"])

    assert result.exit_code == 0
    call_args = worker.execute.call_args
    prompt = call_args.kwargs.get("prompt", "")
    assert "Project Manager" in prompt


@patch("nebulus_swarm.overlord.registry.load_config")
@patch("nebulus_swarm.overlord.focus.build_focus_context")
@patch("nebulus_swarm.overlord.workers.load_all_workers")
def test_focus_query_explicit_worker(mock_workers, mock_build, mock_config):
    """focus query with --worker should use specified worker."""
    mock_config.return_value = _mock_config()
    mock_build.return_value = _mock_context()

    worker = MagicMock()
    worker.available = True
    worker.execute.return_value = MagicMock(success=True, output="Local response")
    mock_workers.return_value = {"local": worker, "claude": MagicMock()}

    result = runner.invoke(focus_app, ["query", "--worker", "local", "Quick question"])

    assert result.exit_code == 0
    worker.execute.assert_called_once()


@patch("nebulus_swarm.overlord.registry.load_config")
@patch("nebulus_swarm.overlord.focus.build_focus_context")
@patch("nebulus_swarm.overlord.workers.load_all_workers")
def test_focus_query_unknown_worker(mock_workers, mock_build, mock_config):
    """focus query with unknown worker should exit with error."""
    mock_config.return_value = _mock_config()
    mock_build.return_value = _mock_context()
    mock_workers.return_value = {"claude": MagicMock()}

    result = runner.invoke(focus_app, ["query", "--worker", "nonexistent", "Question"])

    assert result.exit_code == 1
    assert "Unknown worker" in result.output
