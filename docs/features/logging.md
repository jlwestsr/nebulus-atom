# Feature: System Logging

## 1. Overview
**Branch**: `feat/logging`

Mini-Nebulus currently lacks a centralized logging system. Errors and execution details are printed to stdout/stderr or the TUI logs, but there is no persistent record for debugging or auditing. This feature implements a robust, rotating file-based logging system.

## 2. Requirements
- [ ] Create a centralized logging configuration.
- [ ] Logs should be saved to `logs/mini_nebulus.log`.
- [ ] Implement log rotation (e.g., 5MB max size, keep 3 backups).
- [ ] Ensure logs capture timestamp, level, logger name, and message.
- [ ] Integrate logging into key components:
    - `AgentController` (Task lifecycle events)
    - `ToolExecutor` (Tool execution inputs/outputs/errors)
    - `OpenAIService` (LLM request/response stats - careful with PII/Tokens)
    - `Config` (Startup/Environment issues)
- [ ] Ensure logging works seamlessly with TUI/CLI (i.e., doesn't pollute stdout in CLI mode unexpectedly).

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/utils/logger.py`: New module for logging setup.
    - `mini_nebulus/config.py`: Add logging constants (path, level).
    - `mini_nebulus/controllers/agent_controller.py`: Add log calls.
    - `mini_nebulus/services/tool_executor.py`: Add log calls.
    - `mini_nebulus/services/openai_service.py`: Add log calls.
- **Dependencies**: Standard library `logging` and `logging.handlers`. No new external deps.
- **Data**: `logs/` directory creation.

## 4. Verification Plan
**Automated Tests**:
- [ ] Script/Test: `pytest tests/test_logging.py`
- [ ] Logic Verified: Check if log file is created, rotation works, and specific messages appear.

**Manual Verification**:
- [ ] Step 1: Run `python -m mini_nebulus.main start`
- [ ] Step 2: Execute a command (e.g., "list files")
- [ ] Step 3: Check `logs/mini_nebulus.log` for correct entries.

## 5. Workflow Checklist
Follow the AI Behavior strict workflow:
- [ ] **Branch**: Created `feat/logging` branch?
- [ ] **Work**: Implemented changes?
- [ ] **Test**: All tests pass (`pytest`)?
- [ ] **Doc**: Updated `README.md` if necessary?
- [ ] **Data**: `git add .`, `git commit`, `git push`?
