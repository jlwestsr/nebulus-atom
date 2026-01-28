import pytest
import os
import shutil
from mini_nebulus.services.doc_service import DocService


@pytest.fixture
def test_docs():
    doc_root = "test_docs"
    os.makedirs(doc_root, exist_ok=True)
    with open(os.path.join(doc_root, "test.md"), "w") as f:
        f.write("# Test Doc")
    yield doc_root
    if os.path.exists(doc_root):
        shutil.rmtree(doc_root)


def test_list_docs(test_docs):
    service = DocService(doc_root=test_docs)
    docs = service.list_docs()
    assert "test.md" in docs


def test_read_doc(test_docs):
    service = DocService(doc_root=test_docs)
    content = service.read_doc("test.md")
    assert "# Test Doc" in content


def test_read_doc_not_found(test_docs):
    service = DocService(doc_root=test_docs)
    content = service.read_doc("missing.md")
    assert content is None


def test_path_traversal(test_docs):
    service = DocService(doc_root=test_docs)
    # Try to read outside of doc root
    content = service.read_doc("../outside.txt")
    assert content is None
