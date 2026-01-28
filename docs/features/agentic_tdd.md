# Feature: Agentic TDD Loop (The "Fixer")

## 1. Overview
**Branch**: `feat/agentic-tdd`

A specialized autonomous mode that strictly follows Test-Driven Development (TDD). It moves autonomy from "linear execution" to "self-correcting loops," significantly increasing reliability by writing tests first, confirming failure, and iterating on the implementation until the test passes.

## 2. Requirements
- [x] **TDD Loop**: Implement a specialized execution loop: Test -> Fail -> Implement -> Verify -> Refactor.
- [x] **Test Generation**: Agent creates a new test file in `tests/` based on the user requirement.
- [x] **Verification**: Agent runs the specific test using `pytest` and parses the output to determine success/failure.
- [x] **Iteration**: If the test fails after implementation, the agent reads the error log and retries the implementation (max retries configurable).
- [x] **Tools**: Use existing `write_file` and `run_shell_command` tools.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/controllers/agent_controller.py`: Add `run_tdd_loop` method or new `TDDController`.
    - `mini_nebulus/services/tool_executor.py`: Ensure test runner output is clean for the LLM.
- **Dependencies**: None (`pytest` is standard).
- **Data**: None.

## 4. Verification Plan
**Automated Tests**:
- [x] `tests/test_tdd_loop.py`:
    - Mock the LLM to generate a test, then a fail implementation, then a fix.
    - Verify the loop iterates 2 times and exits on success.

**Manual Verification**:
- [x] Run `mini-nebulus start`.
- [x] Command: "Implement a function `add(a, b)` using TDD".
- [x] Verify agent creates `tests/test_add.py`, runs it (fails), creates `add.py`, runs test (passes).

## 5. Workflow Checklist
- [x] **Branch**: Created `feat/agentic-tdd` branch?
- [x] **Work**: Implemented changes?
- [x] **Test**: All tests pass (`pytest`)?
- [x] **Doc**: Updated `README.md`?
- [x] **Data**: `git add .`, `git commit`?
