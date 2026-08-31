"""Document chunking strategies for code splitting."""

import ast
import re
from dataclasses import dataclass
from typing import Iterator, List, Optional


@dataclass
class Chunk:
    """A document chunk with metadata."""

    content: str
    source_file: str
    chunk_type: str  # function, class, module, etc.
    start_line: int
    end_line: int
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class CodeChunker:
    """Chunks code files into semantically meaningful segments."""

    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        """Initialize chunker.

        Args:
            chunk_size: Target size of each chunk in characters
            overlap: Overlap between chunks in characters
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_file(self, file_path: str, content: str) -> Iterator[Chunk]:
        """Chunk a single file based on its type.

        Args:
            file_path: Path to the file
            content: File content

        Yields:
            Chunk objects
        """
        if file_path.endswith(".py"):
            yield from self._chunk_python(file_path, content)
        elif file_path.endswith((".js", ".ts", ".jsx", ".tsx")):
            yield from self._chunk_javascript(file_path, content)
        else:
            yield from self._chunk_generic(file_path, content)

    def _chunk_python(self, file_path: str, content: str) -> Iterator[Chunk]:
        """Chunk Python file by functions and classes."""
        try:
            tree = ast.parse(content)
            lines = content.split("\n")

            # Get file-level docstring if exists
            if (
                tree.body
                and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Constant)
                and isinstance(tree.body[0].value.value, str)
            ):
                docstring_end = tree.body[0].end_lineno
                docstring = "\n".join(lines[:docstring_end])
                yield Chunk(
                    content=docstring,
                    source_file=file_path,
                    chunk_type="module_docstring",
                    start_line=1,
                    end_line=docstring_end,
                    metadata={"module_path": file_path},
                )

            # Chunk by top-level definitions
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    chunk_content = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                    yield Chunk(
                        content=chunk_content,
                        source_file=file_path,
                        chunk_type="class" if isinstance(node, ast.ClassDef) else "function",
                        start_line=node.lineno,
                        end_line=node.end_lineno,
                        metadata={
                            "name": node.name,
                            "module_path": file_path,
                        },
                    )

            # If file is small enough, also yield as a whole
            if len(content) <= self.chunk_size:
                yield Chunk(
                    content=content,
                    source_file=file_path,
                    chunk_type="module",
                    start_line=1,
                    end_line=len(lines),
                    metadata={"module_path": file_path},
                )

        except SyntaxError:
            # Fall back to generic chunking
            yield from self._chunk_generic(file_path, content)

    def _chunk_javascript(self, file_path: str, content: str) -> Iterator[Chunk]:
        """Chunk JavaScript/TypeScript file by functions and classes."""
        lines = content.split("\n")

        # Pattern to match function/class definitions
        patterns = [
            (r"(?:export\s+)?(?:default\s+)?(?:class|function)\s+(\w+)", "definition"),
            (r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\([^)]*\)\s*=>)", "arrow_function"),
            (r"(?:async\s+)?function\s+(\w+)", "function"),
        ]

        matches = []
        for pattern, match_type in patterns:
            for match in re.finditer(pattern, content):
                matches.append((match.start(), match_type, match.group(1)))

        matches.sort(key=lambda x: x[0])

        # Create chunks based on matches
        if not matches:
            yield from self._chunk_generic(file_path, content)
            return

        for i, (start_pos, match_type, name) in enumerate(matches):
            # Find end of this definition
            if i + 1 < len(matches):
                end_pos = matches[i + 1][0]
            else:
                end_pos = len(content)

            chunk_content = content[start_pos:end_pos].strip()

            # Calculate line numbers
            start_line = content[:start_pos].count("\n") + 1
            end_line = content[:end_pos].count("\n") + 1

            yield Chunk(
                content=chunk_content,
                source_file=file_path,
                chunk_type=match_type,
                start_line=start_line,
                end_line=end_line,
                metadata={
                    "name": name,
                    "file_path": file_path,
                },
            )

        # Also yield file overview if small enough
        if len(content) <= self.chunk_size:
            yield Chunk(
                content=content,
                source_file=file_path,
                chunk_type="module",
                start_line=1,
                end_line=len(lines),
                metadata={"file_path": file_path},
            )

    def _chunk_generic(self, file_path: str, content: str) -> Iterator[Chunk]:
        """Generic chunking by size with overlap."""
        lines = content.split("\n")

        if len(content) <= self.chunk_size:
            yield Chunk(
                content=content,
                source_file=file_path,
                chunk_type="file",
                start_line=1,
                end_line=len(lines),
                metadata={"file_path": file_path},
            )
            return

        # Sliding window chunking
        start = 0
        chunk_num = 0

        while start < len(content):
            end = start + self.chunk_size

            # Try to break at a newline
            if end < len(content):
                # Look for newline within 100 chars of target
                search_start = max(end - 100, start)
                newline_pos = content.find("\n", end)
                if newline_pos != -1 and newline_pos - end < 100:
                    end = newline_pos + 1

            chunk_content = content[start:end]

            # Calculate line numbers
            start_line = content[:start].count("\n") + 1
            end_line = content[:end].count("\n") + 1

            yield Chunk(
                content=chunk_content,
                source_file=file_path,
                chunk_type="segment",
                start_line=start_line,
                end_line=end_line,
                metadata={
                    "file_path": file_path,
                    "chunk_num": chunk_num,
                },
            )

            # Move with overlap
            start = end - self.overlap
            chunk_num += 1

    def chunk_repository(self, files: dict[str, str]) -> List[Chunk]:
        """Chunk all files in a repository.

        Args:
            files: Dictionary mapping file paths to contents

        Returns:
            List of all chunks
        """
        chunks = []
        for file_path, content in files.items():
            for chunk in self.chunk_file(file_path, content):
                chunks.append(chunk)
        return chunks
