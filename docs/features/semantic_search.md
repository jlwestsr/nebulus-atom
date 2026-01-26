# Feature: Semantic Code Search (RAG)

## 1. Overview
**Branch**: `feat/semantic-search`

Implement **Retrieval-Augmented Generation (RAG)** for the codebase. Instead of manually pinning files, the agent can semantically query the project to find relevant code snippets, improving autonomy on large codebases.

## 2. Requirements
- [ ] Implement `index_codebase` tool to generate embeddings for all project files.
- [ ] Implement `search_code <query>` tool to retrieve top-k relevant snippets.
- [ ] Automatically update index on file writes (incremental indexing).
- [ ] Use a lightweight local embedding model (e.g., `all-MiniLM-L6-v2`) and vector store (e.g., `chromadb` or simple memory/file store).

## 3. Technical Implementation
- **Modules**:
    - `mini_nebulus/services/rag_service.py` (Indexing and retrieval logic).
    - `mini_nebulus/services/tool_executor.py` (Add search tools).
- **Dependencies**: `sentence-transformers`, `chromadb` (or `numpy` + JSON).
- **Data**: `.mini_nebulus/index/` for vector storage.

## 4. Verification Plan
- [ ] Run `index_codebase`.
- [ ] Ask `search_code "how are tools executed?"`.
- [ ] Verify `ToolExecutor.dispatch` code is returned.

## 5. Workflow Checklist
- [ ] Create branch `feat/semantic-search`
- [ ] Implementation
- [ ] Verification
