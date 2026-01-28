# Feature: Autonomous Execution Engine

## 1. Overview
**Branch**: `feat/autonomous-execution`

This feature enables the agent to autonomously execute tasks from the plan without requiring user intervention after each step. It transforms the system from a passive "wait-for-command" tool into an active agent that can churn through a list of tasks.

## 2. Requirements
- [ ] **Execution Loop**: The agent must automatically pick the next `PENDING` task from the active plan.
- [ ] **Task Context**: The agent must use the context of previous tasks (results/history) to inform the current task.
- [ ] **Stop Conditions**: The loop must stop if:
    - All tasks are completed.
    - A task fails (configurable to retry or stop).
    - The user interrupts execution.
- [ ] **Status Updates**: The UI (CLI/TUI) must reflect task progress in real-time.
- [ ] **Integration**: Must work with the existing `TaskService` and `AgentController`.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/controllers/agent_controller.py`: Implement the `execute_plan()` method to loop through tasks.
    - `mini_nebulus/services/tool_executor.py`: Ensure tools return structured output usable by subsequent tasks.
- **Logic**:
    - Add a `auto_mode` flag to the controller.
    - In `run_loop`, if `auto_mode` is active, skip `get_user_input` and instead generate the prompt from the current task description.

## 4. Verification Plan
**Automated Tests**:
- [ ] `tests/test_autonomous_execution.py`:
    - Create a plan with 2 simple tasks.
    - Enable auto-execution.
    - Verify both tasks transition to `COMPLETED` without mock user input.

**Manual Verification**:
- [ ] Run `python -m mini_nebulus.main start --tui`.
- [ ] Command: "Create a plan to (1) echo 'hello' and (2) echo 'world'. Then execute it."
- [ ] Verify the agent runs both steps automatically.

## 5. Workflow Checklist
- [ ] **Branch**: `feat/autonomous-execution`
- [ ] **Work**: Implemented execution loop in Controller
- [ ] **Test**: `pytest` passes
- [ ] **Doc**: Updated docs
- [ ] **Merge**: `develop`
