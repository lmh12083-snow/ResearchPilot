"""
Embedding service — thin wrapper around sentence-transformers.

Model is loaded lazily on first call (not at import time) to avoid
blocking FastAPI startup with the initial download.
"""

from typing import Optional


class EmbeddingService:
    """Generate embeddings for text chunks using sentence-transformers."""

    _model = None
    _model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"

    @classmethod
    def _get_model(cls):
        """Load model on first call, cache in class variable."""
        if cls._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers is not installed. "
                    "Install with: pip install sentence-transformers"
                )
            cls._model = SentenceTransformer(cls._model_name)
        return cls._model

    @classmethod
    def embed(cls, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of float vectors, each with dimension 384 for all-MiniLM-L6-v2.
        """
        if not texts:
            return []

        model = cls._get_model()
        embeddings = model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.tolist()

    @classmethod
    def embed_dimension(cls) -> int:
        """Return the embedding dimension of the loaded model."""
        model = cls._get_model()
        return model.get_sentence_embedding_dimension()
