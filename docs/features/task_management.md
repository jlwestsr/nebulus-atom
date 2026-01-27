# Feature: Persistent Task Management

## 1. Overview
**Branch**: `feat/persistent-tasks`

Currently, `TaskService` stores plans and tasks in memory. If the agent restarts, the plan is lost. This feature implements file-based persistence (JSON) so that the agent can resume long-running plans across sessions, maximizing the utility of the local LLM setup.

## 2. Requirements
- [ ] **Storage Location**: Store plans in `.mini_nebulus/sessions/<session_id>/plan.json`.
- [ ] **Auto-Save**: Automatically save the plan whenever a task is created, added, or updated.
- [ ] **Auto-Load**: Automatically load the existing plan for the session upon `TaskService` initialization.
- [ ] **Data Model**: Ensure `Plan` and `Task` objects can be serialized/deserialized cleanly.
- [ ] **Tools**: No new tools needed, but existing tools (`create_plan`, `add_task`, `update_task`) must trigger persistence.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/task_service.py`: Add `load()` and `save()` methods; hook them into modification methods.
    - `mini_nebulus/models/task.py`: Ensure `to_dict()` and `from_dict()` (or standard serialization) are robust.
- **Data**:
    - Directory structure: `.mini_nebulus/sessions/{session_id}/`

## 4. Verification Plan
**Automated Tests**:
- [ ] `tests/test_task_persistence.py`:
    - Create a plan.
    - Assert file exists on disk.
    - Re-instantiate `TaskService`.
    - Assert plan is loaded correctly.

**Manual Verification**:
- [ ] Run `python -m mini_nebulus.main start --tui`.
- [ ] Ask: "Create a plan to count to 3".
- [ ] Exit the app (`Ctrl+C`).
- [ ] Restart the app.
- [ ] Verify the Plan Tree still shows the plan.

## 5. Workflow Checklist
- [ ] **Branch**: `feat/persistent-tasks`
- [ ] **Work**: Implemented changes
- [ ] **Test**: `pytest` passes
- [ ] **Doc**: Updated docs if needed
- [ ] **Merge**: `develop`
