# digger — Slack prospect-research bot

Listens for `@digger ...` mentions in Slack, runs the prospect-search +
email-finder pipeline in the background, reports heartbeat-style updates
back to the same Slack thread, and writes everything to HubSpot.

```
User in Slack:   @digger find all pizza places within 10 miles of downtown Athens GA

Bot (thread):    :mag: Searching for pizza/pizzeria in Athens GA and 5 nearby towns.
Bot (thread):    :white_check_mark: Found 23 new companies (147 total after dedup).
                 Now looking for emails...
Bot (thread):    :tada: Done. 14 new decision-maker contacts, 9 company emails
                 added to HubSpot.
```

## Architecture

- `slack_app.py` — Socket Mode Slack bot. Listens for mentions, enqueues jobs,
  spawns a single worker thread that runs pipelines one at a time.
- `command_parser.py` — Claude-backed parser that turns free-form `@digger ...`
  into structured `(intent, keywords, areas)` commands via forced tool use.
- `runner.py` — Subprocess wrapper. Runs `../scripts/prospect-search.py` and
  `../scripts/email-finder.py`, parses their stdout line-by-line, emits
  `Heartbeat` events to the bot, which forwards milestone ones to Slack.
- `../scripts/prospect-search.py` + `../scripts/email-finder.py` — unchanged
  pipeline you already have. `square_confidence` is already populated by
  `prospect-search.py` (see `../FIELD_STRUCTURE_GUIDE.md`).

No web server, no webhook URL, no ngrok. Socket Mode handles auth and routing.

## Prerequisites

- Python 3.11+
- macOS (for the launchd plist; bot itself is platform-agnostic)
- The existing `scripts/` folder and `briefs/square-pos-research.md`
- API keys: Slack (bot + app-level), Anthropic, Brave, Google Places,
  HubSpot (Private App), Hunter.io

## One-time Slack app setup

1. Go to <https://api.slack.com/apps> → **Create New App** → "From scratch".
   Name it **digger**, choose your workspace.
2. **Socket Mode** → toggle **Enable Socket Mode** on. When it prompts for an
   App-Level Token, create one with the `connections:write` scope. Save the
   `xapp-...` token — this is `SLACK_APP_TOKEN`.
3. **OAuth & Permissions** → **Bot Token Scopes**, add:
   - `app_mentions:read`
   - `chat:write`
   - `channels:history`   *(so the bot can read the triggering message)*
   - `groups:history`     *(for private channels)*
   - `im:history`         *(for DMs, if you want that)*
   - `im:read`
4. **Event Subscriptions** → toggle **Enable Events** on. Under **Subscribe to
   bot events**, add:
   - `app_mention`
5. **App Home** → **Always Show My Bot as Online**.
6. **Install App** to your workspace. Copy the **Bot User OAuth Token**
   (`xoxb-...`) — this is `SLACK_BOT_TOKEN`.
7. Invite the bot to the channel where you want to use it: `/invite @digger`.

## Install on the basement MacBook

Paths in `com.digger.bot.plist` are already set to `/Users/jc/Nest/digger/...`
(done during the migration), so setup is a one-liner after you populate
`.env`:

```bash
cd /Users/jc/Nest/digger/bot
cp .env.example .env
# Edit .env — paste Slack + Anthropic + Brave + Places + Hubspot + Hunter keys

bash finish-setup.sh
```

`finish-setup.sh` will:
  - create the venv
  - install dependencies from `requirements.txt`
  - create `~/Library/Logs/digger/`
  - run the smoke test (fails fast if anything's wrong)
  - install and load the launchd agent

Pass `--no-launchd` to stop after venv + smoke test if you want to run
interactively first:

```bash
bash finish-setup.sh --no-launchd
.venv/bin/python slack_app.py    # run in foreground
```

You should see:
```
INFO digger: Scripts dir: /Users/jc/Nest/digger/scripts
INFO digger: Connecting to Slack via Socket Mode...
```

Then in Slack: `@digger find all coffee shops in Watkinsville GA` — the bot
should reply with the `:mag:` ack, then heartbeats. Ctrl-C to stop.

### Picking up code changes

Three ways to deploy:

1. **`@digger pull` in Slack** — pulls from GitHub, reinstalls deps if
   `requirements.txt` changed, and restarts the bot. Gives you confirmation in
   the thread. This is the primary mechanism — use it whenever you've pushed
   a change from any machine.

2. **Hourly auto-pull** — the `com.digger.updater` launchd agent runs
   `update.sh` every hour. It pulls code to disk but does *not* restart the
   bot (so it can't interrupt a running pipeline). The new code sits idle
   until the next `@digger pull` or any bot restart. Think of this as a
   safety net, not a deployment mechanism.

3. **Manual reload** — if you're editing files locally on this Mac and
   haven't committed:

   ```bash
   bash finish-setup.sh --reload
   ```

   Unloads and reloads the bot agent to pick up local edits.

### Git workflow

The repo root is `/Users/jc/Nest`, pushed to
<https://github.com/jcornelius/the-nest>. Every machine (this MacBook +
wherever else you're editing) shares the same GitHub remote.

```bash
# From any clone:
git clone git@github.com:jcornelius/the-nest.git
cd the-nest
# edit files
git add -A && git commit -m "..."
git push

# Then from Slack (or wait up to 1h for the auto-pull):
@digger pull
```

**Uncommitted local changes block auto-pull.** `update.sh` refuses to run
`git pull` if `git diff HEAD` is non-empty — it doesn't want to clobber work
in progress. Commit (or stash) your local edits, then pull again.

### Prevent the MacBook from sleeping the bot

`caffeinate` or System Settings → Battery → **Prevent your Mac from sleeping
automatically when the display is off**. Otherwise Socket Mode will disconnect
when the lid closes / the machine idles.

## Usage

Examples:

```
@digger find contact info for Acme Coffee in Atlanta
@digger find all pizza places within 10 miles of downtown Athens GA
@digger coffee shops in the Atlanta metro area
@digger bakeries in Roswell GA and Alpharetta
```

The bot replies in the same thread as the mention. If two people mention it
at once, the second one gets queued — the bot runs pipelines serially to
avoid hammering HubSpot rate limits.

## Access control

Set `DIGGER_ALLOWED_USERS` and/or `DIGGER_ALLOWED_CHANNELS` in `.env` to
comma-separated Slack IDs. Empty = anyone in the workspace can invoke it.

To find a user ID: click their profile in Slack → **... More** → **Copy
member ID**. For a channel: right-click the channel → **View channel
details** → **About** section → copy the ID at the bottom.

## Maintenance

- **Search criteria**: edit `../briefs/square-pos-research.md` directly.
  The bot picks it up on the next run.
- **Logs**: script stdout goes to `./logs/prospect-search.log` and
  `./logs/email-finder.log`. Bot stdout goes to `~/Library/Logs/digger/`.
- **HubSpot custom properties**: `square_online_url`, `primary_website`,
  `square_confidence` (enum) already exist and are populated automatically
  by `prospect-search.py`. See `../FIELD_STRUCTURE_GUIDE.md`.

## Troubleshooting

**"Not authorized" from bot** — the user ID isn't in `DIGGER_ALLOWED_USERS`.
Either add them, or blank the list.

**Bot silent after mention** — check `~/Library/Logs/digger/stderr.log`. Most
common cause: missing env var (bot logs missing keys on startup and exits).

**Script crashes on Brave/Hunter key** — you're still running an old copy of
`prospect-search.py` / `email-finder.py`. The bot's patch makes both prefer
env vars. If the scripts were restored from backup (`.backup` files), re-apply
the patch.

**Slack posts fail with `not_in_channel`** — invite the bot: `/invite @digger`.

**Socket Mode disconnect when MacBook sleeps** — see the caffeinate note above.
