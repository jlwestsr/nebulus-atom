import os
from typing import List, Optional
from mini_nebulus.utils.logger import setup_logger

logger = setup_logger(__name__)


class DocService:
    def __init__(self, doc_root: str = "docs"):
        self.doc_root = os.path.join(os.getcwd(), doc_root)

    def list_docs(self) -> List[str]:
        doc_files = []
        for dirpath, _, filenames in os.walk(self.doc_root):
            for filename in filenames:
                if filename.endswith(".md"):
                    rel_path = os.path.relpath(
                        os.path.join(dirpath, filename), self.doc_root
                    )
                    doc_files.append(rel_path)
        return sorted(doc_files)

    def read_doc(self, rel_path: str) -> Optional[str]:
        # Validate path to prevent directory traversal
        abs_path = os.path.abspath(os.path.join(self.doc_root, rel_path))
        if not abs_path.startswith(self.doc_root):
            logger.warning(f"Attempted directory traversal: {rel_path}")
            return None

        if not os.path.exists(abs_path):
            return None

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read doc {rel_path}: {e}")
            return None


class DocServiceManager:
    def __init__(self):
        self.service = None

    def get_service(self, session_id: str = "default") -> DocService:
        if not self.service:
            self.service = DocService()
        return self.service
