# GEMINI Project Context

## Project Overview
This is a custom, lightweight CLI agent built to interact directly with a local Nebulus (Ollama) server, bypassing complex abstractions. Inspired by https://github.com/clawdbot/clawdbot.

## Technical Stack
- **Runtime**: Node.js
- **Libraries**: openai, inquirer, chalk, dotenv
- **Target Server**: http://nebulus:11434/v1
- **Model**: qwen2.5-coder:latest

## Agent Instructions
- Always work on the `develop` branch.
- Follow the directives in `AI_DIRECTIVES.md`.
- Follow the workflow in `WORKFLOW.md`.
- The main entry point is `agent.js`.
