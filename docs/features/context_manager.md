# Feature: Context Manager (File Pinning)

## 1. Overview
**Branch**: `feat/context-manager`

Implement a system to "pin" specific files or directories to the agent's active context. This ensures critical file contents are always visible to the LLM without requiring repetitive `read_file` calls, improving efficiency for complex refactoring tasks.

## 2. Requirements
List specific, testable requirements:
- [ ] User can pin a file using `pin_file <path>`.
- [ ] User can unpin a file using `unpin_file <path>`.
- [ ] User can list currently pinned files using `list_context`.
- [ ] Pinned file content is automatically injected into the System Prompt or context window.
- [ ] System checks for token limits and warns or truncates if pinned content is too large.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/models/history.py` (Update to store pinned paths).
    - `mini_nebulus/controllers/agent_controller.py` (Update context injection logic).
    - `mini_nebulus/services/context_service.py` (New service for managing pins).
- **Dependencies**: None.
- **Data**: In-memory state within `History` or `ContextService`.

## 4. Verification Plan
**Automated Tests**:
- [ ] Script/Test: `pytest tests/test_context_manager.py`
- [ ] Logic Verified: Verify that `pin_file` adds to state and `unpin_file` removes it. Verify context injection string construction.

**Manual Verification**:
- [ ] Step 1: Run `mini-nebulus start`
- [ ] Step 2: Execute `pin_file README.md`
- [ ] Step 3: Ask "What is in the pinned file?" without using `read_file` tool.
- [ ] Step 4: Verify the agent answers correctly based on context.

## 5. Workflow Checklist
Follow the AI Behavior strict workflow:
- [ ] **Branch**: Created `feat/context-manager` branch?
- [ ] **Work**: Implemented changes?
- [ ] **Test**: All tests pass (`pytest`)?
- [ ] **Doc**: Updated `README.md` and `walkthrough.md`?
- [ ] **Data**: `git add .`, `git commit`, `git push`?
