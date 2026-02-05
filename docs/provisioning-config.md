# Nebulus Atom Provisioning Configuration

Guide for configuring Atom when deployed on Nebulus appliances. Atom is a standalone product that works with any OpenAI-compatible backend — this document covers the specific configuration for Nebulus infrastructure.

## Configuration Precedence

Settings are loaded in this order (highest precedence first):

1. **Environment variables** (`ATOM_*` preferred, `NEBULUS_*` legacy)
2. **Project config** (`.atom.yml` in working directory)
3. **User config** (`~/.atom/config.yml`)
4. **Built-in defaults**

## Configuration Options

### LLM Settings

| Setting | Env Var | YAML Path | Default | Description |
|---------|---------|-----------|---------|-------------|
| Base URL | `ATOM_LLM_BASE_URL` | `llm.base_url` | `http://localhost:5000/v1` | OpenAI-compatible API endpoint |
| Model | `ATOM_LLM_MODEL` | `llm.model` | `Meta-Llama-3.1-8B-Instruct-exl2-8_0` | Model identifier |
| API Key | `ATOM_LLM_API_KEY` | `llm.api_key` | `not-needed` | API key (local servers typically don't require) |
| Timeout | `ATOM_LLM_TIMEOUT` | `llm.timeout` | `300.0` | Request timeout in seconds |
| Streaming | `ATOM_LLM_STREAMING` | `llm.streaming` | `true` | Enable streaming responses |

### Vector Store Settings

| Setting | Env Var | YAML Path | Default | Description |
|---------|---------|-----------|---------|-------------|
| Path | `ATOM_VECTOR_STORE_PATH` | `vector_store.path` | `.nebulus_atom/db` | ChromaDB storage path |
| Collection | `ATOM_VECTOR_STORE_COLLECTION` | `vector_store.collection` | `codebase` | Default collection name |
| Embedding Model | `ATOM_VECTOR_STORE_EMBEDDING_MODEL` | `vector_store.embedding_model` | `all-MiniLM-L6-v2` | Sentence transformer model |

### Connection Pool Settings (Swarm Mode)

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| Concurrency | `ATOM_LLM_CONCURRENCY` | `2` | Max concurrent LLM requests |

### MCP Integration (Optional)

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| MCP URL | `ATOM_MCP_URL` | `None` (disabled) | MCP server endpoint for additional tools |
| MCP Timeout | `ATOM_MCP_TIMEOUT` | `30` | MCP request timeout in seconds |

When `ATOM_MCP_URL` is set, Atom connects to the MCP server and registers additional tools (LTM, document parsing, domain knowledge). When not set, Atom works standalone.

## MCP Integration Details

MCP (Model Context Protocol) integration is **optional** and only relevant when Atom is deployed on Nebulus appliances. It provides:

- **Long-Term Memory (LTM)** — Persistent memory across sessions
- **Document Parsing** — Extract text from PDFs, Office docs, etc.
- **Domain Knowledge** — Access to indexed organizational knowledge

### Enabling MCP

Set the MCP server URL via environment variable:

```bash
export ATOM_MCP_URL=http://nebulus-core:8000/mcp
```

Or in your config file:

```yaml
# ~/.atom/config.yml (YAML config for MCP not yet supported - use env var)
```

### How MCP Works

1. **On startup**, Atom checks if `ATOM_MCP_URL` is set
2. If set, it connects to the MCP server and discovers available tools
3. Tools are registered with an `mcp_` prefix (e.g., `mcp_ltm_search`) to avoid conflicts
4. If the MCP server is unavailable, Atom continues working with its built-in tools

### Graceful Degradation

MCP integration is designed for graceful degradation:

| Scenario | Behavior |
|----------|----------|
| `ATOM_MCP_URL` not set | Atom works standalone (default) |
| MCP server unavailable at startup | Warning logged, Atom continues without MCP tools |
| MCP server goes down mid-session | Tool calls return None, Atom continues working |
| MCP server returns errors | Errors logged, fallback to built-in behavior |

### Nebulus Appliance Configuration

For Tier 1/2/3 appliances with nebulus-core:

```bash
# Edge (Tier 1) — nebulus-core on same machine
ATOM_MCP_URL=http://localhost:8000/mcp

# Prime (Tier 2) — nebulus-core in Docker
ATOM_MCP_URL=http://nebulus-core:8000/mcp

# Tier 3 — nebulus-core on separate host
ATOM_MCP_URL=http://core.internal:8000/mcp
```

### Verifying MCP Connection

```bash
# Check if MCP is configured
python -c "
from nebulus_swarm.integrations.mcp_client import get_mcp_client
client = get_mcp_client()
print(f'MCP available: {client.available}')
print(f'MCP tools: {[t.name for t in client.tools]}')
"

# Test MCP server directly
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

### Troubleshooting MCP

| Issue | Cause | Solution |
|-------|-------|----------|
| MCP tools not appearing | `ATOM_MCP_URL` not set | Set environment variable |
| Connection refused | nebulus-core not running | Start nebulus-core service |
| Timeout errors | Network issues or slow server | Increase `ATOM_MCP_TIMEOUT` |
| Empty tool list | MCP server has no tools registered | Check nebulus-core configuration |

## Recommended Values by Platform

### Tier 1: Mac Mini (Edge)

Apple Silicon with MLX inference server.

```yaml
# ~/.atom/config.yml
llm:
  base_url: "http://localhost:8080/v1"
  model: "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit"
  timeout: 300.0
  streaming: true

vector_store:
  path: "/var/lib/atom/vectors"
  collection: "codebase"
  embedding_model: "all-MiniLM-L6-v2"
```

**Notes:**
- MLX server typically runs on port 8080
- 4-bit quantization recommended for 16GB unified memory
- Concurrency limit: 1-2 (MLX is sequential internally)

### Tier 2: Linux SFF (Prime)

NVIDIA GPU with TabbyAPI/ExLlamaV2.

```yaml
# ~/.atom/config.yml
llm:
  base_url: "http://localhost:5000/v1"
  model: "Meta-Llama-3.1-8B-Instruct-exl2-8_0"
  timeout: 300.0
  streaming: true

vector_store:
  path: "/var/lib/atom/vectors"
  collection: "codebase"
  embedding_model: "all-MiniLM-L6-v2"
```

**Notes:**
- TabbyAPI default port is 5000
- ExL2 8.0bpw quantization balances quality and VRAM
- Concurrency limit: 2-4 (ExLlamaV2 supports batching)

### Tier 3: Headless Server

Remote or containerized deployment.

```yaml
# ~/.atom/config.yml
llm:
  base_url: "http://inference-server:5000/v1"
  model: "Meta-Llama-3.1-8B-Instruct-exl2-8_0"
  api_key: "${ATOM_LLM_API_KEY}"  # Set via environment
  timeout: 600.0
  streaming: true

vector_store:
  path: "/data/atom/vectors"
  collection: "codebase"
  embedding_model: "all-MiniLM-L6-v2"
```

**Notes:**
- Use service hostnames in container networks
- Longer timeout for network latency
- API key may be required for authenticated endpoints

## Docker Deployment

For container deployments, use environment variables:

```bash
# Core LLM settings
ATOM_LLM_BASE_URL=http://tabby:5000/v1
ATOM_LLM_MODEL=Meta-Llama-3.1-8B-Instruct-exl2-8_0
ATOM_LLM_API_KEY=not-needed
ATOM_LLM_TIMEOUT=300
ATOM_LLM_STREAMING=true

# Vector store
ATOM_VECTOR_STORE_PATH=/data/vectors
ATOM_VECTOR_STORE_COLLECTION=codebase
ATOM_VECTOR_STORE_EMBEDDING_MODEL=all-MiniLM-L6-v2

# Connection pool (Swarm mode)
ATOM_LLM_CONCURRENCY=2

# MCP integration (optional)
ATOM_MCP_URL=http://nebulus-core:8000/mcp
```

### Docker Compose Example

```yaml
services:
  atom:
    image: nebulus/atom:latest
    environment:
      - ATOM_LLM_BASE_URL=http://tabby:5000/v1
      - ATOM_LLM_MODEL=Meta-Llama-3.1-8B-Instruct-exl2-8_0
      - ATOM_LLM_CONCURRENCY=2
    volumes:
      - atom-vectors:/data/vectors
    depends_on:
      - tabby

  tabby:
    image: tabbyml/tabby:latest
    # ... TabbyAPI configuration
```

## Provisioning Integration

For automated deployment via Ansible or similar tools:

1. **Template the config file:**
   ```yaml
   # templates/atom-config.yml.j2
   llm:
     base_url: "{{ atom_llm_base_url }}"
     model: "{{ atom_llm_model }}"
     timeout: {{ atom_llm_timeout }}
   ```

2. **Copy to target:**
   ```yaml
   # playbook.yml
   - name: Configure Atom
     ansible.builtin.template:
       src: atom-config.yml.j2
       dest: /home/{{ user }}/.atom/config.yml
       mode: '0644'
   ```

3. **Or set environment variables in systemd:**
   ```ini
   # /etc/systemd/system/atom.service.d/override.conf
   [Service]
   Environment="ATOM_LLM_BASE_URL=http://localhost:5000/v1"
   Environment="ATOM_LLM_MODEL=Meta-Llama-3.1-8B-Instruct-exl2-8_0"
   ```

## Validation

After provisioning, verify configuration:

```bash
# Check config loads correctly
python -c "from nebulus_atom.settings import get_settings; s = get_settings(); print(f'LLM: {s.llm.base_url}')"

# Test LLM connectivity
curl -s http://localhost:5000/v1/models | jq .

# Run smoke test
nebulus-atom start --help
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Connection refused | LLM server not running | Start TabbyAPI/MLX server |
| Timeout errors | Model loading or slow inference | Increase `ATOM_LLM_TIMEOUT` |
| Out of memory | Model too large | Use smaller quantization |
| Config not loading | Wrong file path | Check `~/.atom/config.yml` exists |
| Env vars ignored | Typo in variable name | Use `ATOM_` prefix, check spelling |
