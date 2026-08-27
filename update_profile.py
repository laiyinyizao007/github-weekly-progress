#!/usr/bin/env python3
"""
自动更新 profile.md 中的 GitHub 项目部分
每周运行一次，拉取最新活跃仓库并更新文件
"""

import subprocess
import json
import re
from datetime import datetime, timezone

PROFILE_PATH = "/home/averypi/Projects/jobsearch/githubsummary/profile.md"
GITHUB_USER = "laiyinyizao007"

# 按系列分类的关键词（用于识别主力项目）
PROJECT_SERIES = {
    "green-compass": {
        "name": "Green Compass",
        "desc": "碳排放追踪与管理平台",
        "icon": "🌿",
        "tags": ["TypeScript", "React", "可持续发展"],
    },
    "fidelity-craftsmen": {
        "name": "Fidelity Craftsmen",
        "desc": "AI 职业健康管理系统（GBZ 188-2025 标准）",
        "icon": "🏥",
        "tags": ["TypeScript", "AI", "健康管理"],
    },
    "pact-nexus-light": {
        "name": "Pact Nexus Light",
        "desc": "轻量级合约测试框架",
        "icon": "🔗",
        "tags": ["TypeScript", "PostgreSQL", "测试框架"],
    },
    "atomic-craft-ui": {
        "name": "Atomic Craft UI",
        "desc": "原子化 UI 组件库",
        "icon": "🎨",
        "tags": ["TypeScript", "React", "Design System"],
    },
    "arksu": {
        "name": "Arksu",
        "desc": "近期活跃项目",
        "icon": "🚀",
        "tags": ["TypeScript"],
    },
    # 个人项目
    "lovable-life-hub": {
        "name": "LifeOS",
        "desc": "事件驱动个人生活智能管理系统 · LLM 编排 · Google Calendar / Notion 集成",
        "icon": "🧠",
        "tags": ["TypeScript", "React", "Supabase", "LLM"],
    },
    "my-digital-twin": {
        "name": "Digital Twin",
        "desc": "交互式数字作品集 · D3.js 力导向技能图谱 · Framer Motion",
        "icon": "🌐",
        "tags": ["TypeScript", "React", "D3.js"],
    },
    "mygithubprojectagent": {
        "name": "GitHub RAG Agent",
        "desc": "GitHub 仓库 RAG 智能问答代理 · 自动脱敏 · 项目报告生成",
        "icon": "🤖",
        "tags": ["Python", "RAG", "LLM"],
    },
    "obs-averivendell": {
        "name": "Obsidian Second Brain",
        "desc": "Claude Code + Obsidian 第二大脑套件（Claudesidian 定制分支）",
        "icon": "📓",
        "tags": ["Obsidian", "Claude Code", "MCP"],
    },
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
    """格式化单个项目条目"""
    lang = ""
    if repo.get("primaryLanguage"):
        lang = repo["primaryLanguage"].get("name", "")

    tags = list(meta["tags"])
    if lang and lang not in tags:
        tags = [lang] + tags

    desc = repo.get("description") or meta["desc"]
    pushed = repo.get("pushedAt", "")[:10]

    return [
        f"### {meta['icon']} {meta['name']}",
        f"**{desc}**",
        f"- 最近更新：{pushed}",
        f"- 技术栈：{' · '.join(tags)}",
        f"- 仓库：`{repo['name']}`",
        "",
    ]


def format_project_section(repos):
    """生成 GitHub 项目 Markdown 段落（工作项目 + 个人项目分组）"""
    lines = []
    lines.append(f"*自动更新于 {datetime.now(timezone.utc).strftime('%Y-%m-%d')}（UTC）*\n")

    # ── 工作项目 ──
    work_lines = []
    for keyword in WORK_SERIES_KEYS:
        meta = PROJECT_SERIES.get(keyword)
        if not meta:
            continue
        repo = find_latest_in_series(repos, keyword)
        if not repo:
            continue
        work_lines.extend(format_one_project(repo, meta))

    if work_lines:
        lines.append("#### 工作项目\n")
        lines.extend(work_lines)

    # ── 个人项目 ──
    personal_lines = []
    for keyword in PERSONAL_SERIES_KEYS:
        meta = PROJECT_SERIES.get(keyword)
        if not meta:
            continue
        repo = find_latest_in_series(repos, keyword)
        if not repo:
            continue
        personal_lines.extend(format_one_project(repo, meta))

    if personal_lines:
        lines.append("#### 个人项目\n")
        lines.extend(personal_lines)

    if not work_lines and not personal_lines:
        lines.append("*暂无匹配项目*")

    # 近期新增的其他活跃仓库（非系列，最近 30 天有推送）
    series_keywords = list(PROJECT_SERIES.keys())
    recent_cutoff = datetime.now(timezone.utc).strftime("%Y-%m")
    others = [
        r for r in repos[:20]
        if not any(kw in r["name"].lower() for kw in series_keywords)
        and r.get("pushedAt", "")[:7] >= recent_cutoff
    ]
    if others:
        lines.append("### 🆕 近期新增")
        for r in others[:5]:
            desc = r.get("description") or "—"
            pushed = r.get("pushedAt", "")[:10]
            lang = ""
            if r.get("primaryLanguage"):
                lang = r["primaryLanguage"].get("name", "")
            lines.append(f"- **{r['name']}**：{desc}（{lang}，{pushed}）")
        lines.append("")

    return "\n".join(lines)


def update_profile(content_block):
    """用新内容替换 profile.md 中的项目区块"""
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    # 替换时间戳
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = re.sub(r"<!-- LAST_UPDATED -->.*", f"<!-- LAST_UPDATED -->{now_str}", text)

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


def main():
    print("🔄 拉取 GitHub 仓库信息...")
    repos = get_active_repos()
    if not repos:
        print("❌ 无法获取仓库列表，请确认 gh 已登录")
        return

    print(f"   找到 {len(repos)} 个活跃仓库")
    content = format_project_section(repos)
    update_profile(content)


if __name__ == "__main__":
    main()
