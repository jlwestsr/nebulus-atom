# AI Insights & Lessons Learned

This document captures the nuances, architectural decisions, and "lessons learned" regarding the AI's behavior within the Mini-Nebulus project.

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
