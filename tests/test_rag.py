import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_chroma():
    with patch("nebulus_atom.services.rag_service.chromadb") as mock:
        yield mock


@pytest.fixture
def mock_sentence_transformer():
    with patch("nebulus_atom.services.rag_service.SentenceTransformer") as mock:
        mock_instance = mock.return_value
        # Mock encode to return an object with tolist()
        mock_embeddings = MagicMock()
        mock_embeddings.tolist.return_value = [0.1, 0.2, 0.3]
        mock_instance.encode.return_value = mock_embeddings
        yield mock


@pytest.mark.asyncio
async def test_index_history(mock_chroma, mock_sentence_transformer):
    from nebulus_atom.services.rag_service import RagService

    service = RagService()

    await service.index_history("user", "Hello world", "test_session")

    # Verify add was called on history_collection
    service.history_collection.add.assert_called_once()
    call_kwargs = service.history_collection.add.call_args[1]
    assert call_kwargs["documents"] == ["Hello world"]
    assert call_kwargs["metadatas"][0]["role"] == "user"
    assert call_kwargs["metadatas"][0]["session_id"] == "test_session"


@pytest.mark.asyncio
async def test_search_history(mock_chroma, mock_sentence_transformer):
    from nebulus_atom.services.rag_service import RagService

    service = RagService()

    # Mock query result
    service.history_collection.query.return_value = {
        "ids": [["doc1"]],
        "distances": [[0.5]],
        "documents": [["Hello world"]],
        "metadatas": [[{"role": "user"}]],
    }

    results = await service.search_history("Hello")

    assert len(results) == 1
    assert results[0]["content"] == "Hello world"
    assert results[0]["score"] == 0.5
    assert results[0]["metadata"]["role"] == "user"
