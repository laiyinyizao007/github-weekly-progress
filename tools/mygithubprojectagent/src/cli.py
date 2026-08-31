"""Command-line interface for the GitHub Agent RAG system."""

import sys
from typing import Optional

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from src.config import Config, ensure_directories, load_config
from src.github_client import GitHubClient
from src.knowledge_base import KnowledgeBase
from src.llm_client import create_llm_client
from src.rag_engine import RAGEngine
from src.repo_analyzer import RepoAnalyzer
from src.report_generator import ReportGenerator
from src.retriever import Retriever
from src.sanitizer import Sanitizer


console = Console()


class GitHubAgent:
    """Main application class."""

    def __init__(self, config: Config):
        """Initialize the agent."""
        self.config = config
        self.github = GitHubClient(config.github)
        self.kb = KnowledgeBase(
            config.chroma,
            config.embedding,
        )
        self.retriever = Retriever(self.kb)
        self.rag = RAGEngine(self.retriever, config.llm)
        self.analyzer = RepoAnalyzer(config.app)
        self.sanitizer = Sanitizer(config.privacy)
        self.report_gen = ReportGenerator()
        self.current_repo: Optional[str] = None

    def analyze_repo(self, repo_name: str, ref: str = "main") -> dict:
        """Analyze a repository and build knowledge base.

        Args:
            repo_name: Repository name (owner/repo)
            ref: Branch or commit ref

        Returns:
            Analysis statistics
        """
        console.print(f"[bold blue]Fetching repository: {repo_name}[/bold blue]")

        # Get repository info
        repo_info = self.github.get_repo_info(repo_name)
        console.print(f"[green]✓[/green] Repository found: {repo_info['name']}")

        # Fetch all files
        console.print("[bold blue]Fetching files...[/bold blue]")
        files = self.github.fetch_repository(
            repo_name,
            exclude_patterns=self.config.app.exclude_patterns,
            max_file_size_mb=self.config.app.max_file_size_mb,
            ref=ref,
        )
        console.print(f"[green]✓[/green] Fetched {len(files)} files")

        # Sanitize files
        console.print("[bold blue]Sanitizing sensitive information...[/bold blue]")
        sanitized_files = {}
        for path, content in files.items():
            sanitized = self.sanitizer.sanitize_file(path, content)
            sanitized_files[path] = sanitized
        console.print("[green]✓[/green] Sanitization complete")

        # Analyze repository
        console.print("[bold blue]Analyzing repository structure...[/bold blue]")
        analysis = self.analyzer.analyze(sanitized_files)
        console.print(f"[green]✓[/green] Analysis complete ({analysis.total_lines:,} lines)")

        # Add to knowledge base
        console.print("[bold blue]Building knowledge base...[/bold blue]")
        stats = self.kb.add_repository(
            repo_name,
            sanitized_files,
            metadata={
                "url": repo_info.get("url"),
                "description": repo_info.get("description"),
                "default_branch": repo_info.get("default_branch"),
            },
        )
        console.print(f"[green]✓[/green] Knowledge base built ({stats['chunks']} chunks)")

        self.current_repo = repo_name

        return {
            "repo_info": repo_info,
            "analysis": analysis,
            "stats": stats,
        }

    def chat(self) -> None:
        """Start interactive chat session."""
        if not self.current_repo:
            console.print("[red]No repository loaded. Please analyze a repository first.[/red]")
            return

        console.print(Panel.fit(
            f"[bold green]Chat Mode: {self.current_repo}[/bold green]\n"
            "Type your questions about the code. Use 'quit' or 'exit' to leave.",
            title="GitHub Agent",
        ))

        messages = []

        while True:
            try:
                question = Prompt.ask("\n[bold cyan]You[/bold cyan]")

                if question.lower() in ("quit", "exit", "q"):
                    console.print("[yellow]Goodbye![/yellow]")
                    break

                if not question.strip():
                    continue

                # Add to message history
                messages.append({"role": "user", "content": question})

                # Get response
                with console.status("[bold green]Thinking..."):
                    response = self.rag.chat(
                        messages=messages,
                        repo_filter=self.current_repo,
                    )

                # Display response
                console.print(f"\n[bold green]Agent[/bold green]")
                console.print(Markdown(response))

                # Add to history
                messages.append({"role": "assistant", "content": response})

                # Keep history manageable
                if len(messages) > 10:
                    messages = messages[-10:]

            except KeyboardInterrupt:
                console.print("\n[yellow]Goodbye![/yellow]")
                break

    def ask(self, question: str) -> str:
        """Ask a single question.

        Args:
            question: Question to ask

        Returns:
            Answer string
        """
        if not self.current_repo:
            return "No repository loaded. Please analyze a repository first."

        with console.status("[bold green]Thinking..."):
            result = self.rag.answer(
                question=question,
                repo_filter=self.current_repo,
            )

        return result["answer"]

    def generate_report(self) -> str:
        """Generate a report for the current repository.

        Returns:
            Report markdown string
        """
        if not self.current_repo:
            return "No repository loaded."

        console.print("[bold blue]Generating report...[/bold blue]")

        # Get repo info and analysis
        repo_info = self.github.get_repo_info(self.current_repo)

        # Get analysis from KB stats
        chunks = self.kb.get_repository_chunks(self.current_repo)

        # Re-analyze from chunks
        files = {c["metadata"]["file"]: c["content"] for c in chunks}
        analysis = self.analyzer.analyze(files)

        # Generate AI summary
        with console.status("[bold green]Generating AI summary..."):
            ai_summary = self.rag.summarize_repository(
                self.current_repo,
                self.analyzer.get_summary(analysis),
                len(files),
                analysis.total_lines,
            )

        # Generate report
        report = self.report_gen.generate_report(
            self.current_repo,
            repo_info,
            analysis,
            ai_summary=ai_summary,
        )

        return report


@click.group()
@click.pass_context
def cli(ctx):
    """GitHub Agent RAG - Analyze private repositories with AI."""
    ctx.ensure_object(dict)

    try:
        config = load_config()
        ensure_directories(config)
        ctx.obj["agent"] = GitHubAgent(config)
    except ValueError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("repo")
@click.option("--ref", default="main", help="Branch or commit ref")
@click.pass_context
def analyze(ctx, repo: str, ref: str):
    """Analyze a GitHub repository."""
    agent: GitHubAgent = ctx.obj["agent"]

    try:
        agent.analyze_repo(repo, ref)
        console.print("\n[bold green]✓ Analysis complete![/bold green]")
        console.print(f"[dim]Use 'chat' or 'ask' commands to query the repository.[/dim]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.pass_context
def chat(ctx):
    """Start interactive chat with the repository."""
    agent: GitHubAgent = ctx.obj["agent"]
    agent.chat()


@cli.command()
@click.argument("question")
@click.pass_context
def ask(ctx, question: str):
    """Ask a single question about the repository."""
    agent: GitHubAgent = ctx.obj["agent"]

    answer = agent.ask(question)
    console.print(Markdown(answer))


@cli.command()
@click.option("--output", "-o", help="Output file path")
@click.pass_context
def report(ctx, output: Optional[str]):
    """Generate a project report."""
    agent: GitHubAgent = ctx.obj["agent"]

    try:
        report_md = agent.generate_report()

        if output:
            with open(output, "w") as f:
                f.write(report_md)
            console.print(f"[green]✓ Report saved to {output}[/green]")
        else:
            console.print(Markdown(report_md))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@cli.command()
def status():
    """Show knowledge base status."""
    try:
        config = load_config()
        kb = KnowledgeBase(config.chroma, config.embedding)
        stats = kb.stats()

        table = Table(title="Knowledge Base Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Documents", str(stats["total_documents"]))
        table.add_row("Repositories", ", ".join(stats["repositories"]) or "None")
        table.add_row("Embedding Dimension", str(stats["embedding_dimension"]))

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    cli()
