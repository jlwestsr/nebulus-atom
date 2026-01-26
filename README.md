# Mini-Nebulus

## Context Manager Feature
The Context Manager allows users to "pin" files to the agent s active context. This ensures the agent is always aware of the content of these files without needing to read them repeatedly.

### Commands
- `pin_file <path>`: Pin a file to the active context.
- `unpin_file <path>`: Unpin a file.
- `list_context`: List all currently pinned files.

### Token Limits
The system automatically manages context size. If pinned files exceed the token limit (approx 32,000 characters), content will be truncated to ensure the agent functions correctly.
