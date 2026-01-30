import pytest
from nebulus_atom.services.mcp_service import MCPService

# Create a simple "echo" script to act as a mock MCP server
MOCK_MCP_SERVER_SCRIPT = """
import sys
import json

def read_message():
    try:
        line = sys.stdin.readline()
        if not line:
            return None
        return json.loads(line)
    except Exception:
        return None

def write_message(msg):
    sys.stdout.write(json.dumps(msg) + "\\n")
    sys.stdout.flush()

def main():
    while True:
        msg = read_message()
        if not msg:
            break

        if msg.get("method") == "initialize":
            write_message({
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "mock-server", "version": "1.0"}
                }
            })
        elif msg.get("method") == "notifications/initialized":
            pass # Just ack
        elif msg.get("method") == "tools/list":
            write_message({
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echoes input",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}}
                            }
                        }
                    ]
                }
            })
        elif msg.get("method") == "tools/call":
            params = msg.get("params", {})
            if params.get("name") == "echo":
                text = params.get("arguments", {}).get("text", "")
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {
                        "content": [{"type": "text", "text": f"Echo: {text}"}]
                    }
                })
        else:
             # Basic error/ignore
             pass

if __name__ == "__main__":
    main()
"""


@pytest.fixture
def mock_mcp_server(tmp_path):
    script_path = tmp_path / "mock_mcp.py"
    script_path.write_text(MOCK_MCP_SERVER_SCRIPT)
    return str(script_path)


@pytest.mark.asyncio
async def test_mcp_connection_and_tool_call(mock_mcp_server):
    service = MCPService()

    # 1. Connect
    result = await service.connect_server(
        name="test_server", command="python3", args=[mock_mcp_server]
    )

    assert "Connected" in result
    assert "test_server" in service.sessions

    # 2. Check Tools
    tools = service.get_tools()
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "mcp__test_server__echo"

    # 3. Call Tool
    output = await service.call_tool("mcp__test_server__echo", {"text": "Hello MCP"})

    assert "Echo: Hello MCP" in output

    # 4. Shutdown
    await service.shutdown()
    assert len(service.sessions) == 0
