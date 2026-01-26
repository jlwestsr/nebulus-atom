# Feature: CLI Packaging (Global Install)

## 1. Overview
**Branch**: `feat/cli-packaging`

Package Mini-Nebulus as a proper Python CLI tool that can be installed globally (e.g., `pip install .` or `pipx install .`). This allows the user to open a terminal in any project directory and run `mini-nebulus` (or alias `mn`) to start the agent in that context.

## 2. Requirements
- [x] Make the project installable via `pyproject.toml` (or `setup.py`).
- [x] Define entry points for the CLI command `mini-nebulus` and `mn`.
- [x] Ensure the agent uses `os.getcwd()` as the project root, not the package installation directory.
- [x] Ensure `.env` is loaded from the current working directory (or user home), not the package dir.
- [x] Ensure `CONTEXT.md` is looked for in the current working directory.

## 3. Technical Implementation
- **Modules**:
    - `pyproject.toml`: Define `project.scripts` section.
    - `mini_nebulus/main.py`: Ensure `typer` app is exposed correctly as an entry point function.
    - `mini_nebulus/config.py`: Update logic to look for `.env` in `os.getcwd()` first.
    - `mini_nebulus/services/file_service.py`: Verify path resolution uses CWD.
- **Dependencies**: `setuptools`, `wheel` (standard build tools).
- **Data**: None.

## 4. Verification Plan
- [x] Run `pip install -e .` in the project root.
- [x] Open a new terminal tab (or change dir).
- [x] Run `mini-nebulus --help`.
- [x] Verify it runs and shows the help message.
- [x] Go to a test folder with `CONTEXT.md`.
- [x] Run `mn start "Analyze this folder"`.
- [x] Verify it reads the local `CONTEXT.md`.

## 5. Workflow Checklist
- [x] Create branch `feat/cli-packaging`
- [x] Implementation
- [x] Verification
