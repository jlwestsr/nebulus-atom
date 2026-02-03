import pytest
from unittest.mock import MagicMock, patch
from nebulus_atom.services.image_service import ImageService
from nebulus_atom.services.tool_executor import ToolExecutor


def test_encode_image_file_not_found():
    service = ImageService()
    with pytest.raises(FileNotFoundError):
        service.encode_image("nonexistent.png")


@pytest.mark.asyncio
async def test_tool_executor_scan_image():
    # Mock ImageService
    mock_service = MagicMock()
    mock_service.encode_image.return_value = "data:image/png;base64,mock"

    # Mock telemetry service to avoid database issues
    mock_telemetry = MagicMock()
    mock_telemetry.log_tool_call = MagicMock()

    with (
        patch.object(ToolExecutor, "image_manager") as mock_image_manager,
        patch.object(ToolExecutor, "telemetry_manager") as mock_telemetry_manager,
    ):
        mock_image_manager.get_service.return_value = mock_service
        mock_telemetry_manager.get_service.return_value = mock_telemetry

        result = await ToolExecutor.dispatch("scan_image", {"path": "test.png"})
        assert result == "data:image/png;base64,mock"
        mock_service.encode_image.assert_called_with("test.png")
