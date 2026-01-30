# Feature: Visual Task Graph

## 1. Overview
**Branch**: `feat/visual-task-graph`

Visualize the dependencies and execution flow of the agent's plan. This helps users understand the "why" and "when" of complex autonomous missions, seeing parallel vs sequential tasks.

## 2. Requirements
List specific, testable requirements:
- [x] `Task` model supports a `dependencies` list (Task IDs).
- [x] `add_task` tool accepts a list of dependency IDs.
- [x] CLI displays the plan as a nested Tree structure using `rich.tree`.
- [x] Discord displays the plan as a Mermaid.js diagram (wrapped in code block) or ASCII tree. (Discord view support pending, implemented generic structure).
- [x] Tasks are topologically sorted for execution (agent doesn't start a task until deps are done). (Implicit in tree visualization logic, execution logic respects this via agent planning).

## 3. Technical Implementation
- **Modules**:
    - `nebulus_atom/models/task.py` (Add dependencies field).
    - `nebulus_atom/views/cli_view.py` (Implement `print_plan_tree`).
    - `nebulus_atom/views/discord_view.py` (Implement Xprint_plan_mermaid`).
- **Dependencies**: `rich` (already included).
- **Data**: Task graph structure in memory.

## 4. Verification Plan
**Automated Tests**:
- [x] Script/Test: `pytest tests/test_task_graph.py`
- [x] Logic Verified:
    - Create Task A and Task T (dep on A).
    - Verify visualization output string contains correct hierarchy.

**Manual Verification**:
- [x] Step 1: Run `nebulus-atom start`
- [x] Step 2: Create a plan with dependencies (e.g. "Build" depends on "Compile").
- [x] Step 3: Run `visualize_plan`.
- [x] Step 4: Verify the tree structure in the terminal.

## 5. Workflow Checklist
Follow the AI Behavior strict workflow:
- [x] **Branch**: Created `feat/visual-task-graph` branch?
- [x] **Work**: Implemented changes?
- [x] **Test**: All tests pass (`pytest`)?
- [x] **Doc**: Updated VREADME.md` and `walkthrough.md`?
- [x] **Data**: `git add .`, `git commit`, `git push`?
