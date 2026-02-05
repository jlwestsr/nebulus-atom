"""Response parser for extracting tool calls from LLM responses.

Handles local LLMs that don't support OpenAI-style tool calling by
parsing JSON tool calls from the text content.
"""

import json
import logging
import re
import time
from typing import Any, Dict, Generator, List

logger = logging.getLogger(__name__)


class ResponseParser:
    """Parses LLM responses to extract tool calls from text content."""

    def extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Extract tool call objects from response text.

        Handles:
        - Single JSON objects with "name" field
        - Arrays of tool calls
        - Mixed text and JSON
        - JSON with unescaped newlines

        Args:
            text: Raw LLM response text.

        Returns:
            List of extracted tool call dictionaries.
        """
        # Remove special tokens
        text = re.sub(r"<\|.*?\|>", "", text).strip()
        results: List[Dict[str, Any]] = []

        for candidate in self._find_json_objects(text):
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                # Try to fix common JSON issues
                fixed = self._fix_json_newlines(candidate)
                try:
                    obj = json.loads(fixed)
                except json.JSONDecodeError:
                    continue

            if isinstance(obj, list):
                results.extend(o for o in obj if isinstance(o, dict) and "name" in o)
            elif isinstance(obj, dict) and "name" in obj:
                results.append(obj)

        return results

    def _fix_json_newlines(self, text: str) -> str:
        """Fix unescaped newlines in JSON strings.

        Args:
            text: JSON text with potential unescaped newlines.

        Returns:
            JSON text with newlines properly escaped.
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
                result.append("\\n")
            elif char == "\t" and in_string:
                result.append("\\t")
            else:
                result.append(char)

        return "".join(result)

    def _find_json_objects(self, text: str) -> Generator[str, None, None]:
        """Find balanced JSON objects and arrays in text.

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
        """Normalize extracted dict into standard tool call format.

        Args:
            extracted: Raw extracted dictionary.
            index: Index for generating unique ID.

        Returns:
            Normalized tool call dictionary with id, name, arguments.
        """
        name = extracted.get("name", "unknown")
        args = extracted.get("arguments") or extracted.get("parameters") or {}

        # If arguments is already a string, keep it
        if isinstance(args, str):
            try:
                # Validate it's valid JSON
                json.loads(args)
                args_str = args
            except json.JSONDecodeError:
                args_str = json.dumps({"raw": args})
        else:
            args_str = json.dumps(args)

        return {
            "id": f"extracted_{int(time.time())}_{index}",
            "name": name,
            "arguments": args_str,
        }

    def normalize_all(
        self, extracted_list: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Normalize a list of extracted tool calls.

        Args:
            extracted_list: List of raw extracted dictionaries.

        Returns:
            List of normalized tool call dictionaries.
        """
        return [
            self.normalize_tool_call(item, i) for i, item in enumerate(extracted_list)
        ]
