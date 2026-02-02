"""Tool executor for Minion agent - runs tools within container context."""

import fnmatch
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from nebulus_swarm.minion.agent.minion_agent import ToolResult

logger = logging.getLogger(__name__)

# Default command timeout
DEFAULT_COMMAND_TIMEOUT = 60

# Maximum file size to read (5MB)
MAX_FILE_SIZE = 5 * 1024 * 1024

# Maximum output size for commands (100KB)
MAX_OUTPUT_SIZE = 100 * 1024


class ToolExecutor:
    """Executes tools within the Minion container context."""

    def __init__(
        self,
        workspace: Path,
        skill_loader: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        skill_getter: Optional[Callable[[str], Optional[str]]] = None,
    ):
        """Initialize tool executor.

        Args:
            workspace: Root workspace path (cloned repo).
            skill_loader: Optional function to list available skills.
            skill_getter: Optional function to get skill instructions by name.
        """
        self.workspace = workspace.resolve()
        self._skill_loader = skill_loader
        self._skill_getter = skill_getter

        # Track loaded skills for context
        self._loaded_skills: List[str] = []

    def execute(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute a tool by name.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            ToolResult with execution outcome.
        """
        # Map tool names to handlers
        handlers = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "edit_file": self._edit_file,
            "list_directory": self._list_directory,
            "search_files": self._search_files,
            "glob_files": self._glob_files,
            "run_command": self._run_command,
            "task_complete": self._task_complete,
            "task_blocked": self._task_blocked,
            "list_skills": self._list_skills,
            "use_skill": self._use_skill,
        }

        handler = handlers.get(name)
        if not handler:
            return ToolResult(
                tool_call_id="",
                name=name,
                success=False,
                output="",
                error=f"Unknown tool: {name}",
            )

        try:
            return handler(arguments)
        except Exception as e:
            logger.exception(f"Tool execution error: {e}")
            return ToolResult(
                tool_call_id="",
                name=name,
                success=False,
                output="",
                error=str(e),
            )

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to workspace, ensuring it's within bounds.

        Args:
            path: Relative path.

        Returns:
            Resolved absolute path.

        Raises:
            ValueError: If path escapes workspace.
        """
        # Normalize and resolve
        resolved = (self.workspace / path).resolve()

        # Security check: ensure within workspace
        try:
            resolved.relative_to(self.workspace)
        except ValueError:
            raise ValueError(f"Path escapes workspace: {path}")

        return resolved

    def _read_file(self, args: Dict[str, Any]) -> ToolResult:
        """Read file contents."""
        path = args.get("path", "")
        start_line = args.get("start_line")
        end_line = args.get("end_line")

        try:
            resolved = self._resolve_path(path)

            if not resolved.exists():
                return ToolResult(
                    tool_call_id="",
                    name="read_file",
                    success=False,
                    output="",
                    error=f"File not found: {path}",
                )

            if not resolved.is_file():
                return ToolResult(
                    tool_call_id="",
                    name="read_file",
                    success=False,
                    output="",
                    error=f"Not a file: {path}",
                )

            # Check file size
            if resolved.stat().st_size > MAX_FILE_SIZE:
                return ToolResult(
                    tool_call_id="",
                    name="read_file",
                    success=False,
                    output="",
                    error=f"File too large (>{MAX_FILE_SIZE // 1024 // 1024}MB): {path}",
                )

            content = resolved.read_text()

            # Apply line range if specified
            if start_line is not None or end_line is not None:
                lines = content.splitlines(keepends=True)
                start = (start_line or 1) - 1  # Convert to 0-indexed
                end = end_line or len(lines)
                content = "".join(lines[start:end])

            return ToolResult(
                tool_call_id="",
                name="read_file",
                success=True,
                output=content,
            )

        except ValueError as e:
            return ToolResult(
                tool_call_id="",
                name="read_file",
                success=False,
                output="",
                error=str(e),
            )

    def _write_file(self, args: Dict[str, Any]) -> ToolResult:
        """Write content to a file."""
        path = args.get("path", "")
        content = args.get("content", "")

        try:
            resolved = self._resolve_path(path)

            # Create parent directories if needed
            resolved.parent.mkdir(parents=True, exist_ok=True)

            resolved.write_text(content)

            return ToolResult(
                tool_call_id="",
                name="write_file",
                success=True,
                output=f"Wrote {len(content)} bytes to {path}",
            )

        except ValueError as e:
            return ToolResult(
                tool_call_id="",
                name="write_file",
                success=False,
                output="",
                error=str(e),
            )

    def _edit_file(self, args: Dict[str, Any]) -> ToolResult:
        """Edit a file by replacing text."""
        path = args.get("path", "")
        old_text = args.get("old_text", "")
        new_text = args.get("new_text", "")

        try:
            resolved = self._resolve_path(path)

            if not resolved.exists():
                return ToolResult(
                    tool_call_id="",
                    name="edit_file",
                    success=False,
                    output="",
                    error=f"File not found: {path}",
                )

            content = resolved.read_text()

            if old_text not in content:
                return ToolResult(
                    tool_call_id="",
                    name="edit_file",
                    success=False,
                    output="",
                    error=f"Text not found in file: {old_text[:50]}...",
                )

            # Replace first occurrence
            new_content = content.replace(old_text, new_text, 1)
            resolved.write_text(new_content)

            return ToolResult(
                tool_call_id="",
                name="edit_file",
                success=True,
                output=f"Replaced text in {path}",
            )

        except ValueError as e:
            return ToolResult(
                tool_call_id="",
                name="edit_file",
                success=False,
                output="",
                error=str(e),
            )

    def _list_directory(self, args: Dict[str, Any]) -> ToolResult:
        """List directory contents."""
        path = args.get("path", ".")
        recursive = args.get("recursive", False)

        try:
            resolved = self._resolve_path(path)

            if not resolved.exists():
                return ToolResult(
                    tool_call_id="",
                    name="list_directory",
                    success=False,
                    output="",
                    error=f"Directory not found: {path}",
                )

            if not resolved.is_dir():
                return ToolResult(
                    tool_call_id="",
                    name="list_directory",
                    success=False,
                    output="",
                    error=f"Not a directory: {path}",
                )

            entries = []
            if recursive:
                for item in sorted(resolved.rglob("*")):
                    rel_path = item.relative_to(resolved)
                    # Skip hidden and common ignored paths
                    if any(
                        part.startswith(".") or part in ("__pycache__", "node_modules")
                        for part in rel_path.parts
                    ):
                        continue
                    prefix = "📁 " if item.is_dir() else "📄 "
                    entries.append(f"{prefix}{rel_path}")
            else:
                for item in sorted(resolved.iterdir()):
                    if item.name.startswith("."):
                        continue
                    prefix = "📁 " if item.is_dir() else "📄 "
                    entries.append(f"{prefix}{item.name}")

            output = "\n".join(entries[:500])  # Limit output
            if len(entries) > 500:
                output += f"\n... and {len(entries) - 500} more"

            return ToolResult(
                tool_call_id="",
                name="list_directory",
                success=True,
                output=output,
            )

        except ValueError as e:
            return ToolResult(
                tool_call_id="",
                name="list_directory",
                success=False,
                output="",
                error=str(e),
            )

    def _search_files(self, args: Dict[str, Any]) -> ToolResult:
        """Search for pattern in files."""
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        file_pattern = args.get("file_pattern")

        try:
            resolved = self._resolve_path(path)

            if not resolved.exists():
                return ToolResult(
                    tool_call_id="",
                    name="search_files",
                    success=False,
                    output="",
                    error=f"Path not found: {path}",
                )

            results = []
            regex = re.compile(pattern, re.IGNORECASE)

            # Walk through files
            if resolved.is_file():
                files = [resolved]
            else:
                files = list(resolved.rglob("*"))

            for file_path in files:
                if not file_path.is_file():
                    continue

                # Skip binary and large files
                if file_path.stat().st_size > MAX_FILE_SIZE:
                    continue

                # Apply file pattern filter
                if file_pattern and not fnmatch.fnmatch(file_path.name, file_pattern):
                    continue

                # Skip hidden/ignored
                rel_path = file_path.relative_to(self.workspace)
                if any(
                    part.startswith(".") or part in ("__pycache__", "node_modules")
                    for part in rel_path.parts
                ):
                    continue

                try:
                    content = file_path.read_text()
                    for i, line in enumerate(content.splitlines(), 1):
                        if regex.search(line):
                            results.append(f"{rel_path}:{i}: {line.strip()[:100]}")
                            if len(results) >= 100:
                                break
                except (UnicodeDecodeError, PermissionError):
                    continue

                if len(results) >= 100:
                    break

            output = "\n".join(results)
            if len(results) >= 100:
                output += "\n... (results truncated)"

            return ToolResult(
                tool_call_id="",
                name="search_files",
                success=True,
                output=output or "No matches found",
            )

        except re.error as e:
            return ToolResult(
                tool_call_id="",
                name="search_files",
                success=False,
                output="",
                error=f"Invalid regex pattern: {e}",
            )
        except ValueError as e:
            return ToolResult(
                tool_call_id="",
                name="search_files",
                success=False,
                output="",
                error=str(e),
            )

    def _glob_files(self, args: Dict[str, Any]) -> ToolResult:
        """Find files matching a glob pattern."""
        pattern = args.get("pattern", "")

        try:
            matches = []
            for match in self.workspace.glob(pattern):
                rel_path = match.relative_to(self.workspace)
                # Skip hidden/ignored
                if any(
                    part.startswith(".") or part in ("__pycache__", "node_modules")
                    for part in rel_path.parts
                ):
                    continue
                matches.append(str(rel_path))

            matches.sort()
            output = "\n".join(matches[:200])
            if len(matches) > 200:
                output += f"\n... and {len(matches) - 200} more"

            return ToolResult(
                tool_call_id="",
                name="glob_files",
                success=True,
                output=output or "No files found",
            )

        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name="glob_files",
                success=False,
                output="",
                error=str(e),
            )

    def _run_command(self, args: Dict[str, Any]) -> ToolResult:
        """Execute a shell command."""
        command = args.get("command", "")
        timeout = args.get("timeout", DEFAULT_COMMAND_TIMEOUT)

        if not command:
            return ToolResult(
                tool_call_id="",
                name="run_command",
                success=False,
                output="",
                error="No command specified",
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

            # Combine stdout and stderr
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"

            # Truncate if too large
            if len(output) > MAX_OUTPUT_SIZE:
                output = output[:MAX_OUTPUT_SIZE] + "\n... (output truncated)"

            success = result.returncode == 0

            return ToolResult(
                tool_call_id="",
                name="run_command",
                success=success,
                output=output,
                error=None if success else f"Exit code: {result.returncode}",
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_call_id="",
                name="run_command",
                success=False,
                output="",
                error=f"Command timed out after {timeout}s",
            )
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name="run_command",
                success=False,
                output="",
                error=str(e),
            )

    def _task_complete(self, args: Dict[str, Any]) -> ToolResult:
        """Handle task completion - just returns success."""
        summary = args.get("summary", "Task completed")
        return ToolResult(
            tool_call_id="",
            name="task_complete",
            success=True,
            output=summary,
        )

    def _task_blocked(self, args: Dict[str, Any]) -> ToolResult:
        """Handle task blocked - just returns success."""
        reason = args.get("reason", "Task blocked")
        return ToolResult(
            tool_call_id="",
            name="task_blocked",
            success=True,
            output=reason,
        )

    def _list_skills(self, args: Dict[str, Any]) -> ToolResult:
        """List available skills."""
        if not self._skill_loader:
            return ToolResult(
                tool_call_id="",
                name="list_skills",
                success=True,
                output="No skills available",
            )

        try:
            skills = self._skill_loader()
            if not skills:
                return ToolResult(
                    tool_call_id="",
                    name="list_skills",
                    success=True,
                    output="No skills available",
                )

            lines = ["Available skills:"]
            for skill in skills:
                name = skill.get("name", "unknown")
                desc = skill.get("description", "No description")
                lines.append(f"- {name}: {desc}")

            return ToolResult(
                tool_call_id="",
                name="list_skills",
                success=True,
                output="\n".join(lines),
            )

        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name="list_skills",
                success=False,
                output="",
                error=str(e),
            )

    def _use_skill(self, args: Dict[str, Any]) -> ToolResult:
        """Load a skill's instructions."""
        skill_name = args.get("skill_name", "")

        if not self._skill_getter:
            return ToolResult(
                tool_call_id="",
                name="use_skill",
                success=False,
                output="",
                error="Skill system not available",
            )

        try:
            instructions = self._skill_getter(skill_name)
            if not instructions:
                return ToolResult(
                    tool_call_id="",
                    name="use_skill",
                    success=False,
                    output="",
                    error=f"Skill not found: {skill_name}",
                )

            self._loaded_skills.append(skill_name)

            return ToolResult(
                tool_call_id="",
                name="use_skill",
                success=True,
                output=f"Loaded skill '{skill_name}':\n\n{instructions}",
            )

        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name="use_skill",
                success=False,
                output="",
                error=str(e),
            )

    @property
    def loaded_skills(self) -> List[str]:
        """Get list of loaded skills."""
        return self._loaded_skills.copy()
