import os
import asyncio
import chromadb
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import uuid
import time
from transformers import logging as transformers_logging

transformers_logging.set_verbosity_error()


class RagService:
    def __init__(self, db_path=".nebulus_atom/db", collection_name="codebase"):
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.history_collection = self.client.get_or_create_collection(
            name="command_history"
        )
        self._model_instance = None

    @property
    def model(self):
        if self._model_instance is None:
            # print("Lazy-loading RAG model (bert-base-uncased)...")  # Removed to prevent TUI corruption
            # Suppress logs during heavy model loading
            import contextlib
            import sys

            @contextlib.contextmanager
            def suppress_output():
                with open(os.devnull, "w") as devnull:
                    old_stdout = sys.stdout
                    old_stderr = sys.stderr
                    sys.stdout = devnull
                    sys.stderr = devnull
                    try:
                        yield
                    finally:
                        sys.stdout = old_stdout
                        sys.stderr = old_stderr

            with suppress_output():
                # Use a lighter model for speed or the configured one
                self._model_instance = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model_instance

    async def index_codebase(self, root_dir: str = "."):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._index_codebase_sync, root_dir)

    def _index_codebase_sync(self, root_dir: str):
        documents = []
        ids = []
        metadatas = []

        # Walk through the codebase
        for dirpath, _, filenames in os.walk(root_dir):
            if (
                "venv" in dirpath
                or ".git" in dirpath
                or "__pycache__" in dirpath
                or ".nebulus_atom" in dirpath
                or "egg-info" in dirpath
            ):
                continue

            for filename in filenames:
                if filename.endswith(".py") or filename.endswith(".md"):
                    filepath = os.path.join(dirpath, filename)
                    try:
                        with open(
                            filepath, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            content = f.read()
                            if content.strip():
                                documents.append(content[:2000])  # Chunk limit
                                ids.append(filepath)
                                metadatas.append({"path": filepath})
                    except Exception:
                        continue

        if documents:
            # Accessing self.model here triggers the lazy load in the thread
            embeddings = self.model.encode(documents).tolist()
            self.collection.upsert(
                documents=documents, embeddings=embeddings, metadatas=metadatas, ids=ids
            )
            return f"Indexed {len(documents)} files."
        return "No files found to index."

    async def search_code(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._search_code_sync, query, n_results
        )

    def _search_code_sync(self, query: str, n_results: int) -> List[Dict[str, Any]]:
        query_embedding = self.model.encode([query]).tolist()
        results = self.collection.query(
            query_embeddings=query_embedding, n_results=n_results
        )

        output = []
        if results["ids"]:
            for i in range(len(results["ids"][0])):
                output.append(
                    {
                        "id": results["ids"][0][i],
                        "score": results["distances"][0][i]
                        if "distances" in results and results["distances"] is not None
                        else 0,
                        "content": results["documents"][0][i][:200] + "...",
                        "metadata": results["metadatas"][0][i],
                    }
                )
        return output

    async def index_history(self, role: str, content: str, session_id: str = "default"):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._index_history_sync, role, content, session_id
        )

    def _index_history_sync(self, role: str, content: str, session_id: str):
        if not content or not content.strip():
            return
        doc_id = str(uuid.uuid4())
        timestamp = time.time()
        embedding = self.model.encode([content]).tolist()

        self.history_collection.add(
            documents=[content],
            embeddings=embedding,
            metadatas=[
                {"role": role, "session_id": session_id, "timestamp": timestamp}
            ],
            ids=[doc_id],
        )

    async def search_history(
        self, query: str, n_results: int = 5
    ) -> List[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._search_history_sync, query, n_results
        )

    def _search_history_sync(self, query: str, n_results: int) -> List[Dict[str, Any]]:
        query_embedding = self.model.encode([query]).tolist()
        results = self.history_collection.query(
            query_embeddings=query_embedding, n_results=n_results
        )

        output = []
        if results["ids"]:
            for i in range(len(results["ids"][0])):
                output.append(
                    {
                        "id": results["ids"][0][i],
                        "score": results["distances"][0][i]
                        if "distances" in results and results["distances"] is not None
                        else 0,
                        "content": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                    }
                )
        return output


class RagServiceManager:
    def __init__(self):
        self.service = None

    def get_service(self, session_id: str = "default") -> RagService:
        if not self.service:
            self.service = RagService()
        return self.service
