"""
每周自动用 AI 更新 GitHub repo 描述。
支持公开和私有仓库，跳过 fork 和 skip_repos.txt 中的仓库。
"""

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from github import Auth, Github, GithubException

load_dotenv(Path(__file__).parent / ".env", override=True)

GITHUB_PAT = os.environ["GITHUB_PAT"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
HTTP_PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or None

SKIP_FILE = Path(__file__).parent / "skip_repos.txt"
MAX_DESC_LEN = 150  # GitHub 上限 350，留有余量


def load_skip_list() -> set[str]:
    if not SKIP_FILE.exists():
        return set()
    lines = SKIP_FILE.read_text().splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def get_readme_excerpt(repo, max_chars: int = 800) -> str:
    try:
        readme = repo.get_readme()
        content = readme.decoded_content.decode("utf-8", errors="ignore")
        return content[:max_chars]
    except GithubException:
        return ""


def generate_description(repo_name: str, language: str,
                          topics: list[str], readme_excerpt: str) -> str:
    topic_str = ", ".join(topics) if topics else "none"
    readme_str = readme_excerpt.strip() if readme_excerpt else "not available"

    prompt = f"""Generate a concise, professional GitHub repository description.

Repository info:
- Name: {repo_name}
- Main language: {language or "unknown"}
- Topics: {topic_str}
- README excerpt:
{readme_str}

Rules:
- Maximum {MAX_DESC_LEN} characters
- English only
- No emoji
- No marketing fluff
- Describe what it does, not what it is
- Start with a verb or noun, not "A" or "An"

Output only the description text, nothing else."""

    resp = httpx.post(
        f"{ANTHROPIC_BASE_URL}/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 100,
            "messages": [{"role": "user", "content": prompt}],
        },
        proxy=HTTP_PROXY,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip().strip('"')


def main() -> None:
    skip_list = load_skip_list()
    gh = Github(auth=Auth.Token(GITHUB_PAT))

    user = gh.get_user()
    repos = list(user.get_repos(type="owner"))

    print(f"Found {len(repos)} repos (owner only, excluding forks)")
    print(f"Skip list: {skip_list or 'empty'}\n")

    updated = 0
    skipped = 0
    errors = 0

    for repo in repos:
        name = repo.name

        if repo.fork:
            print(f"[SKIP] {name} — fork")
            skipped += 1
            continue

        if repo.archived:
            print(f"[SKIP] {name} — archived")
            skipped += 1
            continue

        if name in skip_list:
            print(f"[SKIP] {name} — in skip list")
            skipped += 1
            continue

        try:
            readme = get_readme_excerpt(repo)
            new_desc = generate_description(
                repo_name=name,
                language=repo.language or "",
                topics=list(repo.get_topics()),
                readme_excerpt=readme,
            )
            time.sleep(1)  # avoid rate limiting

            if not new_desc:
                print(f"[WARN] {name} — AI returned empty description, skipping")
                skipped += 1
                continue

            if new_desc == repo.description:
                print(f"[SAME] {name} — no change needed")
                skipped += 1
                continue

            repo.edit(description=new_desc)
            print(f"[OK]   {name}")
            print(f"       old: {repo.description!r}")
            print(f"       new: {new_desc!r}")
            updated += 1

        except Exception as e:
            errors += 1
            print(f"[ERR]  {name} — {e}", file=sys.stderr)

    print(f"\nDone. updated={updated} skipped={skipped} errors={errors}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
