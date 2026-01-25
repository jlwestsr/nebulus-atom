import json
import re
import time
from typing import Optional

from mini_nebulus.config import Config
from mini_nebulus.models.history import History
from mini_nebulus.services.openai_service import OpenAIService
from mini_nebulus.services.tool_executor import ToolExecutor
from mini_nebulus.services.input_preprocessor import InputPreprocessor
from mini_nebulus.views.cli_view import CLIView


class AgentController:
    def __init__(self):
        self.history = History(
            'You are Mini-Nebulus, a professional AI engineer CLI. You have full access to the local system via the run_shell_command tool. When asked to perform a task, EXECUTE the command immediately. Prefer detailed output (e.g., `ls -la`). If tree is missing, use `find . -maxdepth 2 -not -path "*/.*"`. DO NOT wrap tool calls in text; use the provided tool structure. CALL THE TOOL NOW.'
        )
        self.openai = OpenAIService()
        self.view = CLIView()
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "run_shell_command",
                    "description": "Executes a shell command on the local machine.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute.",
                            }
                        },
                        "required": ["command"],
                    },
                },
            }
        ]

    async def start(self, initial_prompt: Optional[str] = None):
        self.view.print_welcome()

        if initial_prompt:
            processed = InputPreprocessor.process(initial_prompt)
            self.history.add("user", processed)
            self.view.console.print(f"[user]You:[/user] {initial_prompt}")
            await self.process_turn()

        await self.chat_loop()

    async def chat_loop(self):
        while True:
            try:
                user_input = self.view.prompt_user()
                if not user_input.strip():
                    continue

                if user_input.lower() in Config.EXIT_COMMANDS:
                    self.view.print_goodbye()
                    break

                processed = InputPreprocessor.process(user_input)
                self.history.add("user", processed)
                await self.process_turn()
            except (KeyboardInterrupt, EOFError):
                self.view.print_goodbye()
                break

    def extract_json(self, text: str) -> Optional[dict]:
        clean = re.sub(r"```\w*\n?", "", text)
        clean = re.sub(r"```$", "", clean).strip()
        if clean.startswith("{") and clean.endswith("}"):
            try:
                return json.loads(clean)
            except json.JSONDecodeError:
                pass

        match = re.search(r"run_shell_command\s*\(\s*(\{.*?\})\s*\)", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        start_index = text.find("{")
        while start_index != -1:
            balance = 0
            for i in range(start_index, len(text)):
                char = text[i]
                if char == "{":
                    balance += 1
                elif char == "}":
                    balance -= 1

                if balance == 0:
                    json_cand = text[start_index : i + 1]
                    try:
                        obj = json.loads(json_cand)
                        if "command" in obj or (
                            "arguments" in obj and "command" in obj["arguments"]
                        ):
                            return obj
                        if obj.get("name") == "run_shell_command":
                            return obj
                    except json.JSONDecodeError:
                        pass
                    break
            start_index = text.find("{", start_index + 1)

        return None

    async def process_turn(self):
        finished_turn = False

        while not finished_turn:
            with self.view.create_spinner("Thinking..."):
                try:
                    response_stream = self.openai.create_chat_completion(
                        self.history.get(), self.tools
                    )

                    full_response = ""
                    tool_calls_map = {}

                    for chunk in response_stream:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            full_response += delta.content

                        if delta.tool_calls:
                            for tc in delta.tool_calls:
                                if tc.index not in tool_calls_map:
                                    tool_calls_map[tc.index] = {
                                        "index": tc.index,
                                        "id": tc.id
                                        or f"call_{int(time.time())}_{tc.index}",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                if tc.id:
                                    tool_calls_map[tc.index]["id"] = tc.id
                                if tc.function and tc.function.name:
                                    tool_calls_map[tc.index]["function"][
                                        "name"
                                    ] += tc.function.name
                                if tc.function and tc.function.arguments:
                                    tool_calls_map[tc.index]["function"][
                                        "arguments"
                                    ] += tc.function.arguments

                    tool_calls = list(tool_calls_map.values())

                    # Heuristic extraction
                    if not tool_calls:
                        extracted = self.extract_json(full_response)
                        if extracted:
                            args = extracted.get("arguments", extracted)
                            # Normalize args
                            if (
                                extracted.get("command")
                                and "arguments" not in extracted
                            ):
                                args = extracted

                            tool_calls = [
                                {
                                    "id": f"call_manual_{int(time.time())}",
                                    "type": "function",
                                    "function": {
                                        "name": extracted.get(
                                            "name", "run_shell_command"
                                        ),
                                        "arguments": json.dumps(args)
                                        if isinstance(args, dict)
                                        else args,
                                    },
                                }
                            ]
                            if len(full_response) < 300:
                                full_response = ""

                    if tool_calls:
                        # Deduplicate
                        unique_tool_calls = []
                        seen_calls = set()
                        for tc in tool_calls:
                            key = f"{tc['function']['name']}:{tc['function']['arguments']}"
                            if key not in seen_calls:
                                seen_calls.add(key)
                                unique_tool_calls.append(tc)

                        self.history.add(
                            "assistant",
                            content=full_response.strip() or None,
                            tool_calls=unique_tool_calls,
                        )
                        self.view.print_agent_response(full_response)

                        # Execute tools (logic will run outside of this try block)
                        pass

                except Exception as e:
                    self.view.print_error(str(e))
                    finished_turn = True
                    return

            # Tool execution phase (outside Thinking spinner)
            if tool_calls:
                for tc in unique_tool_calls:
                    try:
                        args_str = tc["function"]["arguments"]
                        args = (
                            json.loads(args_str)
                            if isinstance(args_str, str)
                            else args_str
                        )
                        command = args.get("command")

                        with self.view.create_spinner(f"Executing: {command}"):
                            output = await ToolExecutor.execute(command)

                        self.view.console.print(
                            f"✔ Executed: {command}", style="dim green"
                        )
                        self.view.print_tool_output(output)
                    except Exception as e:
                        output = f"Error: {str(e)}"
                        self.view.console.print(f"✖ Failed: {str(e)}", style="bold red")

                    self.history.add("tool", content=output, tool_call_id=tc["id"])
            else:
                self.view.print_agent_response(full_response)
                print("")  # Newline
                self.history.add("assistant", full_response)
                finished_turn = True
