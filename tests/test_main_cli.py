"""Tests for the CLI entry points in nebulus_atom/main.py."""

from unittest.mock import patch, MagicMock, AsyncMock
from typer.testing import CliRunner

from nebulus_atom.main import app

runner = CliRunner()


class TestStartCommand:
    """Tests for the 'start' CLI command."""

    @patch("nebulus_atom.main._start_agent")
    def test_start_without_prompt(self, mock_start):
        result = runner.invoke(app, ["start"])
        assert result.exit_code == 0
        mock_start.assert_called_once_with(None, "default")

    @patch("nebulus_atom.main._start_agent")
    def test_start_with_prompt(self, mock_start):
        result = runner.invoke(app, ["start", "fix", "the", "login", "bug"])
        assert result.exit_code == 0
        mock_start.assert_called_once_with(["fix", "the", "login", "bug"], "default")

    @patch("nebulus_atom.main._start_agent")
    def test_start_with_session_id(self, mock_start):
        result = runner.invoke(app, ["start", "--session-id", "my-session"])
        assert result.exit_code == 0
        mock_start.assert_called_once_with(None, "my-session")

    @patch("nebulus_atom.main._start_agent")
    def test_start_with_prompt_and_session(self, mock_start):
        result = runner.invoke(app, ["start", "hello", "--session-id", "test-session"])
        assert result.exit_code == 0
        mock_start.assert_called_once_with(["hello"], "test-session")


class TestStartAgentFunction:
    """Tests for the _start_agent internal function."""

    @patch("nebulus_atom.main.asyncio")
    @patch("nebulus_atom.main.AgentController", create=True)
    @patch("nebulus_atom.main.CLIView", create=True)
    def test_start_agent_joins_prompt(self, mock_view_cls, mock_ctrl_cls, mock_asyncio):
        # Import after patching to handle lazy imports
        with (
            patch("nebulus_atom.views.cli_view.CLIView") as view_cls,
            patch(
                "nebulus_atom.controllers.agent_controller.AgentController"
            ) as ctrl_cls,
        ):
            mock_view = MagicMock()
            view_cls.return_value = mock_view
            mock_ctrl = MagicMock()
            ctrl_cls.return_value = mock_ctrl
            mock_ctrl.start = AsyncMock()

            from nebulus_atom.main import _start_agent

            _start_agent(["fix", "the", "bug"], "default")

            mock_asyncio.run.assert_called_once()

    @patch("nebulus_atom.main.asyncio")
    def test_start_agent_none_prompt(self, mock_asyncio):
        with (
            patch("nebulus_atom.views.cli_view.CLIView"),
            patch("nebulus_atom.controllers.agent_controller.AgentController"),
        ):
            from nebulus_atom.main import _start_agent

            _start_agent(None, "default")

            mock_asyncio.run.assert_called_once()

    @patch("nebulus_atom.main.asyncio")
    def test_start_agent_keyboard_interrupt(self, mock_asyncio):
        mock_asyncio.run.side_effect = KeyboardInterrupt()

        with (
            patch("nebulus_atom.views.cli_view.CLIView"),
            patch("nebulus_atom.controllers.agent_controller.AgentController"),
        ):
            from nebulus_atom.main import _start_agent

            # Should not raise
            _start_agent(None, "default")


class TestDocsCommand:
    """Tests for the 'docs' CLI command."""

    @patch("nebulus_atom.main.DocService")
    def test_docs_list_shows_files(self, mock_svc_cls):
        mock_svc = MagicMock()
        mock_svc.list_docs.return_value = ["README.md", "ARCHITECTURE.md"]
        mock_svc_cls.return_value = mock_svc

        result = runner.invoke(app, ["docs", "list"])
        assert result.exit_code == 0
        assert "README.md" in result.output
        assert "ARCHITECTURE.md" in result.output

    @patch("nebulus_atom.main.DocService")
    def test_docs_list_empty(self, mock_svc_cls):
        mock_svc = MagicMock()
        mock_svc.list_docs.return_value = []
        mock_svc_cls.return_value = mock_svc

        result = runner.invoke(app, ["docs", "list"])
        assert result.exit_code == 0
        assert "No documentation files found" in result.output

    @patch("nebulus_atom.main.DocService")
    def test_docs_read_valid_file(self, mock_svc_cls):
        mock_svc = MagicMock()
        mock_svc.read_doc.return_value = "# Hello\nThis is a doc."
        mock_svc_cls.return_value = mock_svc

        result = runner.invoke(app, ["docs", "read", "hello.md"])
        assert result.exit_code == 0
        mock_svc.read_doc.assert_called_once_with("hello.md")

    @patch("nebulus_atom.main.DocService")
    def test_docs_read_missing_filename(self, mock_svc_cls):
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc

        result = runner.invoke(app, ["docs", "read"])
        assert result.exit_code == 0
        assert "Filename required" in result.output

    @patch("nebulus_atom.main.DocService")
    def test_docs_read_file_not_found(self, mock_svc_cls):
        mock_svc = MagicMock()
        mock_svc.read_doc.return_value = None
        mock_svc_cls.return_value = mock_svc

        result = runner.invoke(app, ["docs", "read", "nonexistent.md"])
        assert result.exit_code == 0
        assert "Could not read" in result.output

    @patch("nebulus_atom.main.DocService")
    def test_docs_unknown_action(self, mock_svc_cls):
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc

        result = runner.invoke(app, ["docs", "delete"])
        assert result.exit_code == 0
        assert "Unknown action" in result.output


class TestDashboardCommand:
    """Tests for the 'dashboard' CLI command."""

    @patch("nebulus_atom.main.subprocess", create=True)
    @patch("nebulus_atom.main.os.path.exists", return_value=True)
    def test_dashboard_launches_streamlit(self, mock_exists, mock_subprocess):
        # Need to patch inside the function since it imports lazily
        with patch("subprocess.run"):
            result = runner.invoke(app, ["dashboard"])
            assert result.exit_code == 0

    @patch("os.path.exists", return_value=False)
    def test_dashboard_missing_file(self, mock_exists):
        result = runner.invoke(app, ["dashboard"])
        assert result.exit_code == 0
        assert "not found" in result.output


class TestMainCallback:
    """Tests for the main app callback."""

    def test_help_output(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Nebulus Atom" in result.output

    def test_start_help(self):
        result = runner.invoke(app, ["start", "--help"])
        assert result.exit_code == 0
        assert "session-id" in result.output

    def test_docs_help(self):
        result = runner.invoke(app, ["docs", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output or "read" in result.output
