# Feature: Shell Macro Generator

## 1. Overview
**Branch**: `feat/shell-macro`

Allow the agent to take a successful tool execution or plan and "compile" it into a standard Bash script or shell alias for the user to use *without* the agent next time. This reduces latency for repetitive tasks.

## 2. Requirements
- [x] **Macro Creation**: Agent can generate a shell script from a sequence of `run_shell_command` calls.
- [x] **Alias Suggestion**: Agent can suggest an alias (e.g., `alias clean-docker="..."`).
- [x] **Persistence**: Save macros to `~/.nebulus_atom/macros/` or append to `.bashrc` (with user permission).
- [x] **Tool Integration**: Add `create_macro` tool.

## 3. Technical Implementation
- **Modules**:
    - `nebulus_atom/services/macro_service.py`: Logic to extract shell commands from history and format them.
    - `nebulus_atom/services/tool_executor.py`: Add `create_macro`.
- **Dependencies**: None.
- **Data**: Macro files.

## 4. Verification Plan
**Automated Tests**:
- [x] `tests/test_macro_service.py`:
    - Pass a history of commands.
    - Verify generated script content.

**Manual Verification**:
- [x] Run `nebulus-atom start`.
- [x] Ask: "Create a macro to clean all docker containers".
- [x] Verify `clean_docker.sh` is created and executable.

## 5. Workflow Checklist
- [x] **Branch**: Created `feat/shell-macro` branch?
- [x] **Work**: Implemented changes?
- [x] **Test**: All tests pass (`pytest`)?
- [x] **Doc**: Updated `README.md`?
- [x] **Data**: `git add .`, `git commit`?
