import os
import pkgutil
import importlib
import inspect
from typing import List, Dict, Callable, Any


class SkillService:
    def __init__(self, skills_dir: str = "mini_nebulus/skills"):
        self.skills_dir = skills_dir
        self.skills: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict] = []

    def load_skills(self):
        """Scans the skills directory and loads all valid skill functions."""
        self.skills = {}
        self.tool_definitions = []

        # Ensure directory exists
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir)

        # Iterate over all modules in the skills package
        # We assume the package is reachable as mini_nebulus.skills
        package_name = self.skills_dir.replace("/", ".")

        # Check if the path is actually importable or just a file path
        # If running from root, mini_nebulus.skills is correct

        try:
            # Reload existing modules to support hot-reloading
            importlib.invalidate_caches()

            for _, name, _ in pkgutil.iter_modules([self.skills_dir]):
                module_name = f"{package_name}.{name}"
                try:
                    module = importlib.import_module(module_name)
                    importlib.reload(module)  # Force reload

                    # Inspect module for functions
                    for attr_name, attr_value in inspect.getmembers(module):
                        if inspect.isfunction(attr_value):
                            # We look for functions that don't start with _
                            # In a real system, we might use a @skill decorator
                            if not attr_name.startswith("_"):
                                self._register_skill(attr_name, attr_value)
                except Exception as e:
                    print(f"Failed to load skill module {name}: {e}")

        except Exception as e:
            print(f"Error loading skills: {e}")

    def _register_skill(self, name: str, func: Callable):
        """Parses a function to create a tool definition."""
        doc = inspect.getdoc(func) or "No description provided."
        sig = inspect.signature(func)

        params = {"type": "object", "properties": {}, "required": []}

        for param_name, param in sig.parameters.items():
            param_type = "string"  # Default
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == bool:
                param_type = "boolean"

            # Basic parsing, can be improved with Pydantic
            params["properties"][param_name] = {
                "type": param_type,
                "description": f"Parameter {param_name}",
            }
            if param.default == inspect.Parameter.empty:
                params["required"].append(param_name)

        tool_def = {
            "type": "function",
            "function": {"name": name, "description": doc, "parameters": params},
        }

        self.skills[name] = func
        self.tool_definitions.append(tool_def)

    def get_tool_definitions(self) -> List[Dict]:
        return self.tool_definitions

    def execute_skill(self, name: str, args: Dict[str, Any]) -> str:
        if name not in self.skills:
            raise ValueError(f"Skill {name} not found")

        func = self.skills[name]
        try:
            result = func(**args)
            return str(result)
        except Exception as e:
            return f"Error executing skill {name}: {str(e)}"
