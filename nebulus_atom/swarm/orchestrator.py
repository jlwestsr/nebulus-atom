from typing import Optional
from nebulus_atom.swarm.agents.router_agent import RouterAgent
from nebulus_atom.swarm.agents.coder_agent import CoderAgent

# from nebulus_atom.swarm.agents.architect_agent import ArchitectAgent
# from nebulus_atom.swarm.agents.tester_agent import TesterAgent
from nebulus_atom.utils.logger import setup_logger
from nebulus_atom.views.base_view import BaseView
from nebulus_atom.views.cli_view import CLIView
import json

logger = setup_logger(__name__)


class SwarmOrchestrator:
    def __init__(self, view: Optional[BaseView] = None):
        self.view = view if view else CLIView()

        # Init Agents
        self.router = RouterAgent()

        # Lazy load or init all agents
        # For now, we mainly use Coder as the default fallback
        self.agents = {
            "coder": CoderAgent(self.view),
            "architect": CoderAgent(
                self.view
            ),  # Placeholder: Architect is just Coder with different prompt?
            "tester": CoderAgent(self.view),  # Placeholder
        }

    async def start(
        self, initial_prompt: Optional[str] = None, session_id: str = "default"
    ):
        await self.view.print_welcome()
        if initial_prompt:
            # If TUI, we might want to queue it or process it.
            # For now, let's process it. But if TUI blocks, we need to spawn it?
            # Actually, Textual's run_async blocks.
            # So we should process request, *then* start app?
            # But process_request might need the app running to print to log?

            # Better approach:
            if hasattr(self.view, "start_app"):
                # Queue it in the Coder's history so it appears
                # The TUI will show history on load presumably
                # Or we can launch a background task?
                pass
                # For now, TUI users usually type in the TUI.
                # If they passed a prompt, let's try to process it *before* blocking?
                # But TUI controls need to be mounted.
                pass
            else:
                await self.process_request(initial_prompt, session_id)

        if hasattr(self.view, "start_app"):
            await self.view.start_app()
            return

    async def process_request(self, user_input: str, session_id: str):
        # 1. Route
        if hasattr(self.view, "print_agent_response"):
            await self.view.print_agent_response("🔄 [Swarm] Routing request...")

        routing_json = await self.router.process_turn(session_id, user_input)

        try:
            decision = json.loads(routing_json)
            target_agent_name = decision.get("agent", "coder")
            reasoning = decision.get("reasoning", "Defaulting to Coder")
        except Exception:
            target_agent_name = "coder"
            reasoning = "Router failed JSON parsing"

        if hasattr(self.view, "print_agent_response"):
            await self.view.print_agent_response(
                f"👉 Handoff to **{target_agent_name.upper()}**: {reasoning}"
            )

        # 2. Handoff
        agent = self.agents.get(target_agent_name, self.agents["coder"])

        # 3. Execute
        # We need to bridge the CoderAgent (which is basically AgentController) to run its loop
        # Since I'm reusing AgentController code for CoderAgent, I need to make sure CoderAgent.process_turn works similar

        # NOTE: CoderAgent is special because it's interactive.
        # We might just call agent.process_turn(session_id, user_input)

        if hasattr(agent, "handle_tui_input"):
            # It's an interactive controller
            # Inject the input into history first
            agent.history_manager.get_session(session_id).add("user", user_input)
            await agent.process_turn(session_id)
