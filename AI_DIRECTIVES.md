# AI Directives for Mini-Nebulus

1. **Commit Messages**: Use Conventional Commits.
2. **Branching**: All work happens on `develop`. `main` is for stable releases.
3. **Coding Style**: Use modern JavaScript (ES6+) with ES Modules.
4. **Testing**: Manual testing via the CLI for now.

# Architecture Standards (v2.0 - Refactored)

We adhere to the **MVC (Model-View-Controller)** pattern for this Node.js CLI application, inspired by the Nebulus Gantry standards.

## Directory Structure
- **src/models/**: Data structures and state management (Config, History, ToolRegistry).
- **src/views/**: UI logic, prompts, and output formatting (CLIView).
- **src/controllers/**: Business logic and orchestration (AgentController).
- **src/services/**: External integrations (OpenAIService, ToolExecutor).

## Coding Standards
- **ES6 Modules**: Use `import`/`export` syntax.
- **Classes**: Encapsulate logic in classes.
- **Configuration**: Use `Config` model for env vars and constants.
- **State**: Manage state via the `History` model, not global variables.

## Source Control Standards

- **Strict Branching**: Always create a specific branch (`feat/`, `fix/`, `docs/`, `chore/`) for your work.
- **Local-Only Policy**: Do not push feature branches to remote. Merge them into `develop` locally, then push `develop`.
- **Commit Messages**: Strictly follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g., `feat: ...`, `fix: ...`).
- **Verification**: Ensure `npm start` runs successfully before merging to `develop`.
