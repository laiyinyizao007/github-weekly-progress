"""Main entry point for GitHub Agent RAG system."""

import sys

from src.cli import cli


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    sys.exit(main())
