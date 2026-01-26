# Mini-Nebulus

## Context Manager Feature
The Context Manager allows users to "pin" files to the agent s active context. This ensures the agent is always aware of the content of these files without needing to read them repeatedly.

### Commands
- `pin_file <path>`: Pin a file to the active context.
- `unpin_file <path>`: Unpin a file.
- `list_context`: List all currently pinned files.

### Token Limits
The system automatically manages context size. If pinned files exceed the token limit (approx 32,000 characters), content will be truncated to ensure the agent functions correctly.

## Interactive Clarification
The agent can now pause execution to ask for user input using the `ask_user` tool. This enables a Human-in-the-Loop workflow where the agent can resolve ambiguities dynamically.

## Smart Undo
The agent protects your files by automatically creating checkpoints before risky operations (like `write_file`).
- **Auto-Checkpoint**: Triggered before file overwrites.
- **Manual Tools**:
    - `create_checkpoint(label)`: Snapshot the project.
    - `rollback_checkpoint(id)`: Restore project to a previous state.
    - `list_checkpoints()`: View available backups.
