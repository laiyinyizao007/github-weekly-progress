#!/usr/bin/env python3
"""
自动更新 profile.md 中的 GitHub 项目部分
每周运行一次，拉取最新活跃仓库并更新文件
"""

import subprocess
import json
import re
import sys
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROFILE_PATH = str(Path(__file__).parent / "profile.md")
GITHUB_USER = "laiyinyizao007"

NO_PUSH = "--no-push" in sys.argv

# 按系列分类的关键词（用于识别主力项目）
PROJECT_SERIES = {
    "green-compass": {
        "name": "Green Compass",
        "desc": "Carbon footprint tracking and management platform",
        "icon": "🌿",
        "tags": ["TypeScript", "React", "Sustainability"],
    },
    "fidelity-craftsmen": {
        "name": "Fidelity Craftsmen",
        "desc": "AI occupational health management SaaS (GBZ 188-2025 compliant)",
        "icon": "🏥",
        "tags": ["TypeScript", "AI", "Health"],
    },
    "pact-nexus-light": {
        "name": "Pact Nexus Light",
        "desc": "Lightweight contract testing framework",
        "icon": "🔗",
        "tags": ["TypeScript", "PostgreSQL", "Testing"],
    },
    "atomic-craft-ui": {
        "name": "Atomic Craft UI",
        "desc": "Atomic UI component library",
        "icon": "🎨",
        "tags": ["TypeScript", "React", "Design System"],
    },
    "arksu": {
        "name": "Arksu",
        "desc": "Recently active project",
        "icon": "🚀",
        "tags": ["TypeScript"],
    },
    "lovable-life-hub": {
        "name": "LifeOS",
        "desc": "Event-driven personal OS — LLM-orchestrated workflows, Google Calendar / Notion integration",
        "icon": "🧠",
        "tags": ["TypeScript", "React", "Supabase", "LLM"],
    },
    "my-digital-twin": {
        "name": "Digital Twin",
        "desc": "Interactive portfolio — D3.js force-directed skill graph, i18n, Supabase",
        "icon": "🌐",
        "tags": ["TypeScript", "React", "D3.js"],
    },
    "mygithubprojectagent": {
        "name": "GitHub RAG Agent",
        "desc": "RAG agent for private repo Q&A with automatic sensitive-data sanitization",
        "icon": "🤖",
        "tags": ["Python", "RAG", "LLM"],
    },
    "obs-averivendell": {
        "name": "Obsidian Second Brain",
        "desc": "Claude Code + Obsidian second-brain starter kit (PARA, Git, mobile access)",
        "icon": "📓",
        "tags": ["Obsidian", "Claude Code", "MCP"],
    },
}

LANG_COLORS = {
    "TypeScript": ("3178C6", "typescript"),
    "Python": ("3776AB", "python"),
    "JavaScript": ("F7DF1E", "javascript"),
    "Go": ("00ADD8", "go"),
    "Rust": ("000000", "rust"),
    "PLpgSQL": ("336791", "postgresql"),
    "HTML": ("E34F26", "html5"),
    "CSS": ("1572B6", "css3"),
    "Shell": ("121011", "gnubash"),
    "Dockerfile": ("2496ED", "docker"),
}


def run_gh(args):
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_active_repos():
    """获取所有活跃（未归档）仓库，按最近推送排序"""
    output = run_gh([
        "repo", "list", "--limit", "200",
        "--json", "name,description,pushedAt,isArchived,isPrivate,primaryLanguage,url"
    ])
    if not output:
        return []
    repos = json.loads(output)
    active = [r for r in repos if not r["isArchived"]]
    active.sort(key=lambda x: x.get("pushedAt", ""), reverse=True)
    return active


def find_latest_in_series(repos, keyword):
    """找到某个系列中最新的仓库"""
    matches = [r for r in repos if keyword in r["name"].lower()]
    if not matches:
        return None
    return matches[0]  # 已按时间排序，第一个是最新的


# 工作项目关键词（前5个）与个人项目关键词（后4个）
WORK_SERIES_KEYS = ["green-compass", "fidelity-craftsmen", "pact-nexus-light", "atomic-craft-ui", "arksu"]
PERSONAL_SERIES_KEYS = ["lovable-life-hub", "my-digital-twin", "mygithubprojectagent", "obs-averivendell"]


def format_one_project(repo, meta):
    """格式化单个项目条目（英文简洁风格）"""
    lang = ""
    if repo.get("primaryLanguage"):
        lang = repo["primaryLanguage"].get("name", "")

    tags = list(meta["tags"])
    if lang and lang not in tags:
        tags = [lang] + tags

    desc = repo.get("description") or meta["desc"]
    pushed = repo.get("pushedAt", "")[:10]

    return [
        f"**{meta['icon']} [{meta['name']}](https://github.com/laiyinyizao007/{repo['name']})**"
        f" — {desc}",
        f"`{'` · `'.join(tags[:4])}` · *updated {pushed}*",
        "",
    ]


def format_project_section(repos):
    """生成 GitHub 项目 Markdown 段落（英文，table 格式）"""
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Work ──
    work_rows = []
    for keyword in WORK_SERIES_KEYS:
        meta = PROJECT_SERIES.get(keyword)
        if not meta:
            continue
        repo = find_latest_in_series(repos, keyword)
        if not repo:
            continue
        desc = meta["desc"]
        lang = ""
        if repo.get("primaryLanguage"):
            lang = repo["primaryLanguage"].get("name", "")
        tags = list(meta["tags"])
        if lang and lang not in tags:
            tags = [lang] + tags
        stack = " · ".join(tags[:3])
        name_link = f"**[{meta['icon']} {meta['name']}](https://github.com/laiyinyizao007/{repo['name']})**"
        work_rows.append(f"| {name_link} | {desc} | `{stack}` |")

    # ── Personal ──
    personal_rows = []
    for keyword in PERSONAL_SERIES_KEYS:
        meta = PROJECT_SERIES.get(keyword)
        if not meta:
            continue
        repo = find_latest_in_series(repos, keyword)
        if not repo:
            continue
        desc = meta["desc"]
        lang = ""
        if repo.get("primaryLanguage"):
            lang = repo["primaryLanguage"].get("name", "")
        tags = list(meta["tags"])
        if lang and lang not in tags:
            tags = [lang] + tags
        stack = " · ".join(tags[:3])
        name_link = f"**[{meta['icon']} {meta['name']}](https://github.com/laiyinyizao007/{repo['name']})**"
        personal_rows.append(f"| {name_link} | {desc} | `{stack}` |")

    lines = []
    header = "| Project | Description | Stack |"
    divider = "|---------|-------------|-------|"

    if work_rows:
        lines.append("**Work**")
        lines.append("")
        lines.append(header)
        lines.append(divider)
        lines.extend(work_rows)
        lines.append("")

    if personal_rows:
        lines.append("**Personal**")
        lines.append("")
        lines.append(header)
        lines.append(divider)
        lines.extend(personal_rows)
        lines.append("")

    if not work_rows and not personal_rows:
        lines.append("*No matching projects found.*")

    lines.append(f"*auto-updated {updated} UTC*")

    return "\n".join(lines)


def update_profile(content_block):
    """用新内容替换 profile.md 中的项目区块"""
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    # 替换时间戳
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = re.sub(r"<!-- LAST_UPDATED -->[^·]*", f"<!-- LAST_UPDATED -->{now_str} ", text)

    # 替换项目区块
    pattern = r"<!-- GITHUB_PROJECTS_START -->.*?<!-- GITHUB_PROJECTS_END -->"
    replacement = (
        f"<!-- GITHUB_PROJECTS_START -->\n"
        f"{content_block}\n"
        f"<!-- GITHUB_PROJECTS_END -->"
    )
    text = re.sub(pattern, replacement, text, flags=re.DOTALL)

    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"✅ profile.md 已更新（{now_str}）")


def generate_stats_block(repos):
    """Generate shields.io badge block from live GitHub API data."""
    user_info = run_gh(["api", f"/users/{GITHUB_USER}", "--jq",
        "[.public_repos, .followers] | @csv"])
    public_repos, followers = 0, 0
    if user_info:
        parts = user_info.strip('"').split(",")
        if len(parts) >= 2:
            public_repos, followers = int(parts[0]), int(parts[1])

    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    recent_active = sum(1 for r in repos if r.get("pushedAt", "")[:10] >= cutoff)

    lang_counts = {}
    for r in repos:
        lang = r.get("primaryLanguage")
        if lang and lang.get("name"):
            name = lang["name"]
            lang_counts[name] = lang_counts.get(name, 0) + 1
    top_lang = max(lang_counts, key=lang_counts.get) if lang_counts else "TypeScript"
    top_lang_color, top_lang_logo = LANG_COLORS.get(top_lang, ("58A6FF", ""))

    badges = [
        f"![](https://img.shields.io/badge/Repos-{public_repos}-58A6FF?style=flat-square&logo=github&logoColor=white)",
        f"![](https://img.shields.io/badge/Followers-{followers}-orange?style=flat-square&logo=github&logoColor=white)",
    ]
    lang_label = top_lang.replace("+", "%2B").replace(" ", "_")
    if top_lang_logo:
        badges.append(f"![](https://img.shields.io/badge/Top__Lang-{lang_label}-{top_lang_color}?style=flat-square&logo={top_lang_logo}&logoColor=white)")
    else:
        badges.append(f"![](https://img.shields.io/badge/Top__Lang-{lang_label}-{top_lang_color}?style=flat-square)")
    badges.append(f"![](https://img.shields.io/badge/Active__90d-{recent_active}_repos-3ECF8E?style=flat-square)")

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        '<div align="center">',
        "",
        "  ".join(badges),
        "",
        "</div>",
        "",
        f"*auto-updated {updated} UTC*",
    ]
    return "\n".join(lines)


def update_stats_block(content_block):
    """Replace the GITHUB_STATS_START/END block in profile.md."""
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    pattern = r"<!-- GITHUB_STATS_START -->.*?<!-- GITHUB_STATS_END -->"
    replacement = (
        f"<!-- GITHUB_STATS_START -->\n"
        f"{content_block}\n"
        f"<!-- GITHUB_STATS_END -->"
    )
    text = re.sub(pattern, replacement, text, flags=re.DOTALL)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print("✅ stats block updated")


def git_push_profile():
    """将 profile.md 变更 commit 并推送到 github-weekly-progress"""
    base_dir = str(Path(PROFILE_PATH).parent)
    cmds = [
        ["git", "-C", base_dir, "add", "profile.md"],
        ["git", "-C", base_dir, "commit", "-m",
         f"chore: 更新项目展示 {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"],
        ["git", "-C", base_dir, "push"],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            if "nothing to commit" in r.stdout + r.stderr:
                print("   ℹ️  profile.md 无变更，跳过 commit")
                return False
            print(f"   ⚠️  git 操作失败：{r.stderr.strip()[:80]}")
            return False
    return True


def sync_profile_readme():
    """将 profile.md 内容同步到 GitHub 个人主页仓库（laiyinyizao007/laiyinyizao007）"""
    profile_repo = f"/repos/{GITHUB_USER}/{GITHUB_USER}/contents/README.md"
    content_b64 = base64.b64encode(
        Path(PROFILE_PATH).read_text(encoding="utf-8").encode()
    ).decode()

    # 获取当前 README 的 SHA（更新已有文件必须提供）
    r = subprocess.run(
        ["gh", "api", profile_repo, "--jq", ".sha"],
        capture_output=True, text=True,
    )
    sha = r.stdout.strip() if r.returncode == 0 else None

    args = ["api", "--method", "PUT", profile_repo,
            "-f", "message=chore: sync profile",
            "-f", f"content={content_b64}"]
    if sha:
        args += ["-f", f"sha={sha}"]

    r2 = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if r2.returncode == 0:
        print(f"   ✅ 个人主页 README 已同步（{GITHUB_USER}/{GITHUB_USER}）")
        return True
    else:
        print(f"   ⚠️  个人主页同步失败：{r2.stderr.strip()[:120]}")
        return False


def main():
    print("🔄 拉取 GitHub 仓库信息...")
    repos = get_active_repos()
    if not repos:
        print("❌ 无法获取仓库列表，请确认 gh 已登录")
        return

    print(f"   找到 {len(repos)} 个活跃仓库")
    content = format_project_section(repos)
    update_profile(content)

    print("📊 生成 stats badges...")
    stats_content = generate_stats_block(repos)
    update_stats_block(stats_content)

    if not NO_PUSH:
        print("\n📤 推送并同步...")
        pushed = git_push_profile()
        if pushed:
            sync_profile_readme()
    else:
        print("\nℹ️  跳过 git push（--no-push）")


if __name__ == "__main__":
    main()
