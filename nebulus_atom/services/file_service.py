import os
from typing import List


class FileService:
    @staticmethod
    def read_file(path: str) -> str:
        """Reads a file and returns its content."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def write_file(path: str, content: str) -> str:
        """Writes content to a file. Creates directories if needed."""
        # Unescape literal "\n" sequences if they appear to be artifact of JSON transport
        # This is a heuristic: if we see literal \n and no actual newlines, we swap them.
        if "\\n" in content and "\n" not in content:
            content = content.replace("\\n", "\n").replace("\\t", "\t")

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"

    @staticmethod
    def list_dir(path: str = ".") -> List[str]:
        """Lists files in a directory."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Directory not found: {path}")
        return os.listdir(path)
