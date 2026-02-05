# Feature: Interactive Clarification (Human-in-the-Loop)

## 1. Overview
**Branch**: `feat/interactive-clarification`

Allow the autonomous agent to pause execution and ask the user for guidance when it encounters ambiguity, rather than guessing or aborting. This "Human-in-the-Loop" capability ensures higher accuracy for complex tasks.

## 2. Requirements
List specific, testable requirements:
- [x] Agent can call `ask_user(question="...")` as a tool.
- [x] Execution loop pauses when `ask_user` is called.
- [x] In CLI mode, the user is prompted to type an answer.
- [x] In Discord mode, the bot sends a message and waits for a reply from the same user/channel. (Note: Discord view implementation is pending, but architectural support is added in BaseView)
- [x] The user s answer is returned to the agent as the result of the tool call.

## 3. Technical Implementation
- **Modules**:
    - `nebulus_atom/services/tool_executor.py` (Add `ask_user` tool definition).
    - `nebulus_atom/controllers/agent_controller.py` (Handle the pause/resume logic).
    - `nebulus_atom/views/base_view.py` (Add `ask_user_input` method).
    - `nebulus_atom/gateways/discord_gateway.py` (Implement wait_for logic).
- **Dependencies**: None.
- **Data**: Temporary state for the pending question.

## 4. Verification Plan
**Automated Tests**:
- [x] Script/Test: `pytest tests/test_interactive.py` (Temporary test passed)
- [x] Logic Verified: Mock the view input and verify the agent receives it correctly.

**Manual Verification**:
- [x] Step 1: Run `nebulus-atom start`
- [x] Step 2: Instruct agent: "If you don t know my name, ask me."
- [x] Step 3: Agent calls `ask_user("What is your name?")`.
- [x] Step 4: User types name.
- [x] Step 5: Agent confirms "Hello [Name]".

## 5. Workflow Checklist
Follow the AI Behavior strict workflow:
- [x] **Branch**: Created `feat/interactive-clarification` branch?
- [x] **Work**: Implemented changes?
- [x] **Test**: All tests pass (`pytest`)?
- [x] **Doc**: Updated `README.md` and `walkthrough.md`?
- [x] **Data**: `git add .`, `git commit`, `git push`?
