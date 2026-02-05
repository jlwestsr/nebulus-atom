# Feature: Embedded Documentation Dashboard

## 1. Overview
**Branch**: `feat/embedded-docs`

This feature provides in-terminal access to the project s documentation. Users can list, read, and search documentation files directly from the CLI or via the agent, reducing the need to switch context to a browser or file explorer.

## 2. Requirements
- [x] **Doc Listing**: List available documentation files in `docs/` and its subdirectories.
- [x] **Doc Viewing**: Render Markdown files in the terminal using `rich`.
- [x] **Doc Searching**: Simple keyword search or RAG-based search (reusing `RagService` if applicable) for documentation.
- [x] **CLI Command**: `nebulus-atom docs` subcommand.
- [x] **Agent Tool**: `read_doc` and `list_docs` tools for the agent.

## 3. Technical Implementation
- **Modules**:
    - `nebulus_atom/services/doc_service.py`: Service to scan and read docs.
    - `nebulus_atom/main.py`: Add `docs` subcommand.
    - `nebulus_atom/services/tool_executor.py`: Add `read_doc`, `list_docs` tools.
- **Dependencies**: `rich` (already installed).

## 4. Verification Plan
**Automated Tests**:
- [x] `tests/test_doc_service.py`:
    - Verify file listing.
    - Verify file reading.

**Manual Verification**:
- [x] Run `python -m nebulus_atom.main docs list`.
- [x] Run `python -m nebulus_atom.main docs read features/task_management.md`.

## 5. Workflow Checklist
- [x] **Branch**: `feat/embedded-docs`
- [x] **Work**: Implement DocService and CLI commands
- [x] **Test**: `pytest` passes
- [x] **Doc**: Updated docs
- [x] **Merge**: `develop`
