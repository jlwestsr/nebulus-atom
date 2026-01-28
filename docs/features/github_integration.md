# Feature: GitHub Integration (via MCP)

## 1. Overview
**Branch**: `feat/github-mcp`

Leverage the **MCP Client** to connect to the official GitHub MCP server. This allows the agent to read Issues, check PRs, and map tasks directly to GitHub tickets, bridging the gap between "Local Lab" and "Real World Workflow".

## 2. Requirements
- [ ] **MCP Connection**: Connect to the GitHub MCP server using `connect_mcp_server`.
- [ ] **Auth Handling**: Handle GitHub Personal Access Token (PAT) via env vars or the MCP server's auth flow.
- [ ] **Tool Exposure**: Expose GitHub tools (e.g., `github_create_issue`, `github_list_prs`) to the agent.
- [ ] **Task Linking**: (Optional) Allow `Task` objects to link to GitHub Issue IDs.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/mcp_service.py`: Ensure environment variables are passed correctly to the server.
    - `mini_nebulus/config.py`: Add `GITHUB_TOKEN`.
- **Dependencies**: None (Uses existing MCP client).
- **Data**: None.

## 4. Verification Plan
**Automated Tests**:
- [ ] `tests/test_github_mcp.py`:
    - Mock the MCP server connection.
    - Verify tools are registered.

**Manual Verification**:
- [ ] Set `GITHUB_TOKEN`.
- [ ] Run `mini-nebulus start`.
- [ ] Command: "Connect to GitHub MCP".
- [ ] Command: "List my open PRs".
- [ ] Verify real data from GitHub is returned.

## 5. Workflow Checklist
- [ ] **Branch**: Created `feat/github-mcp` branch?
- [ ] **Work**: Implemented changes?
- [ ] **Test**: All tests pass (`pytest`)?
- [ ] **Doc**: Updated `README.md`?
- [ ] **Data**: `git add .`, `git commit`?
