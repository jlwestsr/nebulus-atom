# Feature: Session Journal (Daily Standup)

## 1. Overview
**Branch**: `feat/session-journal`

Generates a human-readable markdown summary of what was accomplished during a session (Tasks completed, Files changed, decisions made). It turns the "black box" of agent activity into a useful "Standup Report" for the user.

## 2. Requirements
- [ ] **Activity Tracking**: Record high-level events (Task Completion, File Edits, User Interactions).
- [ ] **Summary Generation**: Generate a Markdown report at the end of a session (or on demand).
- [ ] **Persistence**: Save journals to `.mini_nebulus/journals/YYYY-MM-DD.md`.
- [ ] **Tool Integration**: Add `generate_journal` tool.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/journal_service.py`: Service to aggregate `History` and `Task` data.
    - `mini_nebulus/models/history.py`: Potentially add metadata to turns for easier summarization.
    - `mini_nebulus/services/tool_executor.py`: Add `generate_journal`.
- **Dependencies**: None.
- **Data**: Journal files.

## 4. Verification Plan
**Automated Tests**:
- [ ] `tests/test_journal_service.py`:
    - Simulate a session with 1 completed task and 1 file edit.
    - Call generation.
    - Verify the markdown string contains the task description and file path.

**Manual Verification**:
- [ ] Run `mini-nebulus start`.
- [ ] Perform some actions.
- [ ] Run `generate_journal`.
- [ ] Read the output file.

## 5. Workflow Checklist
- [ ] **Branch**: Created `feat/session-journal` branch?
- [ ] **Work**: Implemented changes?
- [ ] **Test**: All tests pass (`pytest`)?
- [ ] **Doc**: Updated `README.md`?
- [ ] **Data**: `git add .`, `git commit`?
