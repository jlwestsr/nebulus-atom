from typing import List, Dict
import os
from nebulus_atom.services.file_service import FileService


class ContextService:
    # Approx 8000 tokens * 4 chars/token = 32000 chars
    MAX_CONTEXT_CHARS = 32000

    def __init__(self):
        self.pinned_files: List[str] = []

    def pin_file(self, path: str) -> str:
        if not os.path.exists(path):
            return f"Error: File {path} does not exist."

        if path not in self.pinned_files:
            self.pinned_files.append(path)
            return f"Pinned {path}"
        return f"{path} is already pinned."

    def unpin_file(self, path: str) -> str:
        if path in self.pinned_files:
            self.pinned_files.remove(path)
            return f"Unpinned {path}"
        return f"{path} is not pinned."

    def list_context(self) -> List[str]:
        return self.pinned_files

    def get_context_string(self) -> str:
        """Reads all pinned files and returns a formatted string for the LLM."""
        if not self.pinned_files:
            return ""

        context_parts = ["\n### PINNED FILES (Active Context) ###"]
        current_length = len(context_parts[0])

        for path in self.pinned_files:
            try:
                content = FileService.read_file(path)
                header = f"\n--- BEGIN FILE: {path} ---\n"
                footer = f"\n--- END FILE: {path} ---"

                # Check if adding this file exceeds limit
                added_len = len(header) + len(content) + len(footer)

                if current_length + added_len > self.MAX_CONTEXT_CHARS:
                    # Truncate content
                    available_space = (
                        self.MAX_CONTEXT_CHARS
                        - current_length
                        - len(header)
                        - len(footer)
                    )
                    if available_space > 0:
                        content = (
                            content[:available_space]
                            + "\n... [TRUNCATED DUE TO LENGTH LIMIT] ..."
                        )
                        part = f"{header}{content}{footer}"
                        context_parts.append(part)
                    else:
                        context_parts.append(f"\n[Skipped {path} due to context limit]")

                    break  # Stop adding files

                context_parts.append(f"{header}{content}{footer}")
                current_length += added_len

            except Exception as e:
                context_parts.append(f"\n[Error reading pinned file {path}: {str(e)}]")

        return "\n".join(context_parts)


class ContextServiceManager:
    """Manages ContextService instances per session."""

    def __init__(self):
        self.sessions: Dict[str, ContextService] = {}

    def get_service(self, session_id: str) -> ContextService:
        if session_id not in self.sessions:
            self.sessions[session_id] = ContextService()
        return self.sessions[session_id]
