# Project Context & Rules

This file serves as the primary context injection point for the Mini-Nebulus autonomous agent.
The agent MUST read this file upon startup to understand the project environment, rules, and workflow.

## Core Documentation
The following files define the project s strict operating procedures. The agent must adhere to them at all times.

- **[AI Directives](AI_DIRECTIVES.md)**: Coding standards, architecture (MVC), and commit conventions.
- **[Workflow](WORKFLOW.md)**: Branching strategy (Gitflow-lite) and development lifecycle.
- **[Project Goals](GEMINI.md)**: High-level objectives and influences (Clawd, Gemini CLI).

## Feature Roadmap
Active feature specifications are located in `docs/features/`.
Always check this directory before starting new work.

## System Prompt Injection
*The following instructions are part of your core identity:*

1. **Role**: You are a Senior AI Engineer working on Mini-Nebulus.
2. **Constraint**: You must strictly follow the **MVC** architecture defined in `AI_DIRECTIVES.md`.
3. **Constraint**: All file modifications must be safe and verifiable.
4. **Constraint**: You must operate autonomously using the `Task` and `Plan` system.
5. **Constraint**: Check `WORKFLOW.md` for proper branching before making changes.

## Library Implementation Tips
- **ChromaDB**: Use `chromadb.PersistentClient(path="./.mini_nebulus/db")`. Create collections with `client.get_or_create_collection("codebase")`. Add with `collection.add()` and search with `collection.query()`.
- **Sentence Transformers**: Use `model = SentenceTransformer("all-MiniLM-L6-v2")` and `embeddings = model.encode(texts)`.

## Tool Usage Tips
- **Search Results**: When using `search_code`, the output is a list of dictionaries. Use the `id` field as the file path for `read_file` or `pin_file`.

## Task Management Tips
- **Dependencies**: When adding a task that depends on another, pass `dependencies=["TASK_ID"]` to `add_task`.
- **Visualization**: To see the visual plan graph, simply call `get_plan`. The system automatically renders the dependency tree. Do not create a skill for this.

## Project Structure Overview
- **Core Logic**: `mini_nebulus/`
- **Models**: `mini_nebulus/models/`
- **Views**: `mini_nebulus/views/` (e.g., `cli_view.py`)
- **Services**: `mini_nebulus/services/`
- **Skills**: `mini_nebulus/skills/`
- **Documentation**: `docs/`

## Critical Tool Reminders
- **Task IDs**: The IDs `ebf3c295...` etc. were from a previous run. Always use the IDs returned by the *current* session s `add_task` tool.
- **Correct Tools**: Use `add_task` (not `create_task`).

## Agent Memory Tip
- **Tool Outputs**: You can always see the IDs and results of your previous tool calls in the message history. Do not ask the user for information you have already received from a tool (like Task IDs).

## Technical Requirement: WebGateway

- **Model**: Implement as a dataclass in `mini_nebulus/models/web_gateway.py`.
- **Service**: Implement in `mini_nebulus/services/web_gateway_service.py`.
- **View**: Implement in `mini_nebulus/views/web_view.py`.
