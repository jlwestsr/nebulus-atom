import pytest
import sys
import os
from unittest.mock import patch

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))


def test_dependencies_installed():
    """Verify that UI dependencies are importable."""
    try:
        import importlib.util

        for module in ["textual", "streamlit", "pandas"]:
            if importlib.util.find_spec(module) is None:
                raise ImportError(f"Missing dependency: {module}")
    except ImportError as e:
        pytest.fail(f"Missing dependency: {e}")


def test_tui_view_initialization():
    """Verify TextualView can be instantiated."""
    # We might need to mock Textual's App init if it does heavy lifting
    with patch("textual.app.App.__init__", return_value=None):
        from nebulus_atom.views.tui_view import TextualView

        view = TextualView()
        assert hasattr(view, "compose")
        assert hasattr(view, "set_controller")


def test_dashboard_file_exists():
    """Verify dashboard.py exists."""
    dashboard_path = os.path.join(
        os.path.dirname(__file__), "../../nebulus_atom/ui/dashboard.py"
    )
    assert os.path.exists(dashboard_path), "dashboard.py not found"


def test_dashboard_command_import():
    """Verify main.py has the dashboard command."""
    # access local commands via internal storage or just check it imports
    import nebulus_atom.main as main_module

    assert hasattr(main_module, "dashboard")
