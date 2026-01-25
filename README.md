# Mini-Nebulus

A professional, lightweight AI agent CLI built with Python.

## Architecture

Built on the **Nebulus Gantry** standards using a strict **MVC** architecture.

- **Models**: `mini_nebulus/models/`
- **Views**: `mini_nebulus/views/`
- **Controllers**: `mini_nebulus/controllers/`
- **Services**: `mini_nebulus/services/`

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
   ```

## Usage

Start the agent:
```bash
python3 -m mini_nebulus.main start
```

Or with an initial prompt:
```bash
python3 -m mini_nebulus.main start "Check disk usage"
```

## Development

- **Linting**: `pre-commit run --all-files` (Uses `ruff`)
- **Format**: `ruff format`
