# Nebulus Atom Project Context

## Project Overview
A lightweight CLI agent that interacts directly with a local Nebulus (Ollama) server, bypassing complex abstractions.

## Technical Stack
- **Language**: Python 3.12+ (type hints mandatory)
- **Framework**: Typer (CLI), Streamlit (Dashboard)
- **UI**: Rich
- **LLM Client**: OpenAI Python Library
- **Architecture**: Strict MVC with OOP/SOLID principles
- **Target Server**: http://localhost:5000/v1
- **Model**: Meta-Llama-3.1-8B-Instruct-exl2-8_0

## Entry Point
```bash
python3 -m nebulus_atom.main start
```

## Directory Structure
```
nebulus_atom/
├── models/       # Data structures (Pydantic/Dataclasses)
├── views/        # UI logic using rich
├── controllers/  # Orchestration logic
├── services/     # Integrations (OpenAI, Subprocess)
└── main.py       # Entry point
```

## Development Standards
- **Testing**: `pytest`
- **Linting**: `ruff` (enforced via pre-commit)
- **Commits**: Conventional Commits format
- **Async**: Use `async`/`await` for I/O operations

## Git Workflow (STRICT - MUST FOLLOW)
**NEVER commit directly to develop. ALWAYS use feature branches.**

Before ANY code changes:
```bash
git checkout -b <prefix>/<name>   # feat/, fix/, chore/, docs/
```

After changes are complete:
```bash
git checkout develop
git merge <branch> --no-ff -m "Merge branch '<branch>' into develop"
git branch -d <branch>
```

Push only `develop` to remote:
```bash
git push nebulus-atom develop
```

## Architecture Principles
- **SOLID**: Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion
- **Composition over Inheritance**
- **Dependency Injection**: Inject via `__init__`, not globals
- **Encapsulation**: Use `_variable` for private members, `@property` for access
- **Data Models**: Use `@dataclass` or Pydantic, avoid raw dicts
- **Interfaces**: Use `abc.ABC` and `abc.abstractmethod`

## Key Features
- **Context Manager**: Pin files to active context
- **Smart Undo**: Auto-checkpoints before risky operations
- **RAG**: Semantic code search using embeddings
- **Skill Library**: Persistent autonomous capabilities

## Project Influences
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) - Terminal UX
- [Get Shit Done](https://github.com/glittercowboy/get-shit-done) - Task-oriented approach
- [Moltbot](https://docs.molt.bot/start/getting-started) - Autonomous agent capabilities

## Reference Files
- `AI_DIRECTIVES.md` - Detailed coding and autonomy mandates
- `WORKFLOW.md` - Git workflow procedures
- `docs/features/` - Feature documentation
