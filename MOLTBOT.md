# Moltbot Context: Nebulus Atom

## Project Overview
This is **Nebulus Atom**, a lab environment for testing the "Nebulus" infrastructure patterns.

## Key Files
- `GEMINI.md`: Core project directives and current status.
- `AI_DIRECTIVES.md`: Rules for AI interaction.
- `WORKFLOW.md`: Approved workflows.
- `src/`: Source code directory.
- `ansible/`: Infrastructure automation.

## Agent Instructions
- **Tools**: You are running on the Host OS.
    - To read files, use `grep` or `exec cat <filename>`.
    - To list files, use `ls -F`.
    - Do not try to use `read_file` (it does not exist).
- **Environment**: You have full access to the user's tools (`git`, `docker`, `pnpm`, `ansible`).
- **Goal**: Assist the user in verifying and developing this project.

## Current Mode
- **Host**: `shurtugal-lnx`
- **User**: `jlwestsr`
