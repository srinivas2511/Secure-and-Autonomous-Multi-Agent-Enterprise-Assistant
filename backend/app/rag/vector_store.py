from dataclasses import dataclass
from functools import lru_cache

import chromadb

from app.core.config import settings
from app.rag.embeddings import embed

COLLECTION_NAME = "enterprise_documents"


@dataclass
class RetrievedChunk:
    text: str
    source: str
    distance: float
    allowed_roles: list[str]


@lru_cache(maxsize=1)
def _get_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
        settings=chromadb.config.Settings(anonymized_telemetry=False),
    )


def get_collection():
    return _get_client().get_or_create_collection(COLLECTION_NAME)


def upsert_documents(
    ids: list[str], texts: list[str], sources: list[str], allowed_roles: list[list[str]]
) -> None:
    collection = get_collection()
    collection.upsert(
        ids=ids,
        embeddings=embed(texts),
        documents=texts,
        metadatas=[
            # Chroma metadata values must be scalar -- roles are joined into a string.
            {"source": source, "allowed_roles": ",".join(roles)}
            for source, roles in zip(sources, allowed_roles)
        ],
    )


def query(text: str, n_results: int = 3) -> list[RetrievedChunk]:
    collection = get_collection()
    result = collection.query(query_embeddings=embed([text]), n_results=n_results)

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
