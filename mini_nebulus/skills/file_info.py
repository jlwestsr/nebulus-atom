import os
from datetime import datetime


def file_info(path: str) -> dict[str, str]:
    """
    Retrieve file statistics including size and last modified time.

    Args:
        path (str): The file path to inspect.

    Returns:
        dict[str, str]: A dictionary with 'file_size' and 'last_modified' keys.
    """
    file_stat = os.stat(path)
    return {
        "file_size": f"{file_stat.st_size} bytes",
        "last_modified": datetime.fromtimestamp(file_stat.st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }
