import os
import pkgutil
import importlib
import importlib.util
import inspect
import shutil
import sys
from typing import List, Dict, Callable, Any
from mini_nebulus.config import Config


class SkillService:
    def __init__(self, skills_dir: str = "mini_nebulus/skills"):
        self.skills_dir = skills_dir
        self.global_skills_dir = Config.GLOBAL_SKILLS_PATH
        self.skills: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict] = []

    def load_skills(self):
        """Scans local and global skills directories and loads all valid skill functions."""
        self.skills = {}
        self.tool_definitions = []

        # Ensure directories exist
        for d in [self.skills_dir, self.global_skills_dir]:
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)

        # 1. Load Local Skills
        self._load_from_path(self.skills_dir, package_prefix="mini_nebulus.skills")

        # 2. Load Global Skills
        self._load_from_path(self.global_skills_dir, namespace="global")

    def _load_from_path(
        self, path: str, package_prefix: str = None, namespace: str = None
    ):
        """Helper to load modules from a specific path."""
        try:
            importlib.invalidate_caches()
            for _, name, _ in pkgutil.iter_modules([path]):
                try:
                    module = None
                    if package_prefix:
                        try:
                            module_name = f"{package_prefix}.{name}"
                            module = importlib.import_module(module_name)
                            importlib.reload(module)
                        except (ImportError, ModuleNotFoundError):
                            pass

                    if not module:
                        file_path = os.path.join(path, f"{name}.py")
                        spec = importlib.util.spec_from_file_location(name, file_path)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            sys.modules[name] = module
                            spec.loader.exec_module(module)

                    if module:
                        for attr_name, attr_value in inspect.getmembers(module):
                            if inspect.isfunction(
                                attr_value
                            ) and not attr_name.startswith("_"):
                                reg_name = (
                                    f"{namespace}.{attr_name}"
                                    if namespace
                                    else attr_name
                                )
                                self._register_skill(reg_name, attr_value)
                except Exception as e:
                    print(f"Failed to load skill module {name} from {path}: {e}")
        except Exception as e:
            print(f"Error scanning path {path}: {e}")

    def publish_skill(self, name: str) -> str:
        """Moves a local skill to the global library."""
        local_path = os.path.join(self.skills_dir, f"{name}.py")
        global_path = os.path.join(self.global_skills_dir, f"{name}.py")

        if not os.path.exists(local_path):
            return f"Error: Local skill {name} not found at {local_path}"

        try:
            shutil.copy2(local_path, global_path)
            self.load_skills()  # Refresh
            return f"Skill {name} published to global library at {global_path}"
        except Exception as e:
            return f"Error publishing skill: {str(e)}"

    def _register_skill(self, name: str, func: Callable):
        """Parses a function to create a tool definition."""
        doc = inspect.getdoc(func) or "No description provided."
        sig = inspect.signature(func)

        params = {"type": "object", "properties": {}, "required": []}

        for param_name, param in sig.parameters.items():
            param_type = "string"
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == bool:
                param_type = "boolean"

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
