# AI Directives for Nebulus Atom

# Autonomy Mandates
1. **Autonomous Implementation**: Once a task is IN_PROGRESS, execute it immediately.
2. **No Permission needed**: Do NOT ask for permission to write individual files or run standard shell commands if they are part of the active plan.
3. **JSON Tool Output**: ALWAYS output tool calls in JSON. NEVER just print code blocks without using a tool to save them.

1. **Commit Messages**: Use Conventional Commits.
2. **Branching**: All work happens on `develop`. `main` is for stable releases.
3. **Coding Style**: Python 3.12+ with Type Hinting.
4. **Testing**: `pytest` for unit tests.
5. **Linting**: `ruff` is enforced via pre-commit.

# Architecture Standards (v3.0 - Python MVC)

We adhere to the **MVC (Model-View-Controller)** pattern for this Python CLI application.

## Directory Structure
- **nebulus_atom/models/**: Data structures (Pydantic/Dataclasses).
- **nebulus_atom/views/**: UI logic using `rich`.
- **nebulus_atom/controllers/**: Orchestration logic.
- **nebulus_atom/services/**: Integrations (OpenAI, Subprocess).

## Coding Standards
- **Type Hints**: Mandatory for all function signatures.
- **AsyncIO**: Use `async`/`await` for I/O operations.
- **Configuration**: Use `config.py` for env vars.

## Python OOP Best Practices
- **SOLID Principles**: Adhere to Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, and Dependency Inversion.
- **Composition over Inheritance**: Prefer object composition to achieve code reuse and flexibility.
- **Dependency Injection**: Inject dependencies (e.g., services, config) via `__init__` rather than instantiating them internally or using globals.
- **Encapsulation**: Protect internal state. Use `_variable` naming convention for internal/private members. Use properties (`@property`) for controlled access.
- **Data Models**: Use `@dataclass` (standard library) or `Pydantic` models for data-centric classes. Avoid raw dictionaries for internal state.
- **Interfaces**: Use `abc.ABC` and `abc.abstractmethod` to define clear interfaces for Services and interchangeable components.

## Source Control Standards

- **Strict Branching**: Always create a specific branch (`feat/`, `fix/`, `docs/`, `chore/`) for your work.
- **Local-Only Policy**: Do not push feature branches to remote. Merge them into `develop` locally, then push `develop`.
- **Commit Messages**: Strictly follow [Conventional Commits](https://www.conventionalcommits.org/).
- **Verification**: Ensure `pre-commit run --all-files` passes.

# Strict Execution Protocol
1. **Stop Talking, Start Coding**: If you describe a technical step, you MUST execute it in the same turn using a tool.
2. **Assume Approval**: Once a plan is confirmed, you have full approval to implement all tasks. Do not ask "Should I proceed?" or "Is this okay?". Just do it.

# Strict Execution Protocol
1. **Stop Talking, Start Coding**: If you describe a technical step, you MUST execute it in the same turn using a tool.
2. **Assume Approval**: Once a plan is confirmed, you have full approval to implement all tasks. Do not ask "Should I proceed?" or "Is this okay?". Just do it.

## Communication Standards
- **Prompt Delivery**: When suggesting a prompt for the user to run, ALWAYS wrap it in a code block under a "Proposed Prompt" header. This facilitates easy copy/pasting.
