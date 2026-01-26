# Feature: Interactive Dashboard (TUI)

## 1. Overview
**Branch**: `feat/interactive-dashboard`

Upgrade the User Interface from a scrolling CLI to a full **Terminal User Interface (TUI)**. This provides a persistent dashboard with dedicated panels for Chat, Plan/Graph, and Context, mimicking a "Mission Control" center.

## 2. Requirements
- [ ] Replace `CLIView` (Rich) with a `Textual` App.
- [ ] **Layout**:
    - **Sidebar (Left)**: Active Plan (Tree), Pinned Files list.
    - **Main (Center)**: Chat History (Scrollable).
    - **Input (Bottom)**: Multi-line prompt area.
- [ ] Real-time updates: When task status changes, the Sidebar updates immediately without re-printing the whole screen.
- [ ] Keyboard shortcuts (e.g., Ctrl+C to stop, Ctrl+L to clear).

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/views/tui_view.py` (New view implementation using Textual).
    - `mini_nebulus/main.py` (Switch to TUI mode).
- **Dependencies**: `textual`.
- **Data**: Async event loop integration with Textual.

## 4. Verification Plan
- [ ] Run `mini-nebulus start --tui`.
- [ ] Verify layout renders correctly.
- [ ] Run a complex plan.
- [ ] Verify the Plan Panel updates task icons in real-time.
- [ ] Verify chat interaction works smoothly.

## 5. Workflow Checklist
- [ ] Create branch `feat/interactive-dashboard`
- [ ] Implementation
- [ ] Verification
