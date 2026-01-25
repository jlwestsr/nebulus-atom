# Feature: Smart Undo (Transactional Filesystem)

## 1. Overview
**Branch**: `feat/smart-undo`

Provide a safety net for autonomous operations by creating restore points before risky changes. This allows the user or agent to rollback changes if a plan fails or corrupts the codebase, utilizing a transactional approach.

## 2. Requirements
List specific, testable requirements:
- [ ] Agent automatically creates a checkpoint (backup) before overwriting any file via `write_file`.
- [ ] Agent automatically creates a checkpoint before running shell commands that modify the filesystem.
- [ ] User can manually trigger `create_checkpoint`.
- [ ] User can trigger `rollback_checkpoint` to restore the state to the last safe point.
- [ ] The system uses Git stash or a hidden backup directory without interfering with user's manual Git workflow.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/checkpoint_service.py` (New service).
    - `mini_nebulus/services/tool_executor.py` (Integrate checkpoint hook before execution).
- **Dependencies**: Git (system requirement).
- **Data**: `.git/` operations or `.mini_nebulus/backups/`.

## 4. Verification Plan
**Automated Tests**:
- [ ] Script/Test: `pytest tests/test_smart_undo.py`
- [ ] Logic Verified:
    - Create a file -> Checkpoint -> Modify file -> Rollback -> Verify original content.
    - Verify multiple checkpoints work (stack).

**Manual Verification**:
- [ ] Step 1: Run `mini-nebulus start`
- [ ] Step 2: Ask agent to "Overwrite README.md with 'BROKEN'"
- [ ] Step 3: Verify it did so.
- [ ] Step 4: Run `rollback_checkpoint`.
- [ ] Step 5: Verify `README.md` is restored.

## 5. Workflow Checklist
Follow the AI Behavior strict workflow:
- [ ] **Branch**: Created `feat/smart-undo` branch?
- [ ] **Work**: Implemented changes?
- [ ] **Test**: All tests pass (`pytest`)?
- [ ] **Doc**: Updated `README.md` and `walkthrough.md`?
- [ ] **Data**: `git add .`, `git commit`, `git push`?
