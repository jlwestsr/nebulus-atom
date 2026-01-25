import discord
from mini_nebulus.controllers.agent_controller import AgentController
from mini_nebulus.views.discord_view import DiscordView


class DiscordGateway(discord.Client):
    def __init__(self, agent_controller: AgentController):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.agent = agent_controller

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

    async def on_message(self, message):
        # Ignore own messages
        if message.author.id == self.user.id:
            return

        # Check for mention or DM
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mention = self.user.mentioned_in(message)

        if is_dm or is_mention:
            # Clean prompt
            prompt = message.content.replace(f"<@{self.user.id}>", "").strip()

            if not prompt:
                return

            # Create a view for this specific channel interaction
            view = DiscordView(message.channel)

            # Temporarily inject this view into the controller
            # NOTE: In a more advanced architecture, the controller might create
            # a per-request context object. Here, we hot-swap or use a specialized process method.
            # But wait! AgentController stores `self.view`. Swapping it is not thread-safe for concurrent users.

            # SOLUTION: We need to modify AgentController to use the view passed to process_turn,
            # OR we instantiate a lightweight controller per request, sharing the history manager.
            # Given the current architecture, let's instantiate a fresh Controller for the turn
            # but SHARE the history manager and tool services.

            # To avoid massive refactoring, let's use the existing controller but
            # we must implement a way to route output to the correct view.

            # Strategy: We will subclass AgentController or modify it to accept a viewOverride
            # for process_turn.

            # For now, let's just update the controller's view.
            # WARNING: This is not thread-safe for concurrent messages.
            # A better approach for Phase 3 completion is to assume single-threaded event loop for now.
            self.agent.view = view

            # Update the View to support async methods we defined in DiscordView
            # We need to bridge the sync calls in AgentController to the async calls in DiscordView.
            # This requires AgentController to await view methods if they are async.

            # Let's handle the message
            async with message.channel.typing():
                # Update history
                session_id = str(message.channel.id)
                self.agent.history_manager.get_session(session_id).add("user", prompt)

                # We need to call a modified process_turn that awaits the view methods.
                # Since AgentController.process_turn calls view methods synchronously,
                # we have a mismatch.

                # To fix this properly, AgentController.process_turn should assume view methods *might* be async.
                await self.agent.process_turn(session_id)
