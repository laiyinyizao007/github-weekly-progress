"""Repository analyzer for extracting code structure and metadata."""

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from src.config import AppConfig


@dataclass
class FileInfo:
    """Information about a file in the repository."""

    path: str
    content: str
    language: Optional[str] = None
    size: int = 0
    is_entry_point: bool = False
    imports: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)


@dataclass
class DependencyInfo:
    """Dependency information extracted from package files."""

    name: str
    version: Optional[str] = None
    dev: bool = False


@dataclass
class TechStack:
    """Technology stack information."""

    languages: Dict[str, int] = field(default_factory=dict)  # lang -> file count
    frameworks: List[str] = field(default_factory=list)
    dependencies: List[DependencyInfo] = field(default_factory=list)
    dev_dependencies: List[DependencyInfo] = field(default_factory=list)


@dataclass
class RepoAnalysis:
    """Complete repository analysis result."""

    total_files: int = 0
    total_lines: int = 0
    tech_stack: TechStack = field(default_factory=TechStack)
    entry_points: List[str] = field(default_factory=list)
    core_modules: List[str] = field(default_factory=list)
    file_analyses: Dict[str, FileInfo] = field(default_factory=dict)


class RepoAnalyzer:
    """Analyzes repository structure and extracts metadata."""

    # File extension to language mapping
    LANGUAGE_MAP = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".jsx": "JavaScript",
        ".tsx": "TypeScript",
        ".java": "Java",
        ".go": "Go",
        ".rs": "Rust",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
        ".cpp": "C++",
        ".c": "C",
        ".h": "C/C++",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".scala": "Scala",
        ".r": "R",
        ".m": "Objective-C",
        ".mm": "Objective-C++",
    }

    # Framework indicators
    FRAMEWORK_INDICATORS = {
        "React": ["react", "jsx", "tsx", "create-react-app"],
        "Vue": ["vue", "@vue"],
        "Angular": ["@angular"],
        "Next.js": ["next"],
        "Django": ["django"],
        "Flask": ["flask"],
        "FastAPI": ["fastapi"],
        "Express": ["express"],
        "Spring": ["spring-boot", "springframework"],
        "Laravel": ["laravel"],
        "Rails": ["rails", "ruby-on-rails"],
        "Flutter": ["flutter"],
    }

    def __init__(self, config: Optional[AppConfig] = None):
        """Initialize repository analyzer.

        Args:
            config: Application configuration
        """
        self.config = config or AppConfig()

    def detect_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file path.

        Args:
            file_path: Path to the file

        Returns:
            Language name or None
        """
        ext = Path(file_path).suffix.lower()
        return self.LANGUAGE_MAP.get(ext)

    def analyze_file(self, file_path: str, content: str) -> FileInfo:
        """Analyze a single file.

        Args:
            file_path: Path to the file
            content: File content

        Returns:
            FileInfo with extracted information
        """
        language = self.detect_language(file_path)
        size = len(content.encode("utf-8"))

        info = FileInfo(
            path=file_path,
            content=content,
            language=language,
            size=size,
        )

        # Language-specific analysis
        if language == "Python":
            info = self._analyze_python_file(info)
        elif language in ["JavaScript", "TypeScript"]:
            info = self._analyze_js_file(info)

        # Check if entry point
        info.is_entry_point = self._is_entry_point(file_path, content)

        return info

    def _analyze_python_file(self, info: FileInfo) -> FileInfo:
        """Analyze Python file using AST."""
        try:
            tree = ast.parse(info.content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        info.imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    info.imports.append(module)
                elif isinstance(node, ast.FunctionDef):
                    info.functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    info.classes.append(node.name)

        except SyntaxError:
            pass

        return info

    def _analyze_js_file(self, info: FileInfo) -> FileInfo:
        """Analyze JavaScript/TypeScript file using regex."""
        # Extract imports
        import_patterns = [
            r'import\s+.*?\s+from\s+["\']([^"\']+)["\']',
            r'require\s*\(\s*["\']([^"\']+)["\']\s*\)',
            r'import\s+["\']([^"\']+)["\']',
        ]

        for pattern in import_patterns:
            matches = re.findall(pattern, info.content)
            info.imports.extend(matches)

        # Extract function definitions
        func_pattern = r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\([^)]*\)\s*=>))'
        matches = re.findall(func_pattern, info.content)
        for match in matches:
            name = match[0] or match[1]
            if name:
                info.functions.append(name)

        # Extract class definitions
        class_pattern = r'class\s+(\w+)'
        info.classes = re.findall(class_pattern, info.content)

        return info

    def _is_entry_point(self, file_path: str, content: str) -> bool:
        """Check if file is likely an entry point."""
        entry_patterns = [
            r'^if __name__ == ["\']__main__["\']',
            r'\.listen\s*\(',
            r'createApp\s*\(',
            r'ReactDOM\.render',
            r'root\.render',
            r'func main\s*\(\s*\)',
            r'public static void main',
        ]

        for pattern in entry_patterns:
            if re.search(pattern, content, re.MULTILINE):
                return True

        # Check filename
        entry_names = ["main", "index", "app", "server", "manage", "wsgi", "asgi"]
        base_name = Path(file_path).stem.lower()
        return base_name in entry_names

    def extract_dependencies(self, files: Dict[str, str]) -> TechStack:
        """Extract dependency information from package files.

        Args:
            files: Dictionary of file paths to contents

        Returns:
            TechStack with dependency information
        """
        tech_stack = TechStack()

        for file_path, content in files.items():
            lower_path = file_path.lower()

            if lower_path.endswith("package.json"):
                deps, dev_deps = self._parse_package_json(content)
                tech_stack.dependencies.extend(deps)
                tech_stack.dev_dependencies.extend(dev_deps)

            elif lower_path.endswith("requirements.txt"):
                deps = self._parse_requirements_txt(content)
                tech_stack.dependencies.extend(deps)

            elif lower_path.endswith("pyproject.toml"):
                deps, dev_deps = self._parse_pyproject_toml(content)
                tech_stack.dependencies.extend(deps)
                tech_stack.dev_dependencies.extend(dev_deps)

            elif lower_path.endswith("cargo.toml"):
                deps = self._parse_cargo_toml(content)
                tech_stack.dependencies.extend(deps)

            elif lower_path.endswith("gemfile"):
                deps = self._parse_gemfile(content)
                tech_stack.dependencies.extend(deps)

        # Detect frameworks from dependencies
        all_deps = [d.name.lower() for d in tech_stack.dependencies]
        for framework, indicators in self.FRAMEWORK_INDICATORS.items():
            if any(ind.lower() in all_deps for ind in indicators):
                tech_stack.frameworks.append(framework)

        return tech_stack

    def _parse_package_json(self, content: str) -> Tuple[List[DependencyInfo], List[DependencyInfo]]:
        """Parse package.json for dependencies."""
        try:
            data = json.loads(content)
            deps = []
            dev_deps = []

            for name, version in data.get("dependencies", {}).items():
                deps.append(DependencyInfo(name=name, version=version))

            for name, version in data.get("devDependencies", {}).items():
                dev_deps.append(DependencyInfo(name=name, version=version, dev=True))

            return deps, dev_deps
        except json.JSONDecodeError:
            return [], []

    def _parse_requirements_txt(self, content: str) -> List[DependencyInfo]:
        """Parse requirements.txt for dependencies."""
        deps = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Handle various formats
            match = re.match(r'^([a-zA-Z0-9_-]+)', line)
            if match:
                name = match.group(1)
                version = None
                if "==" in line:
                    version = line.split("==")[1].split()[0]
                deps.append(DependencyInfo(name=name, version=version))

        return deps

    def _parse_pyproject_toml(self, content: str) -> Tuple[List[DependencyInfo], List[DependencyInfo]]:
        """Parse pyproject.toml for dependencies."""
        deps = []
        dev_deps = []

        # Simple regex-based parsing for common patterns
        dep_section = re.search(r'\[project\].*?dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if dep_section:
            dep_str = dep_section.group(1)
            for match in re.findall(r'"([^"]+)"', dep_str):
                name = match.split(">=")[0].split("==")[0].strip()
                version = None
                if ">=" in match:
                    version = match.split(">=")[1].strip()
                elif "==" in match:
                    version = match.split("==")[1].strip()
                deps.append(DependencyInfo(name=name, version=version))

        return deps, dev_deps

    def _parse_cargo_toml(self, content: str) -> List[DependencyInfo]:
        """Parse Cargo.toml for dependencies."""
        deps = []

        dep_section = re.search(r'\[dependencies\](.*?)(?=\[|$)', content, re.DOTALL)
        if dep_section:
            dep_str = dep_section.group(1)
            for match in re.findall(r'^([a-zA-Z0-9_-]+)\s*=\s*"([^"]+)"', dep_str, re.MULTILINE):
                deps.append(DependencyInfo(name=match[0], version=match[1]))

        return deps

    def _parse_gemfile(self, content: str) -> List[DependencyInfo]:
        """Parse Gemfile for dependencies."""
        deps = []

        for match in re.findall(r'^gem\s+["\']([^"\']+)["\']', content, re.MULTILINE):
            deps.append(DependencyInfo(name=match))

        return deps

    def analyze(self, files: Dict[str, str]) -> RepoAnalysis:
        """Perform complete repository analysis.

        Args:
            files: Dictionary of file paths to contents

        Returns:
            RepoAnalysis with complete analysis
        """
        analysis = RepoAnalysis()
        analysis.total_files = len(files)

        # Language counts
        lang_counts: Dict[str, int] = {}

        for file_path, content in files.items():
            # Analyze individual file
            file_info = self.analyze_file(file_path, content)
            analysis.file_analyses[file_path] = file_info

            # Count lines
            analysis.total_lines += len(content.split("\n"))

            # Count languages
            if file_info.language:
                lang_counts[file_info.language] = lang_counts.get(file_info.language, 0) + 1

            # Track entry points
            if file_info.is_entry_point:
                analysis.entry_points.append(file_path)

            # Track core modules (files with many imports or functions)
            if len(file_info.imports) > 5 or len(file_info.functions) > 3:
                analysis.core_modules.append(file_path)

        analysis.tech_stack.languages = lang_counts

        # Extract dependencies
        deps = self.extract_dependencies(files)
        analysis.tech_stack.dependencies = deps.dependencies
        analysis.tech_stack.dev_dependencies = deps.dev_dependencies
        analysis.tech_stack.frameworks = deps.frameworks

        return analysis

    def get_summary(self, analysis: RepoAnalysis) -> Dict:
        """Get a human-readable summary of the analysis.

        Args:
            analysis: Repository analysis result

        Returns:
            Dictionary with summary information
        """
        return {
            "total_files": analysis.total_files,
            "total_lines": analysis.total_lines,
            "primary_language": max(
                analysis.tech_stack.languages.items(),
                key=lambda x: x[1],
            )[0] if analysis.tech_stack.languages else "Unknown",
            "languages": list(analysis.tech_stack.languages.keys()),
            "frameworks": analysis.tech_stack.frameworks,
            "entry_points": analysis.entry_points[:5],  # Top 5
            "core_modules": analysis.core_modules[:10],  # Top 10
            "dependencies": [d.name for d in analysis.tech_stack.dependencies][:20],
        }
