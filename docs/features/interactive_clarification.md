# Feature: Interactive Clarification (Human-in-the-Loop)

## 1. Overview
**Branch**: `feat/interactive-clarification`

Allow the autonomous agent to pause execution and ask the user for guidance when it encounters ambiguity, rather than guessing or aborting. This "Human-in-the-Loop" capability ensures higher accuracy for complex tasks.

## 2. Requirements
List specific, testable requirements:
- [ ] Agent can call `ask_user(question="...")` as a tool.
- [ ] Execution loop pauses when `ask_user` is called.
- [ ] In CLI mode, the user is prompted to type an answer.
- [ ] In Discord mode, the bot sends a message and waits for a reply from the same user/channel.
- [ ] The user's answer is returned to the agent as the result of the tool call.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/tool_executor.py` (Add `ask_user` tool definition).
    - `mini_nebulus/controllers/agent_controller.py` (Handle the pause/resume logic).
    - `mini_nebulus/views/base_view.py` (Add `ask_user_input` method).
    - `mini_nebulus/gateways/discord_gateway.py` (Implement wait_for logic).
- **Dependencies**: None.
- **Data**: Temporary state for the pending question.

## 4. Verification Plan
**Automated Tests**:
- [ ] Script/Test: `pytest tests/test_interactive.py`
- [ ] Logic Verified: Mock the view input and verify the agent receives it correctly.

**Manual Verification**:
- [ ] Step 1: Run `mini-nebulus start`
- [ ] Step 2: Instruct agent: "If you don't know my name, ask me."
- [ ] Step 3: Agent calls `ask_user("What is your name?")`.
- [ ] Step 4: User types name.
- [ ] Step 5: Agent confirms "Hello [Name]".

## 5. Workflow Checklist
Follow the AI Behavior strict workflow:
- [ ] **Branch**: Created `feat/interactive-clarification` branch?
- [ ] **Work**: Implemented changes?
- [ ] **Test**: All tests pass (`pytest`)?
- [ ] **Doc**: Updated `README.md` and `walkthrough.md`?
- [ ] **Data**: `git add .`, `git commit`, `git push`?
