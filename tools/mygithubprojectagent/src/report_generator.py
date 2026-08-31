"""Report generator for creating project summaries."""

from typing import Dict, List, Optional

from src.repo_analyzer import RepoAnalysis, TechStack


class ReportGenerator:
    """Generates Markdown reports for repository analysis."""

    def __init__(self):
        """Initialize report generator."""
        pass

    def generate_report(
        self,
        repo_name: str,
        repo_info: Dict,
        analysis: RepoAnalysis,
        ai_summary: Optional[str] = None,
    ) -> str:
        """Generate a comprehensive Markdown report.

        Args:
            repo_name: Repository name
            repo_info: Repository metadata from GitHub
            analysis: Repository analysis
            ai_summary: Optional AI-generated summary

        Returns:
            Markdown report string
        """
        lines = []

        # Title
        lines.append(f"# {repo_info.get('name', repo_name)}")
        lines.append("")

        # Description
        if repo_info.get("description"):
            lines.append(f"*{repo_info['description']}*")
            lines.append("")

        # Overview
        lines.append("## Overview")
        lines.append("")

        if ai_summary:
            lines.append(ai_summary)
        else:
            lines.append(self._generate_overview(repo_info, analysis))

        lines.append("")

        # Repository Stats
        lines.append("## Repository Statistics")
        lines.append("")
        lines.append(f"- **Total Files**: {analysis.total_files}")
        lines.append(f"- **Total Lines**: {analysis.total_lines:,}")
        lines.append(f"- **Stars**: {repo_info.get('stars', 'N/A')}")
        lines.append(f"- **Forks**: {repo_info.get('forks', 'N/A')}")
        lines.append(f"- **Open Issues**: {repo_info.get('open_issues', 'N/A')}")
        lines.append("")

        # Technology Stack
        lines.append("## Technology Stack")
        lines.append("")
        lines.append(self._format_tech_stack(analysis.tech_stack))
        lines.append("")

        # Languages
        if analysis.tech_stack.languages:
            lines.append("### Languages")
            lines.append("")
            sorted_langs = sorted(
                analysis.tech_stack.languages.items(),
                key=lambda x: x[1],
                reverse=True,
            )
            for lang, count in sorted_langs:
                lines.append(f"- **{lang}**: {count} files")
            lines.append("")

        # Frameworks
        if analysis.tech_stack.frameworks:
            lines.append("### Frameworks")
            lines.append("")
            lines.append(", ".join(analysis.tech_stack.frameworks))
            lines.append("")

        # Dependencies
        if analysis.tech_stack.dependencies:
            lines.append("### Key Dependencies")
            lines.append("")
            deps = analysis.tech_stack.dependencies[:20]
            for dep in deps:
                version = f" ({dep.version})" if dep.version else ""
                lines.append(f"- {dep.name}{version}")
            lines.append("")

        # Entry Points
        if analysis.entry_points:
            lines.append("## Entry Points")
            lines.append("")
            lines.append("Main entry points identified in the codebase:")
            lines.append("")
            for ep in analysis.entry_points[:10]:
                lines.append(f"- `{ep}`")
            lines.append("")

        # Core Modules
        if analysis.core_modules:
            lines.append("## Core Modules")
            lines.append("")
            lines.append("Key modules with significant functionality:")
            lines.append("")
            for mod in analysis.core_modules[:15]:
                file_info = analysis.file_analyses.get(mod)
                if file_info:
                    funcs = len(file_info.functions)
                    classes = len(file_info.classes)
                    lines.append(f"- `{mod}` ({funcs} functions, {classes} classes)")
                else:
                    lines.append(f"- `{mod}`")
            lines.append("")

        # Architecture Highlights
        lines.append("## Architecture Highlights")
        lines.append("")
        lines.append(self._extract_architecture_highlights(analysis))
        lines.append("")

        # Topics
        if repo_info.get("topics"):
            lines.append("## Topics")
            lines.append("")
            lines.append(", ".join([f"`{t}`" for t in repo_info["topics"]]))
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append(f"*Report generated for repository: [{repo_name}]({repo_info.get('url', '')})*")

        return "\n".join(lines)

    def _generate_overview(self, repo_info: Dict, analysis: RepoAnalysis) -> str:
        """Generate a basic overview if no AI summary provided."""
        primary_lang = (
            max(analysis.tech_stack.languages.items(), key=lambda x: x[1])[0]
            if analysis.tech_stack.languages
            else "Unknown"
        )

        overview = (
            f"This is a {primary_lang} repository with {analysis.total_files} files "
            f"and approximately {analysis.total_lines:,} lines of code. "
        )

        if analysis.tech_stack.frameworks:
            overview += (
                f"It appears to use the following frameworks: "
                f"{', '.join(analysis.tech_stack.frameworks)}. "
            )

        if analysis.entry_points:
            overview += (
                f"The main entry point(s) can be found in: "
                f"{', '.join(analysis.entry_points[:3])}."
            )

        return overview

    def _format_tech_stack(self, tech_stack: TechStack) -> str:
        """Format technology stack as markdown."""
        lines = []

        # Primary language
        if tech_stack.languages:
            primary = max(tech_stack.languages.items(), key=lambda x: x[1])
            lines.append(f"The primary language is **{primary[0]}** ({primary[1]} files).")

        # Framework summary
        if tech_stack.frameworks:
            lines.append(f"")
            lines.append(f"Detected frameworks: **{', '.join(tech_stack.frameworks)}**.")

        # Total dependencies
        total_deps = len(tech_stack.dependencies) + len(tech_stack.dev_dependencies)
        if total_deps > 0:
            lines.append(f"")
            lines.append(f"Total dependencies: {total_deps}")

        return "\n".join(lines) if lines else "No technology stack information available."

    def _extract_architecture_highlights(self, analysis: RepoAnalysis) -> str:
        """Extract and describe architecture highlights."""
        highlights = []

        # Check for common patterns
        has_tests = any("test" in f.lower() for f in analysis.file_analyses.keys())
        has_config = any("config" in f.lower() for f in analysis.file_analyses.keys())
        has_docs = any(
            f.lower().endswith((".md", ".rst", ".txt"))
            and "readme" not in f.lower()
            for f in analysis.file_analyses.keys()
        )

        if has_tests:
            highlights.append("- The project includes test files, indicating a testing strategy is in place.")

        if has_config:
            highlights.append("- Configuration files are present, suggesting externalized configuration.")

        if has_docs:
            highlights.append("- Documentation files are included in the repository.")

        # Analyze module organization
        dir_structure = {}
        for file_path in analysis.file_analyses.keys():
            parts = file_path.split("/")
            if len(parts) > 1:
                top_dir = parts[0]
                dir_structure[top_dir] = dir_structure.get(top_dir, 0) + 1

        if dir_structure:
            highlights.append(f"")
            highlights.append("### Directory Structure")
            highlights.append("")
            highlights.append("Top-level directories:")
            for dir_name, count in sorted(dir_structure.items(), key=lambda x: x[1], reverse=True)[:8]:
                highlights.append(f"- `{dir_name}/` ({count} files)")

        if not highlights:
            highlights.append("No specific architectural patterns identified from the code structure.")

        return "\n".join(highlights)

    def generate_quick_summary(
        self,
        repo_name: str,
        analysis: RepoAnalysis,
    ) -> str:
        """Generate a quick one-paragraph summary.

        Args:
            repo_name: Repository name
            analysis: Repository analysis

        Returns:
            Summary string
        """
        parts = [f"Repository '{repo_name}'"]

        if analysis.tech_stack.languages:
            langs = ", ".join(list(analysis.tech_stack.languages.keys())[:3])
            parts.append(f"is a {langs} project")

        parts.append(f"with {analysis.total_files} files and {analysis.total_lines:,} lines of code.")

        if analysis.tech_stack.frameworks:
            parts.append(f"It uses {', '.join(analysis.tech_stack.frameworks[:3])}.")

        if analysis.entry_points:
            parts.append(f"Main entry: {analysis.entry_points[0]}")

        return " ".join(parts)
