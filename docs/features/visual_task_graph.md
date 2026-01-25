# Feature: Visual Task Graph

## 1. Overview
**Branch**: `feat/visual-task-graph`

Visualize the dependencies and execution flow of the agent's plan. This helps users understand the "why" and "when" of complex autonomous missions, seeing parallel vs sequential tasks.

## 2. Requirements
List specific, testable requirements:
- [ ] `Task` model supports a `dependencies` list (Task IDs).
- [ ] `add_task` tool accepts a list of dependency IDs.
- [ ] CLI displays the plan as a nested Tree structure using `rich.tree`.
- [ ] Discord displays the plan as a Mermaid.js diagram (wrapped in code block) or ASCII tree.
- [ ] Tasks are topologically sorted for execution (agent doesn't start a task until deps are done).

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/models/task.py` (Add dependencies field).
    - `mini_nebulus/views/cli_view.py` (Implement `print_plan_tree`).
    - `mini_nebulus/views/discord_view.py` (Implement `print_plan_mermaid`).
- **Dependencies**: `rich` (already included).
- **Data**: Task graph structure in memory.

## 4. Verification Plan
**Automated Tests**:
- [ ] Script/Test: `pytest tests/test_task_graph.py`
- [ ] Logic Verified:
    - Create Task A and Task B (dep on A).
    - Verify visualization output string contains correct hierarchy.

**Manual Verification**:
- [ ] Step 1: Run `mini-nebulus start`
- [ ] Step 2: Create a plan with dependencies (e.g., "Build" depends on "Compile").
- [ ] Step 3: Run `visualize_plan`.
- [ ] Step 4: Verify the tree structure in the terminal.

## 5. Workflow Checklist
Follow the AI Behavior strict workflow:
- [ ] **Branch**: Created `feat/visual-task-graph` branch?
- [ ] **Work**: Implemented changes?
- [ ] **Test**: All tests pass (`pytest`)?
- [ ] **Doc**: Updated `README.md` and `walkthrough.md`?
- [ ] **Data**: `git add .`, `git commit`, `git push`?
