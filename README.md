# Mini-Nebulus

A professional, lightweight AI agent CLI built with Python, designed for autonomy and extensibility.

## Architecture

Built on the **Nebulus Gantry** standards using a strict **MVC** architecture with a decoupled Gateway interface.

- **Models**: `mini_nebulus/models/` (History, Tasks, Plans)
- **Views**: `mini_nebulus/views/` (CLI, Discord, Base)
- **Controllers**: `mini_nebulus/controllers/` (Agent Logic)
- **Services**: `mini_nebulus/services/` (Skills, Tools, Files)
- **Gateways**: `mini_nebulus/gateways/` (Discord Bot)

## Prerequisites

- Python 3.12+
- `venv` or `uv`
- Local Nebulus/Ollama server running

## Setup

1. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure `.env`:
   ```env
   NEBULUS_BASE_URL=http://nebulus:11434/v1
   NEBULUS_API_KEY=any
   NEBULUS_MODEL=qwen2.5-coder:latest
   DISCORD_TOKEN=your_token_here  # Optional: For Discord Gateway
   ```

## Features (Implemented)

*   **Autonomous Mission Mode**: Break complex goals into Plans and Tasks (`create_plan`, `add_task`).
*   **Dynamic Skills**: The agent can write its own tools (`create_skill`) and hot-load them at runtime from `mini_nebulus/skills/`.
*   **Rich Terminal UI**: Polished CLI experience with spinners, panels, and syntax highlighting.
*   **Gateway Architecture**: Decoupled design supporting both CLI and Discord interfaces.
*   **Safe File Ops**: Dedicated `read_file`, `write_file`, and `list_dir` tools.

## Usage

### CLI Agent
Start the agent in interactive mode:
```bash
python3 -m mini_nebulus.main start
```

Or with an initial prompt:
```bash
python3 -m mini_nebulus.main start "Create a plan to audit the codebase"
```

### Discord Bot
To run the agent as a Discord bot:
```python
# Create run_discord.py
import os
from mini_nebulus.controllers.agent_controller import AgentController
from mini_nebulus.gateways.discord_gateway import DiscordGateway

if __name__ == "__main__":
    bot = DiscordGateway(AgentController())
    bot.run(os.getenv("DISCORD_TOKEN"))
```

## Development

- **Linting**: `pre-commit run --all-files` (Uses `ruff`)
- **Format**: `ruff format`

## Feature Roadmap
The following features are planned for future development. See `docs/features/` for detailed specifications.

- **[Context Manager](docs/features/context_manager.md)**: File pinning for persistent context.
- **[Smart Undo](docs/features/smart_undo.md)**: Transactional filesystem with rollback.
- **[Interactive Clarification](docs/features/interactive_clarification.md)**: Human-in-the-loop support.
- **[Skill Library](docs/features/skill_library.md)**: Persistent and global skill sharing.
- **[Visual Task Graph](docs/features/visual_task_graph.md)**: Visualization of complex task dependencies.
