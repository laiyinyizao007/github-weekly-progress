#!/usr/bin/env python3
"""
GitHub 仓库全量分析工具

功能：
1. 获取所有 GitHub 仓库元数据
2. 按活跃度/语言分类，生成分析报告
3. 提供整理建议（归档/保留/删除）
4. 识别求职展示优化机会
5. 为缺少 README 的仓库生成草稿

用法：
  python3 repo_analyzer.py                    # 完整分析 + 生成报告
  python3 repo_analyzer.py --dry-run          # 仅预览，不写文件
  python3 repo_analyzer.py --skip-readme-gen  # 跳过 README 草稿生成
  python3 repo_analyzer.py --no-auto-update   # 只读，不修改 tracked_config.json
  python3 repo_analyzer.py --output DIR       # 自定义报告目录
"""

import subprocess
import json
import os
import re
import sys
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env（同目录）
load_dotenv(Path(__file__).parent / ".env")

# ── 配置 ──────────────────────────────────────────────────────────────
BASE_DIR     = Path("/home/averypi/Projects/jobsearch/githubsummary")
PROFILE_PATH = BASE_DIR / "profile.md"
CONFIG_PATH   = BASE_DIR / "tracked_config.json"
CACHE_PATH    = BASE_DIR / "repo_cache.json"
DATABASE_PATH = BASE_DIR / "repo_database.md"
GITHUB_USER   = "laiyinyizao007"

# 语言 → emoji 映射（用于自动推断图标）
LANG_ICONS = {
    "Python": "🐍", "TypeScript": "📘", "JavaScript": "⚡",
    "Go": "🐹", "Rust": "🦀", "Java": "☕", "C++": "⚙️",
    "C#": "🔷", "Ruby": "💎", "Swift": "🦉", "Kotlin": "🎯",
    "CSS": "🎨", "HTML": "🌐", "Shell": "🐚", "Dockerfile": "🐳",
}

# ──────────────────────────────────────────────────────────────────────


# ── Step 1: 脚手架与配置 ───────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="GitHub 仓库全量分析工具")
    parser.add_argument("--dry-run",         action="store_true", help="仅预览，不写文件")
    parser.add_argument("--skip-readme-gen", action="store_true", help="跳过 README 草稿生成")
    parser.add_argument("--no-auto-update",  action="store_true", help="只读模式，不修改 tracked_config.json")
    parser.add_argument("--output",          default=str(BASE_DIR / "reports"), help="报告输出目录")
    return parser.parse_args()


def load_config():
    return {
        "api_key":  os.environ.get("ANTHROPIC_API_KEY"),
        "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
    }


def init_anthropic_client(config):
    api_key  = config.get("api_key")
    base_url = config.get("base_url")
    if not api_key:
        return None
    try:
        import anthropic
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return anthropic.Anthropic(**kwargs)
    except Exception as e:
        print(f"⚠️  Anthropic 客户端初始化失败：{e}")
        return None


# ── Step 2: 数据采集层 ─────────────────────────────────────────────────
def run_gh(args):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def fetch_all_repos():
    """获取所有仓库元数据（最多200个），按推送时间降序排列"""
    out = run_gh([
        "repo", "list",
        "--limit", "200",
        "--json", "name,description,primaryLanguage,stargazerCount,pushedAt,isArchived,isFork,isPrivate,url",
    ])
    if not out:
        print("❌ 无法获取仓库列表，请确认已运行 gh auth login")
        return []

    try:
        raw_repos = json.loads(out)
    except json.JSONDecodeError as e:
        print(f"❌ 解析仓库列表失败：{e}")
        return []

    now = datetime.now(timezone.utc)
    repos = []
    for r in raw_repos:
        # primaryLanguage 可能是 {"name": "Python"} 或 null
        lang_obj = r.get("primaryLanguage")
        language = lang_obj["name"] if lang_obj else ""

        # 计算距今天数
        pushed_at = r.get("pushedAt", "")
        days_since_push = -1
        if pushed_at:
            try:
                pushed_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                days_since_push = (now - pushed_dt).days
            except (ValueError, TypeError):
                pass

        repo = {
            # 原始字段
            "name":            r.get("name", ""),
            "description":     r.get("description") or "",
            "primaryLanguage": language,
            "stargazerCount":  r.get("stargazerCount", 0),
            "pushedAt":        pushed_at,
            "isArchived":      r.get("isArchived", False),
            "isFork":          r.get("isFork", False),
            "isPrivate":       r.get("isPrivate", False),
            "url":             r.get("url", ""),
            # 计算字段
            "days_since_push": days_since_push,
            "has_readme":      None,
            "in_tracked":      False,
            "in_profile":      False,
            # 分析字段（annotate_repos 后填充）
            "activity_level":  "",
            "disposition":     "",
            "score":           0,
            "score_breakdown": {},
        }
        repos.append(repo)

    # 按推送时间降序（最新在前）
    repos.sort(key=lambda x: x["days_since_push"] if x["days_since_push"] >= 0 else 99999)
    return repos


def detect_readme(repo_name):
    """检测仓库是否有 README（HTTP 200 → True，404 → False）"""
    result = run_gh(["api", f"/repos/{GITHUB_USER}/{repo_name}/readme"])
    time.sleep(0.5)
    return result is not None


def batch_detect_readmes(repos, cache, skip_archived=True):
    """批量检测 README（增量）：命中缓存的仓库直接复用，只检测有更新的仓库"""
    to_check = []
    for r in repos:
        if skip_archived and r["isArchived"]:
            # 归档仓库：直接用缓存（无论是否更新）
            r["has_readme"] = cache.get(r["name"], {}).get("has_readme")
            continue
        cached = cache.get(r["name"], {})
        if cached.get("last_pushed_at") == r["pushedAt"]:
            # 仓库未变更：复用缓存的 README 状态
            r["has_readme"] = cached.get("has_readme")
        else:
            to_check.append(r)

    cached_count = len(repos) - len(to_check)
    updated_names: set = set()

    if not to_check:
        print(f"   ✅ 全部命中缓存（{cached_count} 个），无需重新检测")
        return repos, updated_names

    print(f"   🔍 检测 README：{len(to_check)} 个有更新（{cached_count} 个命中缓存）")
    total = len(to_check)
    for i, repo in enumerate(to_check, 1):
        repo["has_readme"] = detect_readme(repo["name"])
        # 写入缓存
        cache[repo["name"]] = {
            "last_pushed_at": repo["pushedAt"],
            "has_readme":     repo["has_readme"],
        }
        updated_names.add(repo["name"])
        if i % 10 == 0 or i == total:
            print(f"   📋 进度：{i}/{total}", end="\r", flush=True)
        if i % 20 == 0:
            time.sleep(2.0)

    print(f"\n   ✅ README 检测完成：{total} 个更新，{cached_count} 个命中缓存")
    return repos, updated_names


# ── Step 3: 分析层 ────────────────────────────────────────────────────
def load_tracked_repos():
    return TRACKED_REPO_NAMES.copy()


def load_profile_repos(profile_path):
    """从 profile.md 的 GITHUB_PROJECTS_START~END 区块提取已展示的仓库名"""
    if not profile_path.exists():
        return set()

    text = profile_path.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- GITHUB_PROJECTS_START -->(.*?)<!-- GITHUB_PROJECTS_END -->",
        text,
        flags=re.DOTALL,
    )
    if not match:
        return set()

    block = match.group(1)
    names = set()

    # 方式1：反引号包围的仓库名
    names.update(re.findall(r"`([a-z0-9][a-z0-9\-]+)`", block))

    # 方式2：从 GitHub URL 提取
    for url_match in re.finditer(rf"github\.com/{GITHUB_USER}/([a-z0-9][a-z0-9\-]+)", block):
        names.add(url_match.group(1))

    return names


def classify_activity(days):
    """纯函数：按距今天数分类活跃度"""
    if days < 0:
        return "未知"
    if days <= 90:
        return "最近活跃"
    if days <= 365:
        return "一般活跃"
    return "长期未维护"


def determine_disposition(repo):
    """判断整理建议（规则优先级从高到低）"""
    days  = repo["days_since_push"]
    stars = repo["stargazerCount"]
    desc  = repo["description"]

    # 规则1（最高优先级）：fork 且近期未修改
    if repo["isFork"] and days > 90:
        return "建议删除"

    # 规则2：建议保留（任一满足即保留）
    if days <= 90 or stars > 0 or repo["in_tracked"]:
        return "建议保留"

    # 规则3：建议归档
    if days > 365 and stars == 0 and not desc:
        return "建议归档"

    return "建议保留"


def score_repo(repo):
    """4 维度项目质量评分（满分60，不含活跃度），返回 (total, breakdown)

    活跃度与项目质量无关，单独通过 classify_activity() 展示。
    """
    breakdown = {}

    # 维度1：Stars（0-20）
    stars = repo["stargazerCount"]
    if stars >= 10:
        breakdown["stars"] = 20
    elif stars >= 5:
        breakdown["stars"] = 15
    elif stars >= 2:
        breakdown["stars"] = 10
    elif stars == 1:
        breakdown["stars"] = 5
    else:
        breakdown["stars"] = 0

    # 维度2：README 完整度（0-15）
    has_readme = repo["has_readme"]
    if has_readme is True:
        breakdown["has_readme"] = 15
    elif has_readme is False:
        breakdown["has_readme"] = 0
    else:  # None（未检测/已归档）
        breakdown["has_readme"] = 5

    # 维度3：描述完整度（0-10）
    desc_len = len(repo["description"])
    if desc_len >= 20:
        breakdown["has_description"] = 10
    elif desc_len > 0:
        breakdown["has_description"] = 5
    else:
        breakdown["has_description"] = 0

    # 维度4：已在 profile.md 展示（0-15）
    breakdown["in_profile"] = 15 if repo["in_profile"] else 0

    return sum(breakdown.values()), breakdown


def annotate_repos(repos, tracked, profile_repos):
    """批量填充分析字段（原地修改）"""
    for repo in repos:
        repo["in_tracked"]      = repo["name"] in tracked
        repo["in_profile"]      = repo["name"] in profile_repos
        repo["activity_level"]  = classify_activity(repo["days_since_push"])
        repo["disposition"]     = determine_disposition(repo)
        repo["score"], repo["score_breakdown"] = score_repo(repo)
    return repos


# ── A1: 追踪配置加载/保存 ──────────────────────────────────────────────
def load_tracked_config():
    """加载 tracked_config.json；不存在时创建空配置（由评分自动发现填充）"""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"   ⚠️  读取配置文件失败：{e}，使用空配置")

    # 首次运行：创建空配置，由 auto_discover_new_repos 根据评分填充
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    config = {
        "version": "1.0",
        "last_updated": today,
        "settings": {
            "auto_add_threshold":    40,
            "auto_remove_threshold": 25,
        },
        "tracked_repos": {},
        "ignored_repos": [],
    }
    print("   ℹ️  首次运行：创建空配置，将由评分自动发现填充")
    return config


def save_tracked_config(config, dry_run):
    """保存追踪配置（dry_run 时只打印摘要）"""
    config["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = len(config.get("tracked_repos", {}))
    if dry_run:
        print(f"   [dry-run] tracked_config.json 将包含 {count} 个追踪仓库")
    else:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"   ✅ tracked_config.json 已更新（{count} 个追踪仓库）")


def config_to_tracked_names(config):
    """从配置提取仓库名集合，供 annotate_repos 使用"""
    return set(config.get("tracked_repos", {}).keys())


# ── A2: 自动发现逻辑 ───────────────────────────────────────────────────
def infer_icon(primary_language):
    """根据主语言推断 emoji 图标"""
    return LANG_ICONS.get(primary_language or "", "📦")


def infer_display_name(repo_name):
    """从仓库名生成显示名：my-digital-twin → My Digital Twin"""
    return " ".join(word.capitalize() for word in re.split(r"[-_]", repo_name))


def auto_discover_new_repos(repos, config, today):
    """
    发现评分达标且尚未追踪的仓库，自动写入 config["tracked_repos"]。
    返回 [(repo_name, score), ...] 新增名单。
    """
    tracked   = set(config.get("tracked_repos", {}).keys())
    ignored   = set(config.get("ignored_repos", []))
    threshold = config.get("settings", {}).get("auto_add_threshold", 70)

    new_repos = []
    for repo in repos:
        name = repo["name"]
        if name in tracked or name in ignored or repo["isArchived"]:
            continue
        if repo["score"] < threshold:
            continue

        config["tracked_repos"][name] = {
            "name":          infer_display_name(name),
            "icon":          infer_icon(repo["primaryLanguage"]),
            "type":          "personal",      # 默认个人项目，可手动修改
            "added_date":    today,
            "score_history": [{"date": today, "score": repo["score"]}],
        }
        new_repos.append((name, repo["score"]))

    return new_repos


# ── A3: 评分历史更新 ───────────────────────────────────────────────────
def update_score_history(repos, config, today):
    """为已追踪仓库追加今天的评分历史（最多保留12条，同日幂等）"""
    score_map = {r["name"]: r["score"] for r in repos}
    for name, info in config.get("tracked_repos", {}).items():
        if name not in score_map:
            continue
        history = info.setdefault("score_history", [])
        if history and history[-1]["date"] == today:
            history[-1]["score"] = score_map[name]   # 同日覆盖
        else:
            history.append({"date": today, "score": score_map[name]})
        info["score_history"] = history[-12:]         # 只保留最近12条


# ── A4: 低分告警 ───────────────────────────────────────────────────────
def check_declining_repos(config):
    """
    检查最近两次评分均低于 auto_remove_threshold 的追踪仓库。
    返回 [(repo_name, latest_score, display_name), ...]
    """
    threshold = config.get("settings", {}).get("auto_remove_threshold", 40)
    declining = []
    for name, info in config.get("tracked_repos", {}).items():
        history = info.get("score_history", [])
        if len(history) >= 2:
            last_two = [h["score"] for h in history[-2:]]
            if all(s < threshold for s in last_two):
                declining.append((name, last_two[-1], info.get("name", name)))
    return declining


# ── Step 4: 报告生成层 ─────────────────────────────────────────────────
def _days_label(days):
    if days < 0:
        return "未知"
    if days == 0:
        return "今天"
    return f"{days}天前"


def _repo_table_rows(group):
    """生成仓库列表的 Markdown 表格行"""
    lines = []
    for r in group:
        name  = f"[{r['name']}]({r['url']})" if r["url"] else r["name"]
        lang  = r["primaryLanguage"] or "—"
        stars = r["stargazerCount"]
        push  = _days_label(r["days_since_push"])
        disp  = r["disposition"]
        lines.append(f"| {name} | {lang} | {stars} | {push} | {disp} |")
    return lines


def build_analysis_report(repos, report_date):
    """生成全量分类报告 Markdown"""
    total          = len(repos)
    active_count   = sum(1 for r in repos if r["activity_level"] == "最近活跃")
    moderate_count = sum(1 for r in repos if r["activity_level"] == "一般活跃")
    inactive_count = sum(1 for r in repos if r["activity_level"] == "长期未维护")
    unknown_count  = sum(1 for r in repos if r["activity_level"] == "未知")
    archived_count = sum(1 for r in repos if r["isArchived"])

    lines = [
        f"# 仓库全量分析报告 {report_date}",
        "",
        "## 📊 概览统计",
        "",
        "| 指标 | 数量 |",
        "|------|------|",
        f"| 总仓库数 | {total} |",
        f"| 最近活跃（≤90天） | {active_count} |",
        f"| 一般活跃（91-365天） | {moderate_count} |",
        f"| 长期未维护（>365天） | {inactive_count} |",
        f"| 已归档 | {archived_count} |",
        f"| 建议保留 | {sum(1 for r in repos if r['disposition'] == '建议保留')} |",
        f"| 建议归档 | {sum(1 for r in repos if r['disposition'] == '建议归档')} |",
        f"| 建议删除 | {sum(1 for r in repos if r['disposition'] == '建议删除')} |",
        "",
        "---",
        "",
        "## 📅 按活跃度分类",
        "",
    ]

    def _section(group, title):
        if not group:
            return []
        result = [f"### {title}（{len(group)} 个）", ""]
        result += [
            "| 仓库名 | 语言 | Stars | 最近推送 | 处置建议 |",
            "|--------|------|-------|----------|----------|",
        ]
        result += _repo_table_rows(group)
        result.append("")
        return result

    lines += _section([r for r in repos if r["activity_level"] == "最近活跃"],   "最近活跃")
    lines += _section([r for r in repos if r["activity_level"] == "一般活跃"],   "一般活跃")
    lines += _section([r for r in repos if r["activity_level"] == "长期未维护"], "长期未维护")
    if unknown_count:
        lines += _section([r for r in repos if r["activity_level"] == "未知"], "未知")

    # 按语言分类
    lines += ["---", "", "## 🔤 按语言分类", ""]
    lang_map = {}
    for r in repos:
        lang = r["primaryLanguage"] or "未知"
        lang_map.setdefault(lang, []).append(r["name"])
    for lang in sorted(lang_map.keys()):
        names = ", ".join(f"`{n}`" for n in sorted(lang_map[lang]))
        lines.append(f"**{lang}**（{len(lang_map[lang])} 个）：{names}")
        lines.append("")

    # 整理建议
    lines += ["---", "", "## 🗂 整理建议", ""]

    to_archive = [r for r in repos if r["disposition"] == "建议归档"]
    to_delete  = [r for r in repos if r["disposition"] == "建议删除"]
    to_keep    = sorted([r for r in repos if r["disposition"] == "建议保留"],
                        key=lambda x: x["score"], reverse=True)

    if to_archive:
        lines.append(f"### 📦 建议归档（{len(to_archive)} 个）")
        lines.append("")
        for r in to_archive:
            parts = []
            if r["days_since_push"] > 365:
                parts.append(f"{r['days_since_push']}天未推送")
            if r["stargazerCount"] == 0:
                parts.append("无 stars")
            if not r["description"]:
                parts.append("无描述")
            reason = "，".join(parts) or "长期不活跃"
            lines.append(f"- `{r['name']}`：{reason}")
        lines.append("")

    if to_delete:
        lines.append(f"### 🗑 建议删除（{len(to_delete)} 个）")
        lines.append("")
        for r in to_delete:
            lines.append(f"- `{r['name']}`：fork 仓库，{r['days_since_push']}天未见定制修改")
        lines.append("")

    lines.append(f"### ✅ 建议保留 Top 20（共 {len(to_keep)} 个，按评分排序）")
    lines.append("")
    lines += [
        "| 仓库名 | 质量分 | 活跃度 | Stars |",
        "|--------|--------|--------|-------|",
    ]
    for r in to_keep[:20]:
        name = f"[{r['name']}]({r['url']})" if r["url"] else r["name"]
        lines.append(f"| {name} | {r['score']}/60 | {r['activity_level']} | {r['stargazerCount']} |")
    lines.append("")

    return "\n".join(lines)


def build_profile_suggestions(repos, profile_repos, report_date, top_n=10):
    """生成求职展示优化建议 Markdown"""
    candidates = [r for r in repos if not r["isArchived"] and r["disposition"] != "建议删除"]
    candidates_sorted = sorted(candidates, key=lambda x: x["score"], reverse=True)

    in_profile            = [r for r in candidates_sorted if r["in_profile"]]
    not_in_profile_high   = [r for r in candidates_sorted if not r["in_profile"] and r["score"] >= 40]
    low_score_in_profile  = [r for r in in_profile if r["score"] < 30]

    lines = [
        f"# 求职展示优化建议 {report_date}",
        "",
        "## 📌 当前 profile.md 已展示仓库评分",
        "",
    ]

    if in_profile:
        lines += [
            "| 仓库名 | 质量分 | 活跃度 | Stars | README | 建议 |",
            "|--------|--------|--------|-------|--------|------|",
        ]
        for r in sorted(in_profile, key=lambda x: x["score"], reverse=True):
            if r["score"] >= 40:
                suggest = "✅ 继续展示"
            elif r["score"] >= 25:
                suggest = "⚠️ 考虑替换"
            else:
                suggest = "❌ 建议移除"
            readme_mark = "✅" if r["has_readme"] is True else ("❌" if r["has_readme"] is False else "—")
            lines.append(f"| `{r['name']}` | {r['score']}/60 | {r['activity_level']} | {r['stargazerCount']} | {readme_mark} | {suggest} |")
        lines.append("")
    else:
        lines.append("*（未从 profile.md 中检测到已展示仓库，请检查 GITHUB_PROJECTS_START/END 占位符）*")
        lines.append("")

    lines += ["---", ""]
    lines.append(f"## 🌟 推荐新增到 profile.md（Top {top_n}，质量分 ≥ 40）")
    lines.append("")

    if not_in_profile_high:
        lines += [
            "| 仓库名 | 质量分 | 语言 | 活跃度 | Stars | 描述 |",
            "|--------|--------|------|--------|-------|------|",
        ]
        for r in not_in_profile_high[:top_n]:
            desc = (r["description"][:40] + "...") if len(r["description"]) > 40 else (r["description"] or "—")
            lang = r["primaryLanguage"] or "—"
            lines.append(f"| `{r['name']}` | {r['score']}/60 | {lang} | {r['activity_level']} | {r['stargazerCount']} | {desc} |")
        lines.append("")
    else:
        lines.append("*暂无质量分 ≥ 40 的未展示仓库*")
        lines.append("")

    lines += ["---", ""]

    if low_score_in_profile:
        lines.append(f"## ⬇️ 建议降级或移除（质量分 < 30，共 {len(low_score_in_profile)} 个）")
        lines.append("")
        for r in low_score_in_profile:
            parts = []
            if r["stargazerCount"] == 0:
                parts.append("无 stars")
            if r["has_readme"] is False:
                parts.append("缺少 README")
            if not r["description"]:
                parts.append("无描述")
            reason = "，".join(parts) or "质量分偏低"
            lines.append(f"- `{r['name']}`（质量分 {r['score']}/60，活跃度：{r['activity_level']}）：{reason}")
        lines.append("")
        lines += ["---", ""]

    lines.append("## 📊 质量评分排行（前30名）")
    lines.append("")
    lines += [
        "| 排名 | 仓库名 | 质量分 | 活跃度 | Stars | 已在Profile | 在Tracked |",
        "|------|--------|--------|--------|-------|-------------|-----------|",
    ]
    for i, r in enumerate(candidates_sorted[:30], 1):
        in_p = "✅" if r["in_profile"] else "—"
        in_t = "✅" if r["in_tracked"] else "—"
        lines.append(f"| {i} | `{r['name']}` | {r['score']}/60 | {r['activity_level']} | {r['stargazerCount']} | {in_p} | {in_t} |")
    lines.append("")

    return "\n".join(lines)


def write_report(content, path, dry_run):
    if dry_run:
        print(f"\n[dry-run] {path.name}")
        print("─" * 60)
        print(content[:600])
        if len(content) > 600:
            print(f"... （共 {len(content)} 字符）")
        print("─" * 60)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"   ✅ 已写入：{path}")


# ── A5: GitHub Star 同步 ──────────────────────────────────────────────
def get_starred_own_repos():
    """获取用户已收藏的自己的仓库名集合"""
    out = run_gh(["api", "/user/starred", "--paginate", "--jq", ".[].full_name"])
    if not out:
        return set()
    prefix = f"{GITHUB_USER}/"
    return {
        line.strip()[len(prefix):]
        for line in out.splitlines()
        if line.strip().startswith(prefix)
    }


def _gh_star_action(method, repo_name):
    """执行单个 Star/Unstar 操作，返回是否成功并打印错误信息"""
    r = subprocess.run(
        ["gh", "api", "--method", method, f"/user/starred/{GITHUB_USER}/{repo_name}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        err = r.stderr.strip()[:120] or r.stdout.strip()[:120] or "（无错误信息）"
        print(f"      ⚠️  API 调用失败（{method} /user/starred/{GITHUB_USER}/{repo_name}）：{err}")
        return False
    return True


def sync_stars(config, dry_run):
    """将 GitHub 收藏与追踪配置同步：追踪→收藏，停止追踪→取消收藏"""
    tracked = set(config.get("tracked_repos", {}).keys())
    starred = get_starred_own_repos()

    to_star   = tracked - starred
    to_unstar = starred - tracked

    if not to_star and not to_unstar:
        print("   ✅ 收藏状态已同步，无需变更")
        return

    for name in sorted(to_star):
        if dry_run:
            print(f"   [dry-run] ⭐ 收藏：{name}")
        elif _gh_star_action("PUT", name):
            print(f"   ⭐ 已收藏：{name}")

    for name in sorted(to_unstar):
        if dry_run:
            print(f"   [dry-run] ✂️  取消收藏：{name}")
        elif _gh_star_action("DELETE", name):
            print(f"   ✂️  取消收藏：{name}")


# ── A6: 缓存层（增量分析）─────────────────────────────────────────────
def load_repo_cache():
    """加载仓库缓存（记录每个仓库上次 README 检测时的 pushedAt）"""
    if not CACHE_PATH.exists():
        return {}
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_repo_cache(cache, dry_run):
    """保存 README 缓存到 repo_cache.json"""
    if dry_run:
        return
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── A7: 数据库文档 ─────────────────────────────────────────────────────
def build_repo_database(repos, tracked_cfg, updated_names, now_str):
    """生成持久化仓库数据库 repo_database.md（每次分析后完整重写）"""
    tracked_names = set(tracked_cfg.get("tracked_repos", {}).keys())
    tracked_repos = sorted(
        [r for r in repos if r["name"] in tracked_names],
        key=lambda x: x["score"], reverse=True,
    )
    all_sorted = sorted(repos, key=lambda x: x["score"], reverse=True)
    updated_count = len(updated_names)
    cached_count  = len(repos) - updated_count

    lines = [
        "# GitHub 仓库数据库",
        "",
        f"> 最后更新：{now_str}  ",
        f"> 共 **{len(repos)}** 个仓库 ｜ 追踪 **{len(tracked_repos)}** 个 ｜"
        f" 本次重新分析 **{updated_count}** 个（{cached_count} 个命中缓存）",
        "",
        "---",
        "",
    ]

    # ── 追踪中的项目（详情块）──────────────────────────────────────────
    if tracked_repos:
        lines += [f"## ⭐ 追踪中的项目（{len(tracked_repos)} 个）", ""]
        for r in tracked_repos:
            cfg_info = tracked_cfg["tracked_repos"].get(r["name"], {})
            display  = cfg_info.get("name", r["name"])
            icon     = cfg_info.get("icon", "📦")
            readme_m = "✅" if r["has_readme"] is True else ("❌" if r["has_readme"] is False else "—")
            profile_m = "✅" if r["in_profile"] else "—"
            tag      = " *(本次更新)*" if r["name"] in updated_names else " *(缓存)*"
            pushed   = r["pushedAt"][:10] if r["pushedAt"] else "—"
            days_str = f"{r['days_since_push']} 天前" if r["days_since_push"] >= 0 else "未知"
            lines += [
                f"### {icon} {display} (`{r['name']}`){tag}",
                "",
                "| 项目 | 值 |",
                "|------|-----|",
                f"| 描述 | {r['description'] or '—'} |",
                f"| 语言 | {r['primaryLanguage'] or '—'} |",
                f"| Stars | {r['stargazerCount']} |",
                f"| 质量评分 | {r['score']} / 60 |",
                f"| 活跃度 | {r['activity_level']}（{days_str}）|",
                f"| README | {readme_m} |",
                f"| 已在 profile.md | {profile_m} |",
                f"| 处置建议 | {r['disposition']} |",
                f"| 最近推送 | {pushed} |",
                "",
            ]
        lines += ["---", ""]

    # ── 所有仓库总表 ───────────────────────────────────────────────────
    lines += [
        f"## 📋 所有仓库（{len(repos)} 个，按质量分排序）",
        "",
        "| 仓库名 | 语言 | 质量分 | 活跃度 | Stars | README | Profile | 追踪 | 处置 | 最近推送 |",
        "|--------|------|--------|--------|-------|--------|---------|------|------|----------|",
    ]
    for r in all_sorted:
        readme_m  = "✅" if r["has_readme"] is True else ("❌" if r["has_readme"] is False else "—")
        profile_m = "✅" if r["in_profile"] else "—"
        tracked_m = "⭐" if r["name"] in tracked_names else "—"
        pushed    = r["pushedAt"][:10] if r["pushedAt"] else "—"
        arch_tag  = " [归档]" if r["isArchived"] else ""
        lines.append(
            f"| `{r['name']}`{arch_tag} | {r['primaryLanguage'] or '—'} | {r['score']}/60 |"
            f" {r['activity_level']} | {r['stargazerCount']} | {readme_m} |"
            f" {profile_m} | {tracked_m} | {r['disposition']} | {pushed} |"
        )
    lines.append("")

    return "\n".join(lines)


# ── Step 5: README 生成层 ─────────────────────────────────────────────
def generate_readme_with_claude(client, repo):
    """用 Claude Haiku 为仓库生成中英双语 README 草稿"""
    name = repo["name"]
    desc = repo["description"] or "（无描述）"
    lang = repo["primaryLanguage"] or "未知"

    prompt = (
        f"请为以下 GitHub 仓库生成一份简洁的 README.md，使用中英双语。\n\n"
        f"仓库名：{name}\n"
        f"描述：{desc}\n"
        f"主要语言：{lang}\n\n"
        "README 结构要求：\n"
        "# {仓库名}\n\n"
        "## 简介 / Introduction\n（50-80字中文 + 30-50字英文）\n\n"
        "## 技术栈 / Tech Stack\n（列表）\n\n"
        "## 使用方法 / Usage\n（基本步骤）\n\n"
        "只输出 Markdown 内容，不要额外说明。"
    )

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        result = resp.content[0].text.strip()
        time.sleep(1.0)
        return result
    except Exception as e:
        print(f"      ⚠️  README 生成失败（{name}）：{e}")
        time.sleep(1.0)
        return ""


def batch_generate_readmes(client, repos, drafts_dir, dry_run):
    """批量为缺少 README 的仓库生成草稿，写入 drafts_dir/"""
    candidates = [
        r for r in repos
        if r["has_readme"] is False
        and not r["isArchived"]
        and r["disposition"] != "建议删除"
    ]

    if not candidates:
        print("   ℹ️  无需生成 README 草稿（所有候选仓库均已有 README）")
        return 0

    print(f"   📝 共 {len(candidates)} 个仓库缺少 README，开始生成草稿...")

    if client is None:
        print("   ⚠️  未配置 ANTHROPIC_API_KEY，跳过 README 生成")
        return 0

    success = 0
    for repo in candidates:
        print(f"   ✍️  生成：{repo['name']}", end="  ", flush=True)
        content = generate_readme_with_claude(client, repo)
        if content:
            out_path = drafts_dir / f"{repo['name']}.md"
            write_report(content, out_path, dry_run)
            success += 1
            if not dry_run:
                print("✅")
        else:
            print("⚠️  失败")

    print(f"   📋 README 草稿：成功 {success}/{len(candidates)} 个")
    return success


# ── Step 6: 主流程 ────────────────────────────────────────────────────
def main():
    args   = parse_args()
    config = load_config()
    client = init_anthropic_client(config)

    output_dir  = Path(args.output)
    dry_run     = args.dry_run
    skip_readme = args.skip_readme_gen
    today       = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print("🔍 GitHub 仓库全量分析")
    print(f"📅 日期：{today}")
    print(f"🤖 Claude：{'已配置' if client else '未配置（跳过 AI 功能）'}")
    print(f"📁 输出目录：{output_dir}")
    options = " ".join(filter(None, [
        "--dry-run"         if dry_run              else "",
        "--skip-readme-gen" if skip_readme          else "",
        "--no-auto-update"  if args.no_auto_update  else "",
    ]))
    if options:
        print(f"🔧 选项：{options}")
    print()

    start_time = datetime.now()
    now_str    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 1. 获取全量仓库
    print("1️⃣  获取仓库列表...")
    repos = fetch_all_repos()
    if not repos:
        print("❌ 无法获取仓库，退出")
        sys.exit(1)
    print(f"   ✅ 共获取 {len(repos)} 个仓库")
    print()

    # 2. 增量检测 README（命中缓存的仓库跳过 API 调用）
    print("2️⃣  检测 README（增量）...")
    cache = load_repo_cache()
    repos, updated_names = batch_detect_readmes(repos, cache)
    print()

    # 3. 加载追踪配置并标注
    print("3️⃣  加载追踪配置并分析仓库...")
    tracked_cfg   = load_tracked_config()
    tracked_names = config_to_tracked_names(tracked_cfg)
    profile_repos = load_profile_repos(PROFILE_PATH)
    repos         = annotate_repos(repos, tracked_names, profile_repos)

    if not args.no_auto_update:
        # 自动发现高分新仓库
        new_repos = auto_discover_new_repos(repos, tracked_cfg, today)
        if new_repos:
            print(f"   🆕 自动发现 {len(new_repos)} 个新追踪仓库：")
            for rname, score in new_repos:
                display = tracked_cfg["tracked_repos"][rname]["name"]
                print(f"      + {rname}（{display}，评分 {score}）")
            # 重新标注（新发现的仓库 in_tracked 需更新为 True）
            tracked_names = config_to_tracked_names(tracked_cfg)
            repos = annotate_repos(repos, tracked_names, profile_repos)

        # 更新评分历史
        update_score_history(repos, tracked_cfg, today)

        # 低分告警
        declining = check_declining_repos(tracked_cfg)
        if declining:
            threshold = tracked_cfg["settings"]["auto_remove_threshold"]
            print(f"   ⚠️  以下追踪仓库连续两次评分 < {threshold}，请考虑从 tracked_config.json 中移除：")
            for rname, score, display in declining:
                print(f"      - {rname}（{display}，当前 {score} 分）")

        save_tracked_config(tracked_cfg, dry_run)
    else:
        print(f"   ℹ️  --no-auto-update：使用现有配置（{len(tracked_names)} 个追踪仓库），不修改配置文件")

    # 同步 GitHub 收藏：无论是否 auto_update，追踪状态始终与 Star 保持一致
    print("   🌟 同步 GitHub 收藏...")
    sync_stars(tracked_cfg, dry_run)

    # 保存 README 缓存
    save_repo_cache(cache, dry_run)

    print(f"   ✅ 分析完成：{len(repos)} 个仓库已标注"
          f"（追踪 {len(tracked_names)} 个，profile 已展示 {len(profile_repos)} 个）")
    print()

    # 3.5 更新仓库数据库
    print("   📚 更新仓库数据库...")
    write_report(build_repo_database(repos, tracked_cfg, updated_names, now_str), DATABASE_PATH, dry_run)
    print()

    # 4. 生成分类报告
    print("4️⃣  生成分类报告...")
    analysis_path = output_dir / f"{today}-repo-analysis.md"
    write_report(build_analysis_report(repos, today), analysis_path, dry_run)

    # 5. 生成求职优化建议
    print("5️⃣  生成求职展示优化建议...")
    suggestions_path = output_dir / f"{today}-profile-suggestions.md"
    write_report(build_profile_suggestions(repos, profile_repos, today), suggestions_path, dry_run)
    print()

    # 6. 生成 README 草稿
    if not skip_readme:
        print("6️⃣  生成 README 草稿...")
        drafts_dir = output_dir / f"{today}-readme-drafts"
        batch_generate_readmes(client, repos, drafts_dir, dry_run)
    else:
        print("ℹ️  跳过 README 草稿生成（--skip-readme-gen）")

    elapsed = (datetime.now() - start_time).seconds
    print()
    print(f"🎉 完成！耗时 {elapsed}s")
    if not dry_run:
        print(f"📁 报告位置：{output_dir}/")
        print(f"   - {today}-repo-analysis.md")
        print(f"   - {today}-profile-suggestions.md")
        if not skip_readme:
            print(f"   - {today}-readme-drafts/")


if __name__ == "__main__":
    main()
