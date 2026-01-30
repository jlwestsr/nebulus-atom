# Feature: MCP Client (Model Context Protocol)

## 1. Overview
**Branch**: `feat/mcp-client`

Implement a client for the **Model Context Protocol (MCP)**. This allows Nebulus Atom to dynamically discover and use tools provided by external MCP Servers (e.g., PostgreSQL, GitHub, Slack) without hardcoding integration logic.

## 2. Requirements
- [x] Implement `MCPClient` service to connect to stdio/SSE MCP servers.
- [x] Add `connect_mcp_server <command>` tool to launch and connect to an MCP server.
- [x] Dynamically register tools discovered from MCP servers into `ToolExecutor`.
- [x] Convert Nebulus Atom internal tool calls to MCP JSON-RPC requests.
- [x] Handle MCP resources and prompts (optional, focus on tools first).

## 3. Technical Implementation
- **Modules**:
    - `nebulus_atom/services/mcp_service.py` (New service for protocol handling).
    - `nebulus_atom/services/tool_executor.py` (Integrate dynamic MCP tools).
- **Dependencies**: `mcp` (python sdk) or implement basic JSON-RPC.
- **Data**: Config to store persistent server connections.

## 4. Verification Plan
- [x] Start a simple "Echo" MCP server.
- [x] Connect Nebulus Atom to it.
- [x] Ask agent to "Use the echo tool".
- [x] Verify agent calls the tool via MCP and receives response.

## 5. Workflow Checklist
- [x] Create branch `feat/mcp-client`
- [x] Implementation
- [x] Verification
