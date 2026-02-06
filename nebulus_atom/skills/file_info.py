import os
from datetime import datetime


def file_info(path: str) -> dict[str, str] | str:
    """
    Retrieve file statistics including size and last modified time.

    Args:
        path (str): The file path to inspect.

    Returns:
        dict[str, str]: A dictionary with 'file_size' and 'last_modified' keys,
                        or error message string if file cannot be accessed.
    """
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"

        file_stat = os.stat(path)
        return {
            "file_size": f"{file_stat.st_size} bytes",
            "last_modified": datetime.fromtimestamp(file_stat.st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }
    except PermissionError:
        return f"Error: Permission denied to access {path}"
    except Exception as e:
        return f"Error getting file info for {path}: {str(e)}"
