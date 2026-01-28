# Feature: Shell Macro Generator

## 1. Overview
**Branch**: `feat/shell-macro`

Allow the agent to take a successful tool execution or plan and "compile" it into a standard Bash script or shell alias for the user to use *without* the agent next time. This reduces latency for repetitive tasks.

## 2. Requirements
- [ ] **Macro Creation**: Agent can generate a shell script from a sequence of `run_shell_command` calls.
- [ ] **Alias Suggestion**: Agent can suggest an alias (e.g., `alias clean-docker="..."`).
- [ ] **Persistence**: Save macros to `~/.mini_nebulus/macros/` or append to `.bashrc` (with user permission).
- [ ] **Tool Integration**: Add `create_macro` tool.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/macro_service.py`: Logic to extract shell commands from history and format them.
    - `mini_nebulus/services/tool_executor.py`: Add `create_macro`.
- **Dependencies**: None.
- **Data**: Macro files.

## 4. Verification Plan
**Automated Tests**:
- [ ] `tests/test_macro_service.py`:
    - Pass a history of commands.
    - Verify generated script content.

**Manual Verification**:
- [ ] Run `mini-nebulus start`.
- [ ] Ask: "Create a macro to clean all docker containers".
- [ ] Verify `clean_docker.sh` is created and executable.

## 5. Workflow Checklist
- [ ] **Branch**: Created `feat/shell-macro` branch?
- [ ] **Work**: Implemented changes?
- [ ] **Test**: All tests pass (`pytest`)?
- [ ] **Doc**: Updated `README.md`?
- [ ] **Data**: `git add .`, `git commit`?
