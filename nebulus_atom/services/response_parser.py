"""
Response parser service for extracting tool calls from LLM responses.

Handles JSON extraction from text, including edge cases like malformed JSON
and local model hallucinations.
"""

import ast
import json
import re
import time
from typing import List, Dict, Any, Generator

from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class ResponseParser:
    """Parses LLM responses to extract tool calls."""

    def extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract tool call objects from response text.

        Handles:
        - Single JSON objects
        - Arrays of tool calls
        - Mixed text and JSON
        - Python dict literals (single quotes)
        - JSON with unescaped newlines in strings (common with local models)

        Args:
            text: Raw LLM response text.

        Returns:
            List of extracted tool call dictionaries.
        """
        text = re.sub(r"<\|.*?\|>", "", text).strip()
        results: List[Dict[str, Any]] = []

        for candidate in self._find_json_objects(text):
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                # Try to fix unescaped newlines in JSON strings
                fixed = self._fix_json_newlines(candidate)
                try:
                    obj = json.loads(fixed)
                except json.JSONDecodeError:
                    # Fall back to Python literal eval (existing code, handles single quotes)
                    try:
                        obj = ast.literal_eval(candidate)  # noqa: S307
                    except Exception:
                        continue

            if isinstance(obj, list):
                results.extend(
                    o
                    for o in obj
                    if isinstance(o, dict) and ("name" in o or "command" in o)
                )
            elif isinstance(obj, dict):
                if "name" in obj or "command" in obj:
                    results.append(obj)

        return results

    def _fix_json_newlines(self, text: str) -> str:
        """
        Fix unescaped newlines in JSON strings.

        Some local models return JSON with actual newline characters
        inside string values instead of escaped \\n sequences.

        Args:
            text: JSON text with potential unescaped newlines.

        Returns:
            JSON text with newlines properly escaped within strings.
        """
        result = []
        in_string = False
        escape_next = False

        for char in text:
            if escape_next:
                result.append(char)
                escape_next = False
            elif char == "\\":
                result.append(char)
                escape_next = True
            elif char == '"':
                result.append(char)
                in_string = not in_string
            elif char == "\n" and in_string:
                # Replace actual newline with escaped version
                result.append("\\n")
            elif char == "\t" and in_string:
                # Also handle tabs
                result.append("\\t")
            else:
                result.append(char)

        return "".join(result)

    def _find_json_objects(self, text: str) -> Generator[str, None, None]:
        """
        Find balanced JSON objects and arrays in text.

        Uses bracket matching to find complete JSON structures.

        Args:
            text: Text to search.

        Yields:
            Candidate JSON strings.
        """
        stack: List[str] = []
        start = -1

        for i, char in enumerate(text):
            if char == "{":
                if not stack:
                    start = i
                stack.append("{")
            elif char == "}":
                if stack:
                    stack.pop()
                    if not stack:
                        yield text[start : i + 1]
            elif char == "[":
                if not stack:
                    start = i
                stack.append("[")
            elif char == "]":
                if stack:
                    stack.pop()
                    if not stack:
                        yield text[start : i + 1]

    def normalize_tool_call(
        self, extracted: Dict[str, Any], index: int = 0
    ) -> Dict[str, Any]:
        """
        Normalize an extracted dict into standard tool call format.

        Handles various formats produced by local models:
        - "arguments" vs "parameters" keys
        - Stringified JSON arguments
        - "command" at root level

        Args:
            extracted: Raw extracted dictionary.
            index: Index for generating unique ID.

        Returns:
            Normalized tool call dictionary.
        """
        args = extracted.get("arguments") or extracted.get("parameters") or extracted

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                pass

        if isinstance(args, dict) and "command" not in args and "command" in extracted:
            args = extracted

        tool_name = extracted.get("name", "run_shell_command")
        thought = extracted.get("thought")

        return {
            "id": f"manual_{int(time.time())}_{index}",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(args) if isinstance(args, dict) else args,
            },
            "thought": thought,
        }

    def normalize_all(
        self, extracted_list: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Normalize a list of extracted tool calls.

        Args:
            extracted_list: List of raw extracted dictionaries.

        Returns:
            List of normalized tool call dictionaries.
        """
        return [
            self.normalize_tool_call(item, i) for i, item in enumerate(extracted_list)
        ]

    def clean_response_text(self, text: str) -> str:
        """
        Clean response text by removing special tokens.

        Args:
            text: Raw response text.

        Returns:
            Cleaned text.
        """
        return re.sub(r"<\|.*?\|>", "", text).strip()
