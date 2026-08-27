#!/usr/bin/env python3
"""
每周 GitHub 项目进展分析与周报生成

流程：
1. 获取追踪仓库过去 7 天的 commits（gh api）
2. Claude API 生成智能摘要（需 ANTHROPIC_API_KEY）
3. 写入 weekly-reports/YYYY-WNN.md（存仓库）
4. 更新 profile.md 的「本周进展」区块
5. git commit + push（可选）

用法：
  python3 weekly_report.py           # 正常运行
  python3 weekly_report.py --no-push # 不推送到 GitHub
  python3 weekly_report.py --dry-run # 只打印，不写文件
"""

import subprocess
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────────────────
BASE_DIR    = Path("/home/averypi/Projects/jobsearch/githubsummary")
REPORT_DIR  = BASE_DIR / "weekly-reports"
PROFILE_PATH = BASE_DIR / "profile.md"
GITHUB_USER = "laiyinyizao007"

# 追踪的项目（精确仓库名 -> 展示信息）
TRACKED_REPOS = {
    # 工作项目
    "green-compass-net-f3505092": {"name": "Green Compass",       "icon": "🌿", "type": "work"},
    "fidelity-craftsmen-7dafda64": {"name": "Fidelity Craftsmen", "icon": "🏥", "type": "work"},
    "pact-nexus-light-3c5c9dae":   {"name": "Pact Nexus Light",   "icon": "🔗", "type": "work"},
    "atomic-craft-ui-89d5c7c7":    {"name": "Atomic Craft UI",    "icon": "🎨", "type": "work"},
    "arksusdemo":                  {"name": "ArkSus Demo",         "icon": "🚀", "type": "work"},
    # 个人项目
    "lovable-life-hub":     {"name": "LifeOS",               "icon": "🧠", "type": "personal"},
    "my-digital-twin":      {"name": "Digital Twin",          "icon": "🌐", "type": "personal"},
    "mygithubprojectagent": {"name": "GitHub RAG Agent",      "icon": "🤖", "type": "personal"},
    "obs-averivendell":     {"name": "Obsidian Second Brain", "icon": "📓", "type": "personal"},
}
# ──────────────────────────────────────────────────────────────────────

DRY_RUN  = "--dry-run" in sys.argv
NO_PUSH  = "--no-push" in sys.argv or DRY_RUN


def run_gh(args):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def get_week_id(dt=None):
    return (dt or datetime.now(timezone.utc)).strftime("%Y-W%V")


def get_week_range(dt=None):
    dt = dt or datetime.now(timezone.utc)
    monday = dt - timedelta(days=dt.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def get_commits(repo_name, since_iso):
    """获取仓库自 since_iso 以来的 commits（标题行）"""
    out = run_gh([
        "api", f"/repos/{GITHUB_USER}/{repo_name}/commits",
        "--jq", ".[].commit.message",
        "-F", f"since={since_iso}",
        "-F", "per_page=50",
    ])
    if not out:
        return []
    return [ln.split("\n")[0].strip() for ln in out.splitlines() if ln.strip()]


def summarize_with_claude(repo_name, info, commits):
    """用 claude-haiku 生成单项目进展摘要（需 ANTHROPIC_API_KEY）"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        commit_text = "\n".join(f"- {c}" for c in commits[:20])
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{
                "role": "user",
                "content": (
                    f"项目名：{info['name']}\n"
                    f"本周 commits（{len(commits)} 条）：\n{commit_text}\n\n"
                    "用一句中文概括本周主要进展（15-30字），只输出这一句话。"
                )
            }]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"      ⚠️  Claude API 调用失败：{e}")
        return None


def format_project_block(info, commits, ai_summary):
    """格式化单个项目的详细进展（用于完整周报）"""
    lines = [f"### {info['icon']} {info['name']}"]
    if ai_summary:
        lines.append(f"> {ai_summary}")
        lines.append("")
    lines.append(f"**本周 {len(commits)} 条提交：**")
    for c in commits[:8]:
        lines.append(f"- `{c}`")
    if len(commits) > 8:
        lines.append(f"- *...另有 {len(commits) - 8} 条提交*")
    lines.append("")
    return "\n".join(lines)


def generate_weekly_report(week_id, week_range, project_data):
    """生成完整周报 markdown"""
    start, end = week_range
    active   = [(r, d) for r, d in project_data.items() if d["commits"]]
    inactive = [(r, d) for r, d in project_data.items() if not d["commits"]]

    work_active     = [(r, d) for r, d in active if TRACKED_REPOS[r]["type"] == "work"]
    personal_active = [(r, d) for r, d in active if TRACKED_REPOS[r]["type"] == "personal"]

    lines = [
        f"# 周报 {week_id}",
        f"",
        f"> {start} ~ {end}  ",
        f"> 活跃项目 **{len(active)}** 个（工作 {len(work_active)} · 个人 {len(personal_active)}）/ 追踪中 {len(project_data)} 个",
        f"",
        f"---",
        f"",
    ]

    if work_active:
        lines.append("## 工作项目")
        lines.append("")
        for _, d in work_active:
            lines.append(d["block"])

    if personal_active:
        lines.append("## 个人项目")
        lines.append("")
        for _, d in personal_active:
            lines.append(d["block"])

    if inactive:
        lines.append("## 本周无更新")
        lines.append("")
        for repo, _ in inactive:
            info = TRACKED_REPOS[repo]
            lines.append(f"- {info['icon']} {info['name']}")
        lines.append("")

    return "\n".join(lines)


def build_profile_snippet(week_id, week_range, project_data):
    """生成嵌入 profile.md 的简短摘要（纯文本，不依赖文件路径）"""
    start, end = week_range
    active = [(r, d) for r, d in project_data.items() if d["commits"]]

    lines = [
        f"*周报 {week_id}（{start} ~ {end}）· {len(active)} 个项目有更新*",
        "",
    ]
    for repo, data in active:
        info = TRACKED_REPOS[repo]
        if data["ai_summary"]:
            lines.append(f"**{info['icon']} {info['name']}** — {data['ai_summary']}")
        else:
            top = data["commits"][0] if data["commits"] else "有更新"
            cnt = len(data["commits"])
            lines.append(f"**{info['icon']} {info['name']}** — {top}（共 {cnt} 条提交）")

    lines.append("")
    lines.append(f"📄 [完整周报 →](weekly-reports/{week_id}.md)")
    return "\n".join(lines)


def update_profile_md(snippet):
    """替换 profile.md 中的 WEEKLY_PROGRESS 区块（不存在则自动插入）"""
    text = PROFILE_PATH.read_text(encoding="utf-8")
    replacement = f"<!-- WEEKLY_PROGRESS_START -->\n{snippet}\n<!-- WEEKLY_PROGRESS_END -->"
    pattern = r"<!-- WEEKLY_PROGRESS_START -->.*?<!-- WEEKLY_PROGRESS_END -->"

    if re.search(pattern, text, flags=re.DOTALL):
        text = re.sub(pattern, replacement, text, flags=re.DOTALL)
    else:
        # 首次：插入到 GITHUB_PROJECTS_START 前面
        anchor = "<!-- GITHUB_PROJECTS_START -->"
        text = text.replace(anchor, f"{replacement}\n\n{anchor}", 1)

    PROFILE_PATH.write_text(text, encoding="utf-8")


def git_push_reports(week_id):
    """将新周报 commit 并推送到 GitHub"""
    cmds = [
        ["git", "-C", str(BASE_DIR), "add", "weekly-reports/", "profile.md"],
        ["git", "-C", str(BASE_DIR), "commit", "-m",
         f"chore: 周报 {week_id}"],
        ["git", "-C", str(BASE_DIR), "push"],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"   ⚠️  git 操作失败：{' '.join(cmd[2:])}")
            print(f"      {r.stderr.strip()}")
            return False
    return True


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    now       = datetime.now(timezone.utc)
    week_id   = get_week_id(now)
    week_range = get_week_range(now)
    since_iso = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"📅 周报：{week_id}  ({week_range[0]} ~ {week_range[1]})")
    use_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"🤖 Claude 摘要：{'启用' if use_claude else '未启用（未设置 ANTHROPIC_API_KEY）'}")
    print()

    project_data = {}
    for repo, info in TRACKED_REPOS.items():
        print(f"   📦 {info['name']:20s}", end="  ", flush=True)
        commits    = get_commits(repo, since_iso)
        ai_summary = summarize_with_claude(repo, info, commits) if (commits and use_claude) else None
        block      = format_project_block(info, commits, ai_summary) if commits else None
        project_data[repo] = {"commits": commits, "ai_summary": ai_summary, "block": block}
        print(f"{len(commits)} commits" if commits else "—")

    # 生成并写入周报
    report_md = generate_weekly_report(week_id, week_range, project_data)
    report_path = REPORT_DIR / f"{week_id}.md"
    if DRY_RUN:
        print(f"\n[dry-run] 周报预览：\n{'─'*60}")
        print(report_md[:800])
        print("─"*60)
    else:
        report_path.write_text(report_md, encoding="utf-8")
        print(f"\n✅ 周报已保存：{report_path.relative_to(BASE_DIR)}")

    # 更新 profile.md
    snippet = build_profile_snippet(week_id, week_range, project_data)
    if DRY_RUN:
        print(f"\n[dry-run] profile.md 摘要：\n{snippet}")
    else:
        update_profile_md(snippet)
        print(f"✅ profile.md 已更新（本周进展区块）")

    # 推送到 GitHub
    if not NO_PUSH:
        print("\n📤 推送到 GitHub...", end=" ", flush=True)
        ok = git_push_reports(week_id)
        print("✅ 完成" if ok else "⚠️  请手动 push")
    else:
        print("\nℹ️  跳过 git push（--no-push）")


if __name__ == "__main__":
    main()
