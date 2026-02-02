# Nebulus Atom Project Context

## Project Overview
This is a custom, lightweight CLI agent built to interact directly with a local Nebulus (Ollama) server, bypassing complex abstractions.

## Technical Stack
- **Language**: Python 3.12+
- **Framework**: Typer (CLI), Textual (TUI), Streamlit (Dashboard)
- **UI**: Rich
- **LLM Client**: OpenAI Python Library
- **Architecture**: Strict MVC (Model-View-Controller) with OOP best practices.
- **Target Server**: http://localhost:5000/v1
- **Model**: Meta-Llama-3.1-8B-Instruct-exl2-8_0

## Agent Instructions
- **Branching**: Follow the local feature branch workflow defined in `WORKFLOW.md`. Merge into `develop`.
- Follow the directives in `AI_DIRECTIVES.md` (includes strict OOP/SOLID mandates).
- The main entry point is `nebulus_atom/main.py`.
- Run via: `python3 -m nebulus_atom.main start`.

## Key Features
- **Context Manager**: Pin files to active context for awareness.
- **Smart Undo**: Auto-checkpoints before risky operations.
- **RAG**: Semantic code search using embeddings.
- **Skill Library**: Persistent and shareable autonomous capabilities.

## Project Influences
- **Gemini CLI**: https://github.com/google-gemini/gemini-cli
  - *Goal*: Mimic its terminal features and user experience.
- **Get Shit Done**: https://github.com/glittercowboy/get-shit-done
  - *Goal*: Mimic its features and task-oriented approach.
- **Moltbot**: https://www.molt.bot/
  - *Docs*: https://docs.molt.bot/start/getting-started
  - *Goal*: Enable autonomous agent capabilities.
