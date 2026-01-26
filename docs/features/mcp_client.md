# Feature: MCP Client (Model Context Protocol)

## 1. Overview
**Branch**: `feat/mcp-client`

Implement a client for the **Model Context Protocol (MCP)**. This allows Mini-Nebulus to dynamically discover and use tools provided by external MCP Servers (e.g., PostgreSQL, GitHub, Slack) without hardcoding integration logic.

## 2. Requirements
- [ ] Implement `MCPClient` service to connect to stdio/SSE MCP servers.
- [ ] Add `connect_mcp_server <command>` tool to launch and connect to an MCP server.
- [ ] Dynamically register tools discovered from MCP servers into `ToolExecutor`.
- [ ] Convert Mini-Nebulus internal tool calls to MCP JSON-RPC requests.
- [ ] Handle MCP resources and prompts (optional, focus on tools first).

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/mcp_service.py` (New service for protocol handling).
    - `mini_nebulus/services/tool_executor.py` (Integrate dynamic MCP tools).
- **Dependencies**: `mcp` (python sdk) or implement basic JSON-RPC.
- **Data**: Config to store persistent server connections.

## 4. Verification Plan
- [ ] Start a simple "Echo" MCP server.
- [ ] Connect Mini-Nebulus to it.
- [ ] Ask agent to "Use the echo tool".
- [ ] Verify agent calls the tool via MCP and receives response.

## 5. Workflow Checklist
- [ ] Create branch `feat/mcp-client`
- [ ] Implementation
- [ ] Verification
