import os


def delete_file(path):
    """Delete a file from the filesystem.

    Args:
        path: Path to the file to delete.

    Returns:
        Success or error message.
    """
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        os.remove(path)
        return f"Successfully deleted {path}"
    except PermissionError:
        return f"Error: Permission denied to delete {path}"
    except IsADirectoryError:
        return f"Error: {path} is a directory, use rmdir or shutil.rmtree instead"
    except Exception as e:
        return f"Error deleting {path}: {str(e)}"
