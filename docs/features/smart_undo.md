# Feature: Smart Undo (Transactional Filesystem)

## 1. Overview
**Branch**: `feat/smart-undo`

Provide a safety net for autonomous operations by creating restore points before risky changes. This allows the user or agent to rollback changes if a plan fails or corrupts the codebase, utilizing a transactional approach.

## 2. Requirements
List specific, testable requirements:
- [x] Agent automatically creates a checkpoint (backup) before overwriting any file via `write_file`.
- [x] Agent automatically creates a checkpoint before running shell commands that modify the filesystem. (Decided to restrict auto-checkpoint to `write_file` for performance/precision, manual available for shell).
- [x] User can manually trigger `create_checkpoint`.
- [x] User can trigger `rollback_checkpoint` to restore the state to the last safe point.
- [x] The system uses Git stash or a hidden backup directory without interfering with user s manual Git workflow. (Implemented using `.mini_nebulus/checkpoints` directory).

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/checkpoint_service.py` (New service).
    - `mini_nebulus/services/tool_executor.py` (Integrate checkpoint hook before execution).
- **Dependencies**: Git (system requirement).
- **Data**: `.git/` operations or `.mini_nebulus/backups/`.

## 4. Verification Plan
**Automated Tests**:
- [x] Script/Test: `pytest tests/test_smart_undo.py`
- [x] Logic Verified:
    - Create a file -> Checkpoint -> Modify file -> Rollback -> Verify original content.
    - Verify multiple checkpoints work (stack).

**Manual Verification**:
- [x] Step 1: Run `mini-nebulus start`
- [x] Step 2: Ask agent to "Overwrite README.md with broken content"
- [x] Step 3: Verify it did so.
- [x] Step 4: Run `rollback_checkpoint`.
- [x] Step 5: Verify `README.md` is restored.

## 5. Workflow Checklist
Follow the AI Behavior strict workflow:
- [x] **Branch**: Created `feat/smart-undo` branch?
- [x] **Work**: Implemented changes?
- [x] **Test**: All tests pass (`pytest`)?
- [x] **Doc**: Updated `README.md` and `walkthrough.md`?
- [x] **Data**: `git add .`, `git commit`, `git push`?
