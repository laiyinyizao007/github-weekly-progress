"""Knowledge base management for RAG system."""

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

# Try to import ChromaDB, fallback to simple vector store for Python 3.14+
try:
    import chromadb
    from chromadb.api.types import IncludeEnum
    CHROMADB_AVAILABLE = True
except Exception:
    CHROMADB_AVAILABLE = False

from src.chunker import Chunk, CodeChunker
from src.config import ChromaConfig
from src.embedder import Embedder, create_embedder
from src.config import EmbeddingConfig

if not CHROMADB_AVAILABLE:
    from src.simple_vector_store import SimpleVectorStore


class KnowledgeBase:
    """Manages the vector knowledge base for code retrieval."""

    def __init__(
        self,
        chroma_config: ChromaConfig,
        embedding_config: EmbeddingConfig,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        """Initialize knowledge base.

        Args:
            chroma_config: ChromaDB configuration
            embedding_config: Embedding configuration
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
        """
        self.chroma_config = chroma_config
        self.embedding_config = embedding_config

        # Initialize vector store (ChromaDB or fallback to simple store)
        if CHROMADB_AVAILABLE:
            try:
                self.client = chromadb.PersistentClient(path=chroma_config.db_path)
                self.collection = self.client.get_or_create_collection(
                    name=chroma_config.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                self.using_simple_store = False
            except Exception:
                # Fallback to simple vector store
                self.collection = SimpleVectorStore(
                    collection_name=chroma_config.collection_name,
                    persist_dir=chroma_config.db_path,
                )
                self.using_simple_store = True
        else:
            # Use simple vector store for Python 3.14+ compatibility
            self.collection = SimpleVectorStore(
                collection_name=chroma_config.collection_name,
                persist_dir=chroma_config.db_path,
            )
            self.using_simple_store = True

        # Initialize embedder
        self.embedder = create_embedder(embedding_config)

        # Initialize chunker
        self.chunker = CodeChunker(chunk_size=chunk_size, overlap=chunk_overlap)

    def _generate_id(self, content: str, file_path: str, start_line: int) -> str:
        """Generate a unique ID for a chunk."""
        content_hash = hashlib.sha256(
            f"{file_path}:{start_line}:{content[:100]}".encode()
        ).hexdigest()[:16]
        return content_hash

    def add_repository(
        self,
        repo_name: str,
        files: Dict[str, str],
        metadata: Optional[Dict] = None,
    ) -> Dict[str, int]:
        """Add a repository to the knowledge base.

        Args:
            repo_name: Repository name
            files: Dictionary mapping file paths to contents
            metadata: Optional repository metadata

        Returns:
            Statistics about the operation
        """
        stats = {"files": 0, "chunks": 0, "embeddings": 0}

        # Chunk all files
        chunks = self.chunker.chunk_repository(files)
        stats["chunks"] = len(chunks)

        if not chunks:
            return stats

        # Prepare for embedding
        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            chunk_id = self._generate_id(
                chunk.content, chunk.source_file, chunk.start_line
            )
            ids.append(chunk_id)
            documents.append(chunk.content)

            chunk_metadata = {
                "repo": repo_name,
                "file": chunk.source_file,
                "type": chunk.chunk_type,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
            }
            chunk_metadata.update(chunk.metadata)

            if metadata:
                chunk_metadata["repo_metadata"] = json.dumps(metadata)

            metadatas.append(chunk_metadata)

        # Embed in batches
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_docs = documents[i : i + batch_size]
            batch_metas = metadatas[i : i + batch_size]

            embeddings = self.embedder.embed(batch_docs)

            self.collection.add(
                ids=batch_ids,
                documents=batch_docs,
                embeddings=embeddings,
                metadatas=batch_metas,
            )

            stats["embeddings"] += len(batch_ids)

        stats["files"] = len(files)
        return stats

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        filter_dict: Optional[Dict] = None,
    ) -> List[Dict]:
        """Query the knowledge base.

        Args:
            query_text: Query text
            n_results: Number of results to return
            filter_dict: Optional filter criteria

        Returns:
            List of matching documents with metadata
        """
        query_embedding = self.embedder.embed([query_text])[0]

        if self.using_simple_store:
            # Use simple vector store query
            results = self.collection.query(
                query_embedding=query_embedding,
                n_results=n_results,
                filter_dict=filter_dict,
            )
            formatted_results = []
            if results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    formatted_results.append({
                        "id": doc_id,
                        "content": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i],
                    })
            return formatted_results
        else:
            # Use ChromaDB query
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=filter_dict,
                include=[IncludeEnum.documents, IncludeEnum.metadatas, IncludeEnum.distances],
            )

            formatted_results = []
            if results["ids"] and len(results["ids"][0]) > 0:
                for i, doc_id in enumerate(results["ids"][0]):
                    formatted_results.append({
                        "id": doc_id,
                        "content": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i],
                    })

            return formatted_results

    def delete_repository(self, repo_name: str) -> int:
        """Delete all documents from a repository.

        Args:
            repo_name: Repository name

        Returns:
            Number of documents deleted
        """
        if self.using_simple_store:
            # Get all documents and filter
            docs = self.collection.get_all()
            ids_to_delete = [doc.id for doc in docs if doc.metadata.get("repo") == repo_name]
            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
            return len(ids_to_delete)
        else:
            # Use ChromaDB
            results = self.collection.get(
                where={"repo": repo_name},
                include=[],
            )

            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                return len(results["ids"])

            return 0

    def get_repository_chunks(self, repo_name: str) -> List[Dict]:
        """Get all chunks for a repository.

        Args:
            repo_name: Repository name

        Returns:
            List of chunks with metadata
        """
        if self.using_simple_store:
            docs = self.collection.get_all()
            chunks = []
            for doc in docs:
                if doc.metadata.get("repo") == repo_name:
                    chunks.append({
                        "id": doc.id,
                        "content": doc.content,
                        "metadata": doc.metadata,
                    })
            return chunks
        else:
            results = self.collection.get(
                where={"repo": repo_name},
                include=[IncludeEnum.documents, IncludeEnum.metadatas],
            )

            chunks = []
            if results["ids"]:
                for i, doc_id in enumerate(results["ids"]):
                    chunks.append({
                        "id": doc_id,
                        "content": results["documents"][i],
                        "metadata": results["metadatas"][i],
                    })

            return chunks

    def clear(self) -> None:
        """Clear all documents from the knowledge base."""
        if self.using_simple_store:
            # Get all documents and delete them
            docs = self.collection.get_all()
            if docs:
                self.collection.delete(ids=[doc.id for doc in docs])
        else:
            self.client.delete_collection(self.chroma_config.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=self.chroma_config.collection_name,
                metadata={"hnsw:space": "cosine"},
            )

    def stats(self) -> Dict:
        """Get knowledge base statistics.

        Returns:
            Dictionary with statistics
        """
        if self.using_simple_store:
            docs = self.collection.get_all()
            count = len(docs)
            repos = set(doc.metadata.get("repo") for doc in docs if doc.metadata.get("repo"))
        else:
            count = self.collection.count()

            # Get all metadata to count repos
            results = self.collection.get(include=[])
            repos = set()
            for meta in results.get("metadatas", []) or []:
                if meta and "repo" in meta:
                    repos.add(meta["repo"])

        return {
            "total_documents": count,
            "repositories": list(repos),
            "embedding_dimension": self.embedder.dimension,
        }
