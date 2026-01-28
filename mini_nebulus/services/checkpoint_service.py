import os
import tarfile
import time
from typing import List, Dict


class CheckpointService:
    CHECKPOINT_DIR = ".mini_nebulus/checkpoints"

    # Files/Dirs to include in the backup (root relative)
    # We essentially backup everything except excludes
    EXCLUDES = [
        "venv",
        ".git",
        "__pycache__",
        ".mini_nebulus",
        ".pytest_cache",
        ".ruff_cache",
        "*.pyc",
        ".DS_Store",
    ]

    def __init__(self):
        if not os.path.exists(self.CHECKPOINT_DIR):
            os.makedirs(self.CHECKPOINT_DIR)
        self.checkpoints: List[Dict] = self._load_checkpoints()

    def _load_checkpoints(self) -> List[Dict]:
        """Scans the checkpoint directory for existing backups."""
        backups = []
        if not os.path.exists(self.CHECKPOINT_DIR):
            return []

        for filename in os.listdir(self.CHECKPOINT_DIR):
            if filename.endswith(".tar.gz"):
                # format: {timestamp}_{label}.tar.gz
                try:
                    parts = filename.replace(".tar.gz", "").split("_", 1)
                    timestamp = parts[0]
                    label = parts[1] if len(parts) > 1 else "unnamed"
                    backups.append(
                        {
                            "id": timestamp,
                            "label": label,
                            "filename": filename,
                            "path": os.path.join(self.CHECKPOINT_DIR, filename),
                        }
                    )
                except Exception:
                    continue

        # Sort by timestamp desc
        return sorted(backups, key=lambda x: x["id"], reverse=True)

    def create_checkpoint(self, label: str = "auto") -> str:
        """Creates a snapshot of the current working directory."""
        timestamp = str(int(time.time()))
        filename = f"{timestamp}_{label}.tar.gz"
        filepath = os.path.join(self.CHECKPOINT_DIR, filename)

        try:
            with tarfile.open(filepath, "w:gz") as tar:
                # Add all files in current directory, filtering excludes
                for item in os.listdir("."):
                    if item in self.EXCLUDES or item.startswith("."):
                        # Basic exclude check for root items
                        if item not in [
                            ".gitignore",
                            ".dockerignore",
                            "CONTEXT.md",
                        ]:  # Whitelist some dotfiles
                            if item in [
                                "venv",
                                ".git",
                                ".mini_nebulus",
                                ".pytest_cache",
                                ".ruff_cache",
                            ]:
                                continue

                    # For deeper exclusion, we rely on filter, but tar.add recursive is greedy.
                    # We ll just add specific root items that we care about.
                    # Actually, walking is safer.
                    tar.add(item, recursive=True, filter=self._tar_filter)

            self.checkpoints = self._load_checkpoints()
            return f"Checkpoint created: {filename}"
        except Exception as e:
            return f"Error creating checkpoint: {str(e)}"

    def _tar_filter(self, tarinfo):
        """Filter for tarfile to exclude patterns."""
        name = tarinfo.name
        # Check against excludes
        for exc in self.EXCLUDES:
            if f"/{exc}" in name or name == exc or name.endswith(f"/{exc}"):
                return None
            if exc.startswith("*") and name.endswith(exc[1:]):
                return None
        return tarinfo

    def rollback_checkpoint(self, checkpoint_id: str) -> str:
        """Restores files from a checkpoint."""
        # Find checkpoint
        backup = next(
            (
                cp
                for cp in self.checkpoints
                if cp["id"] == checkpoint_id or cp["label"] == checkpoint_id
            ),
            None,
        )

        # If not found, maybe they passed the index (0 = latest)
        if not backup and checkpoint_id.isdigit():
            idx = int(checkpoint_id)
            if idx < len(self.checkpoints):
                backup = self.checkpoints[idx]

        if not backup:
            return "Error: Checkpoint not found."

        try:
            with tarfile.open(backup["path"], "r:gz") as tar:
                tar.extractall(path=".")  # Overwrite files in current dir
            return f'Rollback successful: Restored {backup["filename"]}'
        except Exception as e:
            return f"Error restoring checkpoint: {str(e)}"

    def list_checkpoints(self) -> str:
        if not self.checkpoints:
            return "No checkpoints available."

        lines = ["Available Checkpoints:"]
        for i, cp in enumerate(self.checkpoints):
            lines.append(f'{i}. ID: {cp["id"]} | Label: {cp["label"]}')
        return "\n".join(lines)


class CheckpointServiceManager:
    def __init__(self):
        self.service = CheckpointService()

    def get_service(self, session_id: str) -> CheckpointService:
        # Checkpoints are global/project-wide, not per session really
        return self.service
