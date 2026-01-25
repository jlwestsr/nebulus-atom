# Mini-Nebulus

A lightweight, custom AI agent CLI for Nebulus, designed with a strict MVC architecture and robust local tool integration.

## Features

- **Local Execution**: Runs entirely on your machine, connecting to a local Nebulus/Ollama server.
- **System Tools**: Can execute shell commands (`ls`, `git`, etc.) autonomously.
- **Smart CLI**:
  - Interactive chat mode.
  - "Fire and forget" initial prompt via arguments.
  - Spinner feedback (`ora`) and colored output (`chalk`).
- **Robustness**: Advanced JSON extraction to handle various LLM output formats.

## Architecture

This project follows a strict **Model-View-Controller (MVC)** pattern:

```text
src/
├── controllers/   # AgentController (Orchestration)
├── models/        # Config, History, ToolRegistry
├── services/      # OpenAIService, ToolExecutor
├── views/         # CLIView (Input/Output)
└── index.js       # Entry Point
```

## Setup & Development

### Prerequisites
- Node.js (v18+)
- Python 3.12+ (for pre-commit hooks)
- Local Nebulus/Ollama instance running on `http://nebulus:11434`

### Installation

1.  **Install Node dependencies:**
    ```bash
    npm install
    ```

2.  **Setup Development Environment (Python Venv & Pre-commit):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install pre-commit
    pre-commit install
    ```

### Running

**Interactive Mode:**
```bash
npm start
```

**Single Command Mode:**
```bash
npm start -- "List files in the current directory"
```

## Source Control Workflow

- **Branching**: All work happens on local `feat/`, `fix/`, or `chore/` branches.
- **Merging**: Merge into `develop`.
- **Commits**: Follow [Conventional Commits](https://www.conventionalcommits.org/).

## References
- [Nebulus (Ollama) Local Server](http://nebulus:11434)
- [Clawdbot](https://github.com/clawdbot/clawdbot) (Inspiration)
