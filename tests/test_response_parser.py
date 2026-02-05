"""Tests for ResponseParser service."""

import json

from nebulus_atom.services.response_parser import ResponseParser


class TestResponseParser:
    """Test cases for ResponseParser."""

    def test_extract_simple_json_object(self):
        """extract_tool_calls should find a simple JSON object."""
        parser = ResponseParser()
        text = '{"name": "run_shell_command", "arguments": {"command": "ls"}}'
        result = parser.extract_tool_calls(text)

        assert len(result) == 1
        assert result[0]["name"] == "run_shell_command"

    def test_extract_json_with_surrounding_text(self):
        """extract_tool_calls should find JSON embedded in text."""
        parser = ResponseParser()
        text = 'I will list the files. {"name": "run_shell_command", "arguments": {"command": "ls"}} Done.'
        result = parser.extract_tool_calls(text)

        assert len(result) == 1
        assert result[0]["name"] == "run_shell_command"

    def test_extract_multiple_json_objects(self):
        """extract_tool_calls should find multiple JSON objects."""
        parser = ResponseParser()
        text = (
            '{"name": "read_file", "arguments": {"path": "a.txt"}} '
            '{"name": "write_file", "arguments": {"path": "b.txt", "content": "hi"}}'
        )
        result = parser.extract_tool_calls(text)

        assert len(result) == 2
        assert result[0]["name"] == "read_file"
        assert result[1]["name"] == "write_file"

    def test_extract_json_array(self):
        """extract_tool_calls should handle arrays of tool calls."""
        parser = ResponseParser()
        text = '[{"name": "read_file", "arguments": {}}, {"name": "write_file", "arguments": {}}]'
        result = parser.extract_tool_calls(text)

        assert len(result) == 2

    def test_extract_json_with_thought(self):
        """extract_tool_calls should preserve thought field."""
        parser = ResponseParser()
        text = '{"thought": "checking files", "name": "run_shell_command", "arguments": {"command": "ls"}}'
        result = parser.extract_tool_calls(text)

        assert len(result) == 1
        assert result[0]["thought"] == "checking files"

    def test_extract_command_shorthand(self):
        """extract_tool_calls should handle objects with 'command' instead of 'name'."""
        parser = ResponseParser()
        text = '{"command": "ls -la"}'
        result = parser.extract_tool_calls(text)

        assert len(result) == 1
        assert result[0]["command"] == "ls -la"

    def test_extract_python_dict_literal(self):
        """extract_tool_calls should handle Python dict literals with single quotes."""
        parser = ResponseParser()
        text = "{'name': 'run_shell_command', 'arguments': {'command': 'ls'}}"
        result = parser.extract_tool_calls(text)

        assert len(result) == 1
        assert result[0]["name"] == "run_shell_command"

    def test_extract_removes_special_tokens(self):
        """extract_tool_calls should remove special tokens like <|...|>."""
        parser = ResponseParser()
        text = (
            '<|system|>{"name": "read_file", "arguments": {"path": "test.txt"}}<|end|>'
        )
        result = parser.extract_tool_calls(text)

        assert len(result) == 1
        assert result[0]["name"] == "read_file"

    def test_extract_ignores_invalid_json(self):
        """extract_tool_calls should skip malformed JSON."""
        parser = ResponseParser()
        text = '{"name": "test" invalid} {"name": "valid", "arguments": {}}'
        result = parser.extract_tool_calls(text)

        assert len(result) == 1
        assert result[0]["name"] == "valid"

    def test_extract_ignores_json_without_name_or_command(self):
        """extract_tool_calls should skip JSON without name or command."""
        parser = ResponseParser()
        text = '{"foo": "bar"} {"name": "valid", "arguments": {}}'
        result = parser.extract_tool_calls(text)

        assert len(result) == 1
        assert result[0]["name"] == "valid"

    def test_normalize_tool_call_basic(self):
        """normalize_tool_call should create standard format."""
        parser = ResponseParser()
        extracted = {"name": "read_file", "arguments": {"path": "test.txt"}}
        result = parser.normalize_tool_call(extracted, 0)

        assert result["type"] == "function"
        assert result["function"]["name"] == "read_file"
        assert "id" in result
        assert result["id"].startswith("manual_")

    def test_normalize_tool_call_with_parameters_key(self):
        """normalize_tool_call should handle 'parameters' as alias for 'arguments'."""
        parser = ResponseParser()
        extracted = {"name": "read_file", "parameters": {"path": "test.txt"}}
        result = parser.normalize_tool_call(extracted)

        args = json.loads(result["function"]["arguments"])
        assert args["path"] == "test.txt"

    def test_normalize_tool_call_stringified_arguments(self):
        """normalize_tool_call should handle stringified JSON in arguments."""
        parser = ResponseParser()
        extracted = {"name": "read_file", "arguments": '{"path": "test.txt"}'}
        result = parser.normalize_tool_call(extracted)

        args = json.loads(result["function"]["arguments"])
        assert args["path"] == "test.txt"

    def test_normalize_tool_call_command_at_root(self):
        """normalize_tool_call should handle command at root level."""
        parser = ResponseParser()
        extracted = {"name": "run_shell_command", "command": "ls -la", "arguments": {}}
        result = parser.normalize_tool_call(extracted)

        args = json.loads(result["function"]["arguments"])
        assert args["command"] == "ls -la"

    def test_normalize_tool_call_default_name(self):
        """normalize_tool_call should default to run_shell_command."""
        parser = ResponseParser()
        extracted = {"command": "ls"}
        result = parser.normalize_tool_call(extracted)

        assert result["function"]["name"] == "run_shell_command"

    def test_normalize_tool_call_preserves_thought(self):
        """normalize_tool_call should include thought in result."""
        parser = ResponseParser()
        extracted = {"name": "test", "thought": "thinking", "arguments": {}}
        result = parser.normalize_tool_call(extracted)

        assert result["thought"] == "thinking"

    def test_normalize_all(self):
        """normalize_all should normalize a list of tool calls."""
        parser = ResponseParser()
        extracted_list = [
            {"name": "read_file", "arguments": {"path": "a.txt"}},
            {"name": "write_file", "arguments": {"path": "b.txt", "content": "hi"}},
        ]
        results = parser.normalize_all(extracted_list)

        assert len(results) == 2
        assert results[0]["function"]["name"] == "read_file"
        assert results[1]["function"]["name"] == "write_file"
        assert results[0]["id"] != results[1]["id"]

    def test_clean_response_text(self):
        """clean_response_text should remove special tokens."""
        parser = ResponseParser()
        text = "<|system|>Hello<|end|> World <|user|>"
        result = parser.clean_response_text(text)

        assert result == "Hello World"

    def test_clean_response_text_strips_whitespace(self):
        """clean_response_text should strip leading/trailing whitespace."""
        parser = ResponseParser()
        text = "   <|token|>   Hello World   <|end|>   "
        result = parser.clean_response_text(text)

        assert result == "Hello World"

    def test_find_json_objects_nested(self):
        """_find_json_objects should handle nested structures."""
        parser = ResponseParser()
        text = '{"outer": {"inner": "value"}}'
        results = list(parser._find_json_objects(text))

        assert len(results) == 1
        parsed = json.loads(results[0])
        assert parsed["outer"]["inner"] == "value"

    def test_find_json_objects_arrays(self):
        """_find_json_objects should find top-level arrays."""
        parser = ResponseParser()
        text = '[{"name": "a"}, {"name": "b"}]'
        results = list(parser._find_json_objects(text))

        assert len(results) == 1
        parsed = json.loads(results[0])
        assert len(parsed) == 2
