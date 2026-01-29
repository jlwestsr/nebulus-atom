# Mini-Nebulus: Production Readiness Roadmap

## Executive Summary
Mini-Nebulus has achieved **Stability** (it runs without crashing) and **Basic Autonomy** (it can write code). To reach **Production Quality**, we must shift focus from "making it run" to "making it smart, safe, and scalable."

## Gap Analysis

| Dimension | Current State | Production Goal | Gap |
| :--- | :--- | :--- | :--- |
| **Cognition** | Linear Execution (Plan $\to$ Act). Prone to "tunnel vision". | **Iterative Reasoning** (Think $\to$ Act $\to$ Observe $\to$ Correct). | Lack of self-correction loops. |
| **Memory** | Ephemeral (Context Window only). | **Persistent Knowledge Graph** (RAG + Learned Preferences). | Agent forgets everything on restart. |
| **Safety** | Heuristics (Regex fixes). `.scratchpad` convention. | **Formal Sandboxing** & Deterministic Guards. | Reliance on "hope" that model outputs valid JSON. |
| **I/O** | Raw CLI / Logs. | **Structured Observability** (Traces, Metrics, UI). | Blind execution; debugging relies on tailing logs. |
| **QA** | Manual "eyeball" testing. | **Agent Evaluation Harness** (Automated benchmarks). | High risk of regression. |

## Proposed Roadmap

### Phase 1: The "Ironclad" Foundation (Quality Assurance)
**Objective**: Guarantee the agent never regresses on basic capabilities.
- [ ] **Agent Test Harness**: A suite of scenarios (e.g., "Create a file", "Refactor Code", "Handle Error") that runs automatically.
- [ ] **Regression Suite**: Add the "JSON Hallucination" and "Context Overflow" cases as permanent regression tests.

### Phase 2: Enhanced Cognition (The "Brain" Upgrade)
**Objective**: Enable the agent to solve complex problems, not just one-shot tasks.
- [ ] **Thinking Loop**: Implement a `Reflect` step where the agent critiques its own code before saving.
- [ ] **Tool Expansion**: Add `LSP` (Language Server Protocol) support so the agent can "see" syntax errors before running code.

### Phase 3: Persistent Memory (RAG)
**Objective**: Stop the "Context Amnesia".
- [ ] **Vector Memory**: Properly Index `AI_DIRECTIVES` and codebases so the agent can query them without loading the full file.
- [ ] **User Profile**: Remember user preferences ("Always use snake_case") across sessions.

### Phase 4: Control Plane (UI)
**Objective**: Better User Experience.
- [ ] **Interactive TUI**: Upgrade `Textual` view to allow real-time intervention.
- [ ] **Web Dashboard**: Visualizing the Plan Graph and Token usage.
