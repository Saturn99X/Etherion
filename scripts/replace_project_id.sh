#!/usr/bin/env bash
# Replace all occurrences of a project ID across the repo, safely and reproducibly.
# Defaults: old="etherion-474013" new="etherion-ai-platform-prod"
# Dry-run by default; requires --apply or -y to write changes.
# Excludes common vendor, VCS, build artifacts, binaries by default.

set -euo pipefail

OLD="etherion-474013"
NEW="etherion-ai-platform-prod"
APPLY=0
INCLUDE_BINARIES=0
REPO_ROOT="$(pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  -o, --old ID           Old string to replace (default: ${OLD})
  -n, --new ID           New string to use (default: ${NEW})
  -y, --apply            Apply changes in-place (default: dry-run)
  --include-binaries     Do NOT skip binary files (dangerous; default: skip)
  -C, --chdir DIR        Run from DIR (defaults to current dir)
  -h, --help             Show this help

Examples:
  # Dry-run (show what would change)
  $(basename "$0")

  # Apply changes
  $(basename "$0") -y

  # Replace a different string
  $(basename "$0") -o old-project -n new-project -y
EOF
}

# Parse args
while (( "$#" )); do
  case "$1" in
    -o|--old) OLD="${2:-}"; shift 2;;
    -n|--new) NEW="${2:-}"; shift 2;;
    -y|--apply) APPLY=1; shift;;
    --include-binaries) INCLUDE_BINARIES=1; shift;;
    -C|--chdir) REPO_ROOT="${2:-}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
  esac
done

if [[ -z "$OLD" || -z "$NEW" ]]; then
  echo "ERROR: old and new strings must be non-empty" >&2
  exit 1
fi

cd "$REPO_ROOT"

# Build exclude globs/paths
EXCLUDES=(
  ".git/**"
  ".venv/**"
  "node_modules/**"
  "**/.terraform/**"
  "**/*.tfstate" "**/*.tfstate.backup" "**/*.tfstate.*" "**/errored.tfstate"
  "**/*.tfplan"
  "**/*.lock"
  "**/*.log" "cloud-sql-proxy*.log" "cloud-sql-proxy-*.log" "codebase.txt"
  "**/*.png" "**/*.jpg" "**/*.jpeg" "**/*.gif" "**/*.webp" "**/*.ico" "**/*.svg"
  "**/*.pdf" "**/*.db" "**/*.db*" "**/*.sqlite" "**/*.sqlite3"
  "logs/**" "Logs/**" "backups/**"
  "cloud-sql-proxy"
  "**/*.gz" "**/*.zip" "**/*.tar" "**/*.tgz"
)

# Helper: join array into multiple -g '!pattern' for ripgrep
_rg_excludes() {
  for pat in "${EXCLUDES[@]}"; do
    printf -- " -g !%s" "$pat"
  done
}

# Determine candidate files containing OLD
FILES=()
if command -v rg >/dev/null 2>&1; then
  # ripgrep route: list files containing OLD; respect excludes unless including binaries
  RG_OPTS=( -l -S -uu )
  if [[ $INCLUDE_BINARIES -eq 0 ]]; then
    RG_OPTS+=( --text ) # treat binary as text? We'll still exclude common bins via globs
  fi
  # shellcheck disable=SC2206
  EXC=( $(_rg_excludes) )
  # shellcheck disable=SC2207
  mapfile -t FILES < <(eval rg "${RG_OPTS[*]}" $(printf '%s ' "${EXC[@]}") -- "$OLD" | sort -u)
else
  # grep fallback: search recursively; filter excludes and binaries
  # List candidate files first using grep -RIl (I=ignore binary); then filter excludes
  # shellcheck disable=SC2016
  mapfile -t FILES < <(grep -RIl --binary-files=without-match -- "$OLD" . | \
    grep -Ev '(^|/)(\.git|node_modules|\.venv|logs|Logs)(/|$)' | \
    grep -Ev '(\.terraform/|\.tfplan$|\.lock$|\.png$|\.jpg$|\.jpeg$|\.gif$|\.webp$|\.ico$|\.svg$|\.pdf$|\.db$|\.db\.|\.sqlite$|\.sqlite3$|\.gz$|\.zip$|\.tar$|\.tgz$)' | sort -u)
fi

TOTAL_FILES=${#FILES[@]}
if [[ $TOTAL_FILES -eq 0 ]]; then
  echo "No files contain '${OLD}'."
  exit 0
fi

# Count occurrences per file and total
TOTAL_MATCHES=0
if command -v rg >/dev/null 2>&1; then
  while IFS= read -r f; do
    c=$(rg -N -S -c -- "$OLD" "$f" || true)
    TOTAL_MATCHES=$((TOTAL_MATCHES + c))
    printf "%7d  %s\n" "$c" "$f"
  done < <(printf '%s\n' "${FILES[@]}")
else
  while IFS= read -r f; do
    # grep -o count
    c=$(grep -o -F -- "$OLD" "$f" | wc -l | tr -d ' ')
    TOTAL_MATCHES=$((TOTAL_MATCHES + c))
    printf "%7d  %s\n" "$c" "$f"
  done < <(printf '%s\n' "${FILES[@]}")
fi

echo "----"
echo "Files with matches: $TOTAL_FILES"
echo "Total occurrences:  $TOTAL_MATCHES"

if [[ $APPLY -eq 0 ]]; then
  echo "Dry-run complete. Re-run with -y to apply replacements."
  exit 0
fi

# Confirm
read -r -p "Apply replacement of '${OLD}' -> '${NEW}' to ${TOTAL_FILES} files? (y/N) " ans
case "${ans:-}" in
  y|Y|yes|YES) ;; 
  *) echo "Aborted."; exit 1;;
 esac

# sed portability for macOS vs Linux
SED_INPLACE=(sed -i)
if [[ "${OSTYPE:-}" == darwin* ]]; then
  SED_INPLACE=(sed -i '')
fi

MODIFIED=0
for f in "${FILES[@]}"; do
  # Skip if file path somehow disappeared
  [[ -f "$f" ]] || continue
  # Perform in-place replacement using a safe delimiter
  "${SED_INPLACE[@]}" -e "s|${OLD//|/\|}|${NEW//|/\|}|g" -- "$f"
  ((MODIFIED++)) || true
  echo "Rewrote: $f"
done

echo "Done. Modified $MODIFIED files."
