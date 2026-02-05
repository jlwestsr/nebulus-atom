from typing import Dict, Any, ContextManager
from contextlib import contextmanager
import asyncio

from nebulus_atom.views.base_view import BaseView


class HeadlessView(BaseView):
    """
    Headless View for API/Container usage.
    Captures all output into an event queue for external consumption (SSE/WebSocket).
    """

    def __init__(self):
        self.event_queue = asyncio.Queue()
        self.controller = None
        self.pending_input_future = None

    def set_controller(self, controller):
        self.controller = controller

    async def _emit(self, event_type: str, data: Any):
        """Pushes an event to the queue."""
        event = {"type": event_type, "data": data}
        await self.event_queue.put(event)

    async def get_events(self):
        """Async generator for consuming events."""
        while True:
            event = await self.event_queue.get()
            yield event
            self.event_queue.task_done()

    # --- BaseView Implementation ---

    async def print_welcome(self):
        await self._emit("welcome", {"active": True})

    async def prompt_user(self) -> str:
        # Wait for external input via API
        loop = asyncio.get_running_loop()
        self.pending_input_future = loop.create_future()
        await self._emit("input_request", {"prompt": "Waiting for input..."})
        return await self.pending_input_future

    async def submit_input(self, user_input: str):
        """Called by API to resolve pending input prompt."""
        if self.pending_input_future and not self.pending_input_future.done():
            self.pending_input_future.set_result(user_input)
            self.pending_input_future = None
        else:
            # If not waiting (autonomous mode or idle), pass to controller directly
            # This handles the "Chat" use case
            if self.controller:
                await self.controller.handle_tui_input(user_input)

    async def ask_user_input(self, question: str) -> str:
        await self._emit("input_request", {"prompt": question})
        # Reuse prompt_user logic
        return await self.prompt_user()

    async def print_agent_response(self, text: str):
        await self._emit("agent_response", {"text": text})

    async def print_telemetry(self, metrics: Dict[str, Any]):
        await self._emit("telemetry", metrics)

    async def print_tool_output(self, output: str, tool_name: str = ""):
        await self._emit("tool_output", {"tool": tool_name, "output": output})

    async def print_plan(self, plan_data: Dict[str, Any]):
        await self._emit("plan_update", plan_data)

    async def print_error(self, message: str):
        await self._emit("error", {"message": message})

    async def print_goodbye(self):
        await self._emit("goodbye", {})

    @contextmanager
    def create_spinner(self, text: str) -> ContextManager:
        # We can't really yield async here comfortably in a sync context manager
        # unless we just fire-and-forget the "start" and "stop" events.
        # Since the consumers are async, we might need a workaround or just
        # assume the event loop is running.

        # Best effort: Fire off a task to emit the event
        async def _notify(status):
            await self._emit("spinner", {"status": status, "text": text})

        # This is a bit hacky because create_spinner is sync in BaseView
        # We'll just define it. In a real threaded env this might be an issue,
        # but with asyncio it's tricky.
        # Ideally BaseView.create_spinner should be async, but it's used in `with` blocks.

        # Workaround: Check if there's a running loop and create a task
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_notify("start"))
        except RuntimeError:
            pass

        try:
            yield
        finally:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_notify("stop"))
            except RuntimeError:
                pass
