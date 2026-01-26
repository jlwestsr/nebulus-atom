import os
import chromadb
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any


class RagService:
    def __init__(self, db_path=".mini_nebulus/db", collection_name="codebase"):
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def index_codebase(self, root_dir: str = "."):
        documents = []
        ids = []
        metadatas = []

        # Walk through the codebase
        for dirpath, _, filenames in os.walk(root_dir):
            if (
                "venv" in dirpath
                or ".git" in dirpath
                or "__pycache__" in dirpath
                or ".mini_nebulus" in dirpath
            ):
                continue

            for filename in filenames:
                if filename.endswith(".py") or filename.endswith(".md"):
                    filepath = os.path.join(dirpath, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                            if content.strip():
                                documents.append(content)
                                ids.append(filepath)
                                metadatas.append({"path": filepath})
                    except Exception as e:
                        print(f"Skipping {filepath}: {e}")

        if documents:
            # Generate embeddings
            embeddings = self.model.encode(documents).tolist()

            # Add to ChromaDB
            self.collection.upsert(
                documents=documents, embeddings=embeddings, metadatas=metadatas, ids=ids
            )
            return f"Indexed {len(documents)} files."
        return "No files found to index."

    def search_code(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
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
                        if "distances" in results
                        else 0,
                        "content": results["documents"][0][i][:200]
                        + "...",  # Truncate content
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
