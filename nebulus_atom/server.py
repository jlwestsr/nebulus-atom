import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from nebulus_atom.controllers.agent_controller import AgentController
from nebulus_atom.views.headless_view import HeadlessView

logger = logging.getLogger(__name__)

# Global State
agent_view = HeadlessView()
agent_controller = AgentController(view=agent_view)
agent_view.set_controller(agent_controller)


# Background Task to start the agent loop
async def run_agent_loop():
    # Start with no prompt, just idle
    await agent_controller.start(initial_prompt=None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    task = asyncio.create_task(run_agent_loop())
    yield
    # Shutdown
    task.cancel()


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Send a user message to the agent.
    """
    await agent_view.submit_input(request.message)
    return {"status": "sent"}


@app.get("/events")
async def get_events():
    """
    Poll for recent events (REST alternative to WS).
    Returns all currently queued events immediately.
    """
    events = []
    while not agent_view.event_queue.empty():
        try:
            event = agent_view.event_queue.get_nowait()
            events.append(event)
            agent_view.event_queue.task_done()
        except asyncio.QueueEmpty:
            break
    return events


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Stream agent events to the client (Web UI).
    """
    await websocket.accept()
    try:
        async for event in agent_view.get_events():
            await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error("WS Error: %s", e)
