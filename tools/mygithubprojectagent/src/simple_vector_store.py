"""Simple in-memory vector store as ChromaDB replacement for Python 3.14 compatibility."""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


@dataclass
class VectorDocument:
    """A document with vector embedding."""

    id: str
    content: str
    embedding: np.ndarray
    metadata: Dict = field(default_factory=dict)


class SimpleVectorStore:
    """Simple in-memory vector store using cosine similarity."""

    def __init__(self, collection_name: str = "default", persist_dir: Optional[str] = None):
        """Initialize vector store.

        Args:
            collection_name: Name of the collection
            persist_dir: Optional directory to persist data
        """
        self.collection_name = collection_name
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self.documents: Dict[str, VectorDocument] = {}

        # Load existing data if available
        if self.persist_dir:
            self._load()

    def add(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict]] = None,
    ) -> None:
        """Add documents to the store.

        Args:
            ids: Document IDs
            documents: Document contents
            embeddings: Document embeddings
            metadatas: Optional metadata for each document
        """
        metadatas = metadatas or [{} for _ in ids]

        for doc_id, content, embedding, metadata in zip(ids, documents, embeddings, metadatas):
            self.documents[doc_id] = VectorDocument(
                id=doc_id,
                content=content,
                embedding=np.array(embedding),
                metadata=metadata,
            )

        if self.persist_dir:
            self._save()

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        filter_dict: Optional[Dict] = None,
    ) -> Dict[str, List]:
        """Query documents by vector similarity.

        Args:
            query_embedding: Query vector
            n_results: Number of results to return
            filter_dict: Optional filter on metadata

        Returns:
            Dictionary with ids, distances, documents, and metadatas
        """
        query_vec = np.array(query_embedding)

        # Filter documents if filter_dict provided
        docs = list(self.documents.values())
        if filter_dict:
            for key, value in filter_dict.items():
                docs = [d for d in docs if d.metadata.get(key) == value]

        if not docs:
            return {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}

        # Calculate cosine similarities
        similarities = []
        for doc in docs:
            similarity = self._cosine_similarity(query_vec, doc.embedding)
            similarities.append((doc, similarity))

        # Sort by similarity (highest first)
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Take top n_results
        top_results = similarities[:n_results]

        return {
            "ids": [[doc.id for doc, _ in top_results]],
            "distances": [[1 - sim for _, sim in top_results]],  # Convert similarity to distance
            "documents": [[doc.content for doc, _ in top_results]],
            "metadatas": [[doc.metadata for doc, _ in top_results]],
        }

    def delete(self, ids: List[str]) -> None:
        """Delete documents by ID."""
        for doc_id in ids:
            if doc_id in self.documents:
                del self.documents[doc_id]

        if self.persist_dir:
            self._save()

    def get_all(self) -> List[VectorDocument]:
        """Get all documents."""
        return list(self.documents.values())

    def count(self) -> int:
        """Get total document count."""
        return len(self.documents)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _save(self) -> None:
        """Persist documents to disk."""
        if not self.persist_dir:
            return

        self.persist_dir.mkdir(parents=True, exist_ok=True)
        data = {
            doc_id: {
                "content": doc.content,
                "embedding": doc.embedding.tolist(),
                "metadata": doc.metadata,
            }
            for doc_id, doc in self.documents.items()
        }

        file_path = self.persist_dir / f"{self.collection_name}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        """Load documents from disk."""
        if not self.persist_dir:
            return

        file_path = self.persist_dir / f"{self.collection_name}.json"
        if not file_path.exists():
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for doc_id, doc_data in data.items():
                self.documents[doc_id] = VectorDocument(
                    id=doc_id,
                    content=doc_data["content"],
                    embedding=np.array(doc_data["embedding"]),
                    metadata=doc_data.get("metadata", {}),
                )
        except (json.JSONDecodeError, KeyError):
            # Ignore corrupted files
            pass
