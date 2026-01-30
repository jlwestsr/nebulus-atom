# AI Insights & Lessons Learned

This document captures the nuances, architectural decisions, and "lessons learned" regarding the AI's behavior within the Nebulus Atom project.

**Project Mandate**: Future AI agents working on this project are **explicitly encouraged** to recommend, document, or append new insights to this file when they discover patterns that affect performance, autonomy, or user experience.

---

## 2026-01-26: The "Autonomy Threshold"

### Insight
There is a distinct "Autonomy Threshold" related to model parameter size when it comes to following negative constraints (e.g., "Do NOT create a plan for simple tasks").

### The Problem
- **Small Models (7B/14B)**: Struggle to inhibit "helpful" behaviors. Even when told "Stop when done," they often feel compelled to "double-check" work by reading extra files or "pinning" context, leading to bureaucratic overhead and slow user iteration cycles.
- **Large Models (30B+)**: Exhibit significantly better "Theory of Mind" regarding their own state. They correctly interpret "Stop when done" as a hard stop condition and do not halluncinate unnecessary verification steps.

### The Solution applied
1.  **Model Upgrade**: We switched from `qwen2.5-coder:latest` (likely ~7B) to `qwen3:30b-a3b` running on Nebulus.
2.  **System Prompt Hardening**: We significantly refactored the `AgentController.py` prompt to include explicit "Anti-Bureaucracy" rules:
    - *Rule 6*: "Simple requests do NOT require `create_plan`."
    - *Rule 8*: "Do NOT create a plan AFTER doing the work."

---

## 2026-01-26: Telemetry as a Feeback Loop

### Insight
Without real-time feedback on "Token Efficiency" and "Latency," it is impossible to tune the agent's behavior. Users cannot distinguish between "slow model" and "stalled network" without visibility.

### Action
Implemented a Telemetry Footer in the CLI:
`⏱️ 0.38s / 3.17s | 🪙 2568 | 🤖 qwen3:30b-a3b`

This allows us to correlate "feeling slow" with actual data (Time-to-First-Token vs Total Generation Time).

---

## Future Recommendations
- **Search Efficiency**: Continue to monitor if the agent "reads" files after searching. If it starts doing so again, we may need to introduce a dedicated `search_and_read` tool to atomicize the operation.
- **Context Pinning**: The agent should be conservative with pinning. If context grows too large (>8k tokens), performance on local models degrades noticeably.

---

## 2026-01-29: The "Integration Tax" of High-Performance Local Backends (Ollama vs. TabbyAPI)

### Insight
Moving from an "All-in-One" backend (Ollama) to a "Raw Inference" backend (TabbyAPI/ExLlamaV2) significantly improves token generation speed and memory efficiency but imposes a steep "Integration Tax" on the application layer.

### The Problem
- **API Strictness**: Ollama acts as a middleware that silently handles "messy" inputs, parallel tool calls, and fuzzy schema matching. TabbyAPI (closer to the metal) rejects non-compliant requests with `400 Bad Request` or `TemplateError`.
- **Tooling Support**: Native OpenAI `tools` API support in raw local backends is often incomplete or buggy compared to Ollama's managed router.
- **Context Bloat**: Bypassing API limitations requires injecting tool schemas directly into the System Prompt, consuming significant context window space (~10-15k characters).

### The Solution: "Prompt-Based Tool Calling"
To achieve stability with TabbyAPI, we fundamentally refactored the agent's architecture:
1.  **Disable Native Tools**: We explicitly set `tools=None` in the API call to bypass backend validation.
2.  **Prompt Injection**: Tool schemas are injected as text into the System Prompt.
3.  **Role Mimicry**: Tool outputs are stored as `User` messages (not `Tool` messages) to trick the backend into treating the interaction as standard chat.

### Assessment
**Verdict**: The move was **Strategic Win, Tactical Pain**.
- **Pros**: Access to ExLlamaV2 (highest possible TPS on consumer hardware), 100% control over the "Thought Process" (no black-box routing), and backend agnosticism.
- **Cons**: Requires stricter context management (frequent restarts) and more complex client-side logic.
