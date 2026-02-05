# Nebulus Atom

> A professional, autonomous AI engineer CLI powered by local LLMs.

Nebulus Atom is a lightweight CLI agent that interacts with a local LLM server (Nebulus, Ollama, TabbyAPI, vLLM) to assist with software engineering tasks. It includes **Nebulus Swarm**, a multi-agent orchestration system that autonomously processes GitHub issues at scale.

## Quick Start

```bash
# Clone and install
git clone git@github.com:jlwestsr/nebulus-atom.git
cd nebulus-atom
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure your LLM server
cp .env.example .env
# Edit .env with your server URL and model name

# Run
python3 -m nebulus_atom.main start
```

See the [Installation Guide](https://github.com/jlwestsr/nebulus-atom/wiki/Installation) for detailed setup instructions.

## Features

### Core Agent

- **Context Manager** - Pin files to active context for persistent awareness
- **Smart Undo** - Auto-checkpoints before risky operations with rollback
- **Skill Library** - Persistent, reusable capabilities across sessions
- **Semantic Code Search (RAG)** - ChromaDB-powered code search by meaning
- **Autonomous Execution** - Multi-turn execution without confirmation prompts
- **Agentic TDD** - Test-driven development cycle automation
- **Advanced Cognition** - "System 2" deeper reasoning for complex tasks
- **MCP Integration** - Model Context Protocol for external tool servers
- **Interactive Clarification** - Asks questions when requirements are ambiguous
- **Codebase Cartographer** - AST-based code structure analysis
- **Sandbox Execution** - Safe command execution with restricted file access
- **Flight Recorder Dashboard** - Streamlit telemetry dashboard

### Nebulus Swarm

- **Overlord** - Slack-driven control plane with natural language commands
- **Minions** - Containerized agents that clone repos, work issues, and create PRs
- **Model Router** - Routes simple tasks to 8B models, complex tasks to 30B
- **Swarm Dashboard** - Streamlit monitoring with live status, history, queue, and metrics
- **PR Reviewer** - Automated code review of minion-created pull requests
- **Clarifying Questions** - Minions ask humans via Slack when requirements are unclear
- **Cron Scheduling** - Automated queue sweeps on configurable schedules

## Architecture

```
nebulus-atom/
├── nebulus_atom/           # Core CLI agent (MVC)
│   ├── models/             # Data structures
│   ├── views/              # UI (Rich TUI)
│   ├── controllers/        # Orchestration
│   ├── services/           # LLM, RAG, Skills, MCP
│   └── main.py             # Entry point
├── nebulus_swarm/           # Multi-agent swarm
│   ├── overlord/            # Control plane
│   ├── minion/              # Worker agents
│   ├── dashboard/           # Streamlit monitoring
│   └── reviewer/            # PR review
└── tests/                   # 376 tests
```

## Commands

```bash
# Start the agent
python3 -m nebulus_atom.main start

# Start with a prompt
python3 -m nebulus_atom.main start "fix the login bug"

# Launch the dashboard
python3 -m nebulus_atom.main dashboard

# View embedded docs
python3 -m nebulus_atom.main docs list
```

## Swarm Usage

```bash
# Build and start the Overlord
docker build -t nebulus-overlord:latest -f nebulus_swarm/overlord/Dockerfile .
docker build -t nebulus-minion:latest -f nebulus_swarm/minion/Dockerfile .
docker compose -f docker-compose.swarm.yml up -d overlord
```

Then in Slack:
```
work on owner/repo#42
status
queue
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| CLI | Typer |
| UI | Rich |
| LLM Client | OpenAI SDK |
| Swarm | Docker, Slack Bolt, aiohttp |
| Dashboard | Streamlit |
| Database | SQLite, ChromaDB |
| Testing | pytest (376 tests) |

## Documentation

Full documentation is available on the [GitHub Wiki](https://github.com/jlwestsr/nebulus-atom/wiki):

- [Installation](https://github.com/jlwestsr/nebulus-atom/wiki/Installation)
- [Quick Start](https://github.com/jlwestsr/nebulus-atom/wiki/Quick-Start)
- [Architecture](https://github.com/jlwestsr/nebulus-atom/wiki/Architecture)
- [CLI Reference](https://github.com/jlwestsr/nebulus-atom/wiki/CLI-Reference)
- [Configuration](https://github.com/jlwestsr/nebulus-atom/wiki/Configuration)
- [Nebulus Swarm](https://github.com/jlwestsr/nebulus-atom/wiki/Nebulus-Swarm)
- [Deployment](https://github.com/jlwestsr/nebulus-atom/wiki/Deployment)
- [Testing](https://github.com/jlwestsr/nebulus-atom/wiki/Testing)
- [Contributing](https://github.com/jlwestsr/nebulus-atom/wiki/Contributing)

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt
pre-commit install

# Run tests
python3 -m pytest tests/ -v

# Git workflow (always use feature branches)
git checkout -b feat/my-feature
# ... make changes ...
git checkout develop
git merge feat/my-feature --no-ff
git push nebulus-atom develop
```

## License

See repository for license details.
