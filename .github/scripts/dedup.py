#!/usr/bin/env python3
"""
dedup.py - GitHub Issue Deduplication Script

Compares the title of a newly opened Issue against all existing open Issues
using two similarity algorithms:
  1. difflib.SequenceMatcher (character sequence similarity)
  2. Jaccard coefficient on word sets (order-insensitive)

If similarity >= threshold (default 0.6), labels the Issue as 'duplicate'
and posts a comment listing the similar Issues.

Environment variables required:
  GH_TOKEN      - GitHub token (provided automatically by GitHub Actions)
  ISSUE_NUMBER  - Number of the newly opened Issue
  ISSUE_TITLE   - Title of the newly opened Issue
  REPO          - Repository in "owner/repo" format

Usage: python3 dedup.py
"""

import json
import os
import re
import subprocess
import sys
from difflib import SequenceMatcher

# --- Configuration ---
SIMILARITY_THRESHOLD = 0.6  # Trigger if either algorithm scores >= this
MAX_SIMILAR_TO_REPORT = 5   # Report at most this many similar Issues

# Stop words to ignore in Jaccard comparison
STOP_WORDS = {
    'the', 'a', 'an', 'is', 'in', 'of', 'for', 'to', 'with', 'and', 'or',
    'but', 'not', 'be', 'are', 'was', 'were', 'has', 'have', 'had', 'do',
    'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
    'on', 'at', 'by', 'from', 'as', 'into', 'through', 'during', 'before',
    'after', 'above', 'below', 'between', 'each', 'more', 'other',
    'fix', 'fixes', 'fixed', 'add', 'adds', 'added', 'update', 'updates',
    'support', 'implement', 'when', 'that', 'this', 'it', 'if',
}


def tokenize(text: str) -> set[str]:
    """Extract meaningful words from text, filtering stop words."""
    words = re.findall(r'[a-z0-9]+', text.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 1}


def sequence_similarity(a: str, b: str) -> float:
    """Character-level sequence similarity using difflib."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def jaccard_similarity(a: str, b: str) -> float:
    """Word-set Jaccard similarity (order-insensitive)."""
    words_a = tokenize(a)
    words_b = tokenize(b)
    union = words_a | words_b
    if not union:
        return 0.0
    return len(words_a & words_b) / len(union)


def combined_score(a: str, b: str) -> float:
    """Combined score: max of sequence and Jaccard similarity."""
    return max(sequence_similarity(a, b), jaccard_similarity(a, b))


def run_gh(*args: str) -> subprocess.CompletedProcess:
    """Run a gh CLI command and return the result."""
    env = os.environ.copy()
    # GH_TOKEN is automatically picked up by gh CLI
    return subprocess.run(
        ['gh', *args],
        capture_output=True,
        text=True,
        env=env,
    )


def get_open_issues(repo: str, exclude_number: int) -> list[dict]:
    """Fetch all open Issues from the repo, excluding the given Issue number."""
    result = run_gh(
        'issue', 'list',
        '--repo', repo,
        '--state', 'open',
        '--limit', '200',
        '--json', 'number,title',
    )
    if result.returncode != 0:
        print(f'Failed to list issues: {result.stderr}', file=sys.stderr)
        return []

    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        print('Failed to parse issue list JSON', file=sys.stderr)
        return []

    return [i for i in issues if i['number'] != exclude_number]


def create_label_if_missing(repo: str, name: str, color: str, description: str) -> None:
    """Create a GitHub label idempotently (ignore if already exists)."""
    run_gh(
        'label', 'create', name,
        '--repo', repo,
        '--color', color,
        '--description', description,
        '--force',  # update if exists (gh >=2.x)
    )


def add_label(repo: str, issue_number: str, label: str) -> None:
    """Add a label to an Issue."""
    result = run_gh(
        'issue', 'edit', issue_number,
        '--repo', repo,
        '--add-label', label,
    )
    if result.returncode != 0:
        print(f'Warning: Failed to add label: {result.stderr}', file=sys.stderr)


def post_comment(repo: str, issue_number: str, body: str) -> None:
    """Post a comment on an Issue."""
    result = run_gh(
        'issue', 'comment', issue_number,
        '--repo', repo,
        '--body', body,
    )
    if result.returncode != 0:
        print(f'Warning: Failed to post comment: {result.stderr}', file=sys.stderr)


def main() -> None:
    # Read environment variables
    issue_number = os.environ.get('ISSUE_NUMBER', '').strip()
    issue_title = os.environ.get('ISSUE_TITLE', '').strip()
    repo = os.environ.get('REPO', '').strip()

    if not all([issue_number, issue_title, repo]):
        print('Missing required environment variables', file=sys.stderr)
        sys.exit(1)

    print(f'Checking issue #{issue_number}: "{issue_title}"')
    print(f'Repository: {repo}')
    print(f'Similarity threshold: {SIMILARITY_THRESHOLD}')
    print()

    # Fetch existing open Issues
    existing_issues = get_open_issues(repo, int(issue_number))
    print(f'Comparing against {len(existing_issues)} open issues...')

    # Calculate similarity for each existing Issue
    matches = []
    for issue in existing_issues:
        score = combined_score(issue_title, issue['title'])
        if score >= SIMILARITY_THRESHOLD:
            matches.append({
                'number': issue['number'],
                'title': issue['title'],
                'score': score,
            })

    # Sort by score descending
    matches.sort(key=lambda x: x['score'], reverse=True)

    if not matches:
        print('No duplicate issues found.')
        return

    print(f'Found {len(matches)} potentially duplicate issue(s)!')

    # Ensure 'duplicate' label exists
    create_label_if_missing(
        repo,
        name='duplicate',
        color='cfd3d7',
        description='This issue or pull request already exists',
    )

    # Add label to new Issue
    add_label(repo, issue_number, 'duplicate')
    print(f'Added "duplicate" label to issue #{issue_number}')

    # Build comment body
    top_matches = matches[:MAX_SIMILAR_TO_REPORT]
    comment_lines = [
        '## Possible Duplicate Issues',
        '',
        'The following existing issues appear to be similar to this one:',
        '',
    ]
    for m in top_matches:
        pct = int(m['score'] * 100)
        comment_lines.append(f'- #{m["number"]}: {m["title"]} _(similarity: {pct}%)_')

    comment_lines += [
        '',
        '---',
        '_If this is a duplicate, please close this issue and add your comments to the existing one._',
        '_If it is **not** a duplicate, feel free to remove the `duplicate` label._',
    ]

    comment_body = '\n'.join(comment_lines)
    post_comment(repo, issue_number, comment_body)
    print(f'Posted duplicate warning comment on issue #{issue_number}')


if __name__ == '__main__':
    main()
