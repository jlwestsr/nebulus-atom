# UI Regression Test Prompts

This document contains a standardized set of prompts for manually verifying the **Mini-Nebulus** CLI agent's capabilities.

## Usage
Run these prompts interactively (e.g., `python -m mini_nebulus.main start --tui`) to ensure the agent correctly identifies and executes the appropriate tools.

## Core Features (Legacy)

| Feature | Test Prompt | Expected Behavior |
| :--- | :--- | :--- |
| **1. Task Management** | "Create a plan to learn about this project. Add a task to read the context file." | Creates a plan (`create_plan`), then adds a task. |
| **2. Context Management** | "Pin the file 'CONTEXT.md' to the context and then list the current context." | Calls `pin_file` on `CONTEXT.md`, then `list_context`. |
| **3. File Operations** | "List the files in the 'mini_nebulus' directory using a shell command." | Calls `run_shell_command` with `ls` (or equivalent). |
| **4. Skill Execution** | "Use the file_info skill to check the size of 'mini_nebulus/main.py'." | Identifies and executes the `file_info` skill. |
| **5. RAG / Search** | "Search the codebase for 'AgentController' and tell me which file it is in." | Calls `search_code` to locate the string. |
| **6. File I/O** | "Write a file named 'test_hello.txt' with the content 'Hello World'." | Calls `write_file` to create the artifact. |

## New Features (v2.0)

### 1. Interactive Dashboard (TUI)
**Prompt:** (Run with `--tui`)
> "What is your current plan?"
**Verification:**
- Check if the chat history scrolls correctly.
- Check if the Sidebar (Plan/Context) updates if you add a task (e.g. "Add a task to check the time").

### 2. Session Journal (Daily Standup)
**Prompt:**
> "Generate a journal for this session."
**Verification:**
- Agent calls `generate_journal`.
- Check `.mini_nebulus/journals/` for a new Markdown file containing your recent interactions.

### 3. Codebase Cartographer (AST)
**Prompt:**
> "Map the codebase structure for the 'mini_nebulus' directory."
**Verification:**
- Agent calls `map_codebase(target_dir="mini_nebulus")`.
- Output should list classes and functions (e.g., `AgentController`, `process_turn`).

### 4. Shell Macro Generator
**Prompt:**
> "Create a shell macro named 'list_python' that lists all python files in the current directory."
**Verification:**
- Agent calls `create_macro(name="list_python", commands=["find . -name "*.py""])`.
- Check `~/.mini_nebulus/macros/list_python.sh` exists and is executable.

### 5. Agentic TDD Loop
**Prompt:**
> "Start a TDD loop to implement a function 'multiply(a, b)'."
**Verification:**
- Agent calls `start_tdd(goal="Implement multiply(a, b)")`.
- Observe the agent autonomously:
    1.  Create `tests/test_multiply.py` (failing).
    2.  Run the test (fail).
    3.  Create/Update `multiply.py`.
    4.  Run the test (pass).

### 6. GitHub Integration (MCP)
**Prompt:**
> "Connect to the GitHub MCP server and list my open issues."
**Verification:**
- Agent calls `connect_mcp_server`.
- Agent calls `github_list_issues` (or similar discovered tool).
- Output should reflect real GitHub data (requires `GITHUB_TOKEN`).

### 7. Multimodal Input
**Prompt:**
> "Scan the image 'test_image.png'." (Ensure you have a dummy image first)
**Verification:**
- Agent calls `scan_image(path="test_image.png")`.
- Returns base64 encoded string.

### 8. Embedded Documentation
**Prompt:**
> "List the available documentation."
**Verification:**
- Agent calls `list_docs`.
- Output lists files in `docs/`.

### 9. Persistent Tasks
**Prompt:**
> "Create a plan to 'Test Persistence'." -> Exit -> Restart.
**Verification:**
- Upon restart, the Plan sidebar should automatically populate with "Test Persistence".

## Integrated Workflow: "The Architect"

**Prompt:**
> "I want to understand the 'TaskService'. First, map the codebase to find where it is defined. Second, search the docs for 'Task Management'. Finally, generate a journal of this research."

**Expected Sequence:**
1.  `map_codebase` (finds `mini_nebulus/services/task_service.py`).
2.  `read_doc` (reads `docs/features/task_management.md`).
3.  `generate_journal` (saves the summary).
