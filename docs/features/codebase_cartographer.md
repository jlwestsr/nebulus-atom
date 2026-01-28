# Feature: Codebase Cartographer (AST Analysis)

## 1. Overview
**Branch**: `feat/codebase-cartographer`

Uses Python's `ast` module to generate a structural map of classes, functions, and imports. This complements the RAG system by providing precise, deterministic answers about the codebase structure (e.g., "Where is X defined?").

## 2. Requirements
- [ ] **AST Parsing**: Recursively scan all `.py` files in the project.
- [ ] **Symbol Extraction**: Extract Class names, Function names, Docstrings, and Imports.
- [ ] **Map Generation**: Generate a JSON or textual representation of the project structure.
- [ ] **Tool Integration**: Add `map_codebase` tool to return this structure to the agent.
- [ ] **Search Integration**: Allow searching the map for specific symbols (e.g., `find_symbol Task`).

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/ast_service.py`: New service for parsing.
    - `mini_nebulus/services/tool_executor.py`: Add `map_codebase` and `find_symbol` tools.
- **Dependencies**: None (Standard `ast` library).
- **Data**: In-memory cache of the AST map.

## 4. Verification Plan
**Automated Tests**:
- [ ] `tests/test_ast_service.py`:
    - Parse a dummy python file.
    - Verify it extracts class and function names correctly.

**Manual Verification**:
- [ ] Run `mini-nebulus start`.
- [ ] Command: "Map the codebase".
- [ ] Verify the agent sees the structure of `mini_nebulus/`.

## 5. Workflow Checklist
- [ ] **Branch**: Created `feat/codebase-cartographer` branch?
- [ ] **Work**: Implemented changes?
- [ ] **Test**: All tests pass (`pytest`)?
- [ ] **Doc**: Updated `README.md`?
- [ ] **Data**: `git add .`, `git commit`?
