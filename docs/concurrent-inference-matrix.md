# Concurrent Inference Backend Matrix

Guide for configuring `ATOM_LLM_CONCURRENCY` based on your LLM backend.

## Quick Reference

| Backend | Concurrent Support | Recommended Concurrency | Notes |
|---------|-------------------|------------------------|-------|
| TabbyAPI | Yes (batched) | 2-4 | ExLlamaV2 supports continuous batching; performance depends on VRAM headroom |
| vLLM | Yes (native) | 4-8 | Designed for high-throughput concurrent serving; PagedAttention handles many parallel requests |
| MLX Serving | Limited | 1-2 | Apple Silicon; sequential inference internally, HTTP server queues requests |
| Ollama | No | 1 | Sequential processing only — requests queue but don't parallelize. Not recommended for Swarm mode |
| OpenAI API | Yes | 2-4 | Cloud; rate-limited by tier (TPM/RPM). Monitor 429 responses |
| Anthropic API | Yes | 2-4 | Cloud; rate-limited by tier. Monitor 429 responses |
| llama.cpp server | Limited | 1-2 | Supports concurrent slots but performance degrades quickly |
| TGI (Text Generation Inference) | Yes (native) | 4-8 | HuggingFace; continuous batching, designed for concurrent serving |

## Configuration

Set concurrency via environment variable:

```bash
export ATOM_LLM_CONCURRENCY=2  # default
```

Or in `.atom.yml`:

```yaml
llm:
  concurrency: 2
```

## Backend Details

### TabbyAPI (ExLlamaV2)

**Concurrent Support**: Yes (continuous batching)

TabbyAPI wraps the ExLlamaV2 inference engine, which implements continuous batching for concurrent request handling. Multiple requests can share GPU compute efficiently.

**Recommended Settings**:
- **2-4 concurrent requests** for most configurations
- Monitor VRAM usage — concurrent batching requires additional KV cache memory
- 8B models on 24GB VRAM: start with 2-3 concurrency
- 13B+ models or limited VRAM: stick to 1-2 concurrency

**Configuration**: Set `max_batch_size` in TabbyAPI config (default 1 = sequential):

```yaml
model:
  max_batch_size: 4  # Enables batching up to 4 concurrent requests
```

**Performance**: Well-suited for Swarm mode. Latency increases sub-linearly with batch size due to continuous batching efficiency.

### vLLM

**Concurrent Support**: Yes (native, PagedAttention)

vLLM is purpose-built for high-throughput LLM serving with PagedAttention memory management. Handles concurrent requests exceptionally well.

**Recommended Settings**:
- **4-8 concurrent requests** for production
- Can scale higher (16+) on beefy GPUs with sufficient VRAM
- Monitor GPU utilization — vLLM batches aggressively

**Configuration**: Set via vLLM server args:

```bash
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --max-num-batched-tokens 8192 \
  --max-num-seqs 8  # Max concurrent sequences
```

**Performance**: Excellent for Swarm mode. PagedAttention enables efficient memory sharing across requests. Best choice for multi-agent workloads.

### MLX Serving

**Concurrent Support**: Limited (HTTP queue only)

MLX framework (Apple Silicon) performs sequential inference internally. The `mlx_lm.server` HTTP wrapper queues concurrent requests but processes them one at a time.

**Recommended Settings**:
- **1-2 concurrent requests** maximum
- Setting >2 just creates a longer queue — no throughput gain
- MLX shines on M1/M2/M3 for single-user interactive workloads

**Configuration**: No special config needed — MLX server handles queueing.

**Performance**: Adequate for light Swarm usage (2 Minions). Not ideal for heavy concurrent workloads. Best for development/testing on macOS.

### Ollama

**Concurrent Support**: No (sequential only)

Ollama processes requests strictly sequentially. Multiple concurrent requests queue but don't parallelize at the inference level.

**Recommended Settings**:
- **1 concurrent request** only
- Higher concurrency just creates unnecessary queuing
- **Not recommended for Swarm mode** — Minions will block waiting for LLM access

**Configuration**: No configuration helps — Ollama is sequential by design.

**Performance**: Great for single-user chat applications. Poor fit for multi-agent systems. Consider switching to vLLM or TabbyAPI for Swarm deployments.

### OpenAI API

**Concurrent Support**: Yes (cloud, rate-limited)

OpenAI's API handles concurrent requests natively but imposes rate limits based on subscription tier.

**Recommended Settings**:
- **2-4 concurrent requests** for Tier 1/2 accounts
- Monitor rate limit headers: `x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens`
- Watch for 429 (rate limit exceeded) responses

**Rate Limits** (as of early 2025):
- **Free tier**: 3 RPM, 40k TPM (GPT-4)
- **Tier 1**: 500 RPM, 30k TPM (GPT-4)
- **Tier 2**: 5k RPM, 450k TPM (GPT-4)

**Configuration**: Implement exponential backoff on 429 errors (OpenAI client does this automatically).

**Performance**: Reliable for Swarm mode within rate limits. Consider costs — high concurrency = faster token consumption.

### Anthropic API

**Concurrent Support**: Yes (cloud, rate-limited)

Anthropic Claude API handles concurrent requests with tier-based rate limits.

**Recommended Settings**:
- **2-4 concurrent requests** for standard tiers
- Monitor rate limit headers in responses
- Watch for 429 (rate limit) and 529 (overloaded) responses

**Rate Limits** (as of early 2025):
- Varies by tier and model
- Sonnet: typically 50 RPM (free tier), higher for paid
- Opus: lower limits due to compute cost

**Configuration**: Implement exponential backoff on 429/529 errors.

**Performance**: Reliable for Swarm mode. Claude models excel at complex reasoning tasks but cost more than local inference.

### llama.cpp server

**Concurrent Support**: Limited (parallel slots)

llama.cpp server mode supports multiple "slots" (parallel inference contexts) but performance degrades quickly beyond 1-2 concurrent requests.

**Recommended Settings**:
- **1-2 concurrent requests** maximum
- Set `--parallel` flag when starting server:

```bash
./server --model model.gguf --parallel 2 --ctx-size 4096
```

**Configuration**: Each slot allocates separate KV cache — VRAM usage scales linearly.

**Performance**: Acceptable for 2 Minions on high-VRAM GPUs. Beyond that, consider vLLM or TabbyAPI for better batching efficiency.

### TGI (Text Generation Inference)

**Concurrent Support**: Yes (native, continuous batching)

HuggingFace's TGI is optimized for production inference serving with continuous batching and efficient memory management.

**Recommended Settings**:
- **4-8 concurrent requests** for production
- Can scale higher on multi-GPU setups
- Monitor GPU utilization and throughput

**Configuration**: Set via Docker/CLI args:

```bash
docker run --gpus all \
  -e MAX_CONCURRENT_REQUESTS=8 \
  -e MAX_BATCH_TOTAL_TOKENS=16384 \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id meta-llama/Llama-3.1-8B-Instruct
```

**Performance**: Excellent for Swarm mode. Production-grade serving with monitoring and observability built in.

## Choosing Concurrency

### Guidelines

**Start Low (2)**: Always begin with default concurrency and increase incrementally while monitoring performance.

**Monitor VRAM**: Concurrent inference increases memory usage:
- Batching requires larger KV cache
- Out-of-memory errors indicate over-allocation
- Use `nvidia-smi` (NVIDIA) or `sudo powermetrics` (Apple) to monitor

**Watch Latency**: Track p50/p95/p99 response times:
- Latency should increase sub-linearly with concurrency
- If p95 latency spikes >2x, reduce concurrency
- Use Atom's built-in LLM pool stats for monitoring

**Cloud APIs**: Monitor rate limit headers:
- `x-ratelimit-remaining-requests`
- `x-ratelimit-remaining-tokens`
- Adjust concurrency to stay below 80% of limits

**Local Models**: VRAM is the primary constraint, not network bandwidth:
- 8B model + batch_size 4 ≈ 16-20GB VRAM (varies by quant)
- 13B model + batch_size 2 ≈ 20-24GB VRAM
- 70B model → typically limited to sequential inference unless multi-GPU

### Concurrency vs Throughput

Higher concurrency ≠ always better:
- **Throughput** (tokens/second) may plateau or decrease
- **Latency** (time to first token) increases with queue depth
- **Memory** usage scales with concurrent batch size
- **Optimal concurrency** balances throughput and latency for your workload

### Workload Patterns

**Swarm Mode** (multiple Minions):
- Minions make frequent short LLM calls (tool selection, reasoning)
- Benefit from moderate concurrency (2-4)
- Prefer low latency over max throughput

**Batch Processing** (single Minion, many tasks):
- Sequential task execution with LLM calls
- Low concurrency (1-2) is fine
- Focus on per-request latency

**Interactive Chat**:
- Single user, conversational
- Concurrency = 1 is sufficient
- Prioritize time-to-first-token

## Pool Behavior

The LLM connection pool (`nebulus_swarm/overlord/llm_pool.py`) manages concurrent LLM access:

### Slot Acquisition

1. Minion worker requests an LLM slot from the pool
2. If slots are available (< `ATOM_LLM_CONCURRENCY`), acquire immediately
3. If all slots in use, worker queues with 60-second timeout
4. On timeout, worker fails the task with `LLMPoolTimeout` error

### Error Handling

- **429 (rate limit)**: Pool records error; client implements backoff
- **503 (service unavailable)**: Pool records error; worker retries task
- **Timeout**: Worker fails gracefully; Overlord reassigns task

### Pool Statistics

Accessible via `LLMPool.stats()`:

```python
{
    "concurrency_limit": 2,
    "active_requests": 1,
    "queued_requests": 0,
    "total_requests": 145,
    "total_errors": 3,
    "error_429_count": 2,
    "error_503_count": 1,
    "average_wait_time_ms": 12.3
}
```

### Integration Points

- **Dashboard**: Real-time pool stats visualization
- **Monitoring**: Prometheus-style metrics export
- **Logs**: Structured logging of pool events (acquire, release, timeout)

## Troubleshooting

### High Queue Times

**Symptom**: Workers waiting >5s for LLM slots

**Diagnosis**:
- Check pool stats: `queued_requests` consistently >0
- Backend may not support claimed concurrency
- Requests may be slow (large context, slow inference)

**Solution**:
- Reduce `ATOM_LLM_CONCURRENCY` if backend doesn't truly parallelize
- Increase concurrency if backend is idle (check GPU utilization)
- Optimize prompts to reduce tokens/request

### Out of Memory (OOM)

**Symptom**: Backend crashes or returns 500 errors under concurrent load

**Diagnosis**:
- Concurrent batching exceeds VRAM capacity
- Check `nvidia-smi` during concurrent requests

**Solution**:
- Reduce `ATOM_LLM_CONCURRENCY`
- Reduce context window size (`max_tokens`)
- Switch to smaller model or better quantization
- For TabbyAPI: reduce `max_batch_size` in config

### Rate Limit Errors (Cloud APIs)

**Symptom**: Frequent 429 errors from OpenAI/Anthropic

**Diagnosis**:
- Exceeding RPM or TPM limits for tier
- Check rate limit headers in responses

**Solution**:
- Reduce `ATOM_LLM_CONCURRENCY` to stay below limits
- Upgrade API tier for higher limits
- Implement smarter backoff (increase initial delay)

### Slow Throughput

**Symptom**: High concurrency but low tokens/second

**Diagnosis**:
- Backend doesn't support true concurrent batching (e.g., Ollama)
- Requests queuing instead of parallelizing
- VRAM bottleneck causing thrashing

**Solution**:
- Verify backend supports batching (see Quick Reference)
- Check backend logs for batching behavior
- Reduce concurrency to find optimal point
- Consider switching to vLLM or TGI for better batching

## References

- **ExLlamaV2**: https://github.com/turboderp/exllamav2
- **vLLM**: https://github.com/vllm-project/vllm
- **MLX**: https://github.com/ml-explore/mlx
- **Ollama**: https://github.com/ollama/ollama
- **llama.cpp**: https://github.com/ggerganov/llama.cpp
- **Text Generation Inference**: https://github.com/huggingface/text-generation-inference
- **OpenAI Rate Limits**: https://platform.openai.com/docs/guides/rate-limits
- **Anthropic Rate Limits**: https://docs.anthropic.com/en/api/rate-limits
