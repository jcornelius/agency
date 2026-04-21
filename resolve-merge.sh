#!/usr/bin/env bash
# resolve-merge.sh — finish the in-progress merge from init-repo.sh cleanly.
#
# Run once from macOS Terminal (after the `init-repo.sh --https` run that
# hit the merge conflict):
#   bash /Users/jc/Nest/resolve-merge.sh
#
# What it does:
#   1. Resolves all three conflicted files by keeping our local versions
#      (our .gitignore is a superset; our Python scripts have the env-var patch).
#   2. `git rm` all the OpenClaw multi-agent debris that arrived from origin
#      (charlie/, donna/, jeff/, ogilvy/, digger/*.md OpenClaw config files,
#      digger/.openclaw/, digger/memory/, unrelated scripts).
#   3. `git rm --cached` the research CSVs so they stay on disk but become
#      gitignored per the new .gitignore.
#   4. Commits the merge with a clear message.
#   5. Pushes to origin/main.

set -euo pipefail
cd /Users/jc/Nest

bold()   { printf '\033[1m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }

# --- Sanity: are we actually mid-merge? ---
if [[ ! -f .git/MERGE_HEAD ]]; then
    red "Not in the middle of a merge. Nothing to resolve."
    red "If you aborted and want to restart: bash init-repo.sh --https"
    exit 1
fi

# --- 1. Resolve the three conflicted files by keeping OURS. ---
bold "Resolving conflicts (keeping local versions)..."
git checkout --ours .gitignore digger/scripts/prospect-search.py digger/scripts/email-finder.py
git add .gitignore digger/scripts/prospect-search.py digger/scripts/email-finder.py
green "  .gitignore, prospect-search.py, email-finder.py → ours"

# --- 2. Remove OpenClaw multi-agent debris. ---
bold "Removing OpenClaw multi-agent debris..."

# Other agents entirely.
for d in charlie donna jeff ogilvy; do
    if [[ -d "$d" ]]; then
        git rm -rf --quiet "$d"
        green "  rm -r $d/"
    fi
done

# OpenClaw config files at digger/ root (we replaced this layer with the bot).
for f in digger/AGENTS.md digger/BOOTSTRAP.md digger/HEARTBEAT.md \
         digger/IDENTITY.md digger/SOUL.md digger/TOOLS.md digger/USER.md \
         digger/MIGRATION_COMPLETE.md digger/MIGRATION_STATUS.md \
         digger/MIGRATION_SUMMARY.md; do
    if [[ -f "$f" ]]; then
        git rm -f --quiet "$f"
        green "  rm $f"
    fi
done

# OpenClaw internal state + agent memory.
for d in digger/.openclaw digger/memory; do
    if [[ -d "$d" ]]; then
        git rm -rf --quiet "$d"
        green "  rm -r $d/"
    fi
done

# Reference docs that we already moved into digger/docs/ during migration.
# The origin versions here would shadow / conflict with our organized copy.
for f in digger/FIELD_STRUCTURE_GUIDE.md digger/square_pos_prospect_research.md; do
    if [[ -f "$f" ]]; then
        git rm -f --quiet "$f"
        green "  rm $f (moved to digger/docs/)"
    fi
done

# OpenClaw-era scripts unrelated to the Square POS digger pipeline.
for f in digger/scripts/donna_outreach.py \
         digger/scripts/hubspot_templates.py \
         digger/scripts/migrate_to_new_fields.py \
         digger/scripts/send_restaurant_outreach.py \
         digger/scripts/test_send_email.py \
         digger/scripts/upload_contacts_hubspot.py \
         digger/scripts/restaurant_outreach_template.json \
         digger/scripts/restaurant_outreach_v2.json; do
    if [[ -f "$f" ]]; then
        git rm -f --quiet "$f"
        green "  rm $f"
    fi
done

# Root-level OpenClaw remnant.
if [[ -f slack-agent-config.md ]]; then
    git rm -f --quiet slack-agent-config.md
    green "  rm slack-agent-config.md"
fi

# --- 3. Untrack research CSVs (stay on disk, become gitignored). ---
bold "Untracking research CSVs (stays on disk, now gitignored)..."
for f in digger/research/*.csv; do
    if [[ -f "$f" ]] && git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        git rm --cached --quiet "$f"
        green "  untracked $f"
    fi
done

# --- 4. Final sanity check: nothing should still be in conflict. ---
if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
    red "Still unresolved files:"
    git diff --name-only --diff-filter=U >&2
    red "Resolve manually, then run: git add -A && git commit && git push"
    exit 2
fi

# --- 5. Commit the merge. ---
bold "Committing..."
git commit --no-edit -m "Migrate to single-agent layout

Merged origin/main (pre-migration OpenClaw monorepo) with the new
Nest layout from /Users/jc/openclaw-workspaces/digger.

Resolutions:
  - .gitignore                          kept local (superset)
  - digger/scripts/prospect-search.py   kept local (BRAVE_API_KEY env patch)
  - digger/scripts/email-finder.py      kept local (HUNTER_API_KEY env patch)

Removed (OpenClaw multi-agent debris):
  - charlie/ donna/ jeff/ ogilvy/                       other agents
  - digger/{AGENTS,BOOTSTRAP,HEARTBEAT,IDENTITY,SOUL,TOOLS,USER}.md
  - digger/MIGRATION_*.md
  - digger/.openclaw/ digger/memory/
  - digger/{FIELD_STRUCTURE_GUIDE,square_pos_prospect_research}.md
    (moved into digger/docs/ during migration)
  - digger/scripts/{donna_outreach,hubspot_templates,migrate_to_new_fields,
    send_restaurant_outreach,test_send_email,upload_contacts_hubspot}.py
  - digger/scripts/restaurant_outreach_*.json
  - slack-agent-config.md

Untracked (now gitignored per new .gitignore):
  - digger/research/*.csv   (stays on disk as runtime output)
" 2>&1 | sed 's/^/  /'

HEAD_NEW=$(git rev-parse --short HEAD)
green "Committed: $HEAD_NEW"

# --- 6. Push. ---
bold "Pushing to origin/main..."
git push -u origin main

echo
bold "Done."
cat <<EOF

The repo is clean and in sync with GitHub:
  $(git rev-parse --short HEAD)  $(git log -1 --pretty=%s)

Final /Users/jc/Nest layout:
EOF
find . -maxdepth 3 -not -path './.git*' -not -path './digger/bot/__pycache__*' \
    -not -path './digger/research*' -not -name '.DS_Store' \
    | sort | sed 's|^\./|  |'

cat <<EOF

Next steps:
  1. cd digger/bot && cp .env.example .env    # fill in your API keys
  2. bash finish-setup.sh                      # venv + deps + launchd install
EOF
