#!/usr/bin/env bash
# update.sh — pull the latest code from GitHub for this repo.
#
# Usage:
#   bash update.sh             # git pull only — safe for cron, never restarts the bot
#   bash update.sh --reload    # pull + reinstall deps (if changed) + reload bot agent
#
# Called by:
#   • com.digger.updater launchd agent (hourly, no flags)
#   • @digger pull Slack command (with --reload)
#
# Exit codes:
#   0 — success (may be a no-op if already up to date)
#   1 — refused because of uncommitted local changes
#   2 — unknown flag
#   3 — git pull failed (non-fast-forward, network error, etc.)

set -euo pipefail

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$BOT_DIR/../.." && pwd)"
RELOAD=0

for a in "$@"; do
    case "$a" in
        --reload) RELOAD=1 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown flag: $a" >&2; exit 2 ;;
    esac
done

cd "$REPO_DIR"

# Refuse to pull if there are uncommitted changes (avoids clobbering work).
if ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    echo "ERROR: uncommitted changes in $REPO_DIR — refusing to pull" >&2
    git status --short >&2
    exit 1
fi

BEFORE=$(git rev-parse HEAD)

# Fetch first so we can see if anything's actually new.
if ! git fetch --quiet origin; then
    echo "ERROR: git fetch failed" >&2
    exit 3
fi

REMOTE_HEAD=$(git rev-parse origin/main 2>/dev/null || git rev-parse origin/HEAD)

if [[ "$BEFORE" == "$REMOTE_HEAD" ]]; then
    echo "up to date (${BEFORE:0:7})"
    exit 0
fi

if ! git pull --ff-only origin main; then
    echo "ERROR: git pull failed (non-fast-forward?)" >&2
    exit 3
fi

AFTER=$(git rev-parse HEAD)
CHANGED=$(git diff --name-only "$BEFORE" "$AFTER" || true)
NUM_FILES=$(printf '%s\n' "$CHANGED" | grep -c . || true)

printf 'pulled %d file(s): %s → %s\n' "$NUM_FILES" "${BEFORE:0:7}" "${AFTER:0:7}"
printf '%s\n' "$CHANGED" | sed 's/^/  /'

if [[ "$RELOAD" == 0 ]]; then
    echo "(not reloading — run with --reload or send @digger pull)"
    exit 0
fi

# Reinstall pip deps if requirements.txt changed.
if printf '%s\n' "$CHANGED" | grep -q 'digger/bot/requirements.txt$'; then
    echo "requirements.txt changed, pip install..."
    "$BOT_DIR/.venv/bin/pip" install -r "$BOT_DIR/requirements.txt" --quiet
fi

# Reload the bot agent so new code takes effect.
PLIST="$HOME/Library/LaunchAgents/com.digger.bot.plist"
if [[ -f "$PLIST" ]]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load -w "$PLIST"
    echo "reloaded bot agent"
else
    echo "(bot agent not installed — skipped reload)"
fi
