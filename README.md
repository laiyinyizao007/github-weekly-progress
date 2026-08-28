# GitHub Summary — 求职项目追踪与周报系统

自动追踪 GitHub 仓库活跃度，生成周报，并持续维护求职用的项目简介（`profile.md`）。

---

## 包含什么

| 脚本 | 功能 |
|------|------|
| `weekly_report.py` | 每周生成追踪仓库的 commit 摘要，更新 `profile.md` 的"本周进展"区块 |
| `update_profile.py` | 拉取最新仓库信息，更新 `profile.md` 的"项目展示"区块 |
| `repo_analyzer.py` | 全量分析所有仓库，自动发现新项目，生成分类报告和求职优化建议 |
| `tracked_config.json` | 追踪配置（由 `repo_analyzer.py` 自动生成和维护） |

---

## 快速上手

### 1. 环境要求

```bash
# Python 3.8+
python3 --version

# GitHub CLI（已登录）
gh auth status

# 安装 Python 依赖
pip install anthropic python-dotenv
```

### 2. 配置 API Key

在项目根目录创建 `.env` 文件：

```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
# 如果使用代理端点，还需要：
# ANTHROPIC_BASE_URL=https://your-proxy-url
```

### 3. 首次初始化追踪配置

运行分析工具，自动生成 `tracked_config.json`：

```bash
python3 repo_analyzer.py --dry-run --skip-readme-gen
```

这一步只预览，不写任何文件。确认输出正常后，去掉 `--dry-run` 正式运行。

---

## 三个工具详解

### `repo_analyzer.py` — 全量分析（最常用）

**作用**：扫描你 GitHub 上的所有仓库，打分排行，自动把高分新项目加入追踪列表。

```bash
# 标准用法：分析 + 生成报告（会更新 tracked_config.json）
python3 repo_analyzer.py --skip-readme-gen

# 完整用法（含 README 草稿生成，较慢）
python3 repo_analyzer.py

# 只看结果，不写任何文件
python3 repo_analyzer.py --dry-run --skip-readme-gen

# 只读模式：分析但不修改追踪配置
python3 repo_analyzer.py --no-auto-update --skip-readme-gen
```

**输出文件**（在 `reports/` 目录下）：

```
reports/
├── 2026-08-28-repo-analysis.md        # 全量分类报告 + 整理建议
├── 2026-08-28-profile-suggestions.md  # 求职展示优化（哪些仓库值得放进简介）
└── 2026-08-28-readme-drafts/
    └── some-repo.md                   # 缺少 README 的仓库草稿
```

**质量评分维度**（满分60分，不含活跃度）：

| 维度 | 满分 | 说明 |
|------|------|------|
| Stars | 20 | ≥10=20，5-9=15，2-4=10，1=5 |
| README | 15 | 有=15，无=0 |
| 描述 | 10 | ≥20字符=10，有但较短=5 |
| 已在 profile | 15 | 是=15 |

> 活跃度（最近推送距今天数）作为独立字段展示，不参与追踪阈值判断——项目质量与活跃度无关。

**自动发现规则**：

- 质量分 ≥ 40 的新仓库 → 自动加入 `tracked_config.json`，图标根据语言自动推断
- 已追踪仓库连续两次质量分 < 25 → 打印警告提醒（不自动删除）
- 加入 `ignored_repos` 的仓库 → 永久跳过

---

### `weekly_report.py` — 周报生成

**作用**：读取 `tracked_config.json` 中的追踪仓库，拉取过去7天的 commits，用 Claude 生成中文摘要，更新 `profile.md`。

```bash
# 正常运行（生成周报 + 更新 profile.md + 推送到 GitHub）
python3 weekly_report.py

# 不推送到 GitHub
python3 weekly_report.py --no-push

# 只预览，不写文件
python3 weekly_report.py --dry-run
```

**输出**：
- `weekly-reports/2026-W35.md`（完整周报，存入仓库）
- 更新 `profile.md` 的 `<!-- WEEKLY_PROGRESS_START -->` 区块

> **推荐频率**：每周一运行一次，或加入 cron job 自动执行。

---

### `update_profile.py` — 项目展示更新

**作用**：拉取最新仓库信息，更新 `profile.md` 中的"项目展示"区块（按系列关键词匹配）。

```bash
python3 update_profile.py
```

> **推荐频率**：有新仓库部署或描述变更时手动运行。

---

## 追踪配置文件 `tracked_config.json`

首次运行 `repo_analyzer.py` 时自动生成，之后每次运行自动维护。你可以手动编辑它：

```json
{
  "settings": {
    "auto_add_threshold": 70,     // 自动加入追踪的最低评分
    "auto_remove_threshold": 40   // 连续两次低于此分时告警
  },
  "tracked_repos": {
    "my-new-project": {
      "name": "My New Project",   // 显示名称（可改成中文）
      "icon": "🚀",               // 显示图标
      "type": "personal",         // "work" 或 "personal"
      "added_date": "2026-08-28",
      "score_history": []
    }
  },
  "ignored_repos": [
    "old-fork-repo"               // 加在这里的仓库永远不会被追踪
  ]
}
```

**常见操作**：

```bash
# 手动加入新项目到追踪（直接编辑 JSON）
# 然后运行周报即可生效
python3 weekly_report.py --dry-run

# 永久忽略某个仓库（不想追踪也不想看到它的告警）
# 在 ignored_repos 数组中加入仓库名即可

# 调整自动发现阈值（比如改为 60 分就加入）
# 修改 settings.auto_add_threshold 为 60
```

---

## 推荐工作流

```
每周一
  ├── python3 repo_analyzer.py --skip-readme-gen   # 分析 + 更新追踪配置
  └── python3 weekly_report.py                      # 生成周报 + 更新 profile

有新项目上线时
  └── python3 update_profile.py                     # 刷新项目展示区块

每月一次
  └── python3 repo_analyzer.py                      # 含 README 草稿生成
      → 查看 reports/ 目录，把草稿复制到对应仓库
```

---

## profile.md 结构说明

`profile.md` 用特殊注释作为占位符，脚本只更新对应区块，其余内容不动：

```markdown
<!-- GITHUB_PROJECTS_START -->
（由 update_profile.py 自动填充）
<!-- GITHUB_PROJECTS_END -->

<!-- WEEKLY_PROGRESS_START -->
（由 weekly_report.py 自动填充）
<!-- WEEKLY_PROGRESS_END -->
```

---

## 常见问题

**Q：新建了仓库，什么时候会出现在周报里？**
运行 `repo_analyzer.py` 后，如果新仓库评分 ≥ 70 会自动加入 `tracked_config.json`；下次运行 `weekly_report.py` 就会追踪它。

**Q：想手动把评分不够但很重要的项目加入追踪怎么办？**
直接编辑 `tracked_config.json`，在 `tracked_repos` 下加入对应条目即可。

**Q：某个仓库总出现在告警里，但我就是不想追踪也不想看到警告？**
把它加入 `ignored_repos` 数组。

**Q：Claude API 没配置，还能用吗？**
可以。`weekly_report.py` 的 AI 摘要和 `repo_analyzer.py` 的 README 生成会跳过，其余功能（commits 统计、分类报告、求职建议）完全正常。

**Q：不想推送到 GitHub 怎么办？**
`weekly_report.py --no-push` 或 `--dry-run`。
