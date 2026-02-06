import os


def get_file_size(path: str) -> int | str:
    """Return the size of a file in bytes.

    Args:
        path (str): The file path to check.

    Returns:
        int: The file size in bytes, or error message string if file cannot be accessed.
    """
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        return os.path.getsize(path)
    except PermissionError:
        return f"Error: Permission denied to access {path}"
    except Exception as e:
        return f"Error getting file size for {path}: {str(e)}"
