import asyncio
import typer
from typing import List, Optional
from mini_nebulus.controllers.agent_controller import AgentController

app = typer.Typer(invoke_without_command=True)


@app.callback()
def main(
    prompt: Optional[List[str]] = typer.Argument(
        None, help="Initial prompt to execute immediately"
    ),
):
    """
    Mini-Nebulus: A professional, autonomous AI engineer CLI.
    """
    # If no subcommand is used (like 'start'), this callback runs.
    # Typer handles subcommands by checking if a command was invoked.
    # But since we only have 'start', we can just make this the main entry.

    # Check if the first argument was 'start' to avoid double execution if someone still uses it
    if prompt and prompt[0] == "start":
        return  # Typer will call the 'start' command automatically

    # If prompt is provided directly or no command used
    initial_prompt = " ".join(prompt) if prompt else None

    # We only run if we aren't about to run a subcommand
    # Actually, with only one command, we can just simplify main.py entirely.
    controller = AgentController()
    asyncio.run(controller.start(initial_prompt))


@app.command()
def start(
    prompt: Optional[List[str]] = typer.Argument(
        None, help="Initial prompt to execute immediately"
    ),
):
    """
    Start the Mini-Nebulus AI Agent.
    """
    initial_prompt = " ".join(prompt) if prompt else None
    controller = AgentController()
    asyncio.run(controller.start(initial_prompt))


if __name__ == "__main__":
    app()
