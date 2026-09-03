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
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env（同目录）
load_dotenv(Path(__file__).parent / ".env")

# ── 配置 ──────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
REPORT_DIR  = BASE_DIR / "weekly-reports"
PROFILE_PATH = BASE_DIR / "profile.md"
CONFIG_PATH  = BASE_DIR / "tracked_config.json"
GITHUB_USER = "laiyinyizao007"


def _load_tracked_repos_from_config():
    """从 tracked_config.json 加载追踪仓库配置，失败时返回 None"""
    if not CONFIG_PATH.exists():
        return None
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        result = {
            name: {
                "name": info["name"],
                "icon": info.get("icon", "📦"),
                "type": info.get("type", "personal"),
            }
            for name, info in cfg.get("tracked_repos", {}).items()
        }
        return result if result else None
    except Exception:
        return None


# 从 tracked_config.json 读取，配置不存在时为空（等待 repo_analyzer 首次发现后填充）
TRACKED_REPOS = _load_tracked_repos_from_config() or {}
# ──────────────────────────────────────────────────────────────────────

DRY_RUN  = "--dry-run" in sys.argv
NO_PUSH  = "--no-push" in sys.argv or DRY_RUN


def run_auto_discovery():
    """运行 repo_analyzer.py 自动发现新仓库、更新追踪配置并同步 GitHub 收藏"""
    analyzer = BASE_DIR / "repo_analyzer.py"
    if not analyzer.exists():
        return False
    r = subprocess.run(
        [sys.executable, str(analyzer), "--skip-readme-gen"],
        capture_output=True, text=True,
    )
    # 透传关键操作结果（新追踪仓库、收藏变更），过滤掉 analyzer 的详细进度输出
    _PASSTHROUGH_KEYWORDS = ("🆕", "⭐", "✂️", "⚠️  以下追踪")
    for line in r.stdout.splitlines():
        stripped = line.strip()
        if stripped and any(k in stripped for k in _PASSTHROUGH_KEYWORDS):
            print(f"   {stripped}")
    return r.returncode == 0


def run_gh(args, debug=False):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.strip()
    # Surface stderr so CI logs show why the call failed (rate limit, scope, etc.)
    if debug or r.stderr.strip():
        sys.stderr.write(f"[gh] {' '.join(args[:3])}... -> {r.returncode}: {r.stderr.strip()[:200]}\n")
    return None


def get_week_id(dt=None):
    return (dt or datetime.now(timezone.utc)).strftime("%Y-W%V")


def get_week_range(dt=None):
    dt = dt or datetime.now(timezone.utc)
    monday = dt - timedelta(days=dt.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


NOISE_PATTERNS = {
    "co-authored-by:", "x-lovable-edit-id:", "changes", "update",
    "co-author:", "signed-off-by:",
}

# Fetch commits for one repo since `since_iso`. Returns [] on any failure.
# Logs to stderr when the API call fails or returns empty so CI logs show why.
def get_commits(repo_name, since_iso):
    out = run_gh([
        "api",
        f"/repos/{GITHUB_USER}/{repo_name}/commits?since={since_iso}&per_page=50",
        "--jq", '[.[].commit.message | split("\n")[0]]',
    ], debug=True)
    if not out:
        sys.stderr.write(f"[gh] {repo_name}: empty response — likely GITHUB_TOKEN can't see this repo's commits\n")
        return []
    try:
        titles = json.loads(out)
    except json.JSONDecodeError:
        titles = [ln.strip() for ln in out.splitlines() if ln.strip()]
    # Filter empty lines and Lovable/bot auto-generated noise commits
    result = []
    for t in titles:
        t = t.strip()
        if not t:
            continue
        low = t.lower()
        if any(low.startswith(p) or low == p for p in NOISE_PATTERNS):
            continue
        result.append(t)
    return result


def summarize_with_claude(repo_name, info, commits):
    """用 claude-haiku 生成单项目进展摘要（需 ANTHROPIC_API_KEY）"""
    api_key  = os.environ.get("ANTHROPIC_API_KEY")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if not api_key:
        return None
    try:
        import anthropic
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = anthropic.Anthropic(**kwargs)
        commit_text = "\n".join(f"- {c}" for c in commits[:20])
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{
                "role": "user",
                "content": (
                    f"Project: {info['name']}\n"
                    f"This week's commits ({len(commits)} total):\n{commit_text}\n\n"
                    "Summarize the main progress this week in one English sentence (15-30 words). Output only that sentence."
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
    lines.append(f"**{len(commits)} commit{'s' if len(commits) != 1 else ''} this week:**")
    for c in commits[:8]:
        lines.append(f"- `{c}`")
    if len(commits) > 8:
        lines.append(f"- *...and {len(commits) - 8} more*")
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
        f"# Weekly Report {week_id}",
        f"",
        f"> {start} ~ {end}  ",
        f"> **{len(active)}** active project{'s' if len(active) != 1 else ''} (work: {len(work_active)} · personal: {len(personal_active)}) / {len(project_data)} tracked",
        f"",
        f"---",
        f"",
    ]

    if work_active:
        lines.append("## Work")
        lines.append("")
        for _, d in work_active:
            lines.append(d["block"])

    if personal_active:
        lines.append("## Personal")
        lines.append("")
        for _, d in personal_active:
            lines.append(d["block"])

    if inactive:
        lines.append("## No updates this week")
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
        f"*Week {week_id} ({start} → {end}) · {len(active)} project{'s' if len(active) != 1 else ''} updated*",
        "",
    ]
    for repo, data in active:
        info = TRACKED_REPOS[repo]
        if data["ai_summary"]:
            lines.append(f"**{info['icon']} {info['name']}** — {data['ai_summary']}")
        else:
            top = data["commits"][0] if data["commits"] else "updated"
            cnt = len(data["commits"])
            lines.append(f"**{info['icon']} {info['name']}** — {top} *({cnt} commits)*")

    lines.append("")
    lines.append(f"📄 [Full report →](https://github.com/{GITHUB_USER}/github-weekly-progress/blob/main/weekly-reports/{week_id}.md)")
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


def update_project_page_activity(repo_name, info, week_id, commits, ai_summary):
    """Update the RECENT_ACTIVITY_START/END block in the matching projects/*.md file."""
    projects_dir = BASE_DIR / "projects"
    if not projects_dir.exists():
        return False
    # Find the project page whose filename is a keyword contained in the repo name
    matched_page = None
    for page in projects_dir.glob("*.md"):
        if page.stem in repo_name.lower():
            matched_page = page
            break
    if not matched_page:
        return False

    commit_count = len(commits)
    if ai_summary:
        activity = f"**Week {week_id}** — {ai_summary} *({commit_count} commit{'s' if commit_count != 1 else ''})*"
    elif commits:
        activity = f"**Week {week_id}** — {commits[0]} *({commit_count} commit{'s' if commit_count != 1 else ''})*"
    else:
        return False  # No activity, leave block as is

    text = matched_page.read_text(encoding="utf-8")
    pattern = r"<!-- RECENT_ACTIVITY_START -->.*?<!-- RECENT_ACTIVITY_END -->"
    replacement = f"<!-- RECENT_ACTIVITY_START -->\n{activity}\n<!-- RECENT_ACTIVITY_END -->"
    new_text = re.sub(pattern, replacement, text, flags=re.DOTALL)
    if new_text != text:
        matched_page.write_text(new_text, encoding="utf-8")
        return True
    return False


def git_push_reports(week_id):
    """将新周报 commit 并推送到 GitHub"""
    cmds = [
        ["git", "-C", str(BASE_DIR), "add", "weekly-reports/", "profile.md", "projects/"],
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


def sync_profile_readme(dry_run=False):
    """将 profile.md 内容同步到 GitHub 个人主页仓库（laiyinyizao007/laiyinyizao007）"""
    profile_repo = f"/repos/{GITHUB_USER}/{GITHUB_USER}/contents/README.md"
    content_b64 = base64.b64encode(
        PROFILE_PATH.read_text(encoding="utf-8").encode()
    ).decode()

    # 获取当前 README 的 SHA（更新已有文件必须提供）
    r = subprocess.run(
        ["gh", "api", profile_repo, "--jq", ".sha"],
        capture_output=True, text=True,
    )
    sha = r.stdout.strip() if r.returncode == 0 else None

    if dry_run:
        print(f"   [dry-run] 同步个人主页 README（{GITHUB_USER}/{GITHUB_USER}）")
        return True

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
    global TRACKED_REPOS
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 自动发现新仓库（在生成周报前先更新追踪配置）
    if not DRY_RUN:
        print("🔍 扫描新仓库...", end=" ", flush=True)
        ok = run_auto_discovery()
        print("✅ 完成" if ok else "⚠️  跳过（repo_analyzer.py 不存在或运行失败）")
        # 重新加载配置，包含本次新发现的仓库
        TRACKED_REPOS = _load_tracked_repos_from_config() or {}
        print()

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

    # 更新项目简介页活动记录
    if not DRY_RUN:
        updated_pages = []
        for repo, data in project_data.items():
            if data["commits"]:
                ok = update_project_page_activity(
                    repo, TRACKED_REPOS[repo], week_id,
                    data["commits"], data["ai_summary"]
                )
                if ok:
                    updated_pages.append(repo)
        if updated_pages:
            print(f"✅ 项目简介页活动更新：{len(updated_pages)} 个")

    # 推送到 GitHub
    if DRY_RUN:
        sync_profile_readme(dry_run=True)
    elif not NO_PUSH:
        print("\n📤 推送到 GitHub...", end=" ", flush=True)
        ok = git_push_reports(week_id)
        print("✅ 完成" if ok else "⚠️  请手动 push")
        if ok:
            sync_profile_readme(dry_run=False)
    else:
        print("\nℹ️  跳过 git push（--no-push）")


if __name__ == "__main__":
    main()
