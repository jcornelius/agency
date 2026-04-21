#!/usr/bin/env bash
# finish-setup.sh — one-shot post-migration setup for digger.
#
# Run from macOS Terminal (NOT from inside Cowork — this needs real macOS
# python3 + launchctl, which the Cowork sandbox can't provide).
#
#   bash /Users/jc/Nest/digger/bot/finish-setup.sh
#
# Flags:
#   --no-launchd    Skip installing the launchd agent (just venv + deps).
#   --reload        Unload + reload the launchd agent (use after editing code).
#
# Idempotent: safe to re-run.

set -euo pipefail

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$HOME/Library/Logs/digger"
PLIST_SRC="$BOT_DIR/com.digger.bot.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.digger.bot.plist"
UPDATER_SRC="$BOT_DIR/com.digger.updater.plist"
UPDATER_DST="$HOME/Library/LaunchAgents/com.digger.updater.plist"

SKIP_LAUNCHD=0
RELOAD_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --no-launchd) SKIP_LAUNCHD=1 ;;
        --reload)     RELOAD_ONLY=1 ;;
        -h|--help)
            sed -n '2,15p' "$0"
            exit 0
            ;;
        *)
            echo "unknown flag: $arg" >&2; exit 2 ;;
    esac
done

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }

# --- Reload-only fast path ---
if [[ "$RELOAD_ONLY" == 1 ]]; then
    bold "Reloading bot agent..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    launchctl load -w "$PLIST_DST"
    green "Reloaded. Tail logs with: tail -f $LOGS_DIR/stdout.log"
    exit 0
fi

# --- Sanity ---
bold "Checking prerequisites..."
command -v python3 >/dev/null || { red "python3 not found on PATH"; exit 1; }
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
green "  python3: $PY_VER"

if ! command -v goplaces >/dev/null 2>&1; then
    red "  goplaces CLI NOT found on PATH"
    red "  The pipeline shells out to it for Google Places lookups."
    red "  Install it before running the bot. (This doesn't block setup — you"
    red "  can still create the venv and install the plist — but the bot"
    red "  will fail at runtime until goplaces is available.)"
else
    green "  goplaces: $(which goplaces)"
fi

if [[ ! -f "$BOT_DIR/.env" ]]; then
    red "  .env missing. Copy .env.example → .env and fill in your tokens first."
    red "  After that, re-run this script."
    exit 1
fi
green "  .env present"

# --- Venv + deps ---
bold "Creating venv and installing dependencies..."
cd "$BOT_DIR"
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
    green "  created .venv"
else
    green "  .venv already exists (reusing)"
fi
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet
green "  installed: slack_bolt, anthropic, python-dotenv"

# --- Log directory ---
mkdir -p "$LOGS_DIR"
green "  logs dir: $LOGS_DIR"

# --- Smoke test ---
bold "Running smoke test..."
if .venv/bin/python test_smoke.py >/tmp/digger-smoke.out 2>&1; then
    green "  smoke test passed"
else
    red "  smoke test FAILED. Output:"
    cat /tmp/digger-smoke.out
    exit 1
fi

if [[ "$SKIP_LAUNCHD" == 1 ]]; then
    echo
    bold "Setup complete (launchd not installed, per --no-launchd)."
    echo "Run interactively with:"
    echo "  $BOT_DIR/.venv/bin/python $BOT_DIR/slack_app.py"
    exit 0
fi

# --- Install both launchd agents (bot + hourly updater) ---
bold "Installing launchd agents..."
mkdir -p "$HOME/Library/LaunchAgents"

# Main bot agent.
cp "$PLIST_SRC" "$PLIST_DST"
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load -w "$PLIST_DST"
green "  com.digger.bot       → loaded"

# Hourly git-pull updater agent (no-op if no GitHub remote yet).
if [[ -f "$UPDATER_SRC" ]]; then
    cp "$UPDATER_SRC" "$UPDATER_DST"
    launchctl unload "$UPDATER_DST" 2>/dev/null || true
    launchctl load -w "$UPDATER_DST"
    green "  com.digger.updater   → loaded (hourly git pull)"
fi

# Give it a moment, then check the bot is actually running.
sleep 2
# launchctl list format: "PID  EXIT_CODE  LABEL" (label at end of line).
# Match by exact column 3 to avoid accidentally matching com.digger.updater.
PID=$(launchctl list | awk '$3 == "com.digger.bot" {print $1}')
if [[ -z "$PID" ]]; then
    red "  launchctl list does not show com.digger.bot — something went wrong."
    exit 1
elif [[ "$PID" == "-" ]]; then
    red "  com.digger.bot is loaded but the process is not running."
    red "  Check $LOGS_DIR/stderr.log and $LOGS_DIR/stdout.log for why."
    exit 1
else
    green "  com.digger.bot running (PID $PID)"
fi

echo
bold "Done."
cat <<EOF

The bot is running as a launchd agent. It will:
  - Auto-start when you log in.
  - Restart if it crashes (subject to a 10s throttle).
  - Write logs to $LOGS_DIR/{stdout,stderr}.log

An updater agent also runs hourly:
  - Pulls from GitHub (no reload — code only activates on @digger pull
    or manual restart), so it can't interrupt a running pipeline.
  - Logs to $LOGS_DIR/updater.log

Handy commands:
  tail -f $LOGS_DIR/stdout.log              # watch bot logs
  tail -f $LOGS_DIR/updater.log             # watch hourly update runs
  launchctl list | grep digger              # are they running?
  bash $BOT_DIR/finish-setup.sh --reload    # pick up local code edits

Slack commands:
  @digger help              # list commands
  @digger status            # heartbeat / queue
  @digger pull              # pull from GitHub + restart

Now go invite @digger to a Slack channel and try:
  @digger find all coffee shops in Watkinsville GA
EOF
