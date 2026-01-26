from mini_nebulus.services.tool_executor import ToolExecutor


def pin_file(path: str) -> str:
    """Pins a file to the active context."""
    # We access the manager from ToolExecutor to stay session-aware if needed
    # but for simplicity in skills, we can use the ToolExecutor singleton instance
    service = ToolExecutor.context_manager.get_service("default")
    return service.pin_file(path)


def unpin_file(path: str) -> str:
    """Unpins a file from the active context."""
    service = ToolExecutor.context_manager.get_service("default")
    return service.unpin_file(path)


def list_context() -> str:
    """Lists currently pinned files."""
    service = ToolExecutor.context_manager.get_service("default")
    return str(service.list_context())
