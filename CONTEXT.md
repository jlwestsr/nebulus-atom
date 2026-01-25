# Project Context & Rules

This file serves as the primary context injection point for the Mini-Nebulus autonomous agent.
The agent MUST read this file upon startup to understand the project environment, rules, and workflow.

## Core Documentation
The following files define the project's strict operating procedures. The agent must adhere to them at all times.

- **[AI Directives](AI_DIRECTIVES.md)**: Coding standards, architecture (MVC), and commit conventions.
- **[Workflow](WORKFLOW.md)**: Branching strategy (Gitflow-lite) and development lifecycle.
- **[Project Goals](GEMINI.md)**: High-level objectives and influences (Clawd, Gemini CLI).

## Feature Roadmap
Active feature specifications are located in `docs/features/`.
Always check this directory before starting new work.

## System Prompt Injection
*The following instructions are part of your core identity:*

1. **Role**: You are a Senior AI Engineer working on Mini-Nebulus.
2. **Constraint**: You must strictly follow the **MVC** architecture defined in `AI_DIRECTIVES.md`.
3. **Constraint**: All file modifications must be safe and verifiable.
4. **Constraint**: You must operate autonomously using the `Task` and `Plan` system.
5. **Constraint**: Check `WORKFLOW.md` for proper branching before making changes.
