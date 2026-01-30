# Feature: Codebase Cartographer (AST Analysis)

## 1. Overview
**Branch**: `feat/codebase-cartographer`

Uses Python's `ast` module to generate a structural map of classes, functions, and imports. This complements the RAG system by providing precise, deterministic answers about the codebase structure (e.g., "Where is X defined?").

## 2. Requirements
- [x] **AST Parsing**: Recursively scan all `.py` files in the project.
- [x] **Symbol Extraction**: Extract Class names, Function names, Docstrings, and Imports.
- [x] **Map Generation**: Generate a JSON or textual representation of the project structure.
- [x] **Tool Integration**: Add `map_codebase` tool to return this structure to the agent.
- [x] **Search Integration**: Allow searching the map for specific symbols (e.g., `find_symbol Task`).

## 3. Technical Implementation
- **Modules**:
    - `nebulus_atom/services/ast_service.py`: New service for parsing.
    - `nebulus_atom/services/tool_executor.py`: Add `map_codebase` and `find_symbol` tools.
- **Dependencies**: None (Standard `ast` library).
- **Data**: In-memory cache of the AST map.

## 4. Verification Plan
**Automated Tests**:
- [x] `tests/test_ast_service.py`:
    - Parse a dummy python file.
    - Verify it extracts class and function names correctly.

**Manual Verification**:
- [x] Run `nebulus-atom start`.
- [x] Command: "Map the codebase".
- [x] Verify the agent sees the structure of `nebulus_atom/`.

## 5. Workflow Checklist
- [x] **Branch**: Created `feat/codebase-cartographer` branch?
- [x] **Work**: Implemented changes?
- [x] **Test**: All tests pass (`pytest`)?
- [x] **Doc**: Updated `README.md`?
- [x] **Data**: `git add .`, `git commit`?
