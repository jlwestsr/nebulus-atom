# Claude Code Configuration — nebulus-atom

**Project Type:** Multi-Agent Python CLI
**Architecture:** Swarm multi-agent orchestration
**Configuration Date:** 2026-02-06

---

## Overview

Per-project Claude Code plugin configuration for Nebulus Atom, the autonomous AI engineer CLI with Swarm multi-agent orchestration and GitHub issue processing (Overlord).

## Enabled Plugins

### High Priority

- ✅ **Pyright LSP** — Type checking for multi-agent code
- ✅ **Serena** — Navigate complex multi-agent codebase
- ✅ **Context7** — Live docs for OpenAI Swarm, mcp, streamlit, textual, PyGithub
- ✅ **Superpowers** — Debug multi-agent workflows and orchestration
- ✅ **Feature Dev** — Complex feature development for agent workflows
- ✅ **GitHub** — GitHub issue integration and automation

### Medium Priority

- ✅ **PR Review Toolkit** — Code quality checks
- ✅ **Commit Commands** — Git workflow automation

### Low Priority

- ✅ **Playwright** — Textual UI testing (future capability)

## Disabled Plugins

- ❌ **TypeScript LSP** — No TypeScript
- ❌ **Supabase** — Not using Supabase
- ❌ **Ralph Loop** — No automation loops

## LSP Configuration

### Pyright

Configuration: `pyrightconfig.json` (project root)

**Settings:**

- Type checking: basic
- Python version: 3.12
- Include: `nebulus_atom/`, `nebulus_swarm/`
- Exclude: `__pycache__`, `.pytest_cache`
- Virtual environment: `./venv`

## Architecture

Atom implements Overlord, a cross-project meta-orchestrator:

- Swarm multi-agent coordination
- GitHub issue processing
- Slack integration
- ChromaDB memory
- Docker orchestration
- Cron scheduling

This is the most complex project in the ecosystem. Multi-agent workflows require sophisticated debugging and feature development.

## Testing

Run tests via pytest with async support:

```bash
pytest tests/ -v
```

## Workflow

This project follows the develop→main git workflow:

1. Branch off `develop` for new work
2. Merge features back to `develop` with `--no-ff`
3. Release from `develop` to `main` with version tags

## Why These Plugins?

**Context7 (High Priority)** — Swarm, mcp, and textual are rapidly evolving. Live docs critical for multi-agent coordination patterns.

**Feature Dev (High Priority)** — Agent workflows are complex multi-file features. Feature dev workflow prevents incomplete implementations.

**GitHub (High Priority)** — Core functionality is GitHub issue processing. Deep GitHub integration essential.

**Superpowers (High Priority)** — Multi-agent debugging is non-trivial. Systematic debugging and brainstorming workflows prevent flailing.

**Playwright (Low Priority)** — Textual TUI testing is future capability. Low priority but available when needed.

## Maintenance

Update this configuration when:

- Adding new agent types or orchestration patterns
- Performance issues (multi-agent workflows can be heavy)
- New Claude Code plugins that benefit complex CLI applications

---

*Part of the West AI Labs plugin strategy. See `../docs/claude-code-plugin-strategy.md` for ecosystem-wide strategy.*
