import pytest
from mini_nebulus.views.tui_view import TUIView


@pytest.mark.asyncio
async def test_tui_instantiation():
    view = TUIView()
    assert view.app is not None
    assert view.controller is None
