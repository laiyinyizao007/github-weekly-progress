"""Retriever for querying the knowledge base."""

from typing import Dict, List, Optional

from src.knowledge_base import KnowledgeBase


class Retriever:
    """Retrieves relevant code chunks for queries."""

    def __init__(self, knowledge_base: KnowledgeBase):
        """Initialize retriever.

        Args:
            knowledge_base: Knowledge base to query
        """
        self.kb = knowledge_base

    def retrieve(
        self,
        query: str,
        n_results: int = 5,
        repo_filter: Optional[str] = None,
        file_filter: Optional[str] = None,
    ) -> List[Dict]:
        """Retrieve relevant chunks for a query.

        Args:
            query: Search query
            n_results: Number of results to return
            repo_filter: Optional repository name filter
            file_filter: Optional file path filter (substring match)

        Returns:
            List of matching chunks with metadata
        """
        # Build filter
        filter_dict = {}
        if repo_filter:
            filter_dict["repo"] = repo_filter

        # Query knowledge base
        results = self.kb.query(
            query_text=query,
            n_results=n_results * 2,  # Get more for post-filtering
            filter_dict=filter_dict if filter_dict else None,
        )

        # Post-filter by file path if specified
        if file_filter:
            results = [
                r for r in results
                if file_filter.lower() in r["metadata"].get("file", "").lower()
            ]

        # Sort by distance and limit results
        results.sort(key=lambda x: x["distance"])

        return results[:n_results]

    def retrieve_for_rag(
        self,
        query: str,
        context_window: int = 3000,
        repo_filter: Optional[str] = None,
    ) -> str:
        """Retrieve and format context for RAG.

        Args:
            query: Search query
            context_window: Maximum context size in characters
            repo_filter: Optional repository filter

        Returns:
            Formatted context string
        """
        results = self.retrieve(
            query=query,
            n_results=10,
            repo_filter=repo_filter,
        )

        if not results:
            return "No relevant code found."

        # Build context string
        context_parts = []
        total_length = 0

        for result in results:
            metadata = result["metadata"]
            content = result["content"]

            # Format chunk
            chunk_header = f"\n{'=' * 60}\n"
            chunk_header += f"File: {metadata.get('file', 'Unknown')}\n"
            chunk_header += f"Type: {metadata.get('type', 'Unknown')}\n"
            chunk_header += f"Lines: {metadata.get('start_line', 0)}-{metadata.get('end_line', 0)}\n"
            chunk_header += f"{'=' * 60}\n"

            chunk_text = chunk_header + content

            # Check if adding this chunk exceeds context window
            if total_length + len(chunk_text) > context_window:
                break

            context_parts.append(chunk_text)
            total_length += len(chunk_text)

        return "\n\n".join(context_parts)

    def search_by_file(
        self,
        file_path: str,
        n_results: int = 5,
    ) -> List[Dict]:
        """Search for chunks from a specific file.

        Args:
            file_path: File path to search
            n_results: Number of results

        Returns:
            List of chunks from the file
        """
        # Get all chunks and filter by file
        all_chunks = []

        # Query with a generic query to get all docs, then filter
        results = self.kb.query(
            query_text="function class module",
            n_results=100,
        )

        for result in results:
            if file_path.lower() in result["metadata"].get("file", "").lower():
                all_chunks.append(result)

        return all_chunks[:n_results]

    def get_file_summary(self, file_path: str) -> Optional[Dict]:
        """Get a summary of a file from its chunks.

        Args:
            file_path: File path

        Returns:
            Summary dictionary or None
        """
        chunks = self.search_by_file(file_path, n_results=100)

        if not chunks:
            return None

        # Extract information from chunks
        functions = []
        classes = []
        imports = []

        for chunk in chunks:
            meta = chunk["metadata"]

            if meta.get("type") == "function":
                if "name" in meta:
                    functions.append(meta["name"])
            elif meta.get("type") == "class":
                if "name" in meta:
                    classes.append(meta["name"])

            # Try to extract imports from content
            content = chunk["content"]
            if "import " in content:
                lines = content.split("\n")
                for line in lines:
                    if line.strip().startswith("import ") or line.strip().startswith("from "):
                        imports.append(line.strip())

        return {
            "file": file_path,
            "chunks": len(chunks),
            "functions": functions,
            "classes": classes,
            "imports": list(set(imports))[:10],  # Limit imports
        }
