# Standalone CLI Audit — nebulus-core Dependency Check

**Date:** 2026-02-05
**Auditor:** Claude Opus 4.5
**Result:** PASS — nebulus-atom has zero dependency on nebulus-core

## Findings

### Import Scan

Searched all Python files in `nebulus_atom/`, `nebulus_swarm/`, and `tests/` for:

```
from nebulus_core import ...
import nebulus_core
```

**Result:** Zero matches. No imports from nebulus-core exist anywhere in the codebase.

### Dependency Declaration Scan

Searched `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, and
`requirements-minion.txt` for references to `nebulus-core`, `nebulus_core`, or
`nebulus.core`.

**Result:** Zero matches. nebulus-core is not declared as a dependency.

### LLM Connectivity Test

Verified the CLI can connect to any OpenAI-compatible endpoint:

- **Endpoint tested:** `http://localhost:5000/v1` (TabbyAPI with ExLlamaV2)
- **Models available:** `Qwen2.5-Coder-14B-Instruct-exl2-4_25`,
  `Meta-Llama-3.1-8B-Instruct-exl2-8_0`, `TinyLlama-1.1B-Chat-v1.0-exl2-6_5`
- **Connection:** Successful via `openai.OpenAI` SDK
- **Configuration:** Uses `NEBULUS_BASE_URL` and `NEBULUS_MODEL` env vars

### How the CLI Talks to LLMs

The CLI uses the `openai` Python SDK directly against any OpenAI-compatible
HTTP endpoint. There is no nebulus-core LLM client wrapper involved.

| Component | LLM Client | Where |
|-----------|-----------|-------|
| Agent controller | `openai.AsyncOpenAI` | `nebulus_atom/services/openai_service.py` |
| Swarm LLM reviewer | `openai.OpenAI` | `nebulus_swarm/reviewer/llm_review.py` |
| Swarm minion agent | `openai.OpenAI` | `nebulus_swarm/minion/agent/llm_client.py` |
| Swarm overlord parser | `openai.AsyncOpenAI` | `nebulus_swarm/overlord/llm_parser.py` |

All four call the OpenAI SDK directly with configurable `base_url`.

## Conclusion

nebulus-atom is a fully standalone project. It does not import, depend on, or
require nebulus-core in any way. The LLM interface is the standard OpenAI Python
SDK pointed at a configurable endpoint, making it compatible with TabbyAPI,
Ollama, vLLM, or any OpenAI-compatible server.
