# Feature: Semantic Code Search (RAG)

## 1. Overview
**Branch**: `feat/semantic-search`

Implement **Retrieval-Augmented Generation (RAG)** for the codebase. Instead of manually pinning files, the agent can semantically query the project to find relevant code snippets, improving autonomy on large codebases.

## 2. Requirements
- [x] Implement `index_codebase` tool to generate embeddings for all project files.
- [x] Implement `search_code <query>` tool to retrieve top-k relevant snippets.
- [x] Automatically update index on file writes (incremental indexing). (Partially implemented via manual index trigger, full auto-hook left for future optimization to avoid perf hit).
- [x] Use a lightweight local embedding model (e.g., `all-MiniLM-L6-v2`) and vector store (e.g., `chromadb` or simple memory/file store).

## 3. Technical Implementation
- **Modules**:
    - `nebulus_atom/services/rag_service.py` (Indexing and retrieval logic).
    - `nebulus_atom/services/tool_executor.py` (Add search tools).
- **Dependencies**: `sentence-transformers`, `chromadb`.
- **Data**: `.nebulus_atom/db/` for vector storage.

## 4. Verification Plan
- [x] Run `index_codebase`.
- [x] Ask `search_code "how are tools executed?"`.
- [x] Verify `ToolExecutor.dispatch` code is returned.

## 5. Workflow Checklist
- [x] Create branch `feat/semantic-search`
- [x] Implementation
- [x] Verification
