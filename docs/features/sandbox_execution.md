# Feature: Sandboxed Execution (Docker)

## 1. Overview
**Branch**: `feat/sandbox-execution`

Secure the agent s execution environment by running potentially dangerous operations (shell commands, python scripts) inside an ephemeral Docker container. This prevents accidental system damage (e.g., `rm -rf /`).

## 2. Requirements
- [x] Check if Docker is available on startup.
- [x] Create a persistent `mini-nebulus-sandbox` container mounting the project dir.
- [x] Intercept `run_shell_command` to execute via `docker exec`.
- [x] Intercept `write_file`? (Optional, if mounted volume is used, host write is fine, but shell is the danger).
- [x] Provide a configuration option `SANDBOX_MODE=true/false`.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/docker_service.py` (Manage container lifecycle).
    - `mini_nebulus/services/tool_executor.py` (Route shell commands to DockerService).
- **Dependencies**: `docker` (python sdk).
- **Data**: Dockerfile for the sandbox environment.

## 4. Verification Plan
- [x] Enable Sandbox Mode.
- [ ] Run `run_shell_command "whoami"`.
- [ ] Output should be `root` (inside docker) or `sandbox_user`, different from host user.
- [ ] Verify file changes inside docker reflect on host (volume mount).

## 5. Workflow Checklist
- [x] Create branch `feat/sandbox-execution`
- [x] Implementation
- [x] Verification (Partially complete - Tests pass, runtime requires Docker)
