import re
from typing import Optional


class ErrorRecoveryService:
    def __init__(self):
        self.error_patterns = [
            (
                r"File not found|No such file",
                "The file you tried to access does not exist. Use `run_shell_command` with `ls` to verify the path.",
            ),
            (
                r"No module named",
                "A Python module is missing. Check imports or use `pip install` if appropriate (only if allowed).",
            ),
            (
                r"Expecting value|Extra data|Invalid control character",
                "You generated invalid JSON. Please check your syntax and escape characters.",
            ),
            (
                r"invalid syntax|unexpected indent",
                "There is a syntax error in your code. Review the file content.",
            ),
            (
                r"is not a directory",
                "You treated a file like a directory. Check your path.",
            ),
            (r"Permission denied", "You do not have permission to access this file."),
            (
                r"non-zero exit code",
                "The command failed. Read the stderr output above carefully.",
            ),
        ]

    def analyze_error(
        self, tool_name: str, error_msg: str, args: Optional[dict] = None
    ) -> str:
        """
        Analyzes a tool failure and returns a constructive prompt for the agent.
        """
        analysis = f"❌ **Tool Failure detected in `{tool_name}`**\n"
        analysis += f"Error: `{error_msg}`\n\n"

        # Heuristic Matching
        found_hint = False
        for pattern, hint in self.error_patterns:
            if re.search(pattern, error_msg, re.IGNORECASE):
                analysis += f"💡 **Recovery Hint**: {hint}\n"
                found_hint = True
                break

        if not found_hint:
            analysis += "💡 **Recovery Hint**: Analyze the error message above and try a different approach.\n"

        analysis += "🔄 **Action Required**: Correct the error and retry. Do not repeat the same invalid action."
        return analysis


class ErrorRecoveryServiceManager:
    def __init__(self):
        self.service = ErrorRecoveryService()

    def get_service(self, session_id: str = "default") -> ErrorRecoveryService:
        return self.service
