# Feature: Skill Library (Persistent Skills)

## 1. Overview
**Branch**: `feat/skill-library`

Expand the "Skill System" to allow generated skills to be persisted, categorized, and reused across different sessions or even different projects globally.

## 2. Requirements
List specific, testable requirements:
- [ ] Skills created via `create_skill` are stored persistently.
- [ ] Users can `publish_skill` to move a local project skill to a global user library (e.g., `~/.mini_nebulus/skills`).
- [ ] `list_skills` displays both project-specific and global skills.
- [ ] The agent can load and use global skills in any directory.
- [ ] Skills are namespaced to avoid conflicts (e.g., `global.calculator`).

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/skill_service.py` (Update `load_skills` to scan multiple paths).
    - `mini_nebulus/config.py` (Add `GLOBAL_SKILLS_PATH` configuration).
- **Dependencies**: None.
- **Data**: Filesystem storage at `~/.mini_nebulus/skills/`.

## 4. Verification Plan
**Automated Tests**:
- [ ] Script/Test: `pytest tests/test_skill_library.py`
- [ ] Logic Verified:
    - Create local skill -> Publish -> Verify file exists in global dir.
    - Start new session in different dir -> Verify global skill is loaded.

**Manual Verification**:
- [ ] Step 1: Run `mini-nebulus start`
- [ ] Step 2: Create a skill "hello_world".
- [ ] Step 3: Run `publish_skill hello_world`.
- [ ] Step 4: Change directory and start agent.
- [ ] Step 5: Ask agent to use "hello_world".

## 5. Workflow Checklist
Follow the AI Behavior strict workflow:
- [ ] **Branch**: Created `feat/skill-library` branch?
- [ ] **Work**: Implemented changes?
- [ ] **Test**: All tests pass (`pytest`)?
- [ ] **Doc**: Updated `README.md` and `walkthrough.md`?
- [ ] **Data**: `git add .`, `git commit`, `git push`?
