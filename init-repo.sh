#!/usr/bin/env bash
# init-repo.sh — one-time git setup for /Users/jc/Nest.
#
# Connects this directory to https://github.com/jcornelius/the-nest.
# Handles all three possible states of the remote:
#   A. Remote is empty             → push our commit as the first one.
#   B. Remote has commits we don't → merge them (--allow-unrelated-histories).
#   C. Remote already matches us   → no-op.
#
# Run once from macOS Terminal:
#   bash /Users/jc/Nest/init-repo.sh
#
# Re-runnable: safe to run again if something went sideways.

set -euo pipefail

REPO="/Users/jc/Nest"
# SSH preferred. If you don't have SSH keys on GitHub, pass --https to use
# the https URL + a Personal Access Token instead.
REMOTE_URL_SSH="git@github.com:jcornelius/the-nest.git"
REMOTE_URL_HTTPS="https://github.com/jcornelius/the-nest.git"
REMOTE_URL="$REMOTE_URL_SSH"

for arg in "$@"; do
    case "$arg" in
        --https) REMOTE_URL="$REMOTE_URL_HTTPS" ;;
        -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    esac
done

cd "$REPO"

bold()   { printf '\033[1m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }

# --- 1. Clean up any partial .git state left by Cowork sandbox. ---
# (The sandbox can create files in .git/ that it can't then remove; your
# user account on macOS can remove them fine.)
if [[ -d .git ]] && ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    yellow "Removing incomplete .git state from sandbox..."
    rm -rf .git
fi

# Remove stale lock files left by a prior crashed/aborted run (including
# from the Cowork sandbox, which can leave index.lock behind because mount
# permissions prevent its self-cleanup).
if [[ -f .git/index.lock ]]; then
    yellow "Removing stale .git/index.lock"
    rm -f .git/index.lock
fi
for ref_lock in .git/HEAD.lock .git/refs/heads/main.lock; do
    if [[ -f "$ref_lock" ]]; then
        yellow "Removing stale $ref_lock"
        rm -f "$ref_lock"
    fi
done

# If no .git at all, or we just removed it, init fresh.
if [[ ! -d .git ]]; then
    bold "Initializing repo..."
    git init -b main --quiet
    green "  main branch created"
fi

# --- 2. Make sure we have a commit locally. ---
if ! git log -1 >/dev/null 2>&1; then
    bold "Staging files..."
    git add -A
    N=$(git status --short | wc -l | tr -d ' ')
    echo "  $N files staged"

    bold "Initial commit..."
    git commit -q -m "Initial commit: digger bot + pipeline

Migrated out of openclaw-workspaces. Layout:
  digger/bot/      — Slack Socket Mode bot (slack_bolt + anthropic SDK)
  digger/scripts/  — Brave + Google Places + Hubspot + Hunter.io pipeline
  digger/briefs/   — Keyword-matching rules (maintained manually)
  digger/docs/     — Reference material

Bot features: @digger <search>, @digger pull, @digger status, @digger help.
Two launchd agents: com.digger.bot (bot), com.digger.updater (hourly pull)."
    green "  committed: $(git rev-parse --short HEAD)"
fi

# --- 3. Configure remote. ---
if git remote | grep -q '^origin$'; then
    current=$(git remote get-url origin)
    if [[ "$current" != "$REMOTE_URL" ]]; then
        yellow "Updating origin URL: $current → $REMOTE_URL"
        git remote set-url origin "$REMOTE_URL"
    else
        green "Remote origin already set to $REMOTE_URL"
    fi
else
    git remote add origin "$REMOTE_URL"
    green "Added origin → $REMOTE_URL"
fi

# --- 4. Fetch and reconcile with whatever is on GitHub. ---
bold "Fetching from GitHub..."
if ! git fetch origin 2>&1 | sed 's/^/  /'; then
    red "git fetch failed. If this is an auth issue:"
    red "  - Re-run with --https to use HTTPS + a Personal Access Token."
    red "  - Or set up an SSH key: https://docs.github.com/en/authentication"
    exit 3
fi

LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git rev-parse origin/main 2>/dev/null || echo "")

if [[ -z "$REMOTE_HEAD" ]]; then
    # Case A: remote is empty.
    bold "Remote main is empty — pushing initial commit..."
    git push -u origin main
    green "Pushed. Repo is now at $REMOTE_URL (branch: main)."
elif [[ "$LOCAL_HEAD" == "$REMOTE_HEAD" ]]; then
    # Case C: already in sync.
    green "Local and remote are already in sync at ${LOCAL_HEAD:0:7}. Nothing to do."
else
    # Case B: remote has history we don't. Merge it in with a merge commit.
    bold "Remote has existing commits — merging them in..."
    if git merge-base --is-ancestor "$REMOTE_HEAD" "$LOCAL_HEAD" 2>/dev/null; then
        # Remote is behind us (we can just fast-forward push). Rare.
        yellow "Local is ahead of remote — pushing."
        git push -u origin main
    elif git merge-base --is-ancestor "$LOCAL_HEAD" "$REMOTE_HEAD" 2>/dev/null; then
        # Remote is ahead of us (only possible if there was a pre-existing
        # commit we didn't have — init-repo has no commits yet means the
        # local HEAD is the one we just created, so this branch is rare).
        yellow "Remote is ahead — fast-forwarding."
        git merge --ff-only origin/main
        git push -u origin main
    else
        # Truly divergent (most common when remote has e.g. a README from
        # when you created the repo on github.com). Merge with
        # --allow-unrelated-histories.
        yellow "Histories are unrelated — merging (pass-through)..."
        if ! git merge --allow-unrelated-histories --no-edit origin/main; then
            red "Merge conflict. Resolve manually:"
            red "  cd $REPO"
            red "  git status"
            red "  # fix conflicting files, then:"
            red "  git add -A && git commit"
            red "  git push -u origin main"
            exit 4
        fi
        git push -u origin main
        green "Merged remote and pushed."
    fi
fi

echo
bold "Done."
cat <<EOF

Your local /Users/jc/Nest is now:
  - A git repo tracking branch 'main'
  - Connected to $REMOTE_URL
  - In sync with GitHub

From any other machine:

  git clone $REMOTE_URL
  cd the-nest/digger/bot
  cp .env.example .env   # fill with your keys (NOT in git)
  # make changes, push back to origin/main

Back on this MacBook, deploys come in via:
  • @digger pull            (in Slack — immediate pull + restart)
  • The com.digger.updater launchd agent (hourly pull, no restart)

EOF
