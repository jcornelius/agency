Note: For this example the app name will be `Archer`.

----

# Part 1: Create the Slack apps

Do this once per agent you want to create.
## 1. Go to https://api.slack.com/apps → Create New App

Choose "From scratch".

```
App Name: Archer
Workspace: pick your workspace
```

## 2. Set Bot Identity (Features → App Home)

Toggle "Always Show My Bot as Online" on
Edit the display name and default name to "archer" (lowercase — this becomes the @mention handle)

## 3. Set OAuth Scopes (Features → OAuth & Permissions)

Scroll to "Bot Token Scopes" and add these:

```
app_mentions:read — so the bot gets events when mentioned
channels:history — read messages in public channels it's in
groups:history — read messages in private channels it's in
im:history — read DMs
mpim:history — read group DMs
chat:write — send messages
chat:write.customize — lets OpenClaw override the displayed name/avatar on replies (useful if you ever want one bot to speak as another)
users:read — resolve user IDs to names
files:read — if you want agents to read uploaded files
files:write — if you want agents to upload files back
```

## 4. Enable Event Subscriptions (Features → Event Subscriptions)

- Toggle Enable Events on
- Request URL: this is the tricky one. OpenClaw's gateway needs to be reachable from Slack's servers. If your gateway is on localhost (which it is, based on your earlier logs: ws://127.0.0.1:18789), you need either:

- ngrok or Cloudflare Tunnel exposing the gateway, or
- Socket Mode enabled instead (skip the Request URL entirely — recommended, see next step)

Under "Subscribe to bot events", add:

```
app_mention
message.channels
message.groups
message.im
message.mpim
```

## 5. Enable Socket Mode (Settings → Socket Mode) — recommended
This avoids the public URL/ngrok dance entirely. Slack pushes events over a WebSocket your gateway opens to them.

Toggle Enable Socket Mode on
You'll be prompted to create an App-Level Token with the connections:write scope — create it and name it something like "archer-socket"
Copy this token (starts with `xapp-`) — you need it for OpenClaw

## 6. Install the app to your workspace (Settings → Install App)
Click Install to Workspace, approve the scopes. After install, Slack gives you a Bot User OAuth Token starting with `xoxb-`. Copy this too.
So from each app you walk away with two tokens:

- `xoxb-...` (Bot User OAuth Token)
- `xapp-...` (App-Level Token for Socket Mode)
