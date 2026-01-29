import asyncio
import sys
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from mini_nebulus.controllers.agent_controller import AgentController
from mini_nebulus.views.headless_view import HeadlessView

# DEBUG: Print installed packages
print("--- INSTALLED PACKAGES ---")
subprocess.run([sys.executable, "-m", "pip", "freeze"])
print("--------------------------")

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
    print(f"DEBUG: Input received: {request.message}")
    await agent_view.submit_input(request.message)
    print("DEBUG: Input submitted to view")
    return {"status": "sent"}


@app.get("/events")
async def get_events():
    """
    Poll for recent events (REST alternative to WS).
    Returns all currently queued events immediately.
    """
    events = []
    # Drain the queue non-blocking
    q_size = agent_view.event_queue.qsize()
    if q_size > 0:
        print(f"DEBUG: Draining {q_size} events")

    while not agent_view.event_queue.empty():
        try:
            event = agent_view.event_queue.get_nowait()
            print(f"DEBUG: Returning event: {event['type']}")
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
        # Loop to consume events from HeadlessView and send to WS
        async for event in agent_view.get_events():
            await websocket.send_json(event)
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WS Error: {e}")
