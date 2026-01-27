# UI Regression Test Prompts

This document contains a standardized set of prompts for manually verifying the **Mini-Nebulus** CLI agent's core capabilities.

## Usage
Run these prompts interactively to ensure the agent correctly identifies and executes the appropriate tools.

## Core Feature Tests

| Feature | Test Prompt | Expected Behavior |
| :--- | :--- | :--- |
| **1. Task Management** | "Create a plan to learn about this project. Add a task to read the context file." | Creates a plan (`create_plan` or similar), then adds a task to it. |
| **2. Context Management** | "Pin the file 'CONTEXT.md' to the context and then list the current context." | Calls `pin_file` on `CONTEXT.md`, then calls `list_context`. |
| **3. File Operations** | "List the files in the 'mini_nebulus' directory using a shell command." | Calls `run_shell_command` with `ls -F mini_nebulus` (or equivalent). |
| **4. Skill Execution** | "Use the file_info skill to check the size of 'mini_nebulus/main.py'." | Identifies and executes the `file_info` skill. |
| **5. RAG / Search** | "Search the codebase for 'AgentController' and tell me which file it is in." | Calls `search_code` (or `grep_search`) to locate the string. |
| **6. File I/O** | "Write a file named 'test_hello.txt' with the content 'Hello World'." | Calls `write_file` to create the artifact. |

## Integrated Workflows

### Audit Workflow
**Prompt:**
> "Create a comprehensive plan to audit the 'mini_nebulus' directory. FIRST, use a shell command to list the files in that directory. SECOND, use the 'file_info' skill to inspect the 'mini_nebulus/main.py' file. FINALLY, write a summary of what you found to 'audit_summary.txt'."

**Expected Sequence:**
1.  **Plan**: Creates a multi-step plan.
2.  **List**: Executes `ls` via shell.
3.  **Inspect**: Uses `file_info` skill.
4.  **Report**: Writes summary to `audit_summary.txt`.
