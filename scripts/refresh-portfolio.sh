#!/usr/bin/env bash
# scripts/refresh-portfolio.sh
#
# Run the full github-weekly-progress pipeline locally on the Pi, using the
# same gh CLI token you already use for everything else. Bypasses the
# GitHub Actions cron + auto-injected GITHUB_TOKEN (which can't read other
# private repos' commits).
#
# What it does (mirrors .github/workflows/weekly-update.yml):
#   1. cd ~/Projects/github-weekly-progress
#   2. Install python deps if missing
#   3. Pull latest from main
#   4. Authenticate gh with your user PAT (from `gh auth token`)
#   5. Run repo_analyzer.py --skip-readme-gen
#   6. Run update_profile.py --no-push
#   7. Run weekly_report.py --no-push
#   8. If anything changed: commit + push as github-actions[bot]
#   9. Sync profile.md to laiyinyizao007/laiyinyizao007 README via PROFILE_SYNC_TOKEN
#
# Usage:
#   ./scripts/refresh-portfolio.sh                # full run, commit if dirty
#   ./scripts/refresh-portfolio.sh --dry-run      # preview only, no writes
#   ./scripts/refresh-portfolio.sh --push         # also push to GitHub (default)
#   ./scripts/refresh-portfolio.sh --no-push      # update locally, don't push
#
# Set REPO_DIR to override the github-weekly-progress checkout path.

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,28p' "$0"
  exit 0
fi

set -euo pipefail

# ---- args ----
DRY_RUN=0
DO_PUSH=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --push)    DO_PUSH=1; shift ;;
    --no-push) DO_PUSH=0; shift ;;
    -h|--help)
      # --help is handled at the top of the file before set -euo pipefail
      echo "See comment block at top of script for usage." >&2
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ---- locate repo ----
REPO_DIR="${REPO_DIR:-$HOME/Projects/github-weekly-progress}"
if [[ ! -d "$REPO_DIR" ]]; then
  echo "Error: $REPO_DIR not found. Set REPO_DIR or clone the repo first." >&2
  exit 1
fi
cd "$REPO_DIR"

echo ">> Repo: $REPO_DIR"

# ---- preflight ----
if ! command -v gh >/dev/null; then
  echo "Error: gh CLI not installed." >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "Error: gh not logged in. Run 'gh auth login' first." >&2
  exit 1
fi
if ! command -v python3 >/dev/null; then
  echo "Error: python3 not installed." >&2
  exit 1
fi

# Sanity: token is actually present (this will print length, not the token).
_TOKEN_LEN=$(gh auth token | wc -c)
echo ">> gh auth token length: ${_TOKEN_LEN} chars"
if [[ $_TOKEN_LEN -lt 30 ]]; then
  echo "Error: gh auth token looks empty / wrong." >&2
  exit 1
fi

# ---- pip deps (once) ----
if ! python3 -c "import anthropic, dotenv" 2>/dev/null; then
  echo ">> Installing python deps..."
  python3 -m pip install --user --quiet anthropic python-dotenv
fi

# ---- sync to latest main ----
echo ">> Pulling latest main..."
git fetch --quiet origin main
git checkout --quiet main
git merge --quiet --ff-only origin/main || {
  echo "Warning: local main diverged from origin. Skipping pull (local changes preserved)." >&2
}

# ---- run the three scripts ----
# Inject GH_TOKEN as the env var the Python scripts read for gh auth
# (they use `subprocess.run(["gh", ...])` which honours GH_TOKEN / GH_CONFIG_DIR
# in this shell).
export GH_TOKEN
GH_TOKEN="$(gh auth token)"

EXTRA=""
[[ $DRY_RUN -eq 1 ]] && EXTRA="--dry-run"

echo ">> Running repo_analyzer.py..."
python3 repo_analyzer.py --skip-readme-gen $EXTRA || {
  echo "Warning: repo_analyzer exited non-zero, continuing anyway." >&2
}

echo ">> Running update_profile.py..."
python3 update_profile.py --no-push || {
  echo "Warning: update_profile exited non-zero, continuing anyway." >&2
}

echo ">> Running weekly_report.py..."
python3 weekly_report.py --no-push $EXTRA || {
  echo "Warning: weekly_report exited non-zero, continuing anyway." >&2
}

# ---- commit + push ----
git add -A
if git diff --cached --quiet; then
  echo ">> No changes to commit."
else
  WEEK_ID=$(date -u +%Y-W%V)
  COMMIT_MSG="chore: auto weekly ${WEEK_ID}"
  echo ">> Committing: $COMMIT_MSG"
  git -c user.name='github-actions[bot]' \
      -c user.email='github-actions[bot]@users.noreply.github.com' \
      commit -m "$COMMIT_MSG" >/dev/null

  if [[ $DO_PUSH -eq 1 && $DRY_RUN -eq 0 ]]; then
    echo ">> Pushing to origin/main..."
    git push origin main
  fi
fi

# ---- sync profile to laiyinyizao007/laiyinyizao007 README ----
if [[ -n "${PROFILE_SYNC_TOKEN:-}" ]]; then
  echo ">> Syncing profile.md to personal README..."
  # Use the user PAT (already in $GH_TOKEN) for this; the personal repo
  # is also private and needs write access.
  GH_TOKEN_FOR_SYNC="$PROFILE_SYNC_TOKEN" python3 - <<'PY' || echo "  profile sync skipped (no PROFILE_SYNC_TOKEN or push failed)"
import base64, os, subprocess, sys
token = os.environ["GH_TOKEN_FOR_SYNC"]
sha_proc = subprocess.run(
    ["gh", "api", "/repos/laiyinyizao007/laiyinyizao007/contents/README.md", "--jq", ".sha"],
    capture_output=True, text=True,
    env={**os.environ, "GH_TOKEN": token},
)
sha = sha_proc.stdout.strip() or None
content = base64.b64encode(open("profile.md", "rb").read()).decode()
args = [
    "gh", "api", "--method", "PUT",
    "/repos/laiyinyizao007/laiyinyizao007/contents/README.md",
    "-f", "message=chore: sync profile",
    "-f", f"content={content}",
]
if sha:
    args += ["-f", f"sha={sha}"]
r = subprocess.run(args, capture_output=True, text=True,
                   env={**os.environ, "GH_TOKEN": token})
print("  profile sync:", "ok" if r.returncode == 0 else r.stderr.strip()[:200])
PY
else
  echo ">> PROFILE_SYNC_TOKEN not set; skipping personal README sync."
fi

echo ">> Done."