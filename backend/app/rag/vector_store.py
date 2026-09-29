import logging
import threading
from dataclasses import dataclass

import chromadb
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.rag.embeddings import embed

logger = logging.getLogger(__name__)

COLLECTION_NAME = "enterprise_documents"

# Thread-safe client holder — replaced on reconnect rather than cached forever.
_client_lock = threading.Lock()
_client: chromadb.HttpClient | None = None


def _make_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def _get_client() -> chromadb.HttpClient:
    """Return the shared ChromaDB client, reconnecting if the connection is dead."""
    global _client
    with _client_lock:
        if _client is None:
            _client = _make_client()
        return _client


def _reset_client() -> None:
    """Discard the cached client so the next call reconnects."""
    global _client
    with _client_lock:
        _client = None


@dataclass
class RetrievedChunk:
    text: str
    source: str
    distance: float
    allowed_roles: list[str]


def get_collection():
    return _get_client().get_or_create_collection(COLLECTION_NAME)


def upsert_documents(
    ids: list[str], texts: list[str], sources: list[str], allowed_roles: list[list[str]]
) -> None:
    try:
        collection = get_collection()
        collection.upsert(
            ids=ids,
            embeddings=embed(texts),
            documents=texts,
            metadatas=[
                {"source": source, "allowed_roles": ",".join(roles)}
                for source, roles in zip(sources, allowed_roles)
            ],
        )
    except Exception:
        _reset_client()
        raise


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
def query(text: str, n_results: int = 3) -> list[RetrievedChunk]:
    try:
        collection = get_collection()
        result = collection.query(query_embeddings=embed([text]), n_results=n_results)
    except Exception:
        _reset_client()
        raise

    documents = result.get("documents") or [[]]
    metadatas = result.get("metadatas") or [[]]
    distances = result.get("distances") or [[]]

    return [
        RetrievedChunk(
            text=doc,
            source=meta.get("source", "unknown"),
            distance=dist,
            allowed_roles=[r for r in meta.get("allowed_roles", "").split(",") if r],
        )
        for doc, meta, dist in zip(documents[0], metadatas[0], distances[0])
    ]
