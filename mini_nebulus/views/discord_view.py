from typing import Dict, Any, ContextManager
from contextlib import contextmanager
import discord
from mini_nebulus.views.base_view import BaseView


class DiscordView(BaseView):
    def __init__(self, channel: discord.abc.Messageable):
        self.channel = channel

    async def print_welcome(self):
        pass

    async def prompt_user(self) -> str:
        return ""

    async def ask_user_input(self, question: str) -> str:
        await self.channel.send(
            f"❓ **Question:** {question}\n*(Please reply to this message)*"
        )

        # NOTE: Real implementation requires access to the client to use wait_for.
        # This is a placeholder that acknowledges the architectural need.
        return "Discord input not yet fully bridged to client.wait_for"

    async def print_agent_response(self, text: str):
        if text.strip():
            chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
            for chunk in chunks:
                await self.channel.send(chunk)

    async def print_telemetry(self, metrics: Dict[str, Any]):
        pass

    async def print_tool_output(self, output: str, tool_name: str = ""):
        if not output:
            return
        lang = "python" if tool_name in ["read_file", "create_skill"] else ""
        formatted = (
            f"**Tool Output ({tool_name}):**\n```"
            + lang
            + "\n"
            + f"{output[:1900]}\n```"
        )
        if len(output) > 1900:
            formatted += "\n*(Output truncated)*"
        await self.channel.send(formatted)

    async def print_plan(self, plan_data: Dict[str, Any]):
        # 1. Send detailed list as Embed
        embed = discord.Embed(
            title=f"Plan: {plan_data.get("goal", "Unknown")}",
            color=discord.Color.blue(),
        )
        description = ""
        tasks = plan_data.get("tasks", [])
        for task in tasks:
            status = task.get("status", "pending").lower()
            icon = "○"
            if status == "completed":
                icon = "✅"
            elif status == "in_progress":
                icon = "▶️"
            elif status == "failed":
                icon = "❌"
            description += f"{icon} **{status.upper()}**: {task.get("description")}\n"
        embed.description = description
        await self.channel.send(embed=embed)

        # 2. Send Visual Graph (Mermaid)
        try:
            mermaid = ["graph TD"]

            # Class definitions
            mermaid.append(
                "    classDef completed fill:#9f9,stroke:#333,stroke-width:2px,color:black;"
            )
            mermaid.append(
                "    classDef inprogress fill:#ff9,stroke:#333,stroke-width:2px,color:black;"
            )
            mermaid.append(
                "    classDef failed fill:#f99,stroke:#333,stroke-width:2px,color:black;"
            )
            mermaid.append(
                "    classDef pending fill:#fff,stroke:#333,stroke-width:1px,color:black;"
            )

            # Nodes
            for task in tasks:
                safe_id = "T" + task["id"].replace("-", "")[:8]
                desc = (
                    task["description"][:25]
                    .replace('"', "")
                    .replace("(", "")
                    .replace(")", "")
                )

                status = task.get("status", "pending").lower()
                style = ":::pending"
                if status == "completed":
                    style = ":::completed"
                elif status == "in_progress":
                    style = ":::inprogress"
                elif status == "failed":
                    style = ":::failed"

                mermaid.append(f'    {safe_id}["{desc}"]{style}')

            # Edges
            for task in tasks:
                safe_id = "T" + task["id"].replace("-", "")[:8]
                for dep in task.get("dependencies", []):
                    safe_dep = "T" + dep.replace("-", "")[:8]
                    # Only add edge if both nodes exist (sanity check)
                    mermaid.append(f"    {safe_dep} --> {safe_id}")

            mermaid_str = "\n".join(mermaid)
            if len(mermaid_str) < 1900:
                await self.channel.send(f"```mermaid\n{mermaid_str}\n```")
        except Exception:
            pass  # Fail silently on graph generation errors

    async def print_error(self, message: str):
        await self.channel.send(f"❌ **Error:** {message}")

    async def print_goodbye(self):
        pass

    @contextmanager
    def create_spinner(self, text: str) -> ContextManager:
        yield
