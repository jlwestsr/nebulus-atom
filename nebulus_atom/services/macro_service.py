import os
import stat
from typing import List
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class MacroService:
    def __init__(self, macro_dir: str = "~/.nebulus_atom/macros"):
        self.macro_dir = os.path.expanduser(macro_dir)
        if not os.path.exists(self.macro_dir):
            os.makedirs(self.macro_dir, exist_ok=True)

    def create_macro(
        self, name: str, commands: List[str], description: str = ""
    ) -> str:
        """Creates a shell script macro."""
        if not name.endswith(".sh"):
            name += ".sh"

        filepath = os.path.join(self.macro_dir, name)

        content = ["#!/bin/bash"]
        if description:
            content.append(f"# {description}")

        content.extend(commands)

        try:
            with open(filepath, "w") as f:
                f.write("\n".join(content) + "\n")

            # Make executable
            st = os.stat(filepath)
            os.chmod(filepath, st.st_mode | stat.S_IEXEC)

            return f"Macro created at {filepath}. You can run it with: {filepath}"
        except Exception as e:
            logger.error(f"Failed to create macro: {e}")
            return f"Error creating macro: {e}"


class MacroServiceManager:
    def __init__(self):
        self.service = MacroService()

    def get_service(self, session_id: str = "default") -> MacroService:
        return self.service
