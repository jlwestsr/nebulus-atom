import asyncio
import typer
from mini_nebulus.controllers.agent_controller import AgentController

app = typer.Typer()


@app.command()
def start(
    prompt: str = typer.Argument(None, help="Initial prompt to execute immediately")
):
    """
    Start the Mini-Nebulus AI Agent.
    """
    controller = AgentController()
    asyncio.run(controller.start(prompt))


if __name__ == "__main__":
    app()
