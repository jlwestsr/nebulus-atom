# AI Directives for Mini-Nebulus

1. **Commit Messages**: Use Conventional Commits.
2. **Branching**: All work happens on `develop`. `main` is for stable releases.
3. **Coding Style**: Python 3.12+ with Type Hinting.
4. **Testing**: `pytest` for unit tests.
5. **Linting**: `ruff` is enforced via pre-commit.

# Architecture Standards (v3.0 - Python MVC)

We adhere to the **MVC (Model-View-Controller)** pattern for this Python CLI application.

## Directory Structure
- **mini_nebulus/models/**: Data structures (Pydantic/Dataclasses).
- **mini_nebulus/views/**: UI logic using `rich`.
- **mini_nebulus/controllers/**: Orchestration logic.
- **mini_nebulus/services/**: Integrations (OpenAI, Subprocess).

## Coding Standards
- **Type Hints**: Mandatory for all function signatures.
- **AsyncIO**: Use `async`/`await` for I/O operations.
- **Configuration**: Use `config.py` for env vars.

## Source Control Standards

- **Strict Branching**: Always create a specific branch (`feat/`, `fix/`, `docs/`, `chore/`) for your work.
- **Local-Only Policy**: Do not push feature branches to remote. Merge them into `develop` locally, then push `develop`.
- **Commit Messages**: Strictly follow [Conventional Commits](https://www.conventionalcommits.org/).
- **Verification**: Ensure `pre-commit run --all-files` passes.
