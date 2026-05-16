"""Qdrant vector store for semantic RAG over the knowledge base.

All operations are resilient — if Qdrant is unreachable or auth fails,
calls return gracefully (empty results / no-op) so chat and SRS keep
working with the structural TOON skeleton only.
"""
import os
import logging
import hashlib
import asyncio
from typing import Optional

logger = logging.getLogger("lama.vector")

QDRANT_URL = os.environ.get("QDRANT_URL", "")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")
COLLECTION = "lama_kb"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2

_client = None
_embedder = None


def _enabled() -> bool:
    return bool(QDRANT_URL)


def get_client():
    global _client
    if _client is None and _enabled():
        try:
            from qdrant_client import QdrantClient
            _client = QdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY or None,
                timeout=30,
            )
        except Exception as e:
            logger.warning(f"Qdrant client init failed: {e}")
            _client = None
    return _client


def get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {EMBED_MODEL}")
            _embedder = SentenceTransformer(EMBED_MODEL)
        except Exception as e:
            logger.warning(f"SentenceTransformer load failed: {e}")
            _embedder = None
    return _embedder


def _stable_id(chunk_id: str) -> int:
    """Convert string chunk ID to a stable uint64."""
    return int(hashlib.md5(chunk_id.encode()).hexdigest()[:16], 16)


async def ensure_collection() -> bool:
    client = get_client()
    if client is None:
        return False
    try:
        from qdrant_client import models
        existing = [c.name for c in client.get_collections().collections]
        if COLLECTION not in existing:
            client.create_collection(
                collection_name=COLLECTION,
                vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection: {COLLECTION}")
        return True
    except Exception as e:
        logger.warning(f"Qdrant ensure_collection failed: {e}")
        return False


def _embed_batch(texts: list[str]) -> Optional[list[list[float]]]:
    embedder = get_embedder()
    if embedder is None:
        return None
    try:
        return embedder.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True).tolist()
    except Exception as e:
        logger.error(f"Embedding batch failed: {e}")
        return None


async def index_chunks(project_id: str, chunks: list[dict]) -> int:
    """Embed and upsert chunks. Returns number successfully indexed."""
    if not chunks or not _enabled():
        return 0
    ok = await ensure_collection()
    if not ok:
        return 0
    client = get_client()
    if client is None:
        return 0
    from qdrant_client import models

    indexed = 0
    BATCH = 256
    loop = asyncio.get_event_loop()
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i + BATCH]
        texts = [c["content"] for c in batch]
        # Run blocking embedding off the event loop
        vectors = await loop.run_in_executor(None, _embed_batch, texts)
        if vectors is None:
            continue
        points = [
            models.PointStruct(
                id=_stable_id(c["id"]),
                vector=vectors[j],
                payload={
                    "project_id": project_id,
                    "chunk_id": c["id"],
                    "content": c["content"],
                    "filename": c.get("filename", ""),
                    "filetype": c.get("filetype", ""),
                },
            )
            for j, c in enumerate(batch)
        ]
        try:
            await loop.run_in_executor(None, lambda: client.upsert(collection_name=COLLECTION, points=points))
            indexed += len(points)
        except Exception as e:
            logger.error(f"Qdrant upsert batch {i} failed: {e}")
    return indexed


async def search(project_id: str, query: str, top_k: int = 8) -> list[str]:
    """Return top-K relevant chunk contents. Returns [] on any failure."""
    if not _enabled() or not query:
        return []
    client = get_client()
    if client is None:
        return []
    embedder = get_embedder()
    if embedder is None:
        return []
    try:
        from qdrant_client import models
        loop = asyncio.get_event_loop()
        vector = await loop.run_in_executor(
            None,
            lambda: embedder.encode([query], normalize_embeddings=True)[0].tolist(),
        )
        query_filter = models.Filter(
            must=[models.FieldCondition(
                key="project_id",
                match=models.MatchValue(value=project_id),
            )]
        )

        def _do_search():
            # qdrant-client >= 1.10 uses query_points; older uses search.
            if hasattr(client, "query_points"):
                res = client.query_points(
                    collection_name=COLLECTION,
                    query=vector,
                    query_filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                )
                # query_points returns a wrapper with .points
                return getattr(res, "points", res)
            return client.search(
                collection_name=COLLECTION,
                query_vector=vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )

        results = await loop.run_in_executor(None, _do_search)
        return [r.payload.get("content", "") for r in results if r.payload]
    except Exception as e:
        logger.warning(f"Qdrant search failed, returning empty: {e}")
        return []


async def delete_project_vectors(project_id: str) -> bool:
    if not _enabled():
        return False
    client = get_client()
    if client is None:
        return False
    try:
        from qdrant_client import models
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: client.delete(
                collection_name=COLLECTION,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[models.FieldCondition(
                            key="project_id",
                            match=models.MatchValue(value=project_id),
                        )]
                    )
                ),
            ),
        )
        return True
    except Exception as e:
        logger.warning(f"Qdrant delete failed: {e}")
        return False
