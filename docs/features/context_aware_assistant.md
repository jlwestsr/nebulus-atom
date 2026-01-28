# Feature: Context-Aware Command Assistant

## 1. Overview
**Branch**: `feat/context-aware-commands`

This feature enhances the CLI with semantic search capabilities over the command history and potentially the codebase (via RAG). It allows the user or the agent to recall past commands, plans, or relevant code snippets using natural language queries.

## 2. Requirements
- [x] **History Indexing**: Automatically index user commands and agent responses into ChromaDB.
- [x] **Semantic Search**: Provide a tool `search_history` to query this index.
- [x] **Integration**: Hook into `AgentController` to index turns automatically.
- [x] **Command Suggestion**: (Optional) Provide suggestions based on current context.

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/rag_service.py`: Add `index_history(turn)` and `search_history(query)` methods.
    - `mini_nebulus/controllers/agent_controller.py`: Call `index_history` in `process_turn`.
    - `mini_nebulus/services/tool_executor.py`: Add `search_history` tool.
- **Data**:
    - ChromaDB collection: `command_history`.

## 4. Verification Plan
**Automated Tests**:
- [x] `tests/test_rag.py`:
    - Index a mock turn.
    - Search for a keyword.
    - Assert the turn is returned.

**Manual Verification**:
- [x] Run `python -m mini_nebulus.main start`.
- [x] Execute: "Create a file named hello.txt".
- [x] Execute: "Search history for 'file creation'".
- [x] Verify the previous command is returned.

## 5. Workflow Checklist
- [x] **Branch**: `feat/context-aware-commands`
- [x] **Work**: Implement RAG updates and Controller integration
- [x] **Test**: `pytest` passes
- [x] **Doc**: Updated docs
- [x] **Merge**: `develop`
