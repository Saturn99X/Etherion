#!/usr/bin/env bash
# =============================================================================
# sync-from-langchain.sh — Selectively sync changes from private langchain-app
#                          to the public Etherion repo.
#
# RULES:
#   - Always run from the ROOT of the Etherion repo on the clean2 branch.
#   - Only the explicit list of ALLOWED_PATHS below is ever touched.
#   - Nothing outside that list is staged or committed.
#   - Frontend, terraform, Z/, Archive/, scripts/evaluation, .venv/, and all
#     files matching .gitignore are NEVER included.
#   - Review `git status` and `git diff --cached` before committing.
#
# USAGE:
#   cd ~/Etherion
#   git checkout clean2
#   bash scripts/sync-from-langchain.sh
#   # Review carefully, then:
#   git commit -m "sync: <describe what changed>"
#   git push origin clean2:main
# =============================================================================

set -euo pipefail

LANGCHAIN_REMOTE="langchain"
LANGCHAIN_PATH="/home/saturnx/langchain-app"   # adjust if needed
REQUIRED_BRANCH="clean2"

# ---------------------------------------------------------------------------
# Guard: must be in Etherion repo on clean2
# ---------------------------------------------------------------------------
CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
if [[ "$CURRENT_BRANCH" != "$REQUIRED_BRANCH" ]]; then
  echo "ERROR: You must be on the '$REQUIRED_BRANCH' branch (currently: $CURRENT_BRANCH)"
  echo "  Run: git checkout $REQUIRED_BRANCH"
  exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
if [[ ! -f "$REPO_ROOT/tui/main.go" ]]; then
  echo "ERROR: Run this script from the root of the Etherion repo."
  exit 1
fi

# ---------------------------------------------------------------------------
# Guard: no dirty working tree (staged or unstaged changes)
# ---------------------------------------------------------------------------
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: Working tree is dirty. Commit or stash changes first."
  git status --short
  exit 1
fi

# ---------------------------------------------------------------------------
# Ensure langchain remote is registered
# ---------------------------------------------------------------------------
if ! git remote get-url "$LANGCHAIN_REMOTE" &>/dev/null; then
  echo "Adding remote '$LANGCHAIN_REMOTE' → file://$LANGCHAIN_PATH"
  git remote add "$LANGCHAIN_REMOTE" "file://$LANGCHAIN_PATH"
fi

echo "Fetching $LANGCHAIN_REMOTE/main …"
git fetch "$LANGCHAIN_REMOTE" main --quiet

# ---------------------------------------------------------------------------
# ALLOWED_PATHS — the ONLY paths ever synced to the public repo.
# Add new entries here when a new public-facing module is created.
# ---------------------------------------------------------------------------
ALLOWED_PATHS=(
  # Python CLI package
  "etherion"
  "pyproject.toml"
  "MANIFEST.in"

  # Go TUI source + pre-built wheel binaries
  "tui"
  "tui-pkg"

  # Backend (FastAPI / Celery / GraphQL)
  "src"

  # Database migrations
  "alembic"
  "alembic.ini"

  # Infra / Docker (bare-metal config)
  "infra"
  "docker-compose.services.yml"
  "docker-compose.yml"
  "Dockerfile"
  "Dockerfile.worker"
  ".dockerignore"
  ".env.example"

  # Public docs
  "README.md"
  "SETUP.md"

  # DB/init scripts
  "sql"

  # Tests
  "tests"

  # Dependencies
  "requirements.txt"
  "requirements-worker.txt"
)

# ---------------------------------------------------------------------------
# Checkout only allowed paths from langchain/main
# ---------------------------------------------------------------------------
echo ""
echo "Checking out allowed paths from $LANGCHAIN_REMOTE/main …"
git checkout "$LANGCHAIN_REMOTE/main" -- "${ALLOWED_PATHS[@]}"

# ---------------------------------------------------------------------------
# Safety: unstage anything that landed outside ALLOWED_PATHS or matches
# .gitignore. (git checkout --  respects .gitignore for new files, but
# belt-and-suspenders check.)
# ---------------------------------------------------------------------------
STAGED=$(git diff --cached --name-only)
UNEXPECTED=()
for f in $STAGED; do
  ALLOWED=false
  for p in "${ALLOWED_PATHS[@]}"; do
    if [[ "$f" == "$p" || "$f" == "$p/"* ]]; then
      ALLOWED=true
      break
    fi
  done
  if [[ "$ALLOWED" == false ]]; then
    UNEXPECTED+=("$f")
  fi
done

if [[ ${#UNEXPECTED[@]} -gt 0 ]]; then
  echo ""
  echo "WARNING: The following files were staged outside ALLOWED_PATHS and will be UNSTAGED:"
  for f in "${UNEXPECTED[@]}"; do
    echo "  $f"
  done
  git restore --staged "${UNEXPECTED[@]}"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================================"
echo " Sync complete. Review the changes below before committing."
echo "========================================================"
echo ""
git diff --cached --stat
echo ""
echo "Next steps:"
echo "  1. Review:  git diff --cached"
echo "  2. Commit:  git commit -m 'sync: <describe changes>'"
echo "  3. Push:    git push origin clean2:main"
echo ""
echo "DO NOT run: git push origin main  (that pushes the local main branch)"
echo "ALWAYS use: git push origin clean2:main"
