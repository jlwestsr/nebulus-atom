import os


def get_file_size(path: str) -> int:
    """Return the size of a file in bytes.

    Args:
        path (str): The file path to check.

    Returns:
        int: The file size in bytes.
    """
    return os.path.getsize(path)
