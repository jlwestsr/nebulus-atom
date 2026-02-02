"""Tool definitions for Minion agent."""

from typing import Any, Dict, List

# Tool definitions in OpenAI function calling format
MINION_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. Returns the file content as text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to workspace root",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional starting line number (1-indexed)",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional ending line number (inclusive)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to workspace root",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace specific text in a file. Use for targeted edits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to workspace root",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Exact text to find and replace",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Text to replace with",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories in a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to directory relative to workspace root. Use '.' for root.",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to list recursively. Default false.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a pattern in files using grep-like functionality.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text or regex pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in. Default is workspace root.",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter files (e.g., '*.py')",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": "Find files matching a glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '**/*.py', 'src/*.js')",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command. Use for running tests, builds, linters, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds. Default 60.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Call when the task is fully implemented and ready for PR. Signals successful completion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Summary of what was accomplished",
                    },
                    "files_changed": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of files that were created or modified",
                    },
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_blocked",
            "description": "Call when you cannot complete the task due to missing information, complexity, or other blockers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why the task cannot be completed",
                    },
                    "blocker_type": {
                        "type": "string",
                        "enum": [
                            "missing_info",
                            "too_complex",
                            "unclear_requirements",
                            "external_dependency",
                        ],
                        "description": "Type of blocker",
                    },
                    "question": {
                        "type": "string",
                        "description": "Optional question to post on the issue for clarification",
                    },
                },
                "required": ["reason", "blocker_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List available skills from the skill library.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "use_skill",
            "description": "Load a skill's instructions to help with the current task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to load",
                    },
                },
                "required": ["skill_name"],
            },
        },
    },
]


def get_tool_names() -> List[str]:
    """Get list of all tool names."""
    return [tool["function"]["name"] for tool in MINION_TOOLS]


def get_tool_by_name(name: str) -> Dict[str, Any] | None:
    """Get a tool definition by name."""
    for tool in MINION_TOOLS:
        if tool["function"]["name"] == name:
            return tool
    return None
