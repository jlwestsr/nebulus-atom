import ast
import os
from typing import Dict, List, Any
from mini_nebulus.utils.logger import setup_logger

logger = setup_logger(__name__)


class CodebaseMap:
    def __init__(self):
        self.files: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return self.files


class ASTService:
    def __init__(self, root_dir: str = "."):
        self.root_dir = root_dir
        self.map = CodebaseMap()

    def generate_map(self, target_dir: str = None) -> Dict[str, Any]:
        """Scans the directory and generates a codebase map."""
        scan_dir = target_dir or self.root_dir
        logger.info(f"Generating AST map for {scan_dir}")

        result = {}

        for root, _, files in os.walk(scan_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.root_dir)

                    # Skip venv and hidden folders
                    if (
                        "venv" in rel_path
                        or ".git" in rel_path
                        or "__pycache__" in rel_path
                    ):
                        continue

                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read()

                        tree = ast.parse(content)
                        file_info = self._analyze_tree(tree)
                        result[rel_path] = file_info
                    except Exception as e:
                        logger.warning(f"Failed to parse {rel_path}: {e}")
                        result[rel_path] = {"error": str(e)}

        self.map.files = result
        return result

    def _analyze_tree(self, tree: ast.AST) -> Dict[str, Any]:
        info = {
            "classes": [],
            "functions": [],
            "imports": [],
            "docstring": ast.get_docstring(tree),
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = {
                    "name": node.name,
                    "methods": [
                        n.name for n in node.body if isinstance(n, ast.FunctionDef)
                    ],
                    "docstring": ast.get_docstring(node),
                    "lineno": node.lineno,
                }
                info["classes"].append(class_info)

            elif isinstance(node, ast.FunctionDef):
                # Only top-level functions (or we catch them in walk anyway)
                # If it is inside a class, it is a method.
                # AST walk visits all nodes.
                # To distinguish top-level, we could check parent, but ast.walk doesn't track parent.
                # For this simple map, listing all defs is fine, or we can iterate tree.body for top-level.
                pass

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    info["imports"].append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    info["imports"].append(f"{module}.{alias.name}")

        # Re-iterate body for top-level functions specifically
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                func_info = {
                    "name": node.name,
                    "docstring": ast.get_docstring(node),
                    "lineno": node.lineno,
                }
                info["functions"].append(func_info)

        return info

    def find_symbol(self, symbol_name: str) -> List[Dict[str, Any]]:
        """Searches the generated map for a specific class or function."""
        if not self.map.files:
            self.generate_map()

        matches = []
        for path, data in self.map.files.items():
            if "error" in data:
                continue

            # Check classes
            for cls in data.get("classes", []):
                if symbol_name.lower() in cls["name"].lower():
                    matches.append(
                        {
                            "type": "class",
                            "name": cls["name"],
                            "file": path,
                            "line": cls["lineno"],
                        }
                    )
                # Check methods
                for method in cls.get("methods", []):
                    if symbol_name.lower() in method.lower():
                        matches.append(
                            {
                                "type": "method",
                                "name": f"{cls["name"]}.{method}",
                                "file": path,
                                "line": cls["lineno"],
                            }
                        )

            # Check functions
            for func in data.get("functions", []):
                if symbol_name.lower() in func["name"].lower():
                    matches.append(
                        {
                            "type": "function",
                            "name": func["name"],
                            "file": path,
                            "line": func["lineno"],
                        }
                    )

        return matches


class ASTServiceManager:
    def __init__(self):
        self.service = ASTService()

    def get_service(self, session_id: str = "default") -> ASTService:
        return self.service
