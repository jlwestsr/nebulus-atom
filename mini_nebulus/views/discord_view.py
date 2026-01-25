from typing import Dict, Any, ContextManager
from contextlib import contextmanager
import discord
from mini_nebulus.views.base_view import BaseView


class DiscordView(BaseView):
    def __init__(self, channel: discord.abc.Messageable):
        self.channel = channel

    def print_welcome(self):
        # We don't need a welcome message for every turn in Discord
        pass

    def prompt_user(self) -> str:
        # In a gateway architecture, we don't prompt; we react to events.
        return ""

    async def print_agent_response(self, text: str):
        if text.strip():
            # Split long messages if needed
            chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
            for chunk in chunks:
                await self.channel.send(chunk)

    async def print_tool_output(self, output: str, tool_name: str = ""):
        if not output:
            return

        # Format as code block
        lang = "python" if tool_name in ["read_file", "create_skill"] else ""
        formatted = f"**Tool Output ({tool_name}):**\n```{lang}\n{output[:1900]}\n```"
        if len(output) > 1900:
            formatted += "\n*(Output truncated)*"

        await self.channel.send(formatted)

    async def print_plan(self, plan_data: Dict[str, Any]):
        embed = discord.Embed(
            title=f"Plan: {plan_data.get('goal', 'Unknown')}",
            color=discord.Color.blue(),
        )

        description = ""
        for task in plan_data.get("tasks", []):
            status = task.get("status", "pending").lower()
            icon = "○"
            if status == "completed":
                icon = "✅"
            elif status == "in_progress":
                icon = "▶️"
            elif status == "failed":
                icon = "❌"

            description += f"{icon} **{status.upper()}**: {task.get('description')}\n"

        embed.description = description
        await self.channel.send(embed=embed)

    async def print_error(self, message: str):
        await self.channel.send(f"❌ **Error:** {message}")

    def print_goodbye(self):
        pass

    @contextmanager
    def create_spinner(self, text: str) -> ContextManager:
        # Spinners don't translate well to Discord messages
        # We could send a "Thinking..." message and delete it, but for now we do nothing
        yield
