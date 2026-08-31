"""RAG (Retrieval-Augmented Generation) engine."""

from typing import Dict, List, Optional

from src.llm_client import LLMClient, create_llm_client
from src.config import LLMConfig
from src.retriever import Retriever


class RAGEngine:
    """RAG engine for answering questions about code."""

    SYSTEM_PROMPT = """You are an expert code analysis assistant. Your task is to answer questions about a GitHub repository based on the provided code context.

Guidelines:
1. Answer based ONLY on the provided code context
2. If the context doesn't contain the answer, say so clearly
3. Be specific - mention file names and line numbers when relevant
4. Explain technical concepts clearly
5. If you're unsure about something, acknowledge the uncertainty

The code context may have been sanitized to remove sensitive information (marked as ***REDACTED***).
"""

    def __init__(
        self,
        retriever: Retriever,
        llm_config: LLMConfig,
    ):
        """Initialize RAG engine.

        Args:
            retriever: Code retriever
            llm_config: LLM configuration
        """
        self.retriever = retriever
        self.llm = create_llm_client(llm_config)
        self.llm_config = llm_config

    def answer(
        self,
        question: str,
        repo_filter: Optional[str] = None,
        include_sources: bool = True,
    ) -> Dict:
        """Answer a question about the code.

        Args:
            question: User question
            repo_filter: Optional repository to filter by
            include_sources: Whether to include source references

        Returns:
            Dictionary with answer and metadata
        """
        # Retrieve relevant context
        context = self.retriever.retrieve_for_rag(
            query=question,
            repo_filter=repo_filter,
        )

        # Build prompt
        prompt = self._build_prompt(question, context)

        # Generate answer
        answer = self.llm.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,  # Lower temperature for factual answers
        )

        result = {
            "question": question,
            "answer": answer,
            "context_length": len(context),
        }

        if include_sources:
            # Extract source references
            sources = self._extract_sources(context)
            result["sources"] = sources

        return result

    def chat(
        self,
        messages: List[Dict[str, str]],
        repo_filter: Optional[str] = None,
    ) -> str:
        """Chat with context from the repository.

        Args:
            messages: Message history
            repo_filter: Optional repository filter

        Returns:
            Response text
        """
        # Get the last user message for retrieval
        last_user_message = None
        for msg in reversed(messages):
            if msg["role"] == "user":
                last_user_message = msg["content"]
                break

        if last_user_message:
            # Retrieve context for the last question
            context = self.retriever.retrieve_for_rag(
                query=last_user_message,
                repo_filter=repo_filter,
            )

            # Prepend context to system prompt
            enhanced_system = self.SYSTEM_PROMPT + f"\n\nRelevant code context:\n{context}"

            # Add system message
            chat_messages = [{"role": "system", "content": enhanced_system}]

            # Add conversation history (excluding old system messages)
            for msg in messages:
                if msg["role"] != "system":
                    chat_messages.append(msg)

            return self.llm.chat(chat_messages, temperature=0.3)

        # Fallback: just chat without context
        return self.llm.chat(messages, temperature=0.3)

    def _build_prompt(self, question: str, context: str) -> str:
        """Build the RAG prompt.

        Args:
            question: User question
            context: Retrieved context

        Returns:
            Complete prompt
        """
        return f"""Please answer the following question about the code repository:

Question: {question}

Relevant code context:
{'=' * 60}
{context}
{'=' * 60}

Based on the code context provided above, please answer the question. If the context doesn't contain enough information to answer the question, please say so.

Answer:"""

    def _extract_sources(self, context: str) -> List[Dict]:
        """Extract source file references from context.

        Args:
            context: Retrieved context

        Returns:
            List of source references
        """
        import re

        sources = []
        pattern = r"={60}\nFile: (.+)\nType: (.+)\nLines: (\d+)-(\d+)"

        for match in re.finditer(pattern, context):
            sources.append({
                "file": match.group(1),
                "type": match.group(2),
                "start_line": int(match.group(3)),
                "end_line": int(match.group(4)),
            })

        # Deduplicate
        seen = set()
        unique_sources = []
        for source in sources:
            key = source["file"]
            if key not in seen:
                seen.add(key)
                unique_sources.append(source)

        return unique_sources

    def explain_code(
        self,
        code_snippet: str,
        file_path: Optional[str] = None,
    ) -> str:
        """Explain a code snippet.

        Args:
            code_snippet: Code to explain
            file_path: Optional file path for context

        Returns:
            Explanation text
        """
        prompt = f"""Please explain the following code snippet:

```
{code_snippet}
```
"""
        if file_path:
            prompt += f"\nThis code is from file: {file_path}\n"

        prompt += """
Please explain:
1. What this code does at a high level
2. Key functions/classes and their purposes
3. Any notable patterns or techniques used
4. Potential issues or improvements (if any)

Explanation:"""

        return self.llm.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.4,
        )

    def summarize_repository(
        self,
        repo_name: str,
        tech_stack: Dict,
        file_count: int,
        line_count: int,
    ) -> str:
        """Generate a natural language summary of the repository.

        Args:
            repo_name: Repository name
            tech_stack: Technology stack information
            file_count: Total number of files
            line_count: Total lines of code

        Returns:
            Summary text
        """
        prompt = f"""Please provide a brief summary of the following code repository:

Repository: {repo_name}
Total Files: {file_count}
Total Lines: {line_count}

Technology Stack:
{self._format_tech_stack(tech_stack)}

Please provide:
1. A brief overview of what this repository appears to be
2. The main technologies used
3. The apparent architecture or project type
4. Any notable characteristics

Keep the summary concise (3-5 sentences)."""

        return self.llm.generate(
            prompt=prompt,
            temperature=0.5,
        )

    def _format_tech_stack(self, tech_stack: Dict) -> str:
        """Format tech stack for prompt."""
        lines = []

        if "languages" in tech_stack:
            lines.append(f"Languages: {', '.join(tech_stack['languages'])}")

        if "frameworks" in tech_stack:
            lines.append(f"Frameworks: {', '.join(tech_stack['frameworks'])}")

        if "dependencies" in tech_stack:
            deps = tech_stack["dependencies"][:10]
            lines.append(f"Key Dependencies: {', '.join(deps)}")

        return "\n".join(lines) if lines else "Unknown"
