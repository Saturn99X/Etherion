#!/usr/bin/env bash
# =============================================================================
# purge_credentials.sh — Remove credential/secret files from working tree
#                         and optionally from git history.
#
# Usage: bash scripts/purge_credentials.sh [--yes]
#   --yes   Skip the interactive safety prompt (for CI use).
# =============================================================================
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { printf "${CYAN}[INFO]${RESET}  %s\n" "$*"; }
warn()    { printf "${YELLOW}[WARN]${RESET}  %s\n" "$*"; }
success() { printf "${GREEN}[OK]${RESET}    %s\n" "$*"; }
danger()  { printf "${RED}[DANGER]${RESET} %s\n" "$*"; }
header()  { printf "\n${BOLD}%s${RESET}\n%s\n" "$*" "$(printf '=%.0s' {1..60})"; }

# ── Target paths ──────────────────────────────────────────────────────────────
TRACKED_FILES=(
    "frontend/.env.local"
    "frontend/.env.production"
    "secrets/export.env"
    "XBin/cloud_db_creds.env"
    "XBin/etherion-deploy.json"
)
TRACKED_GLOBS=(
    "XBin/client_secret_*.json"
)
TRACKED_DIRS=(
    "backupx/secrets"
)

# ── Safety prompt ─────────────────────────────────────────────────────────────
SKIP_PROMPT=false
for arg in "$@"; do
    [[ "$arg" == "--yes" ]] && SKIP_PROMPT=true
done

header "purge_credentials.sh — Credential & Secret Purge"
printf "\n"
danger "This script will:"
danger "  1. Untrack and DELETE credential files from disk"
danger "  2. Optionally rewrite git history to remove these paths entirely"
danger "  3. Modify .gitignore"
printf "\n"
warn "Working directory: ${REPO_ROOT}"
printf "\n"

if [[ "$SKIP_PROMPT" == false ]]; then
    read -r -p "$(printf "${RED}${BOLD}Are you sure you want to continue? Type YES to proceed: ${RESET}")" CONFIRM
    if [[ "$CONFIRM" != "YES" ]]; then
        printf "\nAborted. No changes made.\n"
        exit 0
    fi
fi

# ── Tracking counters ─────────────────────────────────────────────────────────
REMOVED_FROM_GIT=0
DELETED_FROM_DISK=0

# ── Step 1: git rm --cached and delete from disk ──────────────────────────────
header "Step 1: Untrack and delete credential files"

untrack_and_delete() {
    local path="$1"
    # git rm --cached (ignore error if not tracked)
    if git ls-files --error-unmatch "$path" &>/dev/null 2>&1; then
        git rm --cached -r --force -- "$path" && \
            info "git rm --cached: $path" && \
            REMOVED_FROM_GIT=$((REMOVED_FROM_GIT + 1)) || \
            warn "git rm --cached failed for: $path"
    else
        info "Not tracked in git (skip git rm): $path"
    fi

    # Delete from disk
    if [[ -e "$path" || -d "$path" ]]; then
        rm -rf -- "$path"
        success "Deleted from disk: $path"
        DELETED_FROM_DISK=$((DELETED_FROM_DISK + 1))
    else
        info "Not on disk (skip delete): $path"
    fi
}

# Process exact file paths
for f in "${TRACKED_FILES[@]}"; do
    untrack_and_delete "$f"
done

# Process glob patterns
for pattern in "${TRACKED_GLOBS[@]}"; do
    # Check git index for matches
    while IFS= read -r matched; do
        [[ -z "$matched" ]] && continue
        untrack_and_delete "$matched"
    done < <(git ls-files -- "$pattern" 2>/dev/null)

    # Also delete any on-disk matches not necessarily tracked
    while IFS= read -r -d '' disk_file; do
        [[ -z "$disk_file" ]] && continue
        if [[ -e "$disk_file" ]]; then
            rm -f -- "$disk_file"
            success "Deleted from disk (untracked glob match): $disk_file"
            DELETED_FROM_DISK=$((DELETED_FROM_DISK + 1))
        fi
    done < <(find "$REPO_ROOT" -path "*/${pattern#*/}" -print0 2>/dev/null || true)
done

# Process directories
for d in "${TRACKED_DIRS[@]}"; do
    untrack_and_delete "$d"
done

# ── Step 2: git-filter-repo ───────────────────────────────────────────────────
header "Step 2: Purge paths from git history"

FILTER_PATHS=(
    "frontend/.env.local"
    "frontend/.env.production"
    "secrets/export.env"
    "XBin/client_secret_"       # prefix match handled by --path-glob
    "XBin/cloud_db_creds.env"
    "XBin/etherion-deploy.json"
    "backupx/secrets"
)

if command -v git-filter-repo &>/dev/null; then
    info "git-filter-repo found: $(command -v git-filter-repo)"
    warn "Rewriting git history — this is IRREVERSIBLE on a force-pushed repo."
    printf "\n"

    FILTER_ARGS=()
    for p in "${FILTER_PATHS[@]}"; do
        FILTER_ARGS+=("--path" "$p")
    done
    # Add a glob for the client_secret wildcard
    FILTER_ARGS+=("--path-glob" "XBin/client_secret_*.json")

    info "Running: git filter-repo --invert-paths ${FILTER_ARGS[*]}"
    git filter-repo --invert-paths "${FILTER_ARGS[@]}" \
        --path "XBin/client_secret_" \
        2>&1 | sed 's/^/    /'
    success "History rewritten. You MUST force-push: git push --force-with-lease"
else
    warn "git-filter-repo is NOT installed."
    printf "\n"
    printf "  Install it with one of:\n"
    printf "    pip install git-filter-repo\n"
    printf "    pipx install git-filter-repo\n"
    printf "    sudo pacman -S git-filter-repo          # Arch/NixOS\n"
    printf "    sudo apt install git-filter-repo        # Debian/Ubuntu\n"
    printf "    brew install git-filter-repo            # macOS\n"
    printf "\n"
    printf "  Then run:\n"
    printf "    git filter-repo --invert-paths \\\\\n"
    for p in "${FILTER_PATHS[@]}"; do
        printf "        --path '%s' \\\\\n" "$p"
    done
    printf "        --path-glob 'XBin/client_secret_*.json'\n"
    printf "\n"
    printf "  After rewriting history, force-push:\n"
    printf "    git push --force-with-lease\n"
fi

# ── Step 3: .gitignore rules ──────────────────────────────────────────────────
header "Step 3: Update .gitignore"

GITIGNORE_BLOCK="
# Credentials & secrets — NEVER commit
*.env.local
*.env.production
*.env.staging
secrets/
XBin/
backupx/
client_secret_*.json
*-creds.env
*-deploy.json
*-service-account.json
export.env
cloud_db_creds.env
"

GITIGNORE_FILE=".gitignore"
ALREADY_HAS_BLOCK=false

# Check if the sentinel comment already exists
if grep -qF "Credentials & secrets — NEVER commit" "$GITIGNORE_FILE" 2>/dev/null; then
    ALREADY_HAS_BLOCK=true
fi

if [[ "$ALREADY_HAS_BLOCK" == true ]]; then
    info ".gitignore already contains the credentials block — skipping append."
else
    # Check individual patterns and only add ones that are missing
    MISSING_PATTERNS=()
    while IFS= read -r line; do
        # Skip blank lines and comments
        [[ -z "$line" || "$line" == \#* ]] && continue
        if ! grep -qxF "$line" "$GITIGNORE_FILE" 2>/dev/null; then
            MISSING_PATTERNS+=("$line")
        fi
    done <<< "$GITIGNORE_BLOCK"

    if [[ ${#MISSING_PATTERNS[@]} -eq 0 ]]; then
        info "All credential patterns already present in .gitignore — skipping."
    else
        printf "\n%s\n" "$GITIGNORE_BLOCK" >> "$GITIGNORE_FILE"
        success "Appended credentials block to .gitignore"
        info "Patterns added:"
        for p in "${MISSING_PATTERNS[@]}"; do
            printf "    + %s\n" "$p"
        done
    fi
fi

# ── Step 4: Scan tracked files for credential patterns ────────────────────────
header "Step 4: Scan tracked files for embedded secrets"

SCAN_WARNINGS=0

scan_pattern() {
    local label="$1"
    local regex="$2"
    local results
    results=$(git grep -nE "$regex" -- ':!*.png' ':!*.jpg' ':!*.gif' ':!*.ico' \
                                       ':!*.woff' ':!*.woff2' ':!*.ttf' ':!*.eot' \
                                       ':!*.pdf' ':!*.bin' ':!*.lock' 2>/dev/null || true)
    if [[ -n "$results" ]]; then
        warn "Possible ${label} found:"
        while IFS= read -r line; do
            printf "    ${RED}%s${RESET}\n" "$line"
            SCAN_WARNINGS=$((SCAN_WARNINGS + 1))
        done <<< "$results"
    else
        success "No ${label} detected."
    fi
}

scan_pattern "Google OAuth client IDs"  '[0-9]{12}-[a-z0-9]+\.apps\.googleusercontent\.com'
scan_pattern "Slack bot tokens"          'xoxb-[0-9]+-[0-9]+-[A-Za-z0-9]+'
scan_pattern "OpenAI API keys"           'sk-[a-zA-Z0-9]{40,}'
scan_pattern "GitHub Personal Access Tokens" 'ghp_[a-zA-Z0-9]+'
scan_pattern "GCP API keys"              'AIza[a-zA-Z0-9]{35}'

# ── Summary ───────────────────────────────────────────────────────────────────
header "Summary"

printf "  Files removed from git index : ${BOLD}%d${RESET}\n" "$REMOVED_FROM_GIT"
printf "  Files deleted from disk      : ${BOLD}%d${RESET}\n" "$DELETED_FROM_DISK"

if command -v git-filter-repo &>/dev/null; then
    printf "  History rewrite              : ${GREEN}${BOLD}DONE${RESET} (force-push required)\n"
else
    printf "  History rewrite              : ${YELLOW}${BOLD}PENDING${RESET} (install git-filter-repo and re-run)\n"
fi

if [[ $SCAN_WARNINGS -gt 0 ]]; then
    printf "  Secret scan warnings         : ${RED}${BOLD}%d${RESET} — review and rotate these credentials!\n" "$SCAN_WARNINGS"
else
    printf "  Secret scan warnings         : ${GREEN}${BOLD}0${RESET} — clean.\n"
fi

printf "\n"
info "Next steps:"
printf "    1. Review the changes: git status && git diff --cached\n"
printf "    2. Commit the .gitignore update: git add .gitignore && git commit -m 'chore: add credential patterns to .gitignore'\n"
if ! command -v git-filter-repo &>/dev/null; then
    printf "    3. Install git-filter-repo and re-run this script to purge history\n"
else
    printf "    3. Force-push: git push --force-with-lease\n"
    printf "    4. Notify all collaborators to re-clone — local clones have stale history\n"
    printf "    5. Rotate ALL credentials that were ever committed\n"
fi
printf "\n"
