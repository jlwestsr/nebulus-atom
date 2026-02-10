# Nebulus Atom

![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)
![Version](https://img.shields.io/badge/version-2.3.0-green.svg)
![Tests](https://img.shields.io/badge/tests-1247%20passing-brightgreen.svg)
![License](https://img.shields.io/badge/license-proprietary-red.svg)

> **v2.3.0** - A professional, autonomous AI engineer CLI powered by local LLMs for GitHub automation, code generation, and multi-agent orchestration.

Nebulus Atom is a privacy-first, self-hosted AI coding assistant and autonomous software engineering agent. It connects to local LLM servers (Nebulus Prime, Nebulus Edge, Ollama, TabbyAPI, vLLM) to provide intelligent code assistance, automated GitHub issue processing, and multi-agent task orchestration. Perfect for developers who want AI-powered coding tools without cloud dependencies.

**Key capabilities**: Autonomous code generation • GitHub issue automation • Multi-agent swarm orchestration • Local RAG code search • TDD automation • Docker-based minion dispatch • Cross-project dependency analysis • Slack-controlled daemon mode • Proactive monitoring • Approval workflows • Test-driven development • CI/CD integration

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

### Nebulus Swarm (Multi-Agent Orchestration)

**Meta-Orchestration (Phase 1-2)**
- **Project Registry** - Multi-repo discovery with dependency tracking via `overlord.yml`
- **Health Scanner** - Git state monitoring, test health, and commit tracking across projects
- **Dependency Graph** - DAG analysis, blast radius calculation, and impact assessment
- **Action Scope** - Change categorization and autonomy suitability scoring
- **Cross-Project Memory** - SQLite-backed observation store with search and pruning
- **Autonomy Engine** - Confidence-based auto-dispatch with test health correlation

**Slack + Background Mode (Phase 3)**
- **Slack Command Router** - Multi-project commands: status, scan, merge, release, autonomy, memory
- **Proposal Manager** - Approval lifecycle with Slack thread binding (propose/approve/deny/execute)
- **Background Daemon** - Persistent process with croniter-based scheduled sweeps
- **Proactive Detectors** - Stale branch, ahead-of-main, and failing test detection
- **Notification System** - Urgent alerts and daily digest with category-based routing

**Control Plane (Phase 0)**
- **Overlord** - Slack-driven control plane with natural language commands via LLM parsing
- **Minions** - Containerized Docker agents that clone repos, work issues, and create PRs
- **Model Router** - Complexity-based model selection (8B for simple, 30B+ for complex)
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
│   ├── overlord/            # Meta-orchestrator & control plane
│   │   ├── registry.py         # Project discovery & dependencies
│   │   ├── scanner.py          # Git state & health monitoring
│   │   ├── graph.py            # Dependency graph & blast radius
│   │   ├── memory.py           # Cross-project observations
│   │   ├── autonomy.py         # Confidence scoring & dispatch
│   │   ├── slack_commands.py   # Multi-project Slack commands
│   │   ├── proposal_manager.py # Approval workflow lifecycle
│   │   ├── overlord_daemon.py  # Background daemon & scheduler
│   │   ├── detectors.py        # Proactive issue detection
│   │   ├── notifications.py    # Alerts & daily digest
│   │   └── main.py             # Slack/Docker/State control
│   ├── minion/              # Worker agents
│   ├── dashboard/           # Streamlit monitoring
│   └── reviewer/            # PR review
└── tests/                   # 1247 tests
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

### Overlord Daemon (Phase 3)

```bash
# Start the background daemon with scheduled sweeps
nebulus-atom overlord daemon start

# Slack commands (in #nebulus-ops channel)
@atom status              # Ecosystem health
@atom scan core           # Deep scan a project
@atom merge core develop to main  # Propose a merge (requires approval)
@atom help                # List all commands
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| CLI | Typer |
| UI | Rich (Terminal UI) |
| LLM Client | OpenAI SDK |
| Vector DB | ChromaDB (RAG embeddings) |
| Swarm | Docker, Slack Bolt, aiohttp |
| Dashboard | Streamlit |
| Database | SQLite, ChromaDB |
| Testing | pytest (1247 tests) |
| CI/CD | pre-commit hooks, ruff |

## Documentation

Full documentation is available on the [GitHub Wiki](https://github.com/jlwestsr/nebulus-atom/wiki):

**Getting Started**
- [Installation](https://github.com/jlwestsr/nebulus-atom/wiki/Installation)
- [Quick Start](https://github.com/jlwestsr/nebulus-atom/wiki/Quick-Start)
- [Configuration](https://github.com/jlwestsr/nebulus-atom/wiki/Configuration)

**Core System**
- [Architecture](https://github.com/jlwestsr/nebulus-atom/wiki/Architecture)
- [CLI Reference](https://github.com/jlwestsr/nebulus-atom/wiki/CLI-Reference)
- [Features](https://github.com/jlwestsr/nebulus-atom/wiki/Features)

**Nebulus Swarm**
- [Nebulus Swarm Overview](https://github.com/jlwestsr/nebulus-atom/wiki/Nebulus-Swarm)
- [Swarm Overlord](https://github.com/jlwestsr/nebulus-atom/wiki/Swarm-Overlord)
- [Overlord CLI Reference](https://github.com/jlwestsr/nebulus-atom/wiki/Overlord-CLI)
- [Swarm Minion](https://github.com/jlwestsr/nebulus-atom/wiki/Swarm-Minion)
- [Swarm Dashboard](https://github.com/jlwestsr/nebulus-atom/wiki/Swarm-Dashboard)
- [Model Router](https://github.com/jlwestsr/nebulus-atom/wiki/Model-Router)

**Operations**
- [Deployment](https://github.com/jlwestsr/nebulus-atom/wiki/Deployment)
- [Testing](https://github.com/jlwestsr/nebulus-atom/wiki/Testing)
- [Troubleshooting](https://github.com/jlwestsr/nebulus-atom/wiki/Troubleshooting)
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

## Use Cases

- **Autonomous GitHub Issue Processing** - Deploy minions to work on labeled issues automatically
- **Multi-Repo Management** - Track dependencies, blast radius, and health across project ecosystems
- **Local AI Development** - Privacy-first coding assistant without cloud dependencies
- **CI/CD Integration** - Automated testing, code review, and PR generation
- **Code Search & RAG** - Semantic code search powered by ChromaDB embeddings
- **TDD Automation** - Test-driven development cycle with autonomous test writing and fixing

## Topics

`ai-coding-assistant` `autonomous-agent` `github-automation` `local-llm` `self-hosted-ai` `multi-agent-system` `docker-orchestration` `slack-bot` `code-generation` `test-automation` `rag` `chromadb` `ollama` `tabbyapi` `mlx` `python-cli` `typer` `streamlit` `dependency-graph` `ci-cd-automation` `issue-automation` `pr-automation` `code-review` `tdd` `swarm-intelligence` `meta-orchestration`

## License

See repository for license details.
