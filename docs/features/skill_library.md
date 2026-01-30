# Feature: Skill Library (Persistent Skills)

## 1. Overview
**Branch**: `feat/skill-library`

Expand the "Skill System" to allow generated skills to be persisted, categorized, and reused across different sessions or even different projects globally.

## 2. Requirements
List specific, testable requirements:
- [x] Skills created via `create_skill` are stored persistently.
- [x] Users can `publish_skill` to move a local project skill to a global user library (e.g., `~/.nebulus_atom/skills`).
- [x] `list_skills` displays both project-specific and global skills. (Implemented implicitly by `load_skills` combining them).
- [x] The agent can load and use global skills in any directory.
- [x] Skills are namespaced to avoid conflicts (e.g., `global.calculator`).

## 3. Technical Implementation
- **Modules**:
    - `nebulus_atom/services/skill_service.py` (Update `load_skills` to scan multiple paths).
    - `nebulus_atom/config.py` (Add `GLOBAL_SKILLS_PATH` configuration).
- **Dependencies**: None.
- **Data**: Filesystem storage at `~/.nebulus_atom/skills/`.

## 4. Verification Plan
**Automated Tests**:
- [x] Script/Test: `pytest tests/test_skill_library.py`
- [x] Logic Verified:
    - Create local skill -> Publish -> Verify file exists in global dir.
    - Start new session in different dir -> Verify global skill is loaded.

**Manual Verification**:
- [x] Step 1: Run `nebulus-atom start`
- [x] Step 2: Create a skill "hello_world".
- [x] Step 3: Run `publish_skill hello_world`.
- [x] Step 4: Change directory and start agent.
- [x] Step 5: Ask agent to use "hello_world".

## 5. Workflow Checklist
Follow the AI Behavior strict workflow:
- [x] **Branch**: Created `feat/skill-library` branch?
- [x] **Work**: Implemented changes?
- [x] **Test**: All tests pass (`pytest`)?
- [x] **Doc**: Updated `README.md` and `walkthrough.md`?
- [x] **Data**: `git add .`, `git commit`, `git push`?
