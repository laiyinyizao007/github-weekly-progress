"""Embedding model integration for vectorization."""

from abc import ABC, abstractmethod
from typing import List, Union

from openai import OpenAI

from src.config import EmbeddingConfig


class Embedder(ABC):
    """Abstract base class for embedding models."""

    @abstractmethod
    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """Embed text(s) into vectors.

        Args:
            texts: Single text or list of texts to embed

        Returns:
            List of embedding vectors
        """
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimension of the embedding vectors."""
        pass


class OpenAIEmbedder(Embedder):
    """OpenAI embedding model wrapper."""

    def __init__(self, config: EmbeddingConfig):
        """Initialize OpenAI embedder.

        Args:
            config: Embedding configuration
        """
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)
        self._dimension = self._get_dimension()

    def _get_dimension(self) -> int:
        """Get embedding dimension based on model."""
        dimension_map = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dimension_map.get(self.config.model, 1536)

    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """Embed text(s) using OpenAI API."""
        if isinstance(texts, str):
            texts = [texts]

        # Batch requests for efficiency
        batch_size = 100
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self.client.embeddings.create(
                model=self.config.model,
                input=batch,
            )
            embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(embeddings)

        return all_embeddings

    @property
    def dimension(self) -> int:
        return self._dimension


class SentenceTransformerEmbedder(Embedder):
    """Local sentence-transformers embedding model."""

    def __init__(self, config: EmbeddingConfig):
        """Initialize sentence-transformers embedder.

        Args:
            config: Embedding configuration
        """
        self.config = config
        self._load_model()

    def _load_model(self) -> None:
        """Lazy load the model."""
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(self.config.model)
            self._dimension = self.model.get_sentence_embedding_dimension()
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for local embeddings. "
                "Install with: pip install sentence-transformers"
            )

    def embed(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """Embed text(s) using local model."""
        if isinstance(texts, str):
            texts = [texts]

        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        return self._dimension


def create_embedder(config: EmbeddingConfig) -> Embedder:
    """Factory function to create appropriate embedder.

    Args:
        config: Embedding configuration

    Returns:
        Embedder instance
    """
    if config.provider == "openai":
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")
        return OpenAIEmbedder(config)
    elif config.provider == "sentence-transformers":
        return SentenceTransformerEmbedder(config)
    else:
        raise ValueError(f"Unknown embedding provider: {config.provider}")
