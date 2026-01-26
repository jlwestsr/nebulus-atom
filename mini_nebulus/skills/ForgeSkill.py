from typing import List, Dict, Any
import subprocess


class ForgeSkill:
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "create_new_project",
                    "description": "Create a new AI-native project using Forge.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Name of the new project (kebab-case recommended).",
                            },
                            "description": {
                                "type": "string",
                                "description": "Short description of the project.",
                            },
                            "output_dir": {
                                "type": "string",
                                "description": "Parent directory where the project folder will be created. Defaults to current directory.",
                            },
                        },
                        "required": ["name", "description"],
                    },
                },
            }
        ]

    async def execute(
        self, tool_name: str, arguments: Dict[str, Any], session_id: str
    ) -> str:
        if tool_name == "create_new_project":
            return self._create_new_project(
                arguments.get("name"),
                arguments.get("description"),
                arguments.get("output_dir", "."),
            )
        return f"Tool {tool_name} not found in ForgeSkill."

    def _create_new_project(self, name: str, description: str, output_dir: str) -> str:
        """Invokes the 'forge-project' CLI to scaffold a new project."""
        try:
            # Command: forge-project <output_dir> --config-set project_name="foo" project_description="bar"
            # We assume Forge respects these config sets for the current run or prompts otherwise.
            # If Forge is interactive by default, we might have issues.
            # However, looking at the help: `target_dir` is positional.

            import os

            target_path = os.path.join(output_dir, name)

            cmd = [
                "forge-project",
                target_path,
                "--config-set",
                f"project_name={name}",
                f"project_description={description}",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                return f"Successfully created project '{name}' in '{target_path}'.\nOutput:\n{result.stdout}"
            else:
                return f"Failed to create project. Exit Code: {result.returncode}\nError:\n{result.stderr}\nOutput:\n{result.stdout}"

        except FileNotFoundError:
            return "Error: 'forge-project' command not found. Please verify it is installed (pip install . in Scaffolder repo)."
        except Exception as e:
            return f"Error executing forge-project: {str(e)}"
