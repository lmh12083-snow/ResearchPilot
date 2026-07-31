"""
ChromaDB vector store wrapper.

Persists to a local directory — no external server needed.
Uses a single collection "paper_chunks" with cosine similarity.
"""

from pathlib import Path
from typing import Optional


class VectorStore:
    """Persistent ChromaDB wrapper for paper chunk storage and retrieval."""

    def __init__(self, persist_dir: str):
        self._persist_dir = str(Path(persist_dir))
        self._client = None
        self._collection = None

    def _get_client(self):
        """Lazy-init the ChromaDB persistent client."""
        if self._client is None:
            try:
                import chromadb
            except ImportError:
                raise RuntimeError(
                    "chromadb is not installed. "
                    "Install with: pip install chromadb"
                )
            self._client = chromadb.PersistentClient(path=self._persist_dir)
        return self._client

    def _get_collection(self):
        """Lazy-init or get the paper_chunks collection."""
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name="paper_chunks",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_paper_chunks(
        self,
        paper_id: int,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> int:
        """
        Add all chunks of a paper to the vector store.

        Args:
            paper_id: Paper ID for metadata filtering.
            chunks: List of dicts with keys: text, chunk_index, page_number.
            embeddings: List of embedding vectors (same order as chunks).

        Returns:
            Number of chunks added.
        """
        if not chunks or not embeddings:
            return 0

        collection = self._get_collection()
        ids = [f"{paper_id}_{c['chunk_index']}" for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [
            {
                "paper_id": paper_id,
                "chunk_index": c["chunk_index"],
                "page_number": c.get("page_number"),
                "char_length": len(c["text"]),
            }
            for c in chunks
        ]

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        return len(chunks)

    def get_all_chunks(self, paper_ids: Optional[list[int]] = None) -> list[dict]:
        """Fetch all chunks, optionally filtered by a list of paper_ids.

        Used by hybrid search to build a BM25 index over the relevant scope.
        """
        collection = self._get_collection()
        where = None
        if paper_ids:
            if len(paper_ids) == 1:
                where = {"paper_id": paper_ids[0]}
            else:
                where = {"paper_id": {"$in": paper_ids}}

        results = collection.get(where=where, include=["documents", "metadatas"])
        formatted = []
        if results and results["ids"]:
            for i in range(len(results["ids"])):
                formatted.append({
                    "id": results["ids"][i],
                    "text": results["documents"][i],
                    "metadata": results["metadatas"][i],
                })
        return formatted

    def delete_paper_chunks(self, paper_id: int) -> None:
        """Delete all chunks belonging to a paper."""
        try:
            collection = self._get_collection()
            collection.delete(where={"paper_id": paper_id})
        except Exception:
            # ChromaDB might not have this paper's chunks yet
            pass

    def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        paper_id: Optional[int] = None,
    ) -> list[dict]:
        """
        Return top-k chunks by cosine similarity.

        Args:
            query_embedding: Query vector.
            top_k: Number of results to return.
            paper_id: Optional filter to a specific paper.

        Returns:
            List of dicts: {id, text, metadata, distance}.
        """
        collection = self._get_collection()
        where = {"paper_id": paper_id} if paper_id is not None else None

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        formatted = []
        if results and results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                formatted.append({
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                })
        return formatted
